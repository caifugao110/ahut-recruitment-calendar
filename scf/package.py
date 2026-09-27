#!/usr/bin/env python3
"""
scf/package.py —— 把云函数打成可直接上传到腾讯云 SCF 的 zip。

用法：
    python scf/package.py                 # 输出到 scf/dist/
    python scf/package.py --out D:/tmp    # 指定输出目录
    python scf/package.py --list          # 打完顺便列出 zip 内容

打包内容（云函数运行只需要这些，全标准库无第三方依赖）：
    index.py            <- scf/index.py（SCF 的「执行入口」填 index.main_handler）
    src/*.py            抓取 / 匹配 / 生成 / 数据集模块
    config/config.json  唯一配置文件
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "scf" / "dist"
SKIP_DIRS = {"__pycache__", ".git", ".workbuddy", ".idea", ".vscode"}


def add_py_tree(zf: zipfile.ZipFile, src_dir: Path, arc_dir: str) -> int:
    """把 src_dir 下的 .py 写进 zip 的 arc_dir/，跳过缓存目录。返回文件数。"""
    count = 0
    for p in sorted(Path(src_dir).rglob("*.py")):
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        zf.write(p, f"{arc_dir}/{p.relative_to(src_dir).as_posix()}")
        count += 1
    return count


def build(out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    zip_path = out_dir / f"ahut-scf-{stamp}.zip"

    index_src = ROOT / "scf" / "index.py"
    if not index_src.exists():
        raise SystemExit(f"找不到云函数入口：{index_src}")
    config_src = ROOT / "config" / "config.json"
    if not config_src.exists():
        raise SystemExit(f"找不到配置文件：{config_src}")

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(index_src, "index.py")
        n_src = add_py_tree(zf, ROOT / "src", "src")
        zf.write(config_src, "config/config.json")

    print(f"✅ 已打包：{zip_path}  ({zip_path.stat().st_size / 1024:.1f} KB)")
    print(f"   index.py + src/ 下 {n_src} 个模块 + config/config.json")
    return zip_path


def main() -> int:
    parser = argparse.ArgumentParser(description="打包腾讯云函数")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="输出目录（默认 scf/dist）")
    parser.add_argument("--list", action="store_true", help="打完顺便列出 zip 内容")
    args = parser.parse_args()

    zip_path = build(Path(args.out))
    if args.list:
        with zipfile.ZipFile(zip_path) as zf:
            for name in zf.namelist():
                print("   -", name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
