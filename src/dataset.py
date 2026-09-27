"""
dataset.py —— 招聘会数据集（data/dataset.json）的读取 / 合并 / 清洗 / 序列化。

本地脚本（scripts/daily_update.py）与腾讯云函数（scf/index.py）共用本模块，
保证两处对 dataset.json 的处理语义完全一致 —— 否则抓取在云函数、生成本地跑，
两边各写一份合并逻辑迟早会漂移，导致数据来回覆盖。

数据结构：dataset.json 是一个数组，加载后在内存里转成 {id: 条目} 便于按 ID 增量合并。
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List

from src.scraper import normalize_time


def load_dataset(path) -> Dict[str, Dict[str, Any]]:
    """读取 dataset.json，返回 {id: 条目}。文件不存在或损坏时返回空字典而不是抛错。"""
    path = Path(path)
    if not path.exists():
        return {}
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
        return {x["id"]: x for x in rows}
    except (json.JSONDecodeError, KeyError, TypeError):
        return {}


def merge_dataset(dataset: Dict[str, Dict[str, Any]],
                  fresh: Iterable[Dict[str, Any]]) -> int:
    """按 ID 合并新抓到的数据；返回新增条数。已存在的条目用最新内容覆盖。"""
    added = 0
    for item in fresh:
        rid = item["id"]
        if rid not in dataset:
            added += 1
        dataset[rid] = item
    return added


def in_range(date_str: str, start: dt.date, end: dt.date) -> bool:
    """条目的 date 是否落在 [start, end] 内。date 缺失或格式不对视为不在区间内。"""
    try:
        d = dt.date.fromisoformat(str(date_str)[:10])
    except (ValueError, TypeError):
        return False
    return start <= d <= end


def normalize_dataset_times(dataset: Dict[str, Dict[str, Any]],
                            start: dt.date, end: dt.date) -> None:
    """把区间内条目的 time 清洗成统一的 HH:MM-HH:MM。

    历史条目可能还留着 "2026年10月8日18:30-20:00" 这类旧写法，这里顺手收敛掉。
    只处理区间内的条目，区间外的老数据不动。
    """
    for item in dataset.values():
        if in_range(item.get("date", ""), start, end):
            item["time"] = normalize_time(item.get("time", ""))


def sorted_items(dataset: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """按 日期 → 时间 → 主题 排序，用于输出稳定、diff 更小的 dataset.json。"""
    return sorted(dataset.values(),
                  key=lambda x: (x.get("date", ""), x.get("time", ""), x.get("theme", "")))


def dumps_dataset(dataset: Dict[str, Dict[str, Any]], sort: bool = False) -> str:
    """序列化为 dataset.json 的文本内容。sort=True 时按日期排序输出。"""
    rows = sorted_items(dataset) if sort else list(dataset.values())
    return json.dumps(rows, ensure_ascii=False, indent=2)


def save_dataset(path, dataset: Dict[str, Dict[str, Any]], sort: bool = False) -> None:
    """写入 dataset.json（与 dumps_dataset 使用完全相同的序列化方式）。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dumps_dataset(dataset, sort=sort), encoding="utf-8")
