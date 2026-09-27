"""
generate.py — 把抓取到的招聘会数据渲染成一个纯静态单页站点（site/index.html）。

页面结构：
    第一级（默认） 招聘会总览  —— 按月份 / 日期罗列全部场次，已过期的照常列出但灰显
    第二级         与我相关    —— 按 config/profile.json 的画像打分排序，只列匹配项

产物不依赖任何后端，双击即可打开，也能直接托管到任意静态空间。
"""

from __future__ import annotations

import datetime as dt
import html as html_mod
import json
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, List

CSS = """
:root{
  --ink:#1f2430; --ink2:#4a5364; --muted:#8a93a5; --line:#e6e9f0;
  --bg:#f5f7fb; --card:#ffffff;
  --red:#d4243c; --red-soft:#fdeef0;
  --amber:#c77700; --amber-soft:#fff5e6;
  --green:#1a7f52; --green-soft:#e8f6ee;
  --blue:#2563eb; --blue-soft:#eff4ff;
  --grey:#98a1b2; --grey-soft:#f2f3f7;
}
*{box-sizing:border-box;}
body{margin:0;padding:0 14px 60px;background:var(--bg);color:var(--ink);
  font-family:"PingFang SC","Microsoft YaHei","Hiragino Sans GB",-apple-system,"Segoe UI",sans-serif;
  -webkit-font-smoothing:antialiased;line-height:1.6;}
.wrap{max-width:1080px;margin:0 auto;}
a{color:var(--blue);text-decoration:none;}
a:hover{text-decoration:underline;}

header{background:linear-gradient(135deg,#2b3a55,#1f2430);color:#fff;border-radius:18px;
  padding:26px 28px;margin:20px 0 0;position:relative;overflow:hidden;
  box-shadow:0 10px 28px rgba(31,36,48,.16);}
header::after{content:"";position:absolute;right:-40px;top:-50px;width:220px;height:220px;
  background:radial-gradient(circle,rgba(212,36,60,.5),transparent 65%);}
header h1{margin:0 0 6px;font-size:23px;position:relative;z-index:1;}
header .meta{color:#c3cbdd;font-size:13px;position:relative;z-index:1;}
header .meta code{background:rgba(255,255,255,.12);padding:1px 7px;border-radius:5px;}

.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:16px 0;}
.stat{background:var(--card);border:1px solid var(--line);border-radius:13px;padding:14px 16px;}
.stat .n{font-size:26px;font-weight:700;line-height:1.15;}
.stat .n small{font-size:13px;color:var(--muted);font-weight:500;margin-left:3px;}
.stat .l{font-size:12.5px;color:var(--ink2);margin-top:4px;}
.stat.hl .n{color:var(--red);} .stat.ok .n{color:var(--green);} .stat.ex .n{color:var(--grey);}

.tabs{display:flex;gap:8px;margin:22px 0 0;border-bottom:2px solid var(--line);flex-wrap:wrap;}
.tab{appearance:none;border:none;background:transparent;cursor:pointer;font:inherit;
  font-size:15px;font-weight:600;color:var(--muted);padding:10px 18px;border-radius:10px 10px 0 0;}
.tab .lv{font-size:11px;font-weight:700;color:#fff;background:var(--grey);
  border-radius:5px;padding:1px 6px;margin-right:7px;vertical-align:1px;}
.tab[aria-selected="true"]{color:var(--ink);background:var(--card);border:1px solid var(--line);border-bottom:none;}
.tab[aria-selected="true"] .lv{background:var(--red);}
.tab .cnt{font-size:12px;color:var(--muted);margin-left:6px;font-weight:500;}
.panel{display:none;padding-top:18px;}
.panel.active{display:block;}
.nojs .panel{display:block !important;}

.bar{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:0 0 16px;}
.fbtn{appearance:none;border:1px solid var(--line);background:var(--card);cursor:pointer;
  font:inherit;font-size:12.5px;color:var(--ink2);padding:5px 13px;border-radius:999px;}
.fbtn.on{background:var(--ink);color:#fff;border-color:var(--ink);}

h2.month{font-size:16px;margin:24px 0 10px;padding-left:11px;border-left:4px solid var(--ink);}
h2.month span{font-size:12px;color:var(--muted);font-weight:400;margin-left:8px;}
.empty{background:var(--card);border:1px dashed #d9dee8;border-radius:12px;padding:14px 18px;
  font-size:13px;color:var(--muted);}

.day{background:var(--card);border:1px solid var(--line);border-radius:13px;margin-bottom:12px;overflow:hidden;}
.day.past{background:#fbfbfc;}
.day-hd{display:flex;align-items:center;gap:10px;padding:11px 16px;background:#fbfcfe;
  border-bottom:1px solid var(--line);flex-wrap:wrap;}
.day.past .day-hd{background:#f6f7f9;}
.day-hd .d{font-size:15px;font-weight:700;}
.day.past .day-hd .d{color:var(--grey);}
.day-hd .w{font-size:12px;color:var(--muted);}
.day-hd .cnt{margin-left:auto;font-size:11.5px;font-weight:600;border-radius:999px;padding:2px 10px;
  background:var(--blue-soft);color:var(--blue);}
.day.past .day-hd .cnt{background:var(--grey-soft);color:var(--grey);}

.li{display:flex;gap:12px;padding:11px 16px;border-top:1px solid #f1f3f8;align-items:baseline;flex-wrap:wrap;}
.li:first-of-type{border-top:none;}
.li .t{font-variant-numeric:tabular-nums;font-weight:600;font-size:12.5px;color:var(--blue);min-width:104px;}
.day.past .li .t{color:var(--grey);}
.li .co{font-size:14px;font-weight:600;}
.day.past .li .co{color:#9aa2b1;font-weight:500;}
.li .vn{font-size:12.5px;color:var(--ink2);margin-top:2px;}
.day.past .li .vn{color:#aab1bf;}
.li .st{margin-left:auto;font-size:11.5px;font-weight:700;border-radius:6px;padding:2px 9px;white-space:nowrap;}
.st-expired{background:var(--grey-soft);color:var(--grey);}
.st-today{background:var(--red-soft);color:var(--red);}
.st-upcoming{background:var(--green-soft);color:var(--green);}
.li .lk{font-size:12px;color:var(--muted);margin-top:3px;}

.card{background:var(--card);border:1px solid var(--line);border-radius:13px;padding:16px 20px;margin-bottom:12px;}
.card.past{background:#fbfbfc;}
.card-hd{display:flex;align-items:baseline;gap:9px;flex-wrap:wrap;margin-bottom:8px;}
.rank{width:23px;height:23px;flex:0 0 23px;border-radius:7px;color:#fff;font-size:12.5px;
  display:flex;align-items:center;justify-content:center;font-weight:700;background:var(--grey);}
.rank.t1{background:var(--red);} .rank.t2{background:var(--amber);} .rank.t3{background:#9aa2b1;}
.card-hd .co{font-size:15px;font-weight:700;}
.card.past .card-hd .co{color:#9aa2b1;font-weight:600;}
.card-hd .when{margin-left:auto;font-size:12px;color:var(--blue);background:var(--blue-soft);
  border-radius:7px;padding:2px 9px;font-weight:600;white-space:nowrap;}
.row{font-size:13px;margin:4px 0;display:flex;gap:8px;}
.row .k{color:var(--muted);flex:0 0 68px;font-size:12.5px;}
.row .v{flex:1;}
.ev{background:#fafbfd;border:1px dashed #dfe3ec;border-radius:9px;padding:8px 12px;
  font-size:12.5px;margin-top:9px;color:var(--ink2);}
.ev .t{font-weight:700;color:var(--ink2);margin-right:5px;}
.ev.warn{background:var(--amber-soft);border-color:#f0dcb8;}
.ev.warn .t{color:var(--amber);}
.badge{display:inline-block;font-size:11.5px;font-weight:700;padding:2px 9px;border-radius:6px;margin:0 5px 4px 0;}
.b-hi{background:var(--green-soft);color:var(--green);}
.b-mid{background:var(--amber-soft);color:var(--amber);}
.b-lo{background:var(--grey-soft);color:var(--grey);}
.b-city{background:var(--blue-soft);color:var(--blue);}
.b-score{background:var(--red-soft);color:var(--red);}
.b-exp{background:var(--grey-soft);color:var(--grey);}

table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);
  border-radius:12px;overflow:hidden;font-size:12.5px;}
thead th{background:#f0f2f7;color:var(--ink2);font-weight:600;text-align:left;padding:9px 11px;white-space:nowrap;}
tbody td{padding:8px 11px;border-top:1px solid var(--line);vertical-align:middle;}
tbody tr:nth-child(even){background:#fafbfd;}

footer{margin-top:34px;font-size:12px;color:var(--muted);text-align:center;line-height:1.9;}
footer a{color:var(--muted);}
.note{background:var(--blue-soft);border:1px solid #d8e3ff;color:#27407a;border-radius:11px;
  padding:11px 15px;font-size:13px;margin:0 0 16px;}
@media(max-width:760px){
  .stats{grid-template-columns:repeat(2,1fr);}
  .li .t{min-width:0;} .card-hd .when{margin-left:0;} .row{flex-direction:column;gap:2px;}
}
"""

JS = """
(function(){
  var body=document.documentElement;
  body.classList.remove('nojs');
  var tabs=[].slice.call(document.querySelectorAll('.tab'));
  var panels=[].slice.call(document.querySelectorAll('.panel'));
  function select(i){
    tabs.forEach(function(t,k){t.setAttribute('aria-selected', k===i?'true':'false');});
    panels.forEach(function(p,k){p.classList.toggle('active', k===i);});
    try{location.hash='#p'+i;}catch(e){}
  }
  tabs.forEach(function(t,i){t.addEventListener('click',function(){select(i);});});
  var h=(location.hash||'').replace('#p','');
  select(h==='1'?1:0);

  document.querySelectorAll('[data-filter]').forEach(function(btn){
    btn.addEventListener('click',function(){
      var group=btn.parentNode;
      [].slice.call(group.querySelectorAll('[data-filter]')).forEach(function(b){
        b.classList.toggle('on', b===btn);
      });
      var f=btn.getAttribute('data-filter');
      [].slice.call(group.parentNode.parentNode.querySelectorAll('[data-status]')).forEach(function(el){
        var s=el.getAttribute('data-status');
        el.style.display = (f==='all'||f===s) ? '' : 'none';
      });
      [].slice.call(group.parentNode.parentNode.querySelectorAll('.month-block')).forEach(function(bl){
        var vis=[].slice.call(bl.querySelectorAll('[data-status]')).filter(function(e){return e.style.display!=='none';});
        bl.style.display = vis.length ? '' : 'none';
      });
    });
  });
})();
"""


def esc(s: Any) -> str:
    return html_mod.escape(str(s or ""), quote=True)


def _month_label(key: str) -> str:
    y, m = key.split("-")
    return f"{y}年{int(m)}月"


class Generator:
    """静态站点生成器。"""

    def __init__(self, config: Dict[str, Any], profile: Dict[str, Any]) -> None:
        self.config = config
        self.profile = profile
        self.site_dir = Path(config["output"]["site_dir"])
        self.site_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ 分组

    @staticmethod
    def group_by_month(fairs: List[Dict[str, Any]]) -> "OrderedDict[str, List[Dict[str, Any]]]":
        buckets: "OrderedDict[str, List[Dict[str, Any]]]" = OrderedDict()
        for f in fairs:
            key = f["date"][:7]
            buckets.setdefault(key, []).append(f)
        for key in buckets:
            buckets[key].sort(key=lambda x: (x["date"], x["time"], x["theme"]))
        return buckets

    @staticmethod
    def group_by_day(fairs: List[Dict[str, Any]]) -> "OrderedDict[str, List[Dict[str, Any]]]":
        buckets: "OrderedDict[str, List[Dict[str, Any]]]" = OrderedDict()
        for f in fairs:
            buckets.setdefault(f["date"], []).append(f)
        for key in buckets:
            buckets[key].sort(key=lambda x: (x["time"], x["theme"]))
        return buckets

    # ------------------------------------------------------------------ 片段

    def _overview(self, fairs: List[Dict[str, Any]], months: List[str]) -> str:
        buckets = self.group_by_month(fairs)
        parts: List[str] = []

        filters = (
            '<div class="bar" data-group="ov">'
            '<button class="fbtn on" data-filter="all">全部</button>'
            '<button class="fbtn" data-filter="upcoming">未过期</button>'
            '<button class="fbtn" data-filter="today">今天</button>'
            '<button class="fbtn" data-filter="expired">已过期</button>'
            "</div>"
        )
        parts.append(filters)

        for key in months:
            items = buckets.get(key, [])
            upcoming = sum(1 for x in items if x["status"] != "expired")
            parts.append(
                f'<div class="month-block"><h2 class="month">{esc(_month_label(key))}'
                f'<span>共 {len(items)} 场 · 未过期 {upcoming} 场</span></h2>'
            )
            if not items:
                parts.append('<div class="empty">本月暂无招聘会安排（一旦官网放出，每日 02:00 会自动补上）。</div>')
            else:
                for day, rows in self.group_by_day(items).items():
                    d = dt.date.fromisoformat(day)
                    past = rows[0]["status"] == "expired"
                    cls = "day past" if past else "day"
                    parts.append(
                        f'<div class="{cls}" data-status="{esc(rows[0]["status"])}">'
                        f'<div class="day-hd"><span class="d">{int(d.month)}月{int(d.day)}日</span>'
                        f'<span class="w">{esc(rows[0].get("weekday",""))}</span>'
                        f'<span class="cnt">{len(rows)} 场 · {esc(rows[0]["status_label"])}</span></div>'
                    )
                    for r in rows:
                        link = self.config["site"]["detail_url"].format(id=r["id"])
                        parts.append(
                            '<div class="li">'
                            f'<div class="t">{esc(r["time"])}</div>'
                            '<div style="flex:1;min-width:220px">'
                            f'<div class="co">{esc(r["theme"])}</div>'
                            f'<div class="vn">{esc(r["venue"])}</div>'
                            f'<div class="lk"><a href="{esc(link)}" target="_blank" rel="noopener">查看官方简章 →</a></div>'
                            "</div>"
                            f'<div class="st st-{esc(r["status"])}">{esc(r["status_label"])}</div>'
                            "</div>"
                        )
                    parts.append("</div>")
            parts.append("</div>")

        return "".join(parts)

    def _relevant(self, scored: List[Dict[str, Any]]) -> str:
        matched = [s for s in scored if s["tier"] > 0]
        major = esc(self.profile.get("major", ""))
        cities = " / ".join(esc(c) for c in self.profile.get("cities", {}).get("primary", []))
        parts: List[str] = []
        parts.append(
            f'<div class="note">匹配画像：<b>专业 {major}</b>　·　<b>意向城市 {cities}</b>。'
            "打分与关键词均来自 <code>config/profile.json</code>，改动配置即可适配其他人。"
            "已过期的匹配项同样保留，仅作灰显。</div>"
        )

        if not matched:
            parts.append('<div class="empty">当前区间内没有与画像匹配的招聘会。每日 02:00 会自动重新抓取并更新。</div>')
            return "".join(parts)

        filters = (
            '<div class="bar" data-group="rv">'
            '<button class="fbtn on" data-filter="all">全部</button>'
            '<button class="fbtn" data-filter="upcoming">未过期</button>'
            '<button class="fbtn" data-filter="expired">已过期</button>'
            "</div>"
        )
        parts.append(filters)

        tier_meta = {1: ("强相关", "t1"), 2: ("相关", "t2"), 3: ("沾边", "t3")}
        for tier, (label, cls) in tier_meta.items():
            group = [s for s in matched if s["tier"] == tier]
            if not group:
                continue
            parts.append(f'<div class="month-block"><h2 class="month">{label}<span>{len(group)} 家</span></h2>')
            for idx, s in enumerate(group, 1):
                past = s["status"] == "expired"
                card_cls = "card past" if past else "card"
                st_cls = "b-exp" if past else "b-hi"
                parts.append(f'<div class="{card_cls}" data-status="{esc(s["status"])}">')
                parts.append('<div class="card-hd">'
                             f'<span class="rank {cls}">{idx}</span>'
                             f'<span class="co">{esc(s["theme"])}</span>'
                             f'<span class="when">{esc(s["date"][5:].replace("-","月"))}日 {esc(s["time"])}</span>'
                             "</div>")
                badges = [f'<span class="badge b-score">{s["score"]} 分</span>']
                badges.append(f'<span class="badge {st_cls if past else "b-hi"}">{esc(s["status_label"])}</span>')
                if s["major_hits"]:
                    badges.append(f'<span class="badge b-hi">专业：{esc(s["major_hits"][0])}</span>')
                if s["city_hits"]:
                    badges.append(f'<span class="badge b-city">城市：{esc("、".join(s["city_hits"]))}</span>')
                elif s["city_belt_hits"]:
                    badges.append(f'<span class="badge b-city">周边：{esc("、".join(s["city_belt_hits"][:3]))}</span>')
                parts.append(f'<div class="row"><div class="k">匹配</div><div class="v">{"".join(badges)}</div></div>')
                parts.append(f'<div class="row"><div class="k">地点</div><div class="v">{esc(s["venue"])}</div></div>')

                ev = "".join(f"<div>· {esc(x)}</div>" for x in s["major_evidence"][:2])
                if ev:
                    parts.append(f'<div class="ev"><span class="t">专业依据</span>{ev}</div>')
                evc = "".join(f"<div>· {esc(x)}</div>" for x in s["city_evidence"][:2])
                if evc:
                    parts.append(f'<div class="ev"><span class="t">城市依据</span>{evc}</div>')
                if s["note"]:
                    parts.append(f'<div class="ev warn"><span class="t">提示</span>{esc(s["note"])}</div>')

                link = self.config["site"]["detail_url"].format(id=s["id"])
                parts.append(f'<div class="row"><div class="k"></div><div class="v">'
                             f'<a href="{esc(link)}" target="_blank" rel="noopener">查看官方简章 →</a></div></div>')
                parts.append("</div>")
            parts.append("</div>")
        return "".join(parts)

    def _table(self, scored: List[Dict[str, Any]]) -> str:
        rows = []
        for s in scored:
            status = "已过期" if s["status"] == "expired" else s["status_label"]
            rows.append(
                "<tr>"
                f"<td>{esc(s['date'][5:])}</td>"
                f"<td>{esc(s['theme'])}</td>"
                f"<td>{esc(s['time'])}</td>"
                f"<td>{esc(s['venue'])}</td>"
                f"<td>{esc('、'.join(s['major_hits'][:3]) or '—')}</td>"
                f"<td>{esc('、'.join((s['city_hits'] or s['city_belt_hits'])[:3]) or '—')}</td>"
                f"<td>{s['score']}</td>"
                f"<td>{esc(status)}</td>"
                "</tr>"
            )
        return (
            "<table><thead><tr><th>日期</th><th>单位</th><th>时间</th><th>地点</th>"
            "<th>命中专业</th><th>命中城市</th><th>分数</th><th>状态</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table>"
        )

    # ------------------------------------------------------------------ 渲染

    def render(self, fairs: List[Dict[str, Any]], scored: List[Dict[str, Any]],
               months: List[str], today: dt.date) -> str:
        total = len(fairs)
        expired = sum(1 for f in fairs if f["status"] == "expired")
        upcoming = total - expired
        matched = sum(1 for s in scored if s["tier"] > 0)
        now = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
        rng = self.config["range"]

        overview = self._overview(fairs, months)
        relevant = self._relevant(scored)
        table = self._table(scored)

        return (
            "<!DOCTYPE html><html lang=\"zh-CN\" class=\"nojs\">"
            "<head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            f"<title>{esc(self.config['site']['name'])} · {esc(rng['start'][:4])}年9-12月</title>"
            "<meta name=\"description\" content=\"安徽工业大学校园招聘会日历：每日自动抓取，"
            "含招聘会总览与按专业/城市画像筛选的个性化匹配。\">"
            f"<style>{CSS}</style></head><body><div class=\"wrap\">"
            f"<header><h1>{esc(self.config['site']['name'])}</h1>"
            f"<div class=\"meta\">统计区间 <code>{esc(rng['start'])} ~ {esc(rng['end'])}</code>　·　"
            f"数据更新 <code>{esc(now)}</code>　·　每日 <code>02:00</code> 自动更新<br>"
            "来源：<a style=\"color:#cdd6ea\" href=\"" + esc(self.config["site"]["calendar_url"]) +
            "\" target=\"_blank\" rel=\"noopener\">ahut.ahbys.com 招聘日历</a></div></header>"
            "<div class=\"stats\">"
            f"<div class=\"stat hl\"><div class=\"n\">{total}<small>场</small></div><div class=\"l\">区间内总场次</div></div>"
            f"<div class=\"stat ok\"><div class=\"n\">{upcoming}<small>场</small></div><div class=\"l\">未过期</div></div>"
            f"<div class=\"stat ex\"><div class=\"n\">{expired}<small>场</small></div><div class=\"l\">已过期（仍列出）</div></div>"
            f"<div class=\"stat\"><div class=\"n\">{matched}<small>家</small></div><div class=\"l\">与我相关</div></div>"
            "</div>"
            '<div class="tabs">'
            f'<button class="tab" aria-selected="true"><span class="lv">第一级</span>招聘会总览'
            f'<span class="cnt">{total}</span></button>'
            f'<button class="tab" aria-selected="false"><span class="lv">第二级</span>与我相关'
            f'<span class="cnt">{matched}</span></button>'
            "</div>"
            f'<div class="panel active">{overview}</div>'
            f'<div class="panel">{relevant}'
            f'<h2 class="month">匹配明细<span>共 {len(scored)} 场</span></h2>{table}</div>'
            "<footer>"
            "本站为开源项目，每日 02:00 自动从学校就业平台抓取并重新发布；"
            "已过期的场次照常罗列，仅标记为灰色。<br>"
            "招聘信息以学校就业网实时发布为准，如有出入请以前者为准。"
            f"<br>生成时间 {esc(now)}　·　今天是 {esc(today.isoformat())}"
            "</footer></div>"
            f"<script>{JS}</script></body></html>"
        )

    def build(self, fairs: List[Dict[str, Any]], scored: List[Dict[str, Any]],
              months: List[str], today: dt.date) -> Path:
        html_text = self.render(fairs, scored, months, today)
        out = self.site_dir / self.config["output"]["index_name"]
        out.write_text(html_text, encoding="utf-8")
        # 同步一份数据快照，方便前端/其他工具二次利用
        (self.site_dir / "data.json").write_text(
            json.dumps({"updated_at": dt.datetime.now().isoformat(timespec="seconds"),
                        "total": len(fairs), "fairs": scored}, ensure_ascii=False),
            encoding="utf-8")
        return out
