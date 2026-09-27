#!/usr/bin/env python3
"""
publish.py —— 把 site/ 目录发布到码上架（mashangjia）。

说明：
  - 只是官方 CLI 的一层薄封装，不自己拼 HTTP 请求、不把凭据写进任何入库文件。
  - 平台地址、CLI 名称、站点 slug、固定访问地址、Token 环境变量名默认来自
    config/config.json 的 publish 段；其中站点地址与 Token 可在根目录 .env 里覆盖
    （见 .env.example），无需改代码。

两种发布方式：
  A. 指定站点（推荐，config/config.json -> publish.site 或 --site 参数）
     `mashangjia deploy <site-id|slug> <zip>` —— 定向更新已存在的站点，
     地址固定不变。本项目用这个来更新 ahut-recruitment-calendar。
  B. 按目录（--site 为空时的兜底）
     `mashangjia deploy <dir> --mode <mode>` —— 注意：即使目录名相同，它也可能
     **新建站点**而不是更新旧站点，所以绑定自定义域名后请务必用方式 A。

模式（仅方式 B 生效）：auto / anonymous / account

凭据（三选一，优先级从高到低）：
  1. 环境变量（名字取自 provider.credentials.login_token_env，默认
     MASHANGJIA_LOGIN_TOKEN）—— CI 用这个。本脚本会先执行
     `mashangjia login --token <token>` 再部署，Token 只活在进程环境里。
  2. 本机已登录 —— 本地执行过一次 `mashangjia login --token <token>` 后即可反复使用。
  3. 都没有 —— 只能用 anonymous 模式。

注意：CLI 另有部署口令（provider.credentials.deploy_token_env，默认
      MASHANGJIA_DEPLOY_TOKEN），与"登录 Token"不是同一种东西，格式校验不同；
      控制台「API Token」页面生成的是登录 Token，请走上面的第 1 种方式。

用法：
    python scripts/publish.py                       # 按 config/config.json 的 publish.site 定向更新
    python scripts/publish.py --site <slug|id>      # 指定站点
    python scripts/publish.py --mode anonymous      # 按目录匿名发布
    python scripts/publish.py --print-url           # 只打印将要更新的固定地址，不发布
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
sys.path.insert(0, str(ROOT))

from src.envfile import apply_publish_env_overrides, load_env_file  # noqa: E402

# 配置缺省值：config/config.json -> publish 段缺字段时兜底，保证克隆后开箱可用
DEFAULT_PROVIDER = {
    "name": "mashangjia",
    "label": "码上架",
    "base_url": "https://mashangjia.com",
    "cli": {
        "command": "mashangjia",
        "npm_package": "mashangjia",
        "fallback": ["npx", "--yes", "mashangjia"],
    },
    "credentials": {
        "login_token_env": "MASHANGJIA_LOGIN_TOKEN",
        "deploy_token_env": "MASHANGJIA_DEPLOY_TOKEN",
    },
}

DEFAULT_PUBLISH = {
    "mode": "account",
    "project_dir": "site",
    "harness": "workbuddy",
    "site": "",
    "site_url": "",
    "site_url_pattern": "https://{site}.mashangjia.com/",
}


def deep_merge(base: dict, override: dict) -> dict:
    """用 override 覆盖 base，字典递归合并，其余直接替换。"""
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_publish_config(cfg_path: Path) -> dict:
    """读取 config/config.json 的 publish 段，与缺省值合并后返回。"""
    file_cfg = {}
    if cfg_path.exists():
        whole = json.loads(cfg_path.read_text(encoding="utf-8"))
        # 发布配置是统一配置文件里的 publish 段；兼容直接传单段文件的情况
        file_cfg = whole.get("publish") if "publish" in whole else whole
    else:
        print(f"⚠️ 未找到 {cfg_path}，使用内置缺省配置。")

    # 注释字段（下划线开头）不参与逻辑，直接透传
    cfg = deep_merge(DEFAULT_PUBLISH, file_cfg)
    cfg["provider"] = deep_merge(DEFAULT_PROVIDER, file_cfg.get("provider", {}))
    cfg["provider"]["cli"] = deep_merge(DEFAULT_PROVIDER["cli"],
                                        file_cfg.get("provider", {}).get("cli", {}))
    cfg["provider"]["credentials"] = deep_merge(
        DEFAULT_PROVIDER["credentials"],
        file_cfg.get("provider", {}).get("credentials", {}))
    return cfg


def resolve_cli(cli_cfg: dict) -> list:
    """返回可用的 CLI 命令前缀（用绝对路径，避免 PATH 解析问题）。"""
    command = cli_cfg.get("command") or "mashangjia"
    npm_package = cli_cfg.get("npm_package") or command

    exe = shutil.which(command)
    if exe:
        return [exe]

    fallback = list(cli_cfg.get("fallback") or [])
    if fallback:
        head = shutil.which(fallback[0])
        if head:
            return [head, *fallback[1:]]

    raise SystemExit(
        f"找不到 CLI：全局未安装 {command}，也没找到 {fallback[0] if fallback else 'npx'}。"
        f"请先安装 Node.js，或执行 npm i -g {npm_package}"
    )


def resolve_site_url(cfg: dict, site: str) -> str:
    """
    站点固定访问地址：
      - site 就是配置里那个站点 —— 直接用 site_url（最权威，支持自定义域名）；
      - site 是命令行临时传入的其他站点 —— 用 site_url_pattern 推导。
    """
    if not site:
        return ""
    if site == cfg.get("site"):
        url = (cfg.get("site_url") or "").strip()
        if url:
            return url
    pattern = (cfg.get("site_url_pattern") or "").strip()
    try:
        return pattern.format(site=site) if pattern else ""
    except KeyError:
        return ""


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
    parser.add_argument("--dir", default=None, help="待发布目录，默认取配置的 project_dir")
    parser.add_argument("--site", default=None,
                        help="目标站点 slug 或 id，定向更新（推荐，地址固定不变）")
    parser.add_argument("--config", default="config/config.json",
                        help="统一配置文件路径（读取其中的 publish 段）")
    parser.add_argument("--env-file", default=".env",
                        help="本地环境变量文件（不存在则忽略；真实环境变量优先于它）")
    parser.add_argument("--print-url", action="store_true",
                        help="只打印将要更新的固定地址，不执行发布")
    args = parser.parse_args()

    # 先注入 .env：MASHANGJIA_LOGIN_TOKEN 等凭据与站点地址都可写在里面；
    # CI 没有 .env，Secrets 直接注入的真实环境变量同样有效且优先级更高。
    load_env_file(ROOT / args.env_file)

    cfg = load_publish_config(ROOT / args.config)
    apply_publish_env_overrides(cfg)
    provider = cfg["provider"]
    cli_cfg = provider["cli"]
    creds = provider["credentials"]

    mode = args.mode or cfg.get("mode", "auto")
    target = args.dir or cfg.get("project_dir", "site")
    site = args.site or cfg.get("site", "")
    harness = cfg.get("harness", "workbuddy")
    project_dir = ROOT / target
    site_url = resolve_site_url(cfg, site)

    if args.print_url:
        if not site_url:
            print("（未配置 site / site_url，无法推导固定地址）", file=sys.stderr)
            return 0
        print(site_url)
        return 0

    if not (project_dir / "index.html").exists():
        raise SystemExit(f"{project_dir} 下没有 index.html，请先运行 scripts/daily_update.py")

    print(f"发布平台：{provider.get('label') or provider.get('name')}"
          f"（{provider.get('base_url', '').rstrip('/')}）")
    print(f"待发布目录：{project_dir}")
    if site:
        print(f"目标站点：{site}" + (f"　固定地址：{site_url}" if site_url else ""))

    cli = resolve_cli(cli_cfg)

    # CI 场景：先用登录 Token 登录，再部署。Token 只在进程环境中，不落盘。
    token_env = creds.get("login_token_env") or "MASHANGJIA_LOGIN_TOKEN"
    login_token = os.environ.get(token_env, "").strip()
    if login_token:
        print(f"检测到环境变量 {token_env}，先登录 ...")
        r = run_cli([*cli, "login", "--token", login_token, "--json"],
                    cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8")
        ok = bool((parse_result(r.stdout) or {}).get("ok"))
        if not ok:
            print("登录失败，终止发布：", file=sys.stderr)
            sys.stderr.write((r.stdout or "")[-800:] + (r.stderr or "")[-800:])
            print(f"提示：{provider.get('base_url', '').rstrip('/')} 控制台「API Token」页面"
                  f"生成的是登录 Token，不是部署口令（{creds.get('deploy_token_env')}）。",
                  file=sys.stderr)
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
        cmd = [*cli, "deploy", str(project_dir), "--mode", mode,
               "--harness", harness, "--json"]

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
        if site_url:
            print(f"固定地址：{site_url}")
        # CLI 返回的地址与配置不一致时提醒，避免悄悄更新到别的站点
        returned = (result.get("url") or result.get("stable_url")
                    or (result.get("deployment") or {}).get("url") or "")
        if returned and site_url and returned.rstrip("/") != site_url.rstrip("/"):
            print(f"⚠️ CLI 返回地址 {returned} 与配置 {site_url} 不一致，"
                  f"请核对 config/config.json -> publish 的 site / site_url。", file=sys.stderr)
        print(json.dumps(result, ensure_ascii=False)[:1200])
        return 0

    if result.get("ok") and result.get("verified") and result.get("url"):
        print(f"发布成功：{result['url']}")
        print(f"模式：{result.get('mode')}　状态：{result.get('deployment', {}).get('status')}")
        if result.get("mode") == "anonymous":
            print(f"临时站到期：{result.get('expires_at')}　可认领至：{result.get('claim_expires_at')}")
            print("提示：想要固定地址请改用 account 模式并在配置里填好 site。")
        return 0

    print("发布未成功：", json.dumps(result, ensure_ascii=False)[:1500], file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
