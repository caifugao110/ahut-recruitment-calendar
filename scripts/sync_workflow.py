#!/usr/bin/env python3
"""
sync_workflow.py —— 把 config/config.json 里的「自动更新时间」同步到 GitHub Actions。

GitHub Actions 的 on.schedule.cron 只认写死在 .github/workflows/daily.yml 里的
UTC cron 表达式，不能直接读取 JSON 配置，所以用本脚本做一次换算与回填：

    config/config.json -> profile.schedule.daily_at   （北京时间，UTC+8）
        ==> .github/workflows/daily.yml -> - cron: "M H * * *"  （UTC）

中国无夏令时，Asia/Shanghai 固定为 UTC+8。

用法：
    python scripts/sync_workflow.py           # 换算并回填 daily.yml（有改动才写文件）
    python scripts/sync_workflow.py --check   # 只检查不同步；CI 用它在配置漂移时报错提醒

自建服务器 cron / Windows 任务计划程序不走 GitHub Actions，请直接按 config.json
里的 profile.schedule.daily_at（北京时间）设置，无需运行本脚本。
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 只替换「值」，不碰缩进与行尾，保证 diff 最小
CRON_RE = re.compile(r'^(?P<prefix>\s*-\s*cron:\s*)"(?P<expr>[^"]*)"(?P<suffix>.*)$',
                     re.MULTILINE)
COMMENT_RE = re.compile(r"^(?P<indent>\s*)# UTC .*北京时间.*$", re.MULTILINE)

BEIJING_OFFSET_MINUTES = 8 * 60


def load_schedule(config_path: Path) -> str:
    """读取并校验 config.json -> profile.schedule.daily_at，返回 'HH:MM'。"""
    config = json.loads(config_path.read_text(encoding="utf-8"))
    profile = config.get("profile") or {}
    schedule = profile.get("schedule") or {}
    daily_at = schedule.get("daily_at", "")
    timezone = schedule.get("timezone", "Asia/Shanghai")
    if timezone != "Asia/Shanghai":
        raise SystemExit(
            f"暂只支持北京时间（Asia/Shanghai，UTC+8），当前配置为 {timezone!r}。"
            "中国境内无夏令时，直接用 Asia/Shanghai 即可。"
        )
    try:
        t = dt.datetime.strptime(daily_at, "%H:%M")
    except (ValueError, TypeError) as exc:
        raise SystemExit(
            f"config.json -> profile.schedule.daily_at 必须是 24 小时制 'HH:MM' 格式，"
            f"当前为 {daily_at!r}。"
        ) from exc
    return f"{t.hour:02d}:{t.minute:02d}"


def to_utc_cron(daily_at: str) -> tuple[str, str]:
    """北京时间 'HH:MM' -> (UTC cron 表达式 'M H * * *', 说明注释)。"""
    bj_h, bj_m = (int(x) for x in daily_at.split(":"))
    bj_total = bj_h * 60 + bj_m
    utc_total = (bj_total - BEIJING_OFFSET_MINUTES) % (24 * 60)
    utc_h, utc_m = divmod(utc_total, 60)

    # UTC 时刻加 8 小时后是否跨入北京日期的次日
    next_day = utc_total + BEIJING_OFFSET_MINUTES >= 24 * 60
    day_word = "次日" if next_day else "当日"
    comment = (f"# UTC {utc_h:02d}:{utc_m:02d} = 北京时间{day_word} "
               f"{bj_h:02d}:{bj_m:02d}（由 config/config.json -> profile.schedule 生成，"
               f"改时间后运行 python scripts/sync_workflow.py）")
    return f"{utc_m} {utc_h} * * *", comment


def render_workflow(text: str, cron_expr: str, comment: str) -> str:
    """把 daily.yml 中的 cron 行与说明注释替换为配置推导值。"""
    if not CRON_RE.search(text):
        raise SystemExit("在 workflow 文件里找不到 `- cron: \"...\"` 行，已中止。")
    if not COMMENT_RE.search(text):
        raise SystemExit("在 workflow 文件里找不到 `# UTC ... 北京时间...` 注释行，已中止。")

    def _cron_sub(m: re.Match) -> str:
        return f'{m.group("prefix")}"{cron_expr}"{m.group("suffix")}'

    text = CRON_RE.sub(_cron_sub, text, count=1)
    text = COMMENT_RE.sub(lambda m: m.group("indent") + comment, text, count=1)
    return text


def main() -> int:
    parser = argparse.ArgumentParser(description="同步 config.json 的自动更新时间到 GitHub Actions")
    parser.add_argument("--config", default="config/config.json")
    parser.add_argument("--workflow", default=".github/workflows/daily.yml")
    parser.add_argument("--check", action="store_true",
                        help="只检查是否同步，不写文件（CI 用）")
    args = parser.parse_args()

    config_path = ROOT / args.config
    workflow_path = ROOT / args.workflow
    if not config_path.exists():
        raise SystemExit(f"找不到配置文件：{config_path}")
    if not workflow_path.exists():
        raise SystemExit(f"找不到 workflow 文件：{workflow_path}")

    daily_at = load_schedule(config_path)
    cron_expr, comment = to_utc_cron(daily_at)

    # 用字节往返，避免 Windows 上把 LF 改写成 CRLF
    raw = workflow_path.read_bytes().decode("utf-8")
    expected = render_workflow(raw, cron_expr, comment)

    current = CRON_RE.search(raw)
    current_expr = current.group("expr") if current else "(未找到)"

    if raw == expected:
        print(f"✅ workflow 定时已是最新：北京时间每日 {daily_at}（cron: {current_expr}，UTC）")
        return 0

    if args.check:
        print("❌ workflow 定时与 config/config.json 不一致：", file=sys.stderr)
        print(f"   config.json -> profile.schedule.daily_at = 北京时间 {daily_at}", file=sys.stderr)
        print(f"   应为 UTC cron：\"{cron_expr}\"", file=sys.stderr)
        print(f"   daily.yml 当前：\"{current_expr}\"", file=sys.stderr)
        print("   请在本地运行 `python scripts/sync_workflow.py` 后提交 daily.yml。",
              file=sys.stderr)
        return 1

    workflow_path.write_bytes(expected.encode("utf-8"))
    print(f"✅ 已把每日自动更新时间写入 {args.workflow}")
    print(f"   北京时间 {daily_at}  →  UTC cron \"{cron_expr}\"")
    print("   请提交 daily.yml，新的定时即对 GitHub Actions 生效。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
