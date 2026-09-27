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

from src.textutil import clean_leading_marks

CSS = """
:root{
  --ink:#1f2430; --ink2:#4a5364; --muted:#8a93a5; --line:#e6e9f0;
  --bg:#f5f7fb; --card:#ffffff;
  --red:#d4243c; --red-soft:#fdeef0;
  --amber:#c77700; --amber-soft:#fff5e6;
  --green:#1a7f52; --green-soft:#e8f6ee;
  --blue:#2563eb; --blue-soft:#eff4ff;
  --grey:#98a1b2; --grey-soft:#f2f3f7;
  --tab-h:62px;              /* 标签栏实际高度，由页面 JS 实测回写，供筛选条吸顶对齐 */
}
*{box-sizing:border-box;}
body{margin:0;padding:0 14px 60px;background:var(--bg);color:var(--ink);
  font-family:"PingFang SC","Microsoft YaHei","Hiragino Sans GB",-apple-system,"Segoe UI",sans-serif;
  -webkit-font-smoothing:antialiased;line-height:1.6;}
.wrap{max-width:1080px;margin:0 auto;}
a{color:var(--blue);text-decoration:none;}
a:hover{text-decoration:underline;}

header{background:linear-gradient(135deg,#2b3a55,#1f2430);color:#fff;border-radius:20px;
  padding:26px 30px;margin:20px 0 0;position:relative;overflow:hidden;
  box-shadow:0 12px 32px rgba(31,36,48,.16);}
header::after{content:"";position:absolute;right:-50px;top:-60px;width:240px;height:240px;
  background:radial-gradient(circle,rgba(212,36,60,.5),transparent 66%);}
header h1{margin:0 0 7px;font-size:24px;letter-spacing:.3px;position:relative;z-index:1;}
header .meta{color:#c3cbdd;font-size:13px;position:relative;z-index:1;}
header .meta code{background:rgba(255,255,255,.13);padding:1px 7px;border-radius:5px;}
header .meta a{color:#cdd6ea;}

/* 统计卡也是按钮：点哪张就跳到对应的筛选结果 */
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:16px 0 4px;}
.stat{display:block;width:100%;text-align:left;font:inherit;cursor:pointer;
  background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px 16px;
  box-shadow:0 1px 3px rgba(31,36,48,.04);
  transition:transform .15s ease,box-shadow .15s ease,border-color .15s ease;}
.stat:hover{transform:translateY(-2px);border-color:#cfd6e4;
  box-shadow:0 8px 22px rgba(31,36,48,.1);}
.stat:active{transform:translateY(0);}
.stat:focus-visible{outline:2px solid var(--blue);outline-offset:2px;}
.stat .n{display:block;font-size:26px;font-weight:700;line-height:1.15;}
.stat .n small{font-size:13px;color:var(--muted);font-weight:500;margin-left:3px;}
.stat .l{font-size:12.5px;color:var(--ink2);margin-top:4px;display:flex;align-items:center;gap:4px;}
.stat .l .go{font-size:11px;color:var(--muted);opacity:0;transition:opacity .15s ease;}
.stat:hover .l .go{opacity:1;}
.stat.hl .n{color:var(--red);} .stat.ok .n{color:var(--green);} .stat.ex .n{color:var(--grey);}

/* 标签栏：向下滚动时吸顶固定在顶部。
   注意：这里刻意不用 backdrop-filter —— 部分移动端浏览器（Safari 内核 / 微信 X5）
   遇到毛玻璃会让 sticky 失效，移动端反馈过「电脑上固定、手机上不固定」，故改用不透明背景 */
.tabshell{position:-webkit-sticky;position:sticky;top:0;z-index:60;display:flex;
  justify-content:center;margin:22px 0 0;padding:12px 0 10px;background:var(--bg);}
/* JS 兜底：浏览器确实不支持 sticky 时改用 fixed，并撑起等高占位避免跳动 */
.tabshell-ph{height:0;}
.tabshell.js-stuck{position:fixed;left:0;right:0;top:0;margin:0;}
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

/* 筛选条跟着标签栏一起吸顶：往下翻场次时也能随时改筛选（同样不用毛玻璃，理由见标签栏） */
.bar{position:-webkit-sticky;position:sticky;top:var(--tab-h,62px);z-index:55;
  display:flex;gap:7px;flex-wrap:wrap;align-items:center;margin:0 0 14px;padding:9px 0 11px;
  border-bottom:1px solid var(--line);scroll-margin-top:78px;background:var(--bg);}
.fbtn{appearance:none;border:1px solid var(--line);background:var(--card);cursor:pointer;
  font:inherit;font-size:12.5px;color:var(--ink2);padding:5px 14px;border-radius:999px;
  transition:all .15s ease;}
.fbtn:hover{border-color:#c8cfdd;color:var(--ink);}
.fbtn.on{background:var(--ink);color:#fff;border-color:var(--ink);}
.fbtn.disabled{opacity:.4;cursor:not-allowed;}
.fbtn.disabled:hover{border-color:var(--line);color:var(--ink2);}
.fhint{font-size:12px;color:var(--muted);margin-left:auto;}
.fhint b{color:var(--ink);font-weight:700;font-variant-numeric:tabular-nums;}
.filter-empty{background:var(--card);border:1px dashed #d9dee8;border-radius:12px;
  padding:14px 18px;font-size:13px;color:var(--muted);}

/* 按日历筛选：有场次的日期可点，点一下只看当天；默认收起，点标题栏展开 */
.calfilter{background:var(--card);border:1px solid var(--line);border-radius:14px;
  padding:12px 14px 11px;margin:0 0 14px;max-width:472px;
  box-shadow:0 1px 3px rgba(31,36,48,.04);}
.cal-hd{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:10px;
  cursor:pointer;user-select:none;}
.calfilter.collapsed .cal-hd{margin-bottom:0;}
.cal-caret{display:inline-flex;width:16px;height:16px;color:var(--muted);margin-left:1px;
  transition:transform .18s ease;}
.cal-caret svg{width:16px;height:16px;fill:currentColor;}
.calfilter.collapsed .cal-caret{transform:rotate(-90deg);}
.cal-body{animation:calIn .18s ease;}
@keyframes calIn{from{opacity:0;}to{opacity:1;}}
.calfilter.collapsed .cal-body{display:none;}
.cal-hd .cal-ic{display:inline-flex;width:17px;height:17px;color:var(--red);}
.cal-hd .cal-ic svg{width:17px;height:17px;fill:currentColor;}
.cal-hd .cal-tt{font-size:13.5px;font-weight:700;letter-spacing:.2px;}
.cal-hd .cal-sel{margin-left:auto;font-size:11.5px;font-weight:600;color:var(--muted);
  background:var(--grey-soft);border-radius:999px;padding:2px 10px;}
.cal-hd .cal-sel.on{color:#fff;background:var(--red);}
.cal-navs{display:inline-flex;align-items:center;gap:3px;}
.calfilter.collapsed .cal-navs{display:none;}   /* 收起时不显示翻月控件 */
.cal-navs .cal-ym{font-size:12.5px;font-weight:700;color:var(--ink2);min-width:78px;text-align:center;
  font-variant-numeric:tabular-nums;}
.cal-nav{appearance:none;border:1px solid var(--line);background:#fbfcfe;cursor:pointer;
  width:26px;height:26px;border-radius:8px;color:var(--ink2);font-size:14px;line-height:1;
  display:flex;align-items:center;justify-content:center;transition:all .15s ease;padding:0;}
.cal-nav:hover:not(:disabled){border-color:var(--red);color:var(--red);background:#fff;}
.cal-nav:disabled{opacity:.35;cursor:not-allowed;}
.cal-clear{appearance:none;border:1px solid #f0d3d8;background:var(--red-soft);cursor:pointer;
  font:inherit;font-size:11.5px;font-weight:600;color:var(--red);border-radius:8px;
  padding:3px 10px;margin-left:5px;transition:all .15s ease;}
.cal-clear:hover{background:var(--red);border-color:var(--red);color:#fff;}
.cal-grid{display:grid;grid-template-columns:repeat(7,1fr);gap:4px;}
.cal-w{font-size:11px;color:var(--muted);text-align:center;padding-bottom:2px;font-weight:600;}
.cal-d{position:relative;height:31px;display:flex;align-items:center;justify-content:center;
  font-size:12.5px;border-radius:9px;color:#c6ccd9;background:#fafbfd;}
.cal-d.blank{background:transparent;}
.cal-d.has{color:var(--ink);background:#fff;border:1px solid var(--line);cursor:pointer;font-weight:700;}
.cal-d.has:hover{border-color:var(--red);color:var(--red);background:#fffafa;}
.cal-d.has::after{content:"";position:absolute;bottom:4px;width:4px;height:4px;border-radius:50%;
  background:var(--red);}
.cal-d.has .cal-n{position:absolute;top:2px;right:3px;font-size:9.5px;font-style:normal;
  font-weight:700;color:var(--amber);}
.cal-d.sel{background:var(--red);border-color:var(--red);color:#fff;
  box-shadow:0 5px 14px rgba(212,36,60,.3);}
.cal-d.sel::after{background:#fff;}
.cal-d.sel .cal-n{color:#ffe1e5;}
.cal-d.today{outline:2px solid var(--blue);outline-offset:-2px;}
.cal-tip{font-size:11.5px;color:var(--muted);margin-top:9px;}
.cal-tip b{color:var(--red);}

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
/* 列表行三列：左＝时间+地点，中＝单位名 / 查看简章 / 薪资待遇（三行），右＝状态 */
.li .tcol{flex:0 0 126px;display:flex;flex-direction:column;gap:5px;}
.li .t{font-variant-numeric:tabular-nums;font-weight:700;font-size:12px;color:var(--blue);
  background:var(--blue-soft);border-radius:8px;padding:4px 0;text-align:center;}
.day.past .li .t{color:var(--grey);background:var(--grey-soft);}
.li .bd{flex:1;min-width:200px;display:flex;flex-direction:column;align-items:flex-start;}
.li .co{font-size:14.5px;font-weight:700;letter-spacing:.2px;}
.day.past .li .co{color:#9aa2b1;font-weight:600;}
.li .lk{margin-top:6px;}
.li .vn{font-size:11.5px;line-height:1.45;color:var(--ink2);display:flex;align-items:flex-start;
  gap:3px;padding:0 3px;overflow-wrap:break-word;}
.li .vn svg{width:11px;height:11px;fill:#a6aebe;flex:0 0 11px;margin-top:2px;}
.day.past .li .vn{color:#aab1bf;}
/* 薪资待遇单独占一行（放在单位名下方），不与单位名、简章按钮抢同一行的空间 */
.pay{display:inline-flex;align-items:center;gap:5px;margin-top:6px;font-size:12px;line-height:1.5;
  font-weight:600;color:var(--amber);background:var(--amber-soft);border:1px solid #f3e3c3;
  border-radius:8px;padding:2px 9px;max-width:100%;min-width:0;}
.pay svg{width:12px;height:12px;fill:currentColor;flex:0 0 12px;}
.day.past .li .pay,.card.past .pay{color:#b6a98f;background:#f6f4ef;border-color:#e9e5da;}
.li .st{margin-left:auto;font-size:11.5px;font-weight:700;border-radius:6px;padding:3px 10px;
  white-space:nowrap;flex:0 0 auto;}
.st-expired{background:var(--grey-soft);color:var(--grey);}
.st-today{background:var(--red-soft);color:var(--red);}
.st-upcoming{background:var(--green-soft);color:var(--green);}
/* 「查看官方简章」做成小按钮，hover 反色，比裸链接更好点也更好看 */
a.brief{display:inline-flex;align-items:center;gap:6px;font-size:12.5px;font-weight:600;
  color:var(--blue);background:var(--blue-soft);border:1px solid #dbe4fb;border-radius:9px;
  padding:5px 13px;letter-spacing:.1px;transition:all .16s ease;}
a.brief:hover{background:var(--blue);border-color:var(--blue);color:#fff;text-decoration:none;
  transform:translateY(-1px);box-shadow:0 5px 14px rgba(37,99,235,.28);}
a.brief svg{width:12px;height:12px;fill:currentColor;flex:0 0 12px;transition:transform .16s ease;}
a.brief:hover svg{transform:translateX(2px);}
.day.past a.brief,.card.past a.brief{color:#8b94a5;background:#f6f7f9;border-color:#e7eaf0;}
.day.past a.brief:hover,.card.past a.brief:hover{background:#98a1b2;border-color:#98a1b2;color:#fff;box-shadow:none;}

.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px 20px;margin-bottom:12px;
  box-shadow:0 1px 3px rgba(31,36,48,.04);}
.card.t1{border-left:3px solid var(--red);}
.card.t2{border-left:3px solid var(--amber);}
.card.t3{border-left:3px solid #cfd5e0;}
.card.past{background:#fbfbfc;box-shadow:none;opacity:.92;}
.card-hd{display:flex;align-items:center;gap:9px;flex-wrap:wrap;margin-bottom:8px;}
.card-hd .brief{margin-left:auto;}
.rank{width:23px;height:23px;flex:0 0 23px;border-radius:7px;color:#fff;font-size:12.5px;
  display:flex;align-items:center;justify-content:center;font-weight:700;background:var(--grey);}
.rank.t1{background:var(--red);} .rank.t2{background:var(--amber);} .rank.t3{background:#9aa2b1;}
.card-hd .co{font-size:15.5px;font-weight:700;letter-spacing:.2px;}
.card.past .card-hd .co{color:#9aa2b1;font-weight:600;}
/* 时间胶囊：卡片里与地点同一行，时间在左 */
.when{font-size:12px;color:var(--blue);background:var(--blue-soft);
  border-radius:7px;padding:2px 9px;font-weight:600;white-space:nowrap;
  font-variant-numeric:tabular-nums;}
.card.past .when{color:var(--grey);background:var(--grey-soft);}
.place{font-size:12.5px;color:var(--ink2);display:inline-flex;align-items:center;gap:4px;}
.place svg{width:12px;height:12px;fill:#a6aebe;flex:0 0 12px;}
.card.past .place{color:#aab1bf;}
.row.when-place{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:6px 0 5px;}
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
  header{padding:22px 20px;}
  .li{flex-wrap:wrap;}
  .li .tcol{flex:1 1 100%;flex-direction:row;align-items:center;gap:8px;}
  .li .t{flex:0 0 auto;padding:4px 12px;}
  .li .vn{padding:0;font-size:12px;}
  .li .st{margin-left:0;}
  .row{flex-direction:column;gap:2px;}
  .tab{padding:9px 15px;font-size:13.5px;}
  .cal-grid{gap:3px;} .cal-navs .cal-ym{min-width:64px;}
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

# 页面内联 SVG 图标（避免外链依赖）
ICON_PIN = ('<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 1.5a4.75 4.75 0 0 0-4.75 4.75c0 '
            '3.4 4.06 8.1 4.23 8.27a.75.75 0 0 0 1.04 0c.17-.17 4.23-4.87 4.23-8.27A4.75 4.75 0 0 0 8 '
            '1.5zm0 6.5a1.75 1.75 0 1 1 0-3.5 1.75 1.75 0 0 1 0 3.5z"/></svg>')
ICON_COIN = ('<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 1a7 7 0 1 0 0 14A7 7 0 0 0 8 1zm'
             '2.9 4.1l-1.9 2.4h1.6v.9H8.55v.8h2.05v.9H8.55V12H7.45v-1.9H5.4v-.9h2.05v-.8H5.4v-.9H7L5.1 '
             '5.1l.8-.6L8 6.8l2.1-2.3.8.6z"/></svg>')
ICON_ARROW = ('<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8.7 2.29a1 1 0 0 0-1.41 1.42L10.59 7H2a1 '
              '1 0 1 0 0 2h8.59l-3.3 3.29a1 1 0 0 0 1.41 1.42l5-5a1 1 0 0 0 0-1.42l-5-5z"/></svg>')
ICON_CAL = ('<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M5 1a1 1 0 0 1 1 1v1h4V2a1 1 0 1 1 2 0v1h.5A2.5 '
            '2.5 0 0 1 15 5.5v8A2.5 2.5 0 0 1 12.5 16h-9A2.5 2.5 0 0 1 1 13.5v-8A2.5 2.5 0 0 1 3.5 3H4V2a1 '
            '1 0 0 1 1-1zM3 7v6.5c0 .28.22.5.5.5h9a.5.5 0 0 0 .5-.5V7H3z"/></svg>')
ICON_CARET = ('<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 10.6 3.6 6.2l1.1-1.1L8 8.4l3.3-3.3 '
              '1.1 1.1z"/></svg>')

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

  // 把标签栏的实际高度写进 CSS 变量，筛选条吸顶时才能严丝合缝地贴在它下面
  var shell=document.querySelector('.tabshell');
  function syncTabH(){
    if(shell) root.style.setProperty('--tab-h', shell.offsetHeight+'px');
  }
  syncTabH();
  window.addEventListener('resize', syncTabH);

  // 兜底：少数移动端浏览器对 position:sticky 支持不佳（手机反馈过「电脑上固定、手机上不固定」）。
  // 滚动时检测标签栏是否真的吸住了：该吸顶却跟着页面滚走，就改用 fixed + 等高占位元素兜底。
  (function(){
    if(!shell) return;
    var ph=document.createElement('div');
    ph.className='tabshell-ph';
    shell.parentNode.insertBefore(ph, shell);
    var stuck=false;
    function stick(){
      stuck=true;
      ph.style.height=shell.offsetHeight+'px';
      shell.classList.add('js-stuck');
      syncTabH();
    }
    function unstick(){
      stuck=false;
      shell.classList.remove('js-stuck');
      ph.style.height='0px';
      syncTabH();
    }
    function check(){
      if(stuck){
        var phTop=ph.getBoundingClientRect().top+window.pageYOffset;
        if(window.pageYOffset<=phTop+1) unstick();
        return;
      }
      // sticky 生效时 top 恒为 0；滚出明显负值说明它没吸住
      if(shell.getBoundingClientRect().top < -8) stick();
    }
    window.addEventListener('scroll', check, {passive:true});
    window.addEventListener('resize', check);
    check();
  })();

  function panelOf(el){
    var p=el;
    while(p && p.classList && !p.classList.contains('panel')) p=p.parentElement;
    return p;
  }

  // 统一的显示计算：日历选了日期就以日期为准，否则按「未过期 / 全部 / 已过期」
  function applyState(panel){
    if(!panel) return;
    var btn=panel.querySelector('[data-filter].on') || panel.querySelector('[data-filter]');
    var f=btn?btn.getAttribute('data-filter'):'active';
    var sel=panel.getAttribute('data-cal-date') || '';
    var any=false;
    [].slice.call(panel.querySelectorAll('[data-status]')).forEach(function(el){
      var st=el.getAttribute('data-status');
      var show;
      if(sel) show = (el.getAttribute('data-date')===sel);
      else show = (f==='all') ? true : (f==='expired') ? (st==='expired') : (st!=='expired');
      el.style.display = show ? '' : 'none';
      if(show) any=true;
    });
    [].slice.call(panel.querySelectorAll('.month-block')).forEach(function(bl){
      var vis=[].slice.call(bl.querySelectorAll('[data-status]'))
               .filter(function(e){return e.style.display!=='none';});
      bl.style.display = vis.length ? '' : 'none';
    });
    // 日历筛选中时状态按钮不可用，避免两个维度互相干扰
    [].slice.call(panel.querySelectorAll('[data-filter]')).forEach(function(b){
      b.classList.toggle('disabled', !!sel);
    });
    var tip=panel.querySelector('.filter-empty');
    if(tip){
      tip.style.display = any ? 'none' : '';
      tip.textContent = sel ? '这一天没有符合条件的场次。' : '当前筛选条件下没有场次。';
    }
    // 实时回写「当前显示 N 场」：总览里一个日期块含多场，相关面板里一张卡片算一家
    var cnt=panel.querySelector('[data-show-count]');
    if(cnt){
      var n=0;
      [].slice.call(panel.querySelectorAll('[data-status]')).forEach(function(el){
        if(el.style.display==='none') return;
        var inner=el.querySelectorAll('.li');
        n += inner.length ? inner.length : 1;
      });
      cnt.textContent = n;
    }
  }

  // 以代码方式切到某个状态筛选（顶部统计卡跳转用）
  function activateFilter(panel, f){
    if(!panel) return;
    var btn=panel.querySelector('[data-filter="'+f+'"]');
    if(!btn) return;
    var group=btn.parentNode;
    [].slice.call(group.querySelectorAll('[data-filter]')).forEach(function(b){
      b.classList.toggle('on', b===btn);
    });
    // 状态筛选与日历日期筛选互斥：跳转时先清掉已选日期，否则日期筛选会压住状态筛选
    panel.removeAttribute('data-cal-date');
    if(panel.__calDraw) panel.__calDraw();
    applyState(panel);
  }

  document.querySelectorAll('[data-filter]').forEach(function(btn){
    btn.addEventListener('click',function(){
      if(btn.classList.contains('disabled')) return;
      var group=btn.parentNode;
      [].slice.call(group.querySelectorAll('[data-filter]')).forEach(function(b){
        b.classList.toggle('on', b===btn);
      });
      applyState(panelOf(group));
    });
  });

  // 顶部统计卡：点哪张就跳到对应的面板与筛选结果
  document.querySelectorAll('[data-goto]').forEach(function(card){
    card.addEventListener('click',function(){
      var g=card.getAttribute('data-goto');
      var panel;
      if(g==='relevant'){
        select(1);
        panel=panels[1];
        activateFilter(panel,'all');   // 「58 家」是全量，故看全部而非仅未过期
      }else{
        select(0);
        panel=panels[0];
        activateFilter(panel,g);
      }
      var bar=panel.querySelector('.bar');
      if(bar) bar.scrollIntoView({behavior:'smooth',block:'start'});
    });
  });

  // 初始状态：默认只显示未过期，无需手动筛选
  panels.forEach(function(panel){
    var def=panel.querySelector('[data-filter].on') || panel.querySelector('[data-filter]');
    if(def) applyState(panel);
  });

  // ---------------- 按日历筛选 ----------------
  var WEEK=['日','一','二','三','四','五','六'];
  function pad(n){ return (n<10?'0':'')+n; }

  function initCal(box){
    var panel=panelOf(box);
    if(!panel) return;
    var grid=box.querySelector('[data-cal-grid]');
    var ymEl=box.querySelector('[data-cal-ym]');
    var selEl=box.querySelector('[data-cal-sel]');
    var clearBtn=box.querySelector('[data-cal-clear]');
    var prev=box.querySelector('[data-cal-prev]');
    var next=box.querySelector('[data-cal-next]');

    // 从已渲染的场次里收集「哪些日期有场次」与当天场次数
    var map={};
    [].slice.call(panel.querySelectorAll('[data-date]')).forEach(function(el){
      var d=el.getAttribute('data-date');
      if(!d) return;
      map[d]=(map[d]||0)+1;
    });
    var keys=Object.keys(map).sort();
    if(!keys.length){ box.style.display='none'; return; }

    var now=new Date();
    var today=now.getFullYear()+'-'+pad(now.getMonth()+1)+'-'+pad(now.getDate());
    var min=keys[0].slice(0,7), max=keys[keys.length-1].slice(0,7);
    var ym=(today.slice(0,7)>=min && today.slice(0,7)<=max) ? today.slice(0,7) : min;

    function label(ds){ return (+ds.slice(5,7))+'月'+(+ds.slice(8,10))+'日'; }

    function shift(n){
      var y=+ym.slice(0,4), mo=+ym.slice(5,7)+n;
      if(mo<1){ mo=12; y--; }
      if(mo>12){ mo=1; y++; }
      var ny=y+'-'+pad(mo);
      if(ny<min || ny>max) return;
      ym=ny; draw();
    }

    function draw(){
      var y=+ym.slice(0,4), mo=+ym.slice(5,7);
      var first=new Date(y, mo-1, 1).getDay();
      var days=new Date(y, mo, 0).getDate();
      var sel=panel.getAttribute('data-cal-date') || '';
      var out=[];
      for(var w=0;w<7;w++) out.push('<div class="cal-w">'+WEEK[w]+'</div>');
      for(var b=0;b<first;b++) out.push('<div class="cal-d blank"></div>');
      for(var d=1;d<=days;d++){
        var ds=y+'-'+pad(mo)+'-'+pad(d);
        var n=map[ds]||0;
        var cls='cal-d'+(n?' has':'')+(ds===sel?' sel':'')+(ds===today?' today':'');
        var inner=d+(n>1?'<i class="cal-n">'+n+'</i>':'');
        out.push(n
          ? '<div class="'+cls+'" data-day="'+ds+'" title="'+label(ds)+'　'+n+' 场招聘会">'+inner+'</div>'
          : '<div class="'+cls+'">'+inner+'</div>');
      }
      grid.innerHTML=out.join('');
      ymEl.textContent=y+'年'+mo+'月';
      prev.disabled = (ym<=min);
      next.disabled = (ym>=max);
      if(sel){
        selEl.textContent='只看 '+label(sel);
        selEl.classList.add('on');
        clearBtn.hidden=false;
      }else{
        selEl.textContent='全部日期';
        selEl.classList.remove('on');
        clearBtn.hidden=true;
      }
    }

    grid.addEventListener('click',function(e){
      var t=e.target.closest ? e.target.closest('[data-day]') : null;
      if(!t) return;
      var ds=t.getAttribute('data-day');
      if((panel.getAttribute('data-cal-date')||'')===ds) panel.removeAttribute('data-cal-date');
      else panel.setAttribute('data-cal-date', ds);
      draw(); applyState(panel);
    });
    prev.addEventListener('click',function(){ shift(-1); });
    next.addEventListener('click',function(){ shift(1); });
    clearBtn.addEventListener('click',function(){
      panel.removeAttribute('data-cal-date'); draw(); applyState(panel);
    });

    // 默认收起，点标题栏展开/收起；导航与清除按钮的点击不触发折叠
    var hd=box.querySelector('[data-cal-toggle]');
    function setCollapsed(c){
      box.classList.toggle('collapsed', c);
      hd.setAttribute('aria-expanded', c?'false':'true');
    }
    hd.addEventListener('click',function(){
      setCollapsed(!box.classList.contains('collapsed'));
    });
    hd.addEventListener('keydown',function(e){
      if(e.key==='Enter' || e.key===' '){
        e.preventDefault();
        setCollapsed(!box.classList.contains('collapsed'));
      }
    });
    [prev,next,clearBtn].forEach(function(b){
      b.addEventListener('click',function(e){ e.stopPropagation(); });
    });

    panel.__calDraw=draw;   // 暴露给统计卡跳转，便于同步「只看某天」的显示状态
    draw();
  }

  document.querySelectorAll('[data-cal]').forEach(initCal);
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
_NUM_UNIT = re.compile(r"\d+\s*[-~—–－～]?\s*\d*\s*(?:万\s*/?\s*年|万元|万|元\s*/\s*月|元\s*/\s*年|[kKwW])")
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
                out = [clean_leading_marks(v) for v in vals[:3]]
                return " / ".join(x for x in out if x)

    for raw in lines:
        # 先剥掉行首序号/符号，再定位薪资关键词，避免窗口切在「1.1」中间留下半截序号
        line = clean_leading_marks(raw.strip(" ●·|\t").strip())
        if len(line) < 6:
            continue
        kw = _SALARY_KW.search(line)
        if not kw or not _NUM_UNIT.search(line):
            continue
        seg = re.split(r"[。；;]", line)[0].strip(" ，,、")
        # 从薪资关键词处起截取，去掉「实行试用期制度，试用期6个月，」这类铺垫前缀
        start = kw.start()
        if _NUM_UNIT.search(seg[start:]) and len(seg[start:]) >= 8:
            # 只保留紧邻关键词的中文定语（「综合」「转正」「税前」），最多 6 字；
            # 标点、序号、上一句的尾巴一律丢掉
            head = seg[max(0, start - 6):start]
            m = re.search(r"[\u4e00-\u9fff]+$", head)
            seg = (m.group(0) if m else "") + seg[start:]
        if len(seg) > 60:
            seg = seg[:60].rstrip(" ，,、") + "…"
        if not _NUM_UNIT.search(seg):
            continue  # 「薪酬待遇优厚」这类空话，数字在别的分句里，宁缺毋滥
        seg = clean_leading_marks(seg)
        if seg:
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
    def _filter_bar(hint: str, unit: str = "场") -> str:
        """筛选条。默认选中「未过期」，进页面即可直接看到有效场次；右侧实时显示当前条数。"""
        return (
            '<div class="bar">'
            '<button class="fbtn on" data-filter="active">未过期</button>'
            '<button class="fbtn" data-filter="all">全部</button>'
            '<button class="fbtn" data-filter="expired">已过期</button>'
            f'<span class="fhint">当前显示 <b data-show-count>0</b> {esc(unit)}'
            f"　·　{esc(hint)}</span>"
            "</div>"
        )

    @staticmethod
    def _calendar() -> str:
        """
        按日历筛选组件（骨架，日期格由页面内的 JS 依实际场次渲染）。
        默认收起，点标题栏展开；有场次的日期带红点，点击即只看当天；月份可左右翻页。
        """
        return (
            '<div class="calfilter collapsed" data-cal>'
            '<div class="cal-hd" data-cal-toggle role="button" tabindex="0" aria-expanded="false">'
            f'<span class="cal-ic">{ICON_CAL}</span>'
            '<span class="cal-tt">按日历筛选</span>'
            f'<span class="cal-caret">{ICON_CARET}</span>'
            '<span class="cal-sel" data-cal-sel>全部日期</span>'
            '<button type="button" class="cal-clear" data-cal-clear hidden>清除</button>'
            '<span class="cal-navs">'
            '<button type="button" class="cal-nav" data-cal-prev title="上个月">‹</button>'
            '<b class="cal-ym" data-cal-ym></b>'
            '<button type="button" class="cal-nav" data-cal-next title="下个月">›</button>'
            "</span>"
            "</div>"
            '<div class="cal-body">'
            '<div class="cal-grid" data-cal-grid></div>'
            '<div class="cal-tip">点带 <b>●</b> 的日期，只看当天场次；再点一次取消，'
            "红点数字为当天场次数。</div>"
            "</div>"
            "</div>"
        )

    def _overview(self, fairs: List[Dict[str, Any]], months: List[str]) -> str:
        buckets = self.group_by_month(fairs)
        parts: List[str] = []
        parts.append(self._filter_bar("默认只看未过期，可切换「全部」或「已过期」"))
        parts.append(self._calendar())
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
                        f'<div class="{cls}" data-status="{esc(rows[0]["status"])}" '
                        f'data-date="{esc(day)}">'
                        f'<div class="day-hd"><span class="d">{esc(_day_label(day))}</span>'
                        f'<span class="w">{esc(rows[0].get("weekday",""))}</span>'
                        f'<span class="cnt">{len(rows)} 场 · {esc(rows[0]["status_label"])}</span></div>'
                    )
                    for r in rows:
                        link = self.config["site"]["detail_url"].format(id=r["id"])
                        salary = extract_salary(r.get("description", ""))
                        # 单位名与简章按钮并列一行；薪资较长，单独放在单位名下方一行
                        pay_html = (f'<span class="pay">{ICON_COIN}{esc(salary)}</span>'
                                    if salary else "")
                        parts.append(
                            '<div class="li">'
                            '<div class="tcol">'
                            f'<div class="t">{esc(r["time"])}</div>'
                            f'<div class="vn">{ICON_PIN}{esc(r["venue"])}</div>'
                            "</div>"
                            '<div class="bd">'
                            f'<div class="co">{esc(r["theme"])}</div>'
                            '<div class="lk">'
                            f'<a class="brief" href="{esc(link)}" target="_blank" rel="noopener">'
                            f"查看官方简章{ICON_ARROW}</a></div>"
                            f"{pay_html}"
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

        parts.append(self._filter_bar("默认只看未过期；已过期但仍想参考的可切换「全部」", unit="家"))
        parts.append(self._calendar())
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
                salary = extract_salary(s.get("description", ""))
                pay_html = (f'<span class="pay">{ICON_COIN}{esc(salary)}</span>'
                            if salary else "")
                link = self.config["site"]["detail_url"].format(id=s["id"])
                parts.append(f'<div class="{card_cls}" data-status="{esc(s["status"])}" '
                             f'data-date="{esc(s["date"])}">')
                # 单位名与查看简章一行；薪资、时间+地点各占一行
                parts.append('<div class="card-hd">'
                             f'<span class="rank {cls}">{idx}</span>'
                             f'<span class="co">{esc(s["theme"])}</span>'
                             f'<a class="brief" href="{esc(link)}" target="_blank" rel="noopener">'
                             f"查看官方简章{ICON_ARROW}</a>"
                             "</div>")
                if pay_html:
                    parts.append(pay_html)

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
                # 时间在左、地点在右，同一行
                parts.append('<div class="row when-place">'
                             f'<span class="when">{esc(_day_label(s["date"]))} {esc(s["time"])}</span>'
                             f'<span class="place">{ICON_PIN}{esc(s["venue"])}</span>'
                             "</div>")

                ev = "".join(f"<div>· {esc(x)}</div>" for x in s["major_evidence"][:2])
                if ev:
                    parts.append(f'<div class="ev"><span class="t">专业依据</span>{ev}</div>')
                evc = "".join(f"<div>· {esc(x)}</div>" for x in s["city_evidence"][:2])
                if evc:
                    parts.append(f'<div class="ev"><span class="t">城市依据</span>{evc}</div>')
                if s["note"]:
                    parts.append(f'<div class="ev warn"><span class="t">提示</span>{esc(s["note"])}</div>')

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
            f"数据更新 <code>{esc(now)}</code>　·　每日 <code>{esc(self.daily_at)}</code> 自动更新"
            + (f"　·　作者 <code>{esc(author)}</code>" if author else "") + "<br>"
            "来源：<a href=\"" + esc(self.config["site"]["calendar_url"]) +
            "\" target=\"_blank\" rel=\"noopener\">ahut.ahbys.com 招聘日历</a></div></header>"
            '<div class="stats">'
            f'<button type="button" class="stat hl" data-goto="all" title="查看区间内全部 {total} 场">'
            f'<span class="n">{total}<small>场</small></span>'
            '<span class="l">区间内总场次<span class="go">点击查看 ›</span></span></button>'
            f'<button type="button" class="stat ok" data-goto="active" title="查看未过期场次">'
            f'<span class="n">{upcoming}<small>场</small></span>'
            '<span class="l">未过期<span class="go">点击查看 ›</span></span></button>'
            f'<button type="button" class="stat ex" data-goto="expired" title="查看已过期场次">'
            f'<span class="n">{expired}<small>场</small></span>'
            '<span class="l">已过期<span class="go">点击查看 ›</span></span></button>'
            f'<button type="button" class="stat" data-goto="relevant" title="查看与我相关的单位">'
            f'<span class="n">{matched}<small>家</small></span>'
            '<span class="l">与我相关<span class="go">点击查看 ›</span></span></button>'
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
