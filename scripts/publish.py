#!/usr/bin/env python3
"""
publish.py —— 把 site/ 目录发布到码上架（mashangjia）。

说明：
  - 只是官方 CLI 的一层薄封装，不自己拼 HTTP 请求、不处理任何凭据。
  - 全局有 `mashangjia` 就直接用，没有就用 `npx --yes mashangjia`，不改动系统环境。
  - 模式由 config/publish.json 控制：
      "auto"      默认。有账号凭据走账号，没有则匿名
      "anonymous" 强制匿名（临时站，约 24 小时后预览过期，但地址固定不变）
      "account"   强制账号（需要 mashangjia login，失败不会回退匿名）
  - 匿名模式下每次部署都是新项目、新地址；想让"同一个地址"每天更新，
    请先 `mashangjia login --token <token>` 或认领已有站点，再用账号模式部署。

用法：
    python scripts/publish.py
    python scripts/publish.py --mode anonymous
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def resolve_cli() -> list:
    """返回可用的 CLI 命令前缀。"""
    if shutil.which("mashangjia"):
        return ["mashangjia"]
    if shutil.which("npx"):
        return ["npx", "--yes", "mashangjia"]
    raise SystemExit("找不到 mashangjia 或 npx，请先安装 Node.js 或 npm i -g mashangjia")


def main() -> int:
    parser = argparse.ArgumentParser(description="发布 site/ 到码上架")
    parser.add_argument("--mode", choices=["auto", "anonymous", "account"], default=None)
    parser.add_argument("--dir", default=None, help="待发布目录，默认 site/")
    args = parser.parse_args()

    publish_cfg = {}
    cfg_path = ROOT / "config" / "publish.json"
    if cfg_path.exists():
        publish_cfg = json.loads(cfg_path.read_text(encoding="utf-8"))

    mode = args.mode or publish_cfg.get("mode", "auto")
    target = args.dir or publish_cfg.get("project_dir", "site")
    project_dir = ROOT / target

    if not (project_dir / "index.html").exists():
        raise SystemExit(f"{project_dir} 下没有 index.html，请先运行 scripts/daily_update.py")

    cli = resolve_cli()
    cmd = [*cli, "deploy", str(project_dir), "--mode", mode, "--harness", "workbuddy", "--json"]

    print(f"$ {' '.join(cmd)}")
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8")

    # stdout 里应只有一个 JSON 对象
    result = None
    for line in (proc.stdout or "").splitlines():
        line = line.strip()
        if line.startswith("{") and '"command"' in line:
            try:
                result = json.loads(line)
            except json.JSONDecodeError:
                pass

    if proc.stderr:
        sys.stderr.write(proc.stderr[-2000:])

    if result is None:
        print("未能从 CLI 输出中解析到结果 JSON。", file=sys.stderr)
        return 1

    if result.get("ok") and result.get("verified") and result.get("url"):
        print(f"发布成功：{result['url']}")
        print(f"模式：{result.get('mode')}　状态：{result.get('deployment', {}).get('status')}")
        if result.get("mode") == "anonymous":
            print(f"临时站到期：{result.get('expires_at')}　可认领至：{result.get('claim_expires_at')}")
        return 0

    print("发布未成功：", json.dumps(result, ensure_ascii=False)[:1500], file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
