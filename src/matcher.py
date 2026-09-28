"""
matcher.py — 把招聘简章与"个人画像"（专业 + 意向城市）做匹配打分。

设计目标：不写死任何公司名，全部由 config/config.json 的 profile 段驱动。
换一个人、换一个专业或城市，只改配置即可复用。

城市匹配的范围（重要）：
    只认"工作地点 / 面试地址 / 公司地址 / 联系方式"这类要素里出现的城市，
    而不是简章正文里随便提一句就算。否则像"与南京大学产学研合作""2021年于南京成立"
    "社保可缴纳城市有…南京…"都会把单位判成意向城市，产生大量误判。
    实现见 city_context()：先从简章里抽出"说明人在哪儿上班/在哪儿面试/怎么联系"的句子，
    再在这些句子里找城市；页面上的"城市依据"展示的也是这些句子。

打分（取最高档位，不做关键词累加）：
    score = 专业分 + 城市分 * city_weight_ratio
    专业分 = 命中任一 strong 关键词 ? major_strong : (命中 weak ? major_weak : 0)
    城市分 = 命中意向城市 ? city_primary : (命中周边城市 ? city_belt : 0)

注意：早期版本按"命中关键词个数累加"，结果一份简章里出现 5 个材料类词就会虚高到 15 分，
导致 73 场里有 40 家被判为"强相关"，失去筛选意义。改为取档位后，
只有"专业 + 城市"两头都沾的单位才会进入强相关。

同时抽取"证据片段"（简章中真正出现关键词的那几行），页面上直接展示，
避免"凭公司名猜测"造成的误判。
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Any, Dict, List, Optional

from src.textutil import clean_leading_marks
from src.timeutil import cn_today

SENTENCE_SPLIT = re.compile(r"[\n；;。]| \| ")

# 城市上下文的判定关键词（config.json -> profile.cities 里可覆盖）
# location：说明"人在哪儿上班 / 到哪儿面试"的字段
DEFAULT_LOCATION_FIELDS = [
    "地址", "地点", "工作地", "上班地", "办公地", "面试地", "笔试地", "报到地", "入职地",
    "宣讲地", "招聘地", "厂址", "厂区", "基地", "研发中心", "项目部", "驻场",
    "所在城市", "工作城市", "意向城市", "需求城市", "常驻地",
    "位于", "坐落于", "坐落在", "总部", "分公司", "子公司",
]
# contact：联系方式类字段（联系人/电话/邮箱附近写的城市算数）
DEFAULT_CONTACT_FIELDS = [
    "联系方式", "联系人", "联系电话", "电话", "手机", "座机", "直线", "传真",
    "邮箱", "E-mail", "e-mail", "Email", "微信", "QQ", "邮编",
    "投递", "招聘热线", "咨询电话",
]
# exclude：这些词所在的句子不可能是工作地点，命中即整句作废
DEFAULT_EXCLUDE_FIELDS = [
    "社保", "公积金", "五险", "一金", "缴纳", "保险", "福利",
    "生源", "户籍", "校友", "产学研", "合作院校", "生源所在地",
    "销售区域", "业务范围", "客户", "出差", "外派",
]

_CITY_SEP_RE = re.compile(r"[/、,，;；|]")
_HAS_ALNUM_RE = re.compile(r"[0-9A-Za-z]")


def _norm(text: str) -> str:
    return (text or "").replace("\u00a0", " ").strip()


def _count(text: str, keyword: str) -> int:
    return text.count(keyword) if keyword else 0


def _any_of(keywords: List[str]) -> Optional[re.Pattern]:
    """把关键词表编译成"命中任意一个"的正则，空表返回 None。"""
    words = [re.escape(k) for k in keywords if k]
    return re.compile("|".join(words)) if words else None


def _cfg_keywords(value: Any, default: List[str]) -> List[str]:
    """
    读配置里的关键词表。配置里为了写注释用的是 {"_comment": ..., "keywords": [...]}，
    这里两种写法都兼容：字典取 keywords 字段，列表直接用，都没有则回落到默认值。
    """
    if isinstance(value, dict):
        words = value.get("keywords")
        return list(words) if words else list(default)
    if isinstance(value, (list, tuple)) and value:
        return [str(x) for x in value]
    return list(default)


def _looks_like_city_list(seg: str) -> bool:
    """
    判断一个片段是不是"纯城市列表"——例如岗位表里的「工作地点」列：
        "杭州/苏州/南京/成都"、"温州/南京/嘉兴"、"深圳、杭州、南京"
    这类行没有字段名，但内容全是地名，本身就是工作地信号。
    """
    parts = [p.strip() for p in _CITY_SEP_RE.split(seg) if p.strip()]
    if len(parts) < 2 or len(seg) > 80:
        return False
    if any(_HAS_ALNUM_RE.search(p) for p in parts):
        return False
    return all(2 <= len(p) <= 8 for p in parts)


class Matcher:
    """基于画像的匹配器。"""

    def __init__(self, profile: Dict[str, Any]) -> None:
        mk = profile.get("major_keywords", {})
        self.major_label: str = profile.get("major", "")
        self.major_strong: List[str] = list(mk.get("strong", []))
        self.major_weak: List[str] = list(mk.get("weak", []))

        edu = profile.get("education_keywords", {}) or {}
        self.edu_label: str = profile.get("education", "")
        self.edu_target: List[str] = list(edu.get("target", []))
        self.edu_higher: List[str] = list(edu.get("higher", []))

        cities = profile.get("cities", {})
        self.city_primary: List[str] = list(cities.get("primary", []))
        belt = cities.get("belt", {}) or {}
        self.city_belt: Dict[str, List[str]] = {k: list(v) for k, v in belt.items()}
        self.city_belt_all: List[str] = sorted({c for v in self.city_belt.values() for c in v})

        # 城市只在"工作地 / 地址 / 联系方式"类句子里才算命中
        self._loc_re = _any_of(_cfg_keywords(cities.get("location_fields"), DEFAULT_LOCATION_FIELDS))
        self._contact_re = _any_of(_cfg_keywords(cities.get("contact_fields"), DEFAULT_CONTACT_FIELDS))
        self._excl_re = _any_of(_cfg_keywords(cities.get("exclude_fields"), DEFAULT_EXCLUDE_FIELDS))

        w = profile.get("weights", {})
        self.w_major_strong = float(w.get("major_strong", 3.0))
        self.w_major_weak = float(w.get("major_weak", 1.0))
        self.w_city_primary = float(w.get("city_primary", 3.0))
        self.w_city_belt = float(w.get("city_belt", 1.5))
        self.w_city_ratio = float(w.get("city_weight_ratio", 1.2))
        self.w_edu = float(w.get("education_match", 0.6))
        self.w_edu_higher = float(w.get("education_higher_penalty", 0.3))

        t = profile.get("thresholds", {})
        self.t1 = float(t.get("tier1", 4.0))
        self.t2 = float(t.get("tier2", 2.0))
        self.t3 = float(t.get("tier3", 0.1))

    # ------------------------------------------------------------------ 打分

    def score_major(self, text: str) -> tuple:
        """返回 (分数, 命中的关键词列表)。取最高档位，不累加。"""
        strong = [kw for kw in self.major_strong if kw and kw in text]
        weak = [kw for kw in self.major_weak if kw and kw in text]
        if strong:
            score = self.w_major_strong
        elif weak:
            score = self.w_major_weak
        else:
            score = 0.0
        return score, strong + weak

    def city_context(self, text: str) -> str:
        """
        从简章里挑出真正说明"工作地点 / 面试地址 / 联系方式"的句子，拼成一段小文本。

        城市的匹配与证据都只在这段文本里做，避免正文中"和南京大学合作""于南京成立"
        "社保可缴纳南京"这类顺带提及被误当成工作地。
        """
        if not text:
            return ""
        kept: List[str] = []
        for seg in SENTENCE_SPLIT.split(text):
            seg = _norm(seg)
            if len(seg) < 4:
                continue
            # 福利/社保/生源这类句子先整句作废
            if self._excl_re and self._excl_re.search(seg):
                continue
            hit_loc = bool(self._loc_re and self._loc_re.search(seg))
            hit_contact = bool(self._contact_re and self._contact_re.search(seg))
            if hit_loc or hit_contact or _looks_like_city_list(seg):
                kept.append(seg)
        return "\n".join(kept)

    def score_city(self, text: str) -> tuple:
        """返回 (分数, 命中的城市列表, 命中的周边城市列表)。取最高档位，不累加。

        传入的应当只是"城市上下文"（见 city_context），不是整篇简章。
        """
        hits_p = [c for c in self.city_primary if _count(text, c)]
        hits_b = [c for c in self.city_belt_all if _count(text, c)]
        if hits_p:
            score = self.w_city_primary
        elif hits_b:
            score = self.w_city_belt
        else:
            score = 0.0
        return score, hits_p, hits_b

    def score_edu(self, text: str) -> tuple:
        """返回 (加分, 命中的学历关键词)。招硕士→小幅加分；只招博士→小幅扣分。"""
        if not text:
            return 0.0, []
        target = [k for k in self.edu_target if k and k in text]
        higher = [k for k in self.edu_higher if k and k in text]
        if target:
            return self.w_edu, target
        if higher:
            return -self.w_edu_higher, higher
        return 0.0, []

    def evidence(self, text: str, keywords: List[str], limit: int = 3) -> List[str]:
        """抽取包含关键词的原文片段，作为匹配依据展示。"""
        if not keywords or not text:
            return []
        out: List[str] = []
        for seg in SENTENCE_SPLIT.split(text):
            # 展示前先剥掉行首的「2、」「？ 」这类序号与项目符号，页面上更干净
            seg = clean_leading_marks(_norm(seg))
            if len(seg) < 6:
                continue
            if any(k in seg for k in keywords):
                if len(seg) > 160:
                    seg = seg[:160] + "…"
                out.append(seg)
                if len(out) >= limit:
                    break
        return out

    def match(self, fair: Dict[str, Any]) -> Dict[str, Any]:
        """给单个场次打分，返回附加字段。"""
        text = _norm(fair.get("description", ""))
        # 简章缺失时，退化为用单位名+场次名做弱判断，避免漏项
        searchable = text if text else _norm(fair.get("theme", ""))

        # 城市只在"工作地 / 地址 / 联系方式"这些要素里找，正文顺带提及不算
        city_text = self.city_context(text) if text else ""

        m_score, m_hits = self.score_major(searchable)
        c_score, c_hits, c_belt = self.score_city(city_text)
        e_score, e_hits = self.score_edu(searchable)
        total = m_score + c_score * self.w_city_ratio + e_score

        if total >= self.t1:
            tier, tier_label = 1, "强相关"
        elif total >= self.t2:
            tier, tier_label = 2, "相关"
        elif total >= self.t3:
            tier, tier_label = 3, "沾边"
        else:
            tier, tier_label = 0, "不相关"

        # 只对"专业和城市各沾一点"的情况给提示，避免一刀切
        note = ""
        if m_hits and not (c_hits or c_belt):
            note = (f"专业对口（{m_hits[0]}），但简章的工作地/联系方式中未出现意向城市"
                    if text else f"专业对口（{m_hits[0]}），但缺少简章，无法判断工作地")
        elif (c_hits or c_belt) and not m_hits:
            note = f"城市有戏（{(c_hits or c_belt)[0]}），但简章未列出材料类专业"
        elif not m_hits and not (c_hits or c_belt):
            note = "专业与城市均未匹配"

        return {
            **fair,
            "score": round(max(total, 0.0), 2),
            "major_score": round(m_score, 2),
            "city_score": round(c_score, 2),
            "edu_score": round(e_score, 2),
            "edu_hits": e_hits,
            "tier": tier,
            "tier_label": tier_label,
            "major_hits": m_hits,
            "city_hits": c_hits,
            "city_belt_hits": c_belt,
            "major_evidence": self.evidence(text, m_hits),
            "city_evidence": self.evidence(city_text, c_hits + c_belt, limit=2),
            "note": note,
        }

    def match_all(self, fairs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        scored = [self.match(f) for f in fairs]
        # 未过期的排前面（否则高分的老场次会一直占据视线），其次按分数、日期
        scored.sort(key=lambda x: (
            0 if x.get("status") != "expired" else 1,
            -x["score"], x["date"], x["time"],
        ))
        return scored


# ------------------------------------------------------------------ 状态标记

def mark_status(fairs: List[Dict[str, Any]], today: Optional[dt.date] = None) -> List[Dict[str, Any]]:
    """给每场招聘会标记 已过期 / 今天 / 还有N天。过期场次保留，只是状态不同。"""
    today = today or cn_today()
    out: List[Dict[str, Any]] = []
    for f in fairs:
        try:
            d = dt.date.fromisoformat(f["date"][:10])
        except (ValueError, KeyError, TypeError):
            d = today
        delta = (d - today).days
        if delta < 0:
            status, label = "expired", f"已过期 · {-delta}天前"
        elif delta == 0:
            status, label = "today", "今天"
        elif delta == 1:
            status, label = "upcoming", "明天"
        else:
            status, label = "upcoming", f"还有{delta}天"
        item = dict(f)
        item["status"] = status
        item["status_label"] = label
        item["days_left"] = delta
        out.append(item)
    return out
