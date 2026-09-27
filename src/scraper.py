"""
scraper.py — 抓取安徽省大学生就业服务平台（ahut.ahbys.com）的校园招聘会数据。

接口说明（页面为 JS 动态渲染，数据来自 /API/Web/Recruit.ashx）：
  1. 日历红点  POST  action=cale&month=<offset>          -> 有招聘会的日期
  2. 场次列表  POST  action=calelist&year&mon&day         -> 当天所有场次
  3. 场次详情  GET   action=info&rid=<ID>                 -> 招聘简章全文（含需求专业 / 工作地点）

抓取策略：
  - 先用日历接口拿到"红点日期"，可大幅减少请求量；
  - 日历接口覆盖不到的月份（例如已经过去的月份），退化为逐日扫描；
  - 详情按 ID 缓存，重复运行只抓取新增场次。

依赖：仅 Python 标准库。
"""

from __future__ import annotations

import datetime as dt
import html as html_mod
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from src.timeutil import cn_now

WEEKDAY_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def _weekday_cn(d: dt.date) -> str:
    return WEEKDAY_CN[d.weekday()]


class ScraperError(RuntimeError):
    """抓取过程中的可恢复错误。"""


class Scraper:
    """招聘会数据抓取器。"""

    def __init__(self, config: Dict[str, Any], data_dir: Path) -> None:
        site = config["site"]
        req = config.get("request", {})

        self.base_url: str = site["base_url"].rstrip("/")
        self.calendar_url: str = site["calendar_url"]
        self.api_url: str = self.base_url + site["api_path"]

        self.timeout: float = float(req.get("timeout", 30))
        self.retries: int = int(req.get("retries", 3))
        self.delay: float = float(req.get("delay_seconds", 0.15))
        self.user_agent: str = req.get("user_agent", "Mozilla/5.0")

        self.data_dir = Path(data_dir)
        self.cache_dir = self.data_dir / "cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.use_cache: bool = True

        self._opener = urllib.request.build_opener()
        self._opener.addheaders = [
            ("User-Agent", self.user_agent),
            ("Referer", self.calendar_url),
            ("X-Requested-With", "XMLHttpRequest"),
            ("Accept", "application/json, text/javascript, */*; q=0.01"),
        ]

    # ------------------------------------------------------------------ HTTP

    def _request(self, url: str, data: Optional[bytes] = None) -> Any:
        """发起一次请求并解析 JSON，失败自动重试。"""
        last_err: Optional[Exception] = None
        for attempt in range(1, self.retries + 1):
            try:
                req = urllib.request.Request(url, data=data)
                with self._opener.open(req, timeout=self.timeout) as resp:
                    raw = resp.read().decode("utf-8", errors="replace")
                payload = json.loads(raw)
                if payload.get("r") != 0:
                    raise ScraperError(f"接口返回 r={payload.get('r')}: {raw[:200]}")
                return payload
            except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError,
                    ScraperError, TimeoutError) as exc:
                last_err = exc
                if attempt < self.retries:
                    time.sleep(self.delay * attempt * 2)
        raise ScraperError(f"请求失败 {url}: {last_err}")

    def _post(self, params: Dict[str, Any]) -> Any:
        payload = urllib.parse.urlencode(params).encode("utf-8")
        url = f"{self.api_url}?rd={time.time()}"
        time.sleep(self.delay)
        return self._request(url, data=payload)

    def _get(self, params: Dict[str, Any]) -> Any:
        params = dict(params)
        params.setdefault("rd", time.time())
        url = f"{self.api_url}?{urllib.parse.urlencode(params)}"
        time.sleep(self.delay)
        return self._request(url)

    # -------------------------------------------------------------- 日历红点

    def fetch_calendar(self, offset: int) -> Optional[Dict[str, Any]]:
        """
        offset=0 为当月，1 为次月，以此类推。返回 {year, month(1基), days:[int]}。

        注意：接口对"该月没有任何招聘会"会返回 data=[]，但仍带 year/month。
        这是有效信号，必须与"请求失败"区分开——否则会被误判为未知月份而触发逐日扫描。
        只有真正请求失败才返回 None。
        """
        try:
            payload = self._post({"action": "cale", "month": offset, "rand": time.time()})
        except ScraperError:
            return None
        if "year" not in payload or "month" not in payload:
            return None
        return {
            "year": int(payload["year"]),
            "month": int(payload["month"]) + 1,  # 页面用 0 基，这里统一转成 1 基
            "days": sorted(int(x["HoldDate"]) for x in payload.get("data") or []),
        }

    def calendar_days(self, months: Iterable[dt.date]) -> Dict[str, List[int]]:
        """
        批量取红点日期。返回 {'YYYY-MM': [日, ...]}。

        只探测 offset >= 0（当月及以后）；过去的月份接口不保证可用，
        交给 collect() 的逐日扫描兜底。请求失败或接口未覆盖的月份不会出现在这里。
        """
        wanted = {d.strftime("%Y-%m") for d in months}
        result: Dict[str, List[int]] = {}

        for offset in range(0, 13):
            info = self.fetch_calendar(offset)
            if not info:
                continue
            key = f"{info['year']:04d}-{info['month']:02d}"
            if key in wanted and key not in result:
                result[key] = info["days"]
            elif key not in wanted and info["year"] * 12 + info["month"] > max(
                    (m.year * 12 + m.month) for m in months):
                break
        return result

    # -------------------------------------------------------------- 场次列表

    def fetch_day(self, day: dt.date) -> List[Dict[str, Any]]:
        """取某一天的全部场次。"""
        try:
            payload = self._post({
                "pagesize": 100, "pageindex": 1, "action": "calelist",
                "year": day.year, "mon": f"{day.month:02d}", "day": f"{day.day:02d}",
                "rand": time.time(),
            })
        except ScraperError:
            return []
        rows = payload.get("data") or []
        out: List[Dict[str, Any]] = []
        for row in rows:
            out.append({
                "id": str(row.get("ID")),
                "theme": (row.get("Theme") or "").strip(),
                "venue": (row.get("VenuesName") or "").strip(),
                "time": normalize_time((row.get("TimeSlotText") or "").strip()),
                "date": day.isoformat(),
                "weekday": _weekday_cn(day),
            })
        return out

    # ---------------------------------------------------------------- 详情

    def _cache_path(self, rid: str) -> Path:
        return self.cache_dir / f"{rid}.json"

    def fetch_detail(self, rid: str, use_cache: bool = True) -> Dict[str, Any]:
        """取招聘简章全文。结果按 ID 缓存到 data/cache/。"""
        cache_file = self._cache_path(rid)
        if use_cache and self.use_cache and cache_file.exists():
            try:
                return json.loads(cache_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass

        payload = self._get({"action": "info", "rid": rid, "rand": time.time()})
        detail = {
            "id": rid,
            "theme": (payload.get("Theme") or "").strip(),
            "venue": (payload.get("VenuesName") or "").strip(),
            "time": (payload.get("TimeSlotText") or payload.get("TimeSlot") or "").strip(),
            "date": (payload.get("HoldDate") or "")[:10],
            "description": _html_to_text(payload.get("Description") or ""),
            "fetched_at": cn_now().isoformat(timespec="seconds"),
        }
        cache_file.write_text(json.dumps(detail, ensure_ascii=False), encoding="utf-8")
        return detail

    # -------------------------------------------------------------- 主流程

    def collect(self, start: dt.date, end: dt.date, with_detail: bool = True) -> List[Dict[str, Any]]:
        """抓取 [start, end] 区间内的全部招聘会。"""
        months = _months_between(start, end)
        red_days = self.calendar_days(months)

        fairs: List[Dict[str, Any]] = []
        seen: set = set()

        days_to_scan: List[dt.date] = []
        cur = start
        while cur <= end:
            key = cur.strftime("%Y-%m")
            if key in red_days:
                # 该月日历可用：只查红点日期
                if cur.day in red_days[key]:
                    days_to_scan.append(cur)
            else:
                # 日历不可用：整月逐日扫描，保证不漏
                days_to_scan.append(cur)
            cur += dt.timedelta(days=1)

        for day in days_to_scan:
            for item in self.fetch_day(day):
                if item["id"] in seen:
                    continue
                seen.add(item["id"])
                if with_detail:
                    try:
                        detail = self.fetch_detail(item["id"])
                    except ScraperError:
                        detail = {}
                    item["description"] = detail.get("description", "")
                    item["detail_fetched_at"] = detail.get("fetched_at", "")
                else:
                    item["description"] = ""
                    item["detail_fetched_at"] = ""
                fairs.append(item)

        fairs.sort(key=lambda x: (x["date"], x["time"], x["theme"]))
        return fairs


# ------------------------------------------------------------------ 工具函数

def _months_between(start: dt.date, end: dt.date) -> List[dt.date]:
    """返回区间内每个月的第一天。"""
    out: List[dt.date] = []
    cur = dt.date(start.year, start.month, 1)
    while cur <= end:
        out.append(cur)
        cur = dt.date(cur.year + (cur.month // 12), (cur.month % 12) + 1, 1)
    return out


_TIME_RANGE_RE = re.compile(r"(\d{1,2}:\d{2})\s*[-–—~至]\s*(\d{1,2}:\d{2})")
_TIME_SINGLE_RE = re.compile(r"(\d{1,2}:\d{2})")
_DATE_PREFIX_RE = re.compile(r"\d{4}年\d{1,2}月\d{1,2}日|\d{1,2}月\d{1,2}日")


def normalize_time(text: str) -> str:
    """
    把简章里各种写法统一收敛为「HH:MM-HH:MM」（或单个「HH:MM」）。

    源数据里 TimeSlotText 五花八门：
        "10:00-11:30"                 -> 10:00-11:30
        "2026年10月8日18:30-20:00"     -> 18:30-20:00
        "10月9日 18:30-20:00"          -> 18:30-20:00
        "2026年10月15日14:55-16:30"    -> 14:55-16:30
        "2026年9月24日10：30"（全角冒号）-> 10:30
    日期已经在日期列展示了，时间段里再重复一遍很啰嗦，这里只保留时间部分。
    """
    if not text:
        return ""
    t = text.replace("：", ":")          # 全角冒号 -> 半角
    m = _TIME_RANGE_RE.search(t)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    single = _TIME_SINGLE_RE.search(t)
    if single:
        return single.group(1)
    # 只有日期、没有具体时间：至少把重复的日期前缀去掉
    cleaned = _DATE_PREFIX_RE.sub("", t).strip()
    return cleaned or text.strip()


_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"[ \t\u00a0\u3000]+")
_BLANK_RE = re.compile(r"\n\s*\n+")


def _html_to_text(raw: str) -> str:
    """把招聘简章的富文本转成便于检索的纯文本（保留段落与表格分隔）。"""
    if not raw:
        return ""
    text = raw
    text = re.sub(r"<(br|/p|/tr|/div|/li)\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</t[dh]>", " | ", text, flags=re.I)
    text = _TAG_RE.sub("", text)
    text = html_mod.unescape(text)
    text = _SPACE_RE.sub(" ", text)
    text = _BLANK_RE.sub("\n", text)
    return "\n".join(line.strip() for line in text.splitlines() if line.strip()).strip()
