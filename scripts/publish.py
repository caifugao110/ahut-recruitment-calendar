#!/usr/bin/env python3
"""
publish.py —— 把 site/ 目录发布到码上架（mashangjia）。

说明：
  - 只是官方 CLI 的一层薄封装，不自己拼 HTTP 请求、不把凭据写进任何项目文件。
  - 全局有 `mashangjia` 就直接用，没有就用 `npx --yes mashangjia`，不改动系统环境。

两种发布方式：
  A. 指定站点（推荐，config/publish.json 的 "site" 或 --site 参数）
     `mashangjia deploy <site-id|slug> <zip>` —— 定向更新已存在的站点，
     地址固定不变。本项目用这个来更新 ahut-recruitment-calendar。
  B. 按目录（--site 为空时的兜底）
     `mashangjia deploy <dir> --mode <mode>` —— 注意：即使目录名相同，它也可能
     **新建站点**而不是更新旧站点，所以绑定自定义域名后请务必用方式 A。

模式（仅方式 B 生效）：auto / anonymous / account

凭据（三选一，优先级从高到低）：
  1. 环境变量 MASHANGJIA_LOGIN_TOKEN —— CI 用这个。本脚本会先执行
     `mashangjia login --token <token>` 再部署，Token 只活在进程环境里。
  2. 本机已登录 —— 本地执行过一次 `mashangjia login --token <token>` 后即可反复使用。
  3. 都没有 —— 只能用 anonymous 模式。

注意：CLI 另有 MASHANGJIA_DEPLOY_TOKEN（部署口令），与"登录 Token"不是同一种东西，
      格式校验不同；控制台「API Token」页面生成的是登录 Token，请走上面的第 1 种方式。

用法：
    python scripts/publish.py                       # 按 config/publish.json 的 site 定向更新
    python scripts/publish.py --site <slug|id>      # 指定站点
    python scripts/publish.py --mode anonymous      # 按目录匿名发布
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def resolve_cli() -> list:
    """返回可用的 CLI 命令前缀（用绝对路径，避免 PATH 解析问题）。"""
    exe = shutil.which("mashangjia")
    if exe:
        return [exe]
    npx = shutil.which("npx")
    if npx:
        return [npx, "--yes", "mashangjia"]
    raise SystemExit("找不到 mashangjia 或 npx，请先安装 Node.js 或 npm i -g mashangjia")


def run_cli(cmd: list, **kw) -> subprocess.CompletedProcess:
    """
    执行 CLI。Windows 上 npx 是 .cmd，CreateProcess 无法直接执行，
    必须走 shell=True；Linux/macOS 保持列表形式以免 shell 注入。
    """
    return subprocess.run(cmd, shell=(os.name == "nt"), **kw)


def make_zip(src_dir: Path, zip_path: Path) -> None:
    """把目录打包成 zip，条目相对根目录，index.html 位于顶层。"""
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(src_dir.rglob("*")):
            if f.is_file():
                z.write(f, f.relative_to(src_dir).as_posix())


def parse_result(stdout: str):
    """从 CLI 输出里取唯一的结果 JSON 对象。"""
    for line in (stdout or "").splitlines():
        line = line.strip()
        if line.startswith("{") and '"command"' in line:
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="发布 site/ 到码上架")
    parser.add_argument("--mode", choices=["auto", "anonymous", "account"], default=None)
    parser.add_argument("--dir", default=None, help="待发布目录，默认 site/")
    parser.add_argument("--site", default=None,
                        help="目标站点 slug 或 id，定向更新（推荐，地址固定不变）")
    args = parser.parse_args()

    publish_cfg = {}
    cfg_path = ROOT / "config" / "publish.json"
    if cfg_path.exists():
        publish_cfg = json.loads(cfg_path.read_text(encoding="utf-8"))

    mode = args.mode or publish_cfg.get("mode", "auto")
    target = args.dir or publish_cfg.get("project_dir", "site")
    site = args.site or publish_cfg.get("site", "")
    project_dir = ROOT / target

    if not (project_dir / "index.html").exists():
        raise SystemExit(f"{project_dir} 下没有 index.html，请先运行 scripts/daily_update.py")

    cli = resolve_cli()

    # CI 场景：先用登录 Token 登录，再部署。Token 只在进程环境中，不落盘。
    login_token = os.environ.get("MASHANGJIA_LOGIN_TOKEN", "").strip()
    if login_token:
        print("检测到 MASHANGJIA_LOGIN_TOKEN，先登录 ...")
        r = run_cli([*cli, "login", "--token", login_token, "--json"],
                    cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8")
        ok = bool((parse_result(r.stdout) or {}).get("ok"))
        if not ok:
            print("登录失败，终止发布：", file=sys.stderr)
            sys.stderr.write((r.stdout or "")[-800:] + (r.stderr or "")[-800:])
            return 1
        print("登录成功")
        if mode == "auto":
            mode = "account"

    if site:
        # 方式 A：定向更新指定站点
        tmp_dir = tempfile.mkdtemp(prefix="msj-")
        zip_path = Path(tmp_dir) / f"{project_dir.name}.zip"
        make_zip(project_dir, zip_path)
        print(f"打包 {zip_path} ({zip_path.stat().st_size / 1024:.1f} KB)")
        cmd = [*cli, "deploy", str(site), str(zip_path), "--json"]
    else:
        # 方式 B：按目录（可能产生新站点）
        cmd = [*cli, "deploy", str(project_dir), "--mode", mode, "--harness", "workbuddy", "--json"]

    print(f"$ {' '.join(str(c) for c in cmd)}")
    proc = run_cli(cmd, cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8")

    if proc.stderr:
        sys.stderr.write(proc.stderr[-2000:])

    result = parse_result(proc.stdout)
    if result is None:
        print("未能从 CLI 输出中解析到结果 JSON。", file=sys.stderr)
        return 1

    if site:
        if result.get("ok") is False:
            print("发布未成功：", json.dumps(result, ensure_ascii=False)[:1500], file=sys.stderr)
            return 1
        print(f"发布成功 → 站点 {site}")
        print(json.dumps(result, ensure_ascii=False)[:1200])
        return 0

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
