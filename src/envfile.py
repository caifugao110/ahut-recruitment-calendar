"""
envfile.py — 极简 .env 加载器（仅用 Python 标准库，不引入 python-dotenv）。

设计目标：
  - 本项目核心零第三方依赖，不能为了读 .env 强迫用户 pip install；
  - 与「十二要素应用」约定一致：配置走环境变量，.env 只是本地开发时的便捷注入方式；
  - 优先级：进程已有的真实环境变量（如 CI Secret） > .env 文件 > config/config.json 默认值。
    因此 GitHub Actions 里即使没有 .env，Secrets 注入的变量也照常生效，且不会被文件覆盖。

支持的 .env 语法（够用即可，刻意保持简单）：
    KEY=VALUE
    export KEY=VALUE        # 允许 shell 风格的 export 前缀
    KEY="value" / KEY='v'   # 允许成对引号
    # 整行注释               # 行首 # 为注释
    KEY=value  # 说明        # 未加引号时，" #..." 视作行内注释

注意：文件不存在时静默跳过（CI / 未配置场景）；解析失败不致命，只打印一条警告。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict


def load_env_file(path: Path) -> Dict[str, str]:
    """
    把 .env 文件中的变量注入 os.environ，返回本次实际注入的变量。

    已存在于 os.environ 的变量不会被覆盖——真实环境变量（CI Secret、命令行临时
    指定的变量）永远比 .env 文件优先级高。
    """
    path = Path(path)
    if not path.exists():
        return {}

    loaded: Dict[str, str] = {}
    try:
        # utf-8-sig 会自动剥掉 Windows 编辑器（记事本/PowerShell 5）常写的 BOM，
        # 对无 BOM 的文件行为与 utf-8 完全一致
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError as exc:
        print(f"⚠️ 读取 {path} 失败，已忽略：{exc}")
        return {}

    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            continue

        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if not key:
            continue

        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            # 成对引号：原样取引号内内容，不处理转义（凭据/地址里没有转义需求）
            value = value[1:-1]
        else:
            # 未加引号：去掉行内注释
            value = value.split(" #", 1)[0].strip()

        if key in os.environ:
            # 真实环境变量优先：不覆盖，但视为「已有有效值」
            continue
        os.environ[key] = value
        loaded[key] = value

    return loaded


def _env_value(name: str) -> str:
    """读一个环境变量；空字符串视作未配置（避免 .env 里留空时误覆盖默认值）。"""
    return (os.environ.get(name) or "").strip()


def apply_publish_env_overrides(pub: Dict[str, Any]) -> None:
    """用环境变量覆盖 publish 段中「部署时可能变化」的站点字段，就地修改。"""
    if not isinstance(pub, dict):
        return
    if slug := _env_value("MASHANGJIA_SITE_SLUG"):
        pub["site"] = slug
    if url := _env_value("MASHANGJIA_SITE_URL"):
        pub["site_url"] = url


def apply_env_overrides(config: Dict[str, Any]) -> None:
    """
    用 .env / 环境变量覆盖统一配置中「fork / 部署时需要按人调整」的地址字段。

    只覆盖显式配置且非空的变量；其余字段保持 config/config.json 的默认值，
    保证没有 .env 时开箱即用。数据源地址（site 段）与个人画像（profile 段）
    刻意不在这里覆盖——它们不属于部署变量。
    """
    links = config.get("links")
    if isinstance(links, dict):
        if repo := _env_value("AHUT_REPO_URL"):
            links["repo"] = repo
        if pages := _env_value("AHUT_PAGES_URL"):
            links["pages"] = pages

    apply_publish_env_overrides(config.get("publish") or {})
