#!/usr/bin/env python3
"""
scf/index.py —— 腾讯云函数 SCF 入口：抓取招聘会，并把结果提交回 GitHub 仓库。

为什么要把它拆出来：
    数据源 ahut.ahbys.com 在国内（安徽电信单机，无 CDN），GitHub 托管 runner 在境外。
    97 次请求跨洋要十几分钟；把抓取搬进境内的云函数后约 46 秒，
    跨洋环节从「97 次请求」压缩成「1 次提交」。

链路：
    云函数（境内，定时触发）──抓取──> 招聘会数据
        ──Contents API 提交──> data 分支的 data/dataset.json（main 不被自动化改动）
            ──workflow_dispatch(ref=main)──> GitHub Actions（境外）
                                             生成站点 + 部署 Pages + 发布码上架

为什么提交到独立的 data 分支、再用 dispatch 触发：
    main 留作代码分支，不被每日的数据提交污染。GitHub Actions 的 push 触发器只认
    「被推送分支上存在的工作流文件」，孤儿分支不触发、带副本的数据分支又会让工作流
    跑旧副本；所以这里改为「提交到 data 分支 + 主动调 workflow_dispatch(ref=main)」，
    工作流文件只存在于 main，永远以最新版本运行，零漂移。

环境变量（在 SCF 控制台「函数配置 → 环境变量」里填）：
    GITHUB_TOKEN   必填。Personal Access Token，需 Contents 与 Actions 均为
                   Read and write 权限（classic PAT 勾 repo 即天然包含两者）。
                   注意：要用 PAT，不能用 Actions 自带的 GITHUB_TOKEN —— 后者创建的
                   commit 不会再触发 workflow，且没有 dispatch 权限，链路就断了。
    GITHUB_BRANCH  可选，默认 data（数据分支）。填 main 即回滚到旧行为。
    DRY_RUN        可选，设为 1 时只跑抓取与合并、打印将要提交的内容，不真的写仓库。
    SCF_DATA_DIR   可选，详情缓存目录，默认 /tmp/ahut-recruitment-calendar
                   （云函数代码目录是只读的，只能写 /tmp）。

本地试跑（不会写仓库）：
    DRY_RUN=1 python scf/index.py

依赖：仅 Python 标准库，打包时把 index.py + src/ + config/ 一起打进 zip 即可。
"""

from __future__ import annotations

import base64
import datetime as dt
import http.client
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

HERE = Path(__file__).resolve().parent


def _find_root() -> Path:
    """定位项目根（配好 source root 的那个目录）。

    两种布局都要支持：
      - 云函数：index.py 与 src/ config/ 同级，都在 zip 根目录  -> ROOT 就是 HERE
      - 本地开发：index.py 在 scf/ 子目录里                      -> ROOT 是 HERE.parent
    按「能同时找到 config/config.json 和 src/scraper.py」来判定，比硬取 parent 稳。
    """
    for cand in (HERE, HERE.parent):
        if (cand / "config/config.json").is_file() and (cand / "src/scraper.py").is_file():
            return cand
    return HERE


ROOT = _find_root()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.dataset import (  # noqa: E402
    dumps_dataset, in_range, merge_dataset, normalize_dataset_times,
)
from src.scraper import Scraper  # noqa: E402
from src.timeutil import cn_today  # noqa: E402

DEFAULT_BRANCH = "data"        # 数据分支：每日抓取只写它，main 保持不被自动化改动
BASE_BRANCH = "main"           # 代码分支：ensure_branch 的派生来源、dispatch 的目标 ref
WORKFLOW_FILE = "daily.yml"    # 提交成功后要触发的工作流
GITHUB_API = "https://api.github.com"
DATASET_PATH = "data/dataset.json"
USER_AGENT = "ahut-recruitment-calendar-scf"


# ------------------------------------------------------------------ GitHub

class GitHubError(RuntimeError):
    """GitHub API 调用失败。code 为 HTTP 状态码（网络层失败时为 None）。"""

    def __init__(self, message: str, code: Optional[int] = None) -> None:
        super().__init__(message)
        self.code = code


class GitHubContents:
    """极简 GitHub API 客户端，只用到「读文件 / 写文件 / 建分支 / 触发工作流」。"""

    def __init__(self, repo: str, token: str, branch: str = DEFAULT_BRANCH,
                 timeout: float = 30.0, retries: int = 3) -> None:
        self.repo = repo
        self.token = token
        self.branch = branch
        self.timeout = timeout
        self.retries = retries

    def _request(self, method: str, url: str, body: Any = None) -> Any:
        """带重试的请求。国内访问 api.github.com 偶发超时，所以网络层错误一律重试。"""
        data = json.dumps(body).encode("utf-8") if body is not None else None
        last: Optional[Exception] = None
        for attempt in range(1, self.retries + 1):
            try:
                req = urllib.request.Request(url, data=data, method=method)
                if self.token:      # 公开仓库读文件不需要认证，没配 token 也能干跑
                    req.add_header("Authorization", f"Bearer {self.token}")
                req.add_header("Accept", "application/vnd.github+json")
                req.add_header("X-GitHub-Api-Version", "2022-11-28")
                req.add_header("User-Agent", USER_AGENT)
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    raw = resp.read().decode("utf-8", errors="replace")
                return json.loads(raw) if raw else {}
            except urllib.error.HTTPError as exc:
                # 4xx 是确定性错误，重试没有意义，直接抛出；5xx 多半是瞬时故障，照样重试
                detail = ""
                try:
                    detail = exc.read().decode("utf-8", errors="replace")[:300]
                except Exception:  # noqa: BLE001
                    pass
                if exc.code < 500 or attempt >= self.retries:
                    raise GitHubError(f"{method} {url} -> HTTP {exc.code} {detail}",
                                      code=exc.code) from exc
                print(f"      第 {attempt} 次请求失败（HTTP {exc.code}），{2 * attempt}s 后重试")
                time.sleep(2 * attempt)
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError,
                    OSError, http.client.HTTPException) as exc:
                # dataset.json 现在有 500+ KB，跨国读它偶发「读到一半断开」
                # （http.client.IncompleteRead），这类错误重试即可，所以要一并接住。
                last = exc
                if attempt < self.retries:
                    print(f"      第 {attempt} 次请求失败（{exc}），{2 * attempt}s 后重试")
                    time.sleep(2 * attempt)
        raise GitHubError(f"{method} {url} 重试 {self.retries} 次仍失败：{last}")

    def get_file(self, path: str) -> Tuple[Optional[str], Optional[str]]:
        """返回 (文件文本, blob sha)。文件不存在时返回 (None, None)。"""
        url = (f"{GITHUB_API}/repos/{self.repo}/contents/"
               f"{urllib.parse.quote(path)}?ref={urllib.parse.quote(self.branch)}")
        try:
            payload = self._request("GET", url)
        except GitHubError as exc:
            if exc.code == 404:
                return None, None
            raise
        content = payload.get("content") or ""
        text = base64.b64decode(content).decode("utf-8") if content else ""
        return text, payload.get("sha")

    def ensure_branch(self, branch: str, base: str = BASE_BRANCH) -> None:
        """确保数据分支存在（幂等，正常情况只花 1 次 API 调用）。

        不存在时从 base（main）派生：取 heads/main 的 sha，POST /git/refs 建出来。
        """
        try:
            self._request("GET", f"{GITHUB_API}/repos/{self.repo}/git/ref/heads/"
                                 f"{urllib.parse.quote(branch)}")
            return
        except GitHubError as exc:
            if exc.code != 404:
                raise
        ref = self._request("GET", f"{GITHUB_API}/repos/{self.repo}/git/ref/heads/"
                                   f"{urllib.parse.quote(base)}")
        sha = (ref.get("object") or {}).get("sha")
        if not sha:
            raise GitHubError(f"取不到 {base} 分支的 sha，无法派生 {branch}：{ref}")
        self._request("POST", f"{GITHUB_API}/repos/{self.repo}/git/refs",
                      {"ref": f"refs/heads/{branch}", "sha": sha})
        print(f"      已创建 {branch} 分支（从 {base} 派生）")

    def dispatch_workflow(self, workflow: str = WORKFLOW_FILE,
                          ref: str = BASE_BRANCH) -> None:
        """触发 ref 分支上的工作流重建站点。

        固定指向 main：工作流文件只存在于 main，这样永远跑最新版本，不会有分支副本漂移。
        """
        url = (f"{GITHUB_API}/repos/{self.repo}/actions/workflows/"
               f"{urllib.parse.quote(workflow)}/dispatches")
        self._request("POST", url, {"ref": ref})

    def put_file(self, path: str, text: str, sha: Optional[str], message: str) -> Dict[str, Any]:
        body: Dict[str, Any] = {
            "message": message,
            "content": base64.b64encode(text.encode("utf-8")).decode("ascii"),
            "branch": self.branch,
        }
        if sha:
            body["sha"] = sha      # 带 sha 才是「更新」，否则 API 会报文件已存在
        url = f"{GITHUB_API}/repos/{self.repo}/contents/{urllib.parse.quote(path)}"
        return self._request("PUT", url, body)


# ------------------------------------------------------------------ 主流程

def parse_repo(repo_url: str) -> str:
    """https://github.com/owner/name/... -> owner/name"""
    parsed = urllib.parse.urlparse(repo_url)
    if "github.com" not in parsed.netloc.lower():
        raise SystemExit(f"config.json -> links.repo 不是 GitHub 地址：{repo_url!r}")
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 2:
        raise SystemExit(f"无法从 {repo_url!r} 解析出 owner/repo，请检查 links.repo 配置")
    owner, name = parts[0], parts[1]
    if name.endswith(".git"):
        name = name[:-4]
    return f"{owner}/{name}"


def today_message(total: int, added: int) -> str:
    return (f"chore(data): 云函数每日抓取 {cn_today().isoformat()}"
            f"（新增 {added} 场，累计 {total} 场）")


def run(dry_run: bool = False) -> Dict[str, Any]:
    config_path = ROOT / "config/config.json"
    if not config_path.is_file():
        raise SystemExit(
            f"找不到配置文件：{config_path}\n"
            "云函数里正确的结构是 index.py、src/、config/ 三者同级（都在 zip 根目录）。"
        )
    config = json.loads(config_path.read_text(encoding="utf-8"))
    profile = config.get("profile") or {}
    fair_range = profile.get("fair_range") or {}
    try:
        start = dt.date.fromisoformat(fair_range["start"])
        end = dt.date.fromisoformat(fair_range["end"])
    except (KeyError, TypeError, ValueError) as exc:
        raise SystemExit(
            "config/config.json 缺少 profile.fair_range.start / profile.fair_range.end"
        ) from exc

    repo = parse_repo(config["links"]["repo"])
    branch = (os.environ.get("GITHUB_BRANCH") or "").strip() or DEFAULT_BRANCH
    token = (os.environ.get("GITHUB_TOKEN") or "").strip()
    if not token and not dry_run:
        raise SystemExit(
            "缺少环境变量 GITHUB_TOKEN：请在 SCF 控制台填入有 Contents 写权限的 PAT；"
            "只想本地试跑的话加 DRY_RUN=1。"
        )

    # 云函数代码目录只读，缓存只能落在 /tmp
    data_dir = Path(os.environ.get("SCF_DATA_DIR") or "/tmp/ahut-recruitment-calendar")

    print(f"[1/4] 抓取 {start} ~ {end} 的招聘会 ...")
    t0 = time.time()
    fairs = Scraper(config, data_dir).collect(start, end, with_detail=True)
    print(f"      本次抓到 {len(fairs)} 场（耗时 {time.time() - t0:.1f}s）")
    if not fairs:
        print("      ⚠️ 一场都没抓到，通常是对方站点或网络异常；本次不会覆盖已有数据")

    print(f"[2/4] 读取 {repo}@{branch} 已有的 {DATASET_PATH} ...")
    gh = GitHubContents(repo, token, branch)
    sha = None
    if dry_run and not token:
        # 本地没配 token 时改用本地那份，既能验证合并逻辑又不会打到远端
        local = ROOT / config["output"]["data_dir"] / "dataset.json"
        print(f"      （未配置 GITHUB_TOKEN，改用本地 {local.relative_to(ROOT).as_posix()}）")
        old_text = local.read_text(encoding="utf-8") if local.exists() else None
    else:
        gh.ensure_branch(branch)        # 幂等；首次运行会创建 data 分支
        old_text, sha = gh.get_file(DATASET_PATH)
    dataset: Dict[str, Dict[str, Any]] = {}
    if old_text:
        try:
            dataset = {x["id"]: x for x in json.loads(old_text)}
        except (json.JSONDecodeError, KeyError, TypeError):
            print("      ⚠️ 远端 dataset.json 解析失败，将按空数据集重建")
    print(f"      远端已有 {len(dataset)} 场")

    added = merge_dataset(dataset, fairs)
    normalize_dataset_times(dataset, start, end)
    new_text = dumps_dataset(dataset)
    in_window = sum(1 for v in dataset.values() if in_range(v.get("date", ""), start, end))
    print(f"[3/4] 合并完成：新增 {added} 场，累计 {len(dataset)} 场（区间内 {in_window} 场）")

    if old_text == new_text:
        print("[4/4] dataset.json 内容无变化，跳过提交（不会触发 Actions）")
        return {"changed": False, "committed": False, "added": added,
                "total": len(dataset), "in_window": in_window}

    print(f"[4/4] 提交 {DATASET_PATH}（{len(new_text.encode('utf-8')) / 1024:.1f} KB）")
    if dry_run:
        print("      DRY_RUN=1：已跳过实际提交")
        return {"changed": True, "committed": False, "added": added,
                "total": len(dataset), "in_window": in_window}

    result = gh.put_file(DATASET_PATH, new_text, sha, today_message(len(dataset), added))
    commit_sha = (result.get("commit") or {}).get("sha", "")
    print(f"      已提交 {commit_sha[:12] or '(未知)'} 到 {branch} 分支")
    try:
        gh.dispatch_workflow()
        print(f"      已请求 GitHub Actions 重建站点（{BASE_BRANCH} 上的 {WORKFLOW_FILE}）")
    except GitHubError as exc:
        # 失败不致命：工作流还有 schedule 兜底，数据已经落盘，没必要让整次运行失败
        print(f"      ⚠️ 触发 Actions 失败（{exc}）；数据已提交，等 schedule 兜底重建")
    return {"changed": True, "committed": True, "added": added,
            "total": len(dataset), "in_window": in_window, "commit": commit_sha}


def main_handler(event: Any = None, context: Any = None) -> Dict[str, Any]:
    """腾讯云函数 SCF 的 Python 入口。"""
    dry = (os.environ.get("DRY_RUN") or "").strip() in ("1", "true", "True", "yes")
    started = time.time()
    try:
        result = run(dry_run=dry)
        print(f"完成 ✅ 总耗时 {time.time() - started:.1f}s")
        return result
    except Exception as exc:  # noqa: BLE001
        # SCF 只在日志里看得到 traceback，这里显式打一遍便于排查
        import traceback
        traceback.print_exc()
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


if __name__ == "__main__":
    result = main_handler()
    print("\n结果：" + json.dumps(result, ensure_ascii=False))
    sys.exit(0 if result.get("ok", True) else 1)
