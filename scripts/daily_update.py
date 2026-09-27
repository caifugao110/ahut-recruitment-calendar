#!/usr/bin/env python3
"""
daily_update.py —— 每日更新入口（建议由定时任务在 config/config.json 设定的时间调用，默认 02:00）。

流程：
    1. 注入 .env（本地凭据/地址覆盖，没有则跳过），读取唯一配置文件 config/config.json
       （数据源 / 个人画像 profile / 发布都在里面）
    2. 按 config.json -> profile.fair_range 设定的区间抓取全部招聘会（含招聘简章全文）
    3. 写入当日快照 data/snapshot/YYYY-MM-DD.json，并合并进 data/dataset.json
       —— 已结束的场次不会被删除，只是被标记为"已过期"
    4. 按画像打分匹配
    5. 重新生成 site/index.html

用法：
    python scripts/daily_update.py                 # 正常更新
    python scripts/daily_update.py --no-detail     # 跳过简章抓取（快，仅列表）
    python scripts/daily_update.py --rebuild-cache # 忽略本地缓存，重新抓全部简章
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import traceback
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.dataset import (  # noqa: E402
    in_range, load_dataset, merge_dataset, normalize_dataset_times, save_dataset,
)
from src.envfile import apply_env_overrides, load_env_file  # noqa: E402
from src.generate import Generator  # noqa: E402
from src.matcher import Matcher, mark_status  # noqa: E402
from src.scraper import Scraper  # noqa: E402
from src.timeutil import cn_today  # noqa: E402


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main() -> int:
    parser = argparse.ArgumentParser(description="每日抓取并重建招聘会站点")
    parser.add_argument("--no-detail", action="store_true", help="跳过招聘简章抓取")
    parser.add_argument("--rebuild-cache", action="store_true", help="忽略本地详情缓存")
    parser.add_argument("--from-dataset", action="store_true",
                        help="跳过抓取，直接用已有的 data/dataset.json 重建页面（调参时用）")
    parser.add_argument("--config", default="config/config.json",
                        help="唯一配置文件路径（数据源 / profile 画像 / publish 发布）")
    parser.add_argument("--env-file", default=".env",
                        help="本地环境变量文件（不存在则忽略；真实环境变量优先于它）")
    args = parser.parse_args()

    # 先注入 .env（本地凭据/地址覆盖），再读配置；CI 无 .env 时此步静默跳过
    load_env_file(ROOT / args.env_file)

    config = load_json(ROOT / args.config)
    apply_env_overrides(config)
    # 个人画像（时间区间 / 定时 / 专业 / 城市 / 权重）是统一配置里的 profile 段
    profile = config.get("profile") or {}

    fair_range = profile.get("fair_range", {})
    try:
        start = dt.date.fromisoformat(fair_range["start"])
        end = dt.date.fromisoformat(fair_range["end"])
    except (KeyError, TypeError) as exc:
        raise SystemExit(
            "config/config.json 缺少 profile.fair_range.start / profile.fair_range.end，"
            "请参照文件内说明补全招聘会时间区间。"
        ) from exc
    data_dir = ROOT / config["output"]["data_dir"]

    scraper = Scraper(config, data_dir)
    if args.rebuild_cache:
        scraper.use_cache = False

    dataset_path = data_dir / "dataset.json"
    dataset: Dict[str, Dict[str, Any]] = {}

    if args.from_dataset:
        print("[1/5] 跳过抓取，直接读取已有数据集 ...")
        dataset = load_dataset(dataset_path)
        print(f"      数据集共 {len(dataset)} 场")
        added = 0
    else:
        print(f"[1/5] 抓取 {start} ~ {end} 的招聘会列表 ...")
        fairs = scraper.collect(start, end, with_detail=not args.no_detail)
        print(f"      本次抓到 {len(fairs)} 场")

        snapshot_dir = ROOT / config["output"]["data_dir"] / "snapshot"
        save_json(snapshot_dir / f"{cn_today().isoformat()}.json", fairs)

        dataset = load_dataset(dataset_path)
        added = merge_dataset(dataset, fairs)

    # 历史条目可能还留着 "2026年10月8日18:30-20:00" 这类旧写法，统一清洗成 "18:30-20:00"
    normalize_dataset_times(dataset, start, end)
    all_fairs = [v for v in dataset.values() if in_range(v.get("date", ""), start, end)]
    all_fairs.sort(key=lambda x: (x["date"], x["time"], x["theme"]))
    save_dataset(dataset_path, dataset)
    print(f"[2/5] 合并数据集：新增 {added} 场，区间内累计 {len(all_fairs)} 场")

    print("[3/5] 标记过期状态 ...")
    today = cn_today()
    fairs_marked = mark_status(all_fairs, today)
    print(f"      未过期 {sum(1 for f in fairs_marked if f['status'] != 'expired')} 场，"
          f"已过期 {sum(1 for f in fairs_marked if f['status'] == 'expired')} 场")

    print("[4/5] 按画像匹配打分 ...")
    matcher = Matcher(profile)
    scored = matcher.match_all(fairs_marked)
    matched = sum(1 for s in scored if s["tier"] > 0)
    print(f"      匹配到 {matched} 家（强相关 {sum(1 for s in scored if s['tier'] == 1)} 家）")

    months = []
    cur = dt.date(start.year, start.month, 1)
    while cur <= end:
        months.append(cur.strftime("%Y-%m"))
        cur = dt.date(cur.year + (cur.month // 12), (cur.month % 12) + 1, 1)

    print("[5/5] 生成静态站点 ...")
    gen = Generator(config, profile)
    out = gen.build(fairs_marked, scored, months, today)
    print(f"      已生成 {out}  ({out.stat().st_size / 1024:.1f} KB)")
    print("完成 ✅")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        sys.exit(1)
