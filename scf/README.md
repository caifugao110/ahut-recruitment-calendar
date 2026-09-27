# 云函数抓取（腾讯云 SCF）

把「抓取招聘会」这一环从 GitHub Actions 搬到境内的腾讯云函数，其余环节不变。

## 为什么

数据源 `ahut.ahbys.com` 在国内（安徽电信单机、无 CDN），而 GitHub 托管 runner 在境外：
97 次请求跨洋要十几分钟。搬进境内云函数后同样 97 次请求只要约 46 秒，
**跨洋环节从「97 次请求」压缩成「1 次提交」**。

```
云函数（境内，定时触发）
  └─ 抓取招聘会（约 46 秒）
     └─ GitHub Contents API 提交 data/dataset.json → 独立的 data 分支（main 不动）
        └─ 调用 workflow_dispatch（ref=main）
           └─ GitHub Actions（境外）：从 data 分支取数据
              → --from-dataset 生成站点 → 部署 Pages → 发布码上架
```

> **为什么提交到 data 分支、再调 dispatch？**
> main 留作代码分支，不该被每日的数据提交污染。而 GitHub Actions 的 `push` 触发器只认
> 「被推送分支上存在的工作流文件」—— 数据分支上没有工作流副本就永远不触发，放一份副本
> 又会跑旧版本、跟着 main 漂移。所以改为提交到 `data` 分支后主动调
> `workflow_dispatch(ref=main)`：工作流文件只存在于 main，永远跑最新版。
> 万一 dispatch 失败也不影响数据，工作流自带的 `schedule` 兜底会在次日重建站点。

---

## 配置分三处，别搞混

| 位置 | 配什么 | 目的 |
| --- | --- | --- |
| **GitHub** | 生成 PAT | 让云函数有权限提交 `dataset.json` |
| **本地** | 打包 zip、干跑验证、推送代码 | 产出可上传的包，并让新工作流生效 |
| **腾讯云** | 建函数、填 `GITHUB_TOKEN`、加定时触发器 | 每天自动抓取 |

> ⚠️ **PAT 是配在腾讯云上的，不是配在 GitHub Actions 里的。**
> Actions 侧不需要新增任何 Secret —— 它只是被 push 事件唤醒，用仓库里已有的数据出站点。

---

## 一、GitHub 上：生成 PAT

必须用 **Personal Access Token（PAT）**，不能用 Actions 自带的 `GITHUB_TOKEN` ——
后者创建的 commit 不会再触发 workflow，链路会断在中途。

1. GitHub 右上角头像 → **Settings** → 左侧最下方 **Developer settings**
2. **Personal access tokens** → **Fine-grained tokens** → **Generate new token**
3. 按下面填：

| 字段 | 填什么 |
| --- | --- |
| Token name | 随便，比如 `ahut-scf-write` |
| Expiration | 90 天 / 1 年（Fine-grained 最长 1 年，**到期会失效，见下方提醒**） |
| Repository access | **Only select repositories** → 只勾本项目仓库 |
| Permissions → Contents | **Read and write**（提交 dataset.json 用） |
| Permissions → Actions | **Read and write**（提交后触发 workflow_dispatch 用） |

4. **Generate token** → 立刻复制保存（**只显示这一次**，关掉就找不回来了）

> 两个权限都要：只有 Contents 的话数据能提交、但 Actions 不会被触发（日志里会有 dispatch
> 警告，得等 schedule 兜底）。嫌麻烦可以直接用 classic token 勾 `repo`，两项天然包含。

> ⏳ **过期坑**：PAT 到期后云函数会报 `HTTP 401`，站点停止更新（但已有数据不会丢）。
> 建议设个到期前一周的提醒，到时生成新 token 去 SCF 环境变量里替换。
> 嫌麻烦也可以用 classic token 选 **No expiration**、权限只勾 `repo` —— 省事但权限更宽。

## 二、本地：打包、干跑、推代码

### 1. 打包

```bash
python scf/package.py --list
```

产出 `scf/dist/ahut-scf-<时间戳>.zip`（约 35 KB），内容只有三样：

```
index.py             云函数入口
src/*.py             项目模块（纯标准库，无需 layer）
config/config.json   唯一配置文件
```

> 改动了 `config/config.json`（比如调整招聘会区间、专业关键词）之后**要重新打包上传**，
> 因为配置是打进 zip 里的。

### 2. 干跑验证（不会写仓库）

```bash
# Windows（cmd / Git Bash）
set DRY_RUN=1 && python scf/index.py

# Windows PowerShell
$env:DRY_RUN=1; python scf/index.py

# macOS / Linux
DRY_RUN=1 python scf/index.py
```

正常会打印：抓到多少场（含耗时）→ 已有多少场 → 新增多少场 → `DRY_RUN=1：已跳过实际提交`。

> 没配 `GITHUB_TOKEN` 时，干跑会拿本地 `data/dataset.json` 代替远端来练手，不会联网。

### 3. 可选：本地真跑一次，端到端确认

想在上云前确认 PAT 和提交链路都通，就在本地实跑一次（会真提交、真触发 Actions）：

```bash
set GITHUB_TOKEN=你刚生成的PAT && python scf/index.py
```

看到 `已提交 xxxxxxx 到 data 分支` 后，去仓库确认：

- 出现了 `data` 分支且含 `data/dataset.json`（首次运行由云函数自动从 main 派生创建）
- **main 分支没有新增 commit**
- Actions 页出现事件类型为 `workflow_dispatch` 的 `daily-update` 运行

### 4. 推送代码

改过的 `.github/workflows/daily.yml` 要推到 main 才会生效：

```bash
git add . && git commit -m "feat: 抓取迁移到腾讯云函数" && git push
```

## 三、GitHub Actions 侧：确认已有配置

不用新增 Secret，只要确认下面两项（之前配过就不用动）：

1. `Settings → Actions → General → Workflow permissions` 选 **Read and write permissions**
2. `Settings → Pages → Build and deployment → Source` 选 **GitHub Actions**

改完的工作流只做「取数据 + 生成 + 部署」，触发条件是：

- `workflow_dispatch` —— 主链路。云函数提交数据到 `data` 分支后主动调用，也可在 Actions 页手动触发。
- `schedule` —— 兜底（云函数万一没跑或 dispatch 失败，每天仍会用已有数据重建一次站点）。

> 工作流里权限是 `contents: read`：它**不回写**任何分支的 `dataset.json`，
> 只用 `raw.githubusercontent.com` 从 `data` 分支把数据取回来（公开仓库，无需鉴权）；
> 拉取失败时回退 main 上自带的副本。

## 四、腾讯云：建函数

控制台 → 云函数 SCF → 新建 → **从头创建**：

| 配置项 | 填什么 | 说明 |
| --- | --- | --- |
| 函数类型 | 事件函数 | |
| 运行环境 | Python 3.10 或 3.11 | 项目只用标准库，版本不敏感 |
| 创建方式 | **本地上传 zip** | 选第二步打好的包（上限 50 MB，本项目 35 KB） |
| 执行入口 | `index.main_handler` | 默认即是 |
| 内存 | 256 MB | 抓取是网络 IO，内存不敏感 |
| 执行超时 | **300 秒** | 正常约 55 秒；留足余量应对个别请求卡顿（单次卡住上限约 20 秒） |

### 环境变量

函数详情 → 函数配置 → **编辑** → 环境变量，新增：

| 名称 | 值 |
| --- | --- |
| `GITHUB_TOKEN` | 第一步生成的 PAT（必填，需 Contents + Actions 写权限） |
| `GITHUB_BRANCH` | 默认已是 `data`，不用填；**填 `main` 即回滚到旧的「直接提 main」行为** |
| `DRY_RUN` | 上线前先填 `1` 跑一次，确认后删掉或改成 `0` |

### 定时触发器

函数详情 → 触发方式 → **创建触发器** → 触发方式选**定时触发**。
Cron 按控制台提示填写，时区为北京时间（Asia/Shanghai），
**不用像 GitHub Actions 那样把 02:00 换算成 UTC**。

每天北京时间 02:00（保持与 `config/config.json -> profile.schedule.daily_at` 一致）：

- 控制台接受 7 段（秒 分 时 日 月 周 年）时填：`0 0 2 * * * *`（年可省略成 `0 0 2 * * *`）
- 只接受 5 段（分 时 日 月 周）时填：`0 2 * * *`

> 改了 `daily_at` 记得同步改这里；`scripts/sync_workflow.py` 只管 GitHub Actions 那一侧。

### 手动测一次

函数详情 → **测试**，事件模板选空的 `{}` 直接运行，看返回里的 `added` / `total`，
以及日志中的 `完成 ✅ 总耗时 XXs`。

## 五、费用

每天 1 次、256 MB、约 55 秒 ≈ 0.014 GB·s，一个月约 0.42 GB·s。
云函数免费额度是每月 40 万 GB·s + 100 万次调用，实际为零成本。

## 六、排错

| 现象 | 原因与处理 |
| --- | --- |
| 函数状态停在 `CreateFailed` | 多半是账号没开通 CLS 日志服务（SCF 强制依赖它存日志，见下条） |
| 日志提示 `CLS service is unregistered` | 去控制台开通**日志服务 CLS**（免费额度足够），或调一次 CLS 的 `CreateLogset` 即可激活，然后重建函数 |
| `MissingParameter: ClsTopicId` | 手动传了 `ClsLogsetId` 却没传 `ClsTopicId`；让 SCF 自动分配最简单（别传这两个参数） |
| `FileNotFoundError: /var/config/config.json` | 代码包结构不对，zip 根必须是 `index.py` + `src/` + `config/` 三者同级 |
| `HTTP 401 / 403` | PAT 过期，或没开 Contents / Actions 写权限（最常见） |
| `HTTP 404` | 分支名不对（配 `GITHUB_BRANCH`）或 PAT 没授权该仓库 |
| `HTTP 409 / 422` | 远端文件 sha 过期，多因并发提交；重跑一次即可 |
| 提交成功但 Actions 没触发 | PAT 缺 **Actions: Read and write**，dispatch 被拒。日志里会有「⚠️ 触发 Actions 失败」；补权限即可，期间靠 schedule 兜底 |
| 日志出现 `IncompleteRead(...)` / `HTTP 5xx` | 跨国读取 dataset.json（500+ KB）偶发被截断或服务端抖动，脚本会自动重试最多 3 次，成功即无影响；连续 3 次都失败才报错，重跑一次即可 |
| 函数执行超时被杀 | 把执行超时调大（上限 900 秒），或调小 `config.json -> request.timeout` |
| 日志停在抓取、报请求失败 | 对方站点临时不可用；脚本会重试，第二天自动补上 |

函数日志在「日志查询 / CLS」，排查主要靠它。
