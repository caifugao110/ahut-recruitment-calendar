"""
generate.py — 把抓取到的招聘会数据渲染成一个纯静态单页站点（site/index.html）。

页面结构：
    招聘会总览（默认页） —— 按月份 / 日期罗列场次，默认只显示未过期，已过期可一键切出
    与我相关            —— 按 config/config.json -> profile 的画像（专业 + 学历 + 意向城市）打分排序

产物不依赖任何后端，双击即可打开，也能直接托管到任意静态空间。
"""

from __future__ import annotations

import datetime as dt
import html as html_mod
import json
import re
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

header{background:linear-gradient(135deg,#2b3a55,#1f2430);color:#fff;border-radius:20px;
  padding:28px 30px;margin:20px 0 0;position:relative;overflow:hidden;
  box-shadow:0 12px 32px rgba(31,36,48,.16);}
header::after{content:"";position:absolute;right:-50px;top:-60px;width:240px;height:240px;
  background:radial-gradient(circle,rgba(212,36,60,.5),transparent 66%);}
header h1{margin:0 0 7px;font-size:24px;letter-spacing:.3px;position:relative;z-index:1;}
header .meta{color:#c3cbdd;font-size:13px;position:relative;z-index:1;}
header .meta code{background:rgba(255,255,255,.13);padding:1px 7px;border-radius:5px;}
header .meta a{color:#cdd6ea;}
header .links{display:flex;flex-wrap:wrap;gap:10px;margin-top:18px;position:relative;z-index:1;}
header .links a{display:inline-flex;align-items:center;gap:7px;font-size:13px;font-weight:600;
  border-radius:10px;padding:8px 16px;letter-spacing:.2px;
  transition:transform .15s ease,box-shadow .15s ease,background .15s ease;}
header .links a:hover{text-decoration:none;transform:translateY(-1px);}
header .links a.primary{background:#fff;color:#2b3a55;
  box-shadow:0 4px 14px rgba(0,0,0,.22);}
header .links a.primary:hover{box-shadow:0 7px 20px rgba(0,0,0,.3);background:#f4f7ff;}
header .links a.ghost{background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.3);
  color:#e7ecf5;}
header .links a.ghost:hover{background:rgba(255,255,255,.2);border-color:rgba(255,255,255,.5);}
header .links svg{width:14px;height:14px;fill:currentColor;flex:0 0 14px;}

.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:16px 0 4px;}
.stat{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px 16px;
  box-shadow:0 1px 3px rgba(31,36,48,.04);}
.stat .n{font-size:26px;font-weight:700;line-height:1.15;}
.stat .n small{font-size:13px;color:var(--muted);font-weight:500;margin-left:3px;}
.stat .l{font-size:12.5px;color:var(--ink2);margin-top:4px;}
.stat.hl .n{color:var(--red);} .stat.ok .n{color:var(--green);} .stat.ex .n{color:var(--grey);}

/* 标签栏：向下滚动时吸顶固定在顶部 */
.tabshell{position:sticky;top:0;z-index:60;display:flex;justify-content:center;
  margin:22px 0 0;padding:12px 0 10px;
  background:rgba(245,247,251,.93);
  -webkit-backdrop-filter:saturate(180%) blur(10px);
  backdrop-filter:saturate(180%) blur(10px);}
.tabs{display:inline-flex;gap:4px;background:#e8ecf4;padding:4px;border-radius:13px;
  box-shadow:inset 0 1px 2px rgba(31,36,48,.06);}
.tab{appearance:none;border:none;background:transparent;cursor:pointer;font:inherit;
  font-size:14.5px;font-weight:600;color:#5b6478;padding:9px 24px;border-radius:10px;
  display:flex;align-items:center;gap:8px;transition:color .16s ease,background .16s ease;}
.tab:hover{color:var(--ink);}
.tab[aria-selected="true"]{background:#fff;color:var(--ink);box-shadow:0 2px 8px rgba(31,36,48,.13);}
.tab .cnt{font-size:11.5px;font-weight:700;min-width:21px;height:21px;padding:0 6px;
  border-radius:999px;background:#d7dce7;color:#5b6478;
  display:flex;align-items:center;justify-content:center;transition:all .16s ease;}
.tab[aria-selected="true"] .cnt{background:var(--red);color:#fff;}
.panel{display:none;padding-top:16px;}
.panel.active{display:block;}
.nojs .panel{display:block !important;}

.bar{display:flex;gap:7px;flex-wrap:wrap;align-items:center;margin:0 0 14px;
  padding-bottom:13px;border-bottom:1px solid var(--line);}
.fbtn{appearance:none;border:1px solid var(--line);background:var(--card);cursor:pointer;
  font:inherit;font-size:12.5px;color:var(--ink2);padding:5px 14px;border-radius:999px;
  transition:all .15s ease;}
.fbtn:hover{border-color:#c8cfdd;color:var(--ink);}
.fbtn.on{background:var(--ink);color:#fff;border-color:var(--ink);}
.fhint{font-size:12px;color:var(--muted);margin-left:auto;}
.filter-empty{background:var(--card);border:1px dashed #d9dee8;border-radius:12px;
  padding:14px 18px;font-size:13px;color:var(--muted);}

h2.month{font-size:16px;margin:22px 0 10px;padding-left:11px;border-left:4px solid var(--ink);}
h2.month span{font-size:12px;color:var(--muted);font-weight:400;margin-left:8px;}
.empty{background:var(--card);border:1px dashed #d9dee8;border-radius:12px;padding:14px 18px;
  font-size:13px;color:var(--muted);}

.day{background:var(--card);border:1px solid var(--line);border-radius:14px;margin-bottom:12px;overflow:hidden;
  box-shadow:0 1px 3px rgba(31,36,48,.04);}
.day.past{background:#fbfbfc;box-shadow:none;}
.day-hd{display:flex;align-items:center;gap:10px;padding:11px 17px;background:#fbfcfe;
  border-bottom:1px solid var(--line);flex-wrap:wrap;}
.day.past .day-hd{background:#f6f7f9;}
.day-hd .d{font-size:15px;font-weight:700;}
.day.past .day-hd .d{color:var(--grey);}
.day-hd .w{font-size:12px;color:var(--muted);}
.day-hd .cnt{margin-left:auto;font-size:11.5px;font-weight:600;border-radius:999px;padding:2px 10px;
  background:var(--blue-soft);color:var(--blue);}
.day.past .day-hd .cnt{background:var(--grey-soft);color:var(--grey);}

.li{display:flex;gap:14px;padding:13px 17px;border-top:1px solid #f1f3f8;align-items:flex-start;
  transition:background .15s ease;}
.li:first-of-type{border-top:none;}
.li:hover{background:#f8faff;}
.li .t{font-variant-numeric:tabular-nums;font-weight:700;font-size:12px;color:var(--blue);
  min-width:92px;background:var(--blue-soft);border-radius:8px;padding:4px 0;text-align:center;
  margin-top:1px;flex:0 0 92px;}
.day.past .li .t{color:var(--grey);background:var(--grey-soft);}
.li .bd{flex:1;min-width:220px;}
.li .co{font-size:14.5px;font-weight:700;letter-spacing:.2px;}
.day.past .li .co{color:#9aa2b1;font-weight:600;}
.li .vn{font-size:12.5px;color:var(--ink2);margin-top:3px;display:flex;align-items:center;gap:4px;}
.li .vn svg{width:12px;height:12px;fill:#a6aebe;flex:0 0 12px;}
.day.past .li .vn{color:#aab1bf;}
.li .pay{display:inline-flex;align-items:center;gap:5px;margin-top:5px;font-size:12px;
  font-weight:600;color:var(--amber);background:var(--amber-soft);border:1px solid #f3e3c3;
  border-radius:7px;padding:2px 9px;max-width:100%;}
.li .pay svg{width:12px;height:12px;fill:currentColor;flex:0 0 12px;}
.day.past .li .pay{color:#b6a98f;background:#f6f4ef;border-color:#e9e5da;}
.li .st{margin-left:auto;font-size:11.5px;font-weight:700;border-radius:6px;padding:3px 10px;
  white-space:nowrap;flex:0 0 auto;}
.st-expired{background:var(--grey-soft);color:var(--grey);}
.st-today{background:var(--red-soft);color:var(--red);}
.st-upcoming{background:var(--green-soft);color:var(--green);}
.li .lk{font-size:12px;margin-top:5px;}
.li .lk a{color:var(--muted);transition:color .15s ease;}
.li .lk a:hover{color:var(--blue);text-decoration:none;}

.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px 20px;margin-bottom:12px;
  box-shadow:0 1px 3px rgba(31,36,48,.04);}
.card.t1{border-left:3px solid var(--red);}
.card.t2{border-left:3px solid var(--amber);}
.card.t3{border-left:3px solid #cfd5e0;}
.card.past{background:#fbfbfc;box-shadow:none;opacity:.92;}
.card-hd{display:flex;align-items:baseline;gap:9px;flex-wrap:wrap;margin-bottom:8px;}
.rank{width:23px;height:23px;flex:0 0 23px;border-radius:7px;color:#fff;font-size:12.5px;
  display:flex;align-items:center;justify-content:center;font-weight:700;background:var(--grey);}
.rank.t1{background:var(--red);} .rank.t2{background:var(--amber);} .rank.t3{background:#9aa2b1;}
.card-hd .co{font-size:15.5px;font-weight:700;letter-spacing:.2px;}
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
.b-edu{background:#f3eefb;color:#6d3fc4;}
.b-score{background:var(--red-soft);color:var(--red);}

table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);
  border-radius:12px;overflow:hidden;font-size:12.5px;}
thead th{background:#f0f2f7;color:var(--ink2);font-weight:600;text-align:left;padding:9px 11px;white-space:nowrap;}
tbody td{padding:8px 11px;border-top:1px solid var(--line);vertical-align:middle;}
tbody tr:nth-child(even){background:#fafbfd;}

.note{background:linear-gradient(135deg,#eff4ff,#f8faff);border:1px solid #d8e3ff;color:#27407a;
  border-radius:12px;padding:12px 16px;font-size:13px;margin:0 0 16px;line-height:1.75;}
.note b{color:#1b2f5c;}
.note .sep{color:#9fb0d8;margin:0 6px;}
footer{margin-top:34px;font-size:12px;color:var(--muted);text-align:center;line-height:1.9;}
footer a{color:var(--muted);}
@media(max-width:760px){
  .stats{grid-template-columns:repeat(2,1fr);}
  .li{flex-wrap:wrap;} .li .t{min-width:0;flex:0 0 auto;padding:4px 10px;}
  .li .st{margin-left:0;}
  .card-hd .when{margin-left:0;} .row{flex-direction:column;gap:2px;}
  .tab{padding:9px 15px;font-size:13.5px;}
}
"""

FAVICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" role="img" aria-label="招聘日历">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#2b3a55"/>
      <stop offset="1" stop-color="#d4243c"/>
    </linearGradient>
  </defs>
  <rect width="64" height="64" rx="15" fill="url(#g)"/>
  <rect x="11" y="11" width="6" height="13" rx="3" fill="#ffffff"/>
  <rect x="47" y="11" width="6" height="13" rx="3" fill="#ffffff"/>
  <rect x="10" y="17" width="44" height="36" rx="7" fill="#ffffff"/>
  <path d="M10 24a7 7 0 0 1 7-7h30a7 7 0 0 1 7 7v4H10z" fill="#24304a"/>
  <path d="M22 38.5l6.5 6.5L44 30" stroke="#d4243c" stroke-width="6" fill="none"
        stroke-linecap="round" stroke-linejoin="round"/>
</svg>
"""

# GitHub 与 Pages 图标（内联 SVG，避免外链依赖）
ICON_GITHUB = ('<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 '
               '2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94'
               '-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 '
               '2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36'
               '-1.02.08-2.12 0 0 .67-.21 2.2.82a7.4 7.4 0 0 1 2-.27c.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 '
               '2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73'
               '.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8z"/>'
               '</svg>')
ICON_PAGE = ('<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 0a8 8 0 1 0 0 16A8 8 0 0 0 8 0zm'
             '5.9 5h-2.3a12.6 12.6 0 0 0-1-2.4A6.5 6.5 0 0 1 13.9 5zM8 1.6c.6.9 1.1 2 1.4 3.4H6.6C6.9 '
             '3.6 7.4 2.5 8 1.6zM1.6 9.5c-.1-.5-.1-1 0-1.5h2.7a16 16 0 0 0 0 1.5H1.6zm.5 1.5h2.3c.2.9.6 '
             '1.7 1 2.4A6.5 6.5 0 0 1 2.1 11zm2.3-4H2.1a6.5 6.5 0 0 1 3.4-2.4c-.5.7-.8 1.5-1 2.4zM8 '
             '14.4c-.6-.9-1.1-2-1.4-3.4h2.8c-.3 1.4-.8 2.5-1.4 3.4zm1.7-4.9H6.3a14 14 0 0 1 0-1.5h3.4c.1.5.1 '
             '1 0 1.5zm.4 4.4c.4-.7.8-1.5 1-2.4h2.3a6.5 6.5 0 0 1-3.3 2.4zm1.4-4h2.7c.1-.5.1-1 '
             '0-1.5h-2.7a16 16 0 0 1 0 1.5z"/></svg>')
ICON_PIN = ('<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 1.5a4.75 4.75 0 0 0-4.75 4.75c0 '
            '3.4 4.06 8.1 4.23 8.27a.75.75 0 0 0 1.04 0c.17-.17 4.23-4.87 4.23-8.27A4.75 4.75 0 0 0 8 '
            '1.5zm0 6.5a1.75 1.75 0 1 1 0-3.5 1.75 1.75 0 0 1 0 3.5z"/></svg>')
ICON_COIN = ('<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 1a7 7 0 1 0 0 14A7 7 0 0 0 8 1zm'
             '2.9 4.1l-1.9 2.4h1.6v.9H8.55v.8h2.05v.9H8.55V12H7.45v-1.9H5.4v-.9h2.05v-.8H5.4v-.9H7L5.1 '
             '5.1l.8-.6L8 6.8l2.1-2.3.8.6z"/></svg>')

JS = """
(function(){
  var root=document.documentElement;
  root.classList.remove('nojs');

  var tabs=[].slice.call(document.querySelectorAll('.tab'));
  var panels=[].slice.call(document.querySelectorAll('.panel'));
  function select(i){
    tabs.forEach(function(t,k){t.setAttribute('aria-selected', k===i?'true':'false');});
    panels.forEach(function(p,k){p.classList.toggle('active', k===i);});
    try{ history.replaceState(null,'','#p'+i); }catch(e){}
  }
  tabs.forEach(function(t,i){t.addEventListener('click',function(){select(i);});});
  var h=(location.hash||'').replace('#p','');
  select(h==='1'?1:0);

  function panelOf(el){
    var p=el;
    while(p && p.classList && !p.classList.contains('panel')) p=p.parentElement;
    return p;
  }
  function applyFilter(btn){
    var group=btn.parentNode;
    [].slice.call(group.querySelectorAll('[data-filter]')).forEach(function(b){
      b.classList.toggle('on', b===btn);
    });
    var f=btn.getAttribute('data-filter');
    var panel=panelOf(group);
    if(!panel) return;
    var any=false;
    [].slice.call(panel.querySelectorAll('[data-status]')).forEach(function(el){
      var st=el.getAttribute('data-status');
      var show = (f==='all') ? true
               : (f==='expired') ? (st==='expired')
               : (st!=='expired');
      el.style.display = show ? '' : 'none';
      if(show) any=true;
    });
    [].slice.call(panel.querySelectorAll('.month-block')).forEach(function(bl){
      var vis=[].slice.call(bl.querySelectorAll('[data-status]'))
               .filter(function(e){return e.style.display!=='none';});
      bl.style.display = vis.length ? '' : 'none';
    });
    var tip=panel.querySelector('.filter-empty');
    if(tip) tip.style.display = any ? 'none' : '';
  }

  document.querySelectorAll('[data-filter]').forEach(function(btn){
    btn.addEventListener('click',function(){applyFilter(btn);});
  });

  // 初始状态：默认只显示未过期，无需手动筛选
  [].slice.call(document.querySelectorAll('.panel')).forEach(function(panel){
    var def=panel.querySelector('[data-filter].on') || panel.querySelector('[data-filter]');
    if(def) applyFilter(def);
  });
})();
"""


def esc(s: Any) -> str:
    return html_mod.escape(str(s or ""), quote=True)


def _month_label(key: str) -> str:
    y, m = key.split("-")
    return f"{y}年{int(m)}月"


def _day_label(date_str: str) -> str:
    """把 2026-10-08 渲染成「10月8日」。"""
    try:
        d = dt.date.fromisoformat(date_str[:10])
    except (ValueError, TypeError):
        return date_str[:10]
    return f"{int(d.month)}月{int(d.day)}日"


_SALARY_KW = re.compile(r"(薪资|薪酬|年薪|月薪|待遇|工资)")
_NUM_UNIT = re.compile(r"\d+\s*[-~—–]?\s*\d*\s*(?:万\s*/?\s*年|万元|万|元\s*/\s*月|元\s*/\s*年|[kKwW])")
_SALARY_TABLE_LABEL = {"薪资", "薪资待遇", "月薪", "年薪", "薪酬"}


def extract_salary(desc: str) -> str:
    """
    从招聘简章全文里提炼一句薪资待遇；没有明确数字则返回空串（页面不展示）。

    覆盖两类常见写法：
      1. 表格型：单独一行「薪资」，紧随其后是「| 8500元/月」「| 面议」这类数值行
      2. 行文型：一行内同时出现 薪资/年薪等待遇词 与 数字+单位（万/元/月/k/W）
    """
    if not desc:
        return ""
    lines = desc.split("\n")

    for i, raw in enumerate(lines):
        label = raw.strip().strip("|").strip().rstrip("：:")
        if label in _SALARY_TABLE_LABEL:
            vals: List[str] = []
            for nxt in lines[i + 1:i + 6]:
                v = nxt.strip().strip("|").strip()
                if not v:
                    continue
                if _NUM_UNIT.search(v) or v == "面议":
                    vals.append(v)
                elif vals:
                    break
            if vals:
                return " / ".join(vals[:3])

    for raw in lines:
        line = raw.strip(" ●·|\t").strip()
        if len(line) < 6:
            continue
        kw = _SALARY_KW.search(line)
        if not kw or not _NUM_UNIT.search(line):
            continue
        seg = re.split(r"[。；;]", line)[0].strip(" ，,、")
        # 从薪资关键词处起截取，去掉「1、实行试用期制度，试用期6个月，」这类铺垫前缀
        start = kw.start()
        if _NUM_UNIT.search(seg[start:]) and len(seg[start:]) >= 8:
            # 保留关键词前的极短定语（如「综合」「转正」），最多往前取 6 字
            head = seg[max(0, start - 6):start]
            cut = max(head.rfind("，"), head.rfind(","), head.rfind("、"))
            seg = head[cut + 1:] + seg[start:]
        if len(seg) > 60:
            seg = seg[:60].rstrip(" ，,、") + "…"
        if not _NUM_UNIT.search(seg):
            continue  # 「薪酬待遇优厚」这类空话，数字在别的分句里，宁缺毋滥
        return seg
    return ""


class Generator:
    """静态站点生成器。"""

    def __init__(self, config: Dict[str, Any], profile: Dict[str, Any]) -> None:
        self.config = config
        self.profile = profile
        # 招聘会时间区间与每日自动更新时间都来自统一配置的 profile 段
        self.fair_range: Dict[str, Any] = profile.get("fair_range", {})
        self.daily_at: str = (profile.get("schedule") or {}).get("daily_at", "02:00")
        self.site_dir = Path(config["output"]["site_dir"])
        self.site_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def group_by_month(fairs: List[Dict[str, Any]]) -> "OrderedDict[str, List[Dict[str, Any]]]":
        buckets: "OrderedDict[str, List[Dict[str, Any]]]" = OrderedDict()
        for f in fairs:
            buckets.setdefault(f["date"][:7], []).append(f)
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

    @staticmethod
    def _filter_bar(hint: str) -> str:
        """筛选条。默认选中「未过期」，进页面即可直接看到有效场次。"""
        return (
            '<div class="bar">'
            '<button class="fbtn on" data-filter="active">未过期</button>'
            '<button class="fbtn" data-filter="all">全部</button>'
            '<button class="fbtn" data-filter="expired">已过期</button>'
            f'<span class="fhint">{esc(hint)}</span>'
            "</div>"
        )

    def _overview(self, fairs: List[Dict[str, Any]], months: List[str]) -> str:
        buckets = self.group_by_month(fairs)
        parts: List[str] = []
        parts.append(self._filter_bar("默认只显示未过期场次，已过期的可切换到「全部」或「已过期」查看"))
        parts.append('<div class="filter-empty" style="display:none">当前筛选条件下没有场次。</div>')

        for key in months:
            items = buckets.get(key, [])
            upcoming = sum(1 for x in items if x["status"] != "expired")
            parts.append(
                f'<div class="month-block"><h2 class="month">{esc(_month_label(key))}'
                f'<span>共 {len(items)} 场 · 未过期 {upcoming} 场</span></h2>'
            )
            if not items:
                parts.append(f'<div class="empty">本月暂无招聘会安排（一旦官网放出，每日 {esc(self.daily_at)} 会自动补上）。</div>')
            else:
                for day, rows in self.group_by_day(items).items():
                    past = rows[0]["status"] == "expired"
                    cls = "day past" if past else "day"
                    parts.append(
                        f'<div class="{cls}" data-status="{esc(rows[0]['status'])}">'
                        f'<div class="day-hd"><span class="d">{esc(_day_label(day))}</span>'
                        f'<span class="w">{esc(rows[0].get("weekday",""))}</span>'
                        f'<span class="cnt">{len(rows)} 场 · {esc(rows[0]["status_label"])}</span></div>'
                    )
                    for r in rows:
                        link = self.config["site"]["detail_url"].format(id=r["id"])
                        salary = extract_salary(r.get("description", ""))
                        pay_html = (f'<div><span class="pay">{ICON_COIN}{esc(salary)}</span></div>'
                                    if salary else "")
                        parts.append(
                            '<div class="li">'
                            f'<div class="t">{esc(r["time"])}</div>'
                            '<div class="bd">'
                            f'<div class="co">{esc(r["theme"])}</div>'
                            f'<div class="vn">{ICON_PIN}{esc(r["venue"])}</div>'
                            f"{pay_html}"
                            f'<div class="lk"><a href="{esc(link)}" target="_blank" rel="noopener">'
                            "查看官方简章 →</a></div>"
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
        edu = esc(self.profile.get("education", ""))
        cities = " / ".join(esc(c) for c in self.profile.get("cities", {}).get("primary", []))
        parts: List[str] = []

        bits = [f"专业 <b>{major}</b>"]
        if edu:
            bits.append(f"学历 <b>{edu}</b>")
        bits.append(f"意向城市 <b>{cities}</b>")
        parts.append(
            '<div class="note">匹配画像：<span>'
            + '<span class="sep">·</span>'.join(bits)
            + "</span><br>打分与关键词均来自 <code>config/config.json → profile</code>，"
            "改动配置即可适配其他人。已过期的匹配项同样保留，仅作灰显。</div>"
        )

        if not matched:
            parts.append(f'<div class="empty">当前区间内没有与画像匹配的招聘会。每日 {esc(self.daily_at)} 会自动重新抓取并更新。</div>')
            return "".join(parts)

        parts.append(self._filter_bar("默认只显示未过期场次；已过期但仍想参考的可切换到「全部」"))
        parts.append('<div class="filter-empty" style="display:none">当前筛选条件下没有匹配项。</div>')

        tier_meta = {1: ("强相关", "t1"), 2: ("相关", "t2"), 3: ("沾边", "t3")}
        for tier, (label, cls) in tier_meta.items():
            group = [s for s in matched if s["tier"] == tier]
            if not group:
                continue
            parts.append(f'<div class="month-block"><h2 class="month">{label}<span>{len(group)} 家</span></h2>')
            for idx, s in enumerate(group, 1):
                past = s["status"] == "expired"
                card_cls = f"card t{cls}" + (" past" if past else "")
                parts.append(f'<div class="{card_cls}" data-status="{esc(s["status"])}">')
                parts.append('<div class="card-hd">'
                             f'<span class="rank {cls}">{idx}</span>'
                             f'<span class="co">{esc(s["theme"])}</span>'
                             f'<span class="when">{esc(_day_label(s["date"]))} {esc(s["time"])}</span>'
                             "</div>")

                badges = [f'<span class="badge b-score">{s["score"]} 分</span>']
                badges.append(f'<span class="badge {"b-lo" if past else "b-hi"}">{esc(s["status_label"])}</span>')
                if s["major_hits"]:
                    badges.append(f'<span class="badge b-hi">专业：{esc(s["major_hits"][0])}</span>')
                if s["city_hits"]:
                    badges.append(f'<span class="badge b-city">城市：{esc("、".join(s["city_hits"]))}</span>')
                elif s["city_belt_hits"]:
                    badges.append(f'<span class="badge b-city">周边：{esc("、".join(s["city_belt_hits"][:3]))}</span>')
                if s.get("edu_hits"):
                    badges.append(f'<span class="badge b-edu">学历：{esc("、".join(s["edu_hits"][:2]))}</span>')
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
                f"<td>{esc(_day_label(s['date']))}</td>"
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

    def render(self, fairs: List[Dict[str, Any]], scored: List[Dict[str, Any]],
               months: List[str], today: dt.date) -> str:
        total = len(fairs)
        expired = sum(1 for f in fairs if f["status"] == "expired")
        upcoming = total - expired
        matched = sum(1 for s in scored if s["tier"] > 0)
        now = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
        rng = self.fair_range

        overview = self._overview(fairs, months)
        relevant = self._relevant(scored)
        table = self._table(scored)

        links = self.config.get("links", {})
        author = self.config["site"].get("author", "")
        repo_url = links.get("repo", "")
        pages_url = links.get("pages", "")
        link_html = ""
        if pages_url:
            link_html += (f'<a class="primary" href="{esc(pages_url)}" target="_blank" rel="noopener">'
                          f'{ICON_PAGE}<span>GitHub 原始页面</span></a>')
        if repo_url:
            link_html += (f'<a class="ghost" href="{esc(repo_url)}" target="_blank" rel="noopener">'
                          f'{ICON_GITHUB}<span>源代码仓库</span></a>')

        return (
            '<!DOCTYPE html><html lang="zh-CN" class="nojs">'
            '<head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f"<title>{esc(self.config['site']['name'])}</title>"
            f'<link rel="icon" type="image/svg+xml" href="favicon.svg">'
            '<meta name="description" content="安徽工业大学校园招聘会日历：每日自动抓取，'
            '含招聘会总览与按专业、学历、城市画像筛选的个性化匹配。">'
            f"<style>{CSS}</style></head><body><div class=\"wrap\">"
            f"<header><h1>{esc(self.config['site']['name'])}</h1>"
            f"<div class=\"meta\">统计区间 <code>{esc(rng['start'])} ~ {esc(rng['end'])}</code>　·　"
            f"数据更新 <code>{esc(now)}</code>　·　每日 <code>02:00</code> 自动更新"
            + (f"　·　作者 <code>{esc(author)}</code>" if author else "") + "<br>"
            "来源：<a href=\"" + esc(self.config["site"]["calendar_url"]) +
            "\" target=\"_blank\" rel=\"noopener\">ahut.ahbys.com 招聘日历</a></div>"
            f'<div class="links">{link_html}</div></header>'
            "<div class=\"stats\">"
            f"<div class=\"stat hl\"><div class=\"n\">{total}<small>场</small></div>"
            "<div class=\"l\">区间内总场次</div></div>"
            f"<div class=\"stat ok\"><div class=\"n\">{upcoming}<small>场</small></div>"
            "<div class=\"l\">未过期</div></div>"
            f"<div class=\"stat ex\"><div class=\"n\">{expired}<small>场</small></div>"
            "<div class=\"l\">已过期（可切换查看）</div></div>"
            f"<div class=\"stat\"><div class=\"n\">{matched}<small>家</small></div>"
            "<div class=\"l\">与我相关</div></div>"
            "</div>"
            '<div class="tabshell"><div class="tabs">'
            f'<button class="tab" aria-selected="true">招聘会总览'
            f'<span class="cnt">{total}</span></button>'
            f'<button class="tab" aria-selected="false">与我相关'
            f'<span class="cnt">{matched}</span></button>'
            "</div></div>"
            f'<div class="panel active">{overview}</div>'
            f'<div class="panel">{relevant}'
            f'<h2 class="month">匹配明细<span>共 {len(scored)} 场</span></h2>{table}</div>'
            "<footer>"
            f"本站为 MIT 开源项目，每日 {esc(self.daily_at)} 自动从学校就业平台抓取并重新发布；"
            "已过期的场次照常收录，切换筛选即可查看。<br>"
            "招聘信息以学校就业网实时发布为准，如有出入请以前者为准。<br>"
            + (f'<a href="{esc(pages_url)}" target="_blank" rel="noopener">GitHub 原始页面</a>'
               "　·　" if pages_url else "")
            + (f'<a href="{esc(repo_url)}" target="_blank" rel="noopener">源代码仓库</a>　·　'
               if repo_url else "")
            + (f"作者 {esc(author)}　·　" if author else "")
            + f"生成时间 {esc(now)}　·　今天是 {esc(today.isoformat())}"
            "</footer></div>"
            f"<script>{JS}</script></body></html>"
        )

    def build(self, fairs: List[Dict[str, Any]], scored: List[Dict[str, Any]],
              months: List[str], today: dt.date) -> Path:
        html_text = self.render(fairs, scored, months, today)
        out = self.site_dir / self.config["output"]["index_name"]
        out.write_text(html_text, encoding="utf-8")
        # 站点图标（SVG，随站点一起发布，避免依赖外部图床）
        (self.site_dir / "favicon.svg").write_text(FAVICON_SVG, encoding="utf-8")
        (self.site_dir / "data.json").write_text(
            json.dumps({"updated_at": dt.datetime.now().isoformat(timespec="seconds"),
                        "total": len(fairs), "fairs": scored}, ensure_ascii=False),
            encoding="utf-8")
        return out
