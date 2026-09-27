# AHUT 招聘日历 · 自动抓取与个性化匹配

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Python](https://img.shields.io/badge/Python-3.9%2B-blue.svg)](https://www.python.org/)
[![Dependencies](https://img.shields.io/badge/dependencies-stdlib%20only-green.svg)](./requirements.txt)

每天自动抓取 **安徽工业大学就业服务平台**（ahut.ahbys.com）的校园招聘会信息，
深入每场招聘会的完整简章，提取「需求专业 / 学历要求 / 工作地点」，
生成一个纯静态网页：

- **招聘会总览**：按月、按日罗列全部场次，默认只看「未过期」；
- **与我相关**：按你的「专业 + 学历 + 意向城市」画像自动打分、分级、排序，
  并展示命中的关键词与简章原文片段，匹配依据可核查。

已结束的场次**不会删除**，而是标记为「已过期」灰显保留，方便回看复盘。

> 零第三方依赖，只用 Python 标准库（urllib / json / html / datetime …），
> 双击产物即可离线打开。

在线地址（二选一，CI 每次同时更新）：

- GitHub Pages：<https://caifugao110.github.io/ahut-recruitment-calendar/>
- 码上架：<https://ahut-recruitment-calendar.mashangjia.com/>

---

## ✨ 特性

| 特性 | 说明 |
| --- | --- |
| 🗓 **区间全量抓取** | 追踪区间在 `config/config.json` 的 `profile.fair_range`（当前 2026-09-01 ~ 2026-12-31）；先用日历「红点」接口缩小范围，接口覆盖不到的月份自动退化为逐日扫描，保证不漏 |
| 📄 **深入招聘简章** | 不只抓标题列表，还抓每场招聘会的完整简章，从中识别需求专业、学历门槛与工作地点 |
| 🎯 **画像驱动匹配** | 专业 / 学历 / 城市 / 权重 / 阈值全部配置化，换成任何人的画像都不用改代码 |
| 🔍 **匹配有据可查** | 每家单位展示命中的专业、城市、学历标签，并附上简章原文片段，不靠公司名猜测 |
| ♻️ **过期不删除** | 当天之前的场次照常保留，仅标记「已过期」灰显；默认筛选只显示未过期 |
| ⏰ **每日定时自动更新** | 更新时间在 `profile.schedule.daily_at`（默认 02:00，北京时间），GitHub Actions 到点自动抓取、提交数据、重建并发布 |
| 🧠 **增量抓取** | 招聘简章按 ID 缓存到 `data/cache/`，重复运行只抓新增场次 |
| 📦 **纯静态产物** | 输出 `index.html` + `data.json` + `favicon.svg`，可托管到任意静态空间 |

---

## 🚀 快速开始

```bash
git clone https://github.com/caifugao110/ahut-recruitment-calendar.git
cd ahut-recruitment-calendar

# 1) 抓取 + 匹配 + 生成页面（首次运行会逐场抓简章，耗时较长）
python scripts/daily_update.py

# 2) 打开产物
#    Windows: start site\index.html
#    macOS  : open site/index.html
```

不需要建虚拟环境、不需要 `pip install`——Python 3.9+ 标准库即可运行。

### 常用命令参数

| 命令 | 作用 |
| --- | --- |
| `python scripts/daily_update.py` | 完整更新：抓取 → 合并数据集 → 匹配 → 生成页面 |
| `python scripts/daily_update.py --no-detail` | 跳过简章抓取，只拉场次列表（最快；不做画像匹配） |
| `python scripts/daily_update.py --rebuild-cache` | 忽略 `data/cache/`，重新抓取全部简章 |
| `python scripts/daily_update.py --from-dataset` | 不联网，直接用已有 `data/dataset.json` 重建页面（调画像参数时用） |
| `python scripts/daily_update.py --config <路径>` | 指定其它配置文件（默认 `config/config.json`） |
| `python scripts/publish.py --print-url` | 只打印将要更新的固定站点地址，不发布 |
| `python scripts/publish.py` | 按配置里的站点 slug **定向更新**码上架站点（推荐） |
| `python scripts/sync_workflow.py` | 把配置里的更新时间换算成 UTC cron 回填到 GitHub Actions |
| `python scripts/sync_workflow.py --check` | 只校验 cron 是否与配置一致（CI 用，漂移即报错） |

---

## 📁 目录结构

```
.
├── .github/
│   └── workflows/
│       └── daily.yml            # GitHub Actions：每日抓取、提交数据、部署 Pages / 码上架
├── .env.example                 # 环境变量模板（凭据/部署地址，复制成 .env 后填写）
├── config/
│   └── config.json              # ★ 唯一配置文件（数据源 + 个人画像 + 发布，全站就改这一个）
├── src/                         # 核心库（被 scripts 调用，一般不用直接动）
│   ├── __init__.py
│   ├── envfile.py               # 零依赖 .env 加载器（标准库实现）
│   ├── scraper.py               # 抓取：日历红点 → 当日场次 → 招聘简章全文
│   ├── matcher.py               # 匹配：按画像打分、抽取证据、标记过期状态
│   └── generate.py              # 渲染：生成单页静态站点
├── scripts/                     # 命令行入口
│   ├── daily_update.py          # 每日更新：抓取 → 合并 → 匹配 → 生成
│   ├── publish.py               # 发布 site/ 到码上架（官方 CLI 的薄封装）
│   └── sync_workflow.py         # 把更新时间同步成 GitHub Actions 的 cron
├── data/
│   ├── dataset.json             # ★ 累计数据集（已过期场次永久保留，CI 增量提交到独立的 data 分支，主分支不动）
│   ├── snapshot/                # 每日原始快照 YYYY-MM-DD.json（本地，不入库）
│   └── cache/                   # 招聘简章缓存，按 ID 一个文件（本地，不入库）
├── site/                        # ★ 生成产物（不入库，CI 通过 Pages 制品部署）
│   ├── index.html               #   单页站点（内联 CSS/JS，双击即开）
│   ├── data.json                #   结构化结果数据
│   └── favicon.svg              #   站点图标
├── reports/                     # 项目早期的一次性人工分析报告（本地留存，不入库）
├── requirements.txt             # 仅列可选依赖，核心零依赖
├── LICENSE                      # MIT
└── README.md
```

---

## ⚙️ 配置：只改 `config/config.json` 一个文件

所有配置集中在一个文件里，按职责分成四段；以 `_` 开头的键（如 `_comment`）是说明文字，
程序会自动忽略。fork 之后通常只需要改 `profile`（换成你自己的画像）和 `links` / `publish`
（换成你自己的仓库与站点）。

> 其中**凭据与部署地址**（Token、仓库/Pages/码上架地址）也可以放在根目录 `.env` 里覆盖，
> 不必改 config.json，详见下一节 [🔑 .env：凭据与部署地址](#-env凭据与部署地址不入库)。
> 配置的完整优先级是：**真实环境变量（CI Secret）> `.env` 文件 > config.json 默认值**。

### 1. `site` / `links` / `request` / `output`：数据源与产物

```jsonc
{
  "site": {
    "base_url": "https://ahut.ahbys.com",        // 就业平台域名
    "calendar_url": "https://ahut.ahbys.com/RecruitCalendar.html",
    "api_path": "/API/Web/Recruit.ashx",         // 数据接口
    "detail_url": "https://ahut.ahbys.com/Recruit.html?id={id}"
  },
  "links":  { "repo": "你的仓库地址", "pages": "你的 Pages 地址" },
  "request": { "timeout": 30, "retries": 3, "delay_seconds": 0.15 },  // 限速/重试，请勿调高频率
  "output":  { "site_dir": "site", "data_dir": "data", "index_name": "index.html" }
}
```

### 2. `profile`：★ 个人画像（追踪区间 + 定时 + 专业/学历/城市）

```jsonc
"profile": {
  "fair_range": { "start": "2026-09-01", "end": "2026-12-31" },  // 追踪的招聘会日期闭区间
  "schedule":   { "daily_at": "02:00", "timezone": "Asia/Shanghai" }, // 每日自动更新时间（北京时间）

  "major": "材料科学与工程",                // 你的专业（仅作展示）
  "education": "硕士研究生",                // 你的学历（仅作展示）
  "education_keywords": {
    "target": ["硕士", "研究生"],           // 简章出现这些词 = 招你的学历 → 小幅加分
    "higher": ["博士"]                      // 只出现这些词 = 门槛更高 → 小幅扣分
  },
  "major_keywords": {
    "strong": ["材料科学与工程", "材料类", "金属材料工程", ...],  // 核心对口词
    "weak":   ["冶金", "高分子", "焊接", "材料"]                 // 沾边词
  },
  "cities": {
    "primary": ["南京", "徐州"],            // 意向城市（严格匹配）
    "belt": { }                             // 通勤圈，如 {"南京": ["无锡","常州","镇江"]}
  },
  "weights":    { "major_strong": 3.0, "major_weak": 0.8,
                  "city_primary": 3.0, "city_belt": 1.2, "city_weight_ratio": 1.2,
                  "education_match": 0.6, "education_higher_penalty": 0.3 },
  "thresholds": { "tier1": 4.0, "tier2": 2.0, "tier3": 0.1 }
}
```

### 打分规则（取最高档位，不按关键词个数累加）

```
总分   = 专业分 + 城市分 × city_weight_ratio(1.2) + 学历分
专业分 = 命中任一 strong 词 ? 3.0 : (命中任一 weak 词 ? 0.8 : 0)
城市分 = 命中任一意向城市 ? 3.0 : (命中任一通勤圈城市 ? 1.2 : 0)
学历分 = 招硕士/研究生 ? +0.6 : (只提博士 ? −0.3 : 0)
```

| 总分 | 档位 | 页面分组 |
| --- | --- | --- |
| ≥ 4.0 | `tier1` | 强相关（专业、城市两头都沾） |
| ≥ 2.0 | `tier2` | 相关 |
| ≥ 0.1 | `tier3` | 沾边 |
| = 0 | `tier0` | 不相关（只出现在总览明细里） |

几个典型组合（默认权重下）：

| 简章命中情况 | 总分 | 档位 |
| --- | --- | --- |
| 核心专业 + 意向城市 + 招硕士 | 3.0 + 3.0×1.2 + 0.6 = **7.2** | 强相关 |
| 沾边专业 + 意向城市 + 招硕士 | 0.8 + 3.6 + 0.6 = **5.0** | 强相关 |
| 仅意向城市（且招硕士） | 0 + 3.6 + 0.6 = **4.2** | 强相关 |
| 仅核心专业（且招硕士） | 3.0 + 0 + 0.6 = **3.6** | 相关 |
| 仅沾边专业 | 0.8 | 沾边 |

> 设计说明：早期版本按「命中关键词个数」累加，一份简章出现 5 个材料类词就虚高到 15 分，
> 导致大部分单位都被判成强相关，失去筛选意义。现在每个维度只取最高档位，
> 只有专业与城市两头都沾的单位才会进入强相关。

改完画像后不用联网，执行 `python scripts/daily_update.py --from-dataset` 即可立即看效果。

### 3. `publish`：码上架发布（不用可忽略）

见下文[「发布到码上架」](#发布到码上架固定地址可选)章节。

---

## 🔑 `.env`：凭据与部署地址（不入库）

**Token 这一类敏感信息不允许写进 config.json**；同时，fork 之后每人的仓库 / Pages /
码上架地址各不相同，直接改 config.json 容易产生无关提交。为此项目支持在根目录放一个
`.env` 文件，专门存放这些「按机器、按人变化」的值。

### 一分钟使用

```bash
copy .env.example .env      # Windows（macOS / Linux 用 cp .env.example .env）
# 然后用记事本/VS Code 编辑 .env，按需填写
```

`.env` 已被 `.gitignore` 屏蔽，**绝不会入库**；入库的只有模板 [.env.example](./.env.example)。
两个脚本启动时会自动加载它，无需任何额外操作：

- `scripts/daily_update.py`：读取其中的页面外链地址（渲染到站点页头/页脚）；
- `scripts/publish.py`：读取其中的码上架 Token 与目标站点地址。

### 支持的变量

| 变量名 | 作用 | 留空时 |
| --- | --- | --- |
| `MASHANGJIA_LOGIN_TOKEN` | 码上架**登录 Token**（控制台「API Token」页面生成，本地发布用） | 回退到本机 `mashangjia login` 登录态；都没有则只能匿名发布 |
| `MASHANGJIA_DEPLOY_TOKEN` | 码上架**部署口令**（与登录 Token 不是同一种凭据，勿混用） | 不使用 |
| `AHUT_REPO_URL` | 页面上的「源代码仓库」链接 | 用 config.json 的 `links.repo` |
| `AHUT_PAGES_URL` | 页面上的「GitHub Pages」链接 | 用 config.json 的 `links.pages` |
| `MASHANGJIA_SITE_SLUG` | 码上架目标站点 slug，定向更新用 | 用 config.json 的 `publish.site` |
| `MASHANGJIA_SITE_URL` | 码上架固定访问地址 | 用 config.json 的 `publish.site_url` |

`.env` 语法：`KEY=VALUE`，每行一个；支持 `export ` 前缀、成对单/双引号、`#` 注释；
加载器用标准库实现（[src/envfile.py](./src/envfile.py)），**不需要安装 python-dotenv**，
并兼容 Windows 编辑器常写的 UTF-8 BOM。

### 优先级与 CI

```
真实环境变量（如 GitHub Actions Secret、命令行临时指定）  >  .env  >  config/config.json
```

- **本地开发**：把值写进 `.env` 即可，脚本自动读取；
- **GitHub Actions**：不需要也不应该提交 `.env`，在
  `Settings → Secrets and variables → Actions` 配置同名 Secret（见
  [发布到码上架](#发布到码上架固定地址可选)），真实环境变量会自动压过 `.env`；
- 想临时指定别的文件，可加参数：`--env-file <路径>`（两个脚本都支持）。

---

## 🕑 每日定时更新（默认 02:00，北京时间）

三种执行方式任选其一，区别在「谁在跑」：

| 方式 | 谁在跑 | 电脑要开机吗 | 地址是否固定 | 成本 |
| --- | --- | --- | --- | --- |
| **GitHub Actions**（推荐） | GitHub 服务器 | ❌ | ✅ `*.github.io` 永久固定 | 免费 |
| 自建服务器 cron | 你的 VPS | ❌ | 自己掌控 | 服务器费用 |
| 本地定时 | 你的电脑 | ✅ | 取决于发布方式 | 免费 |

> GitHub Actions 的 `schedule` **不保证准点**，高峰可能延迟几分钟到半小时；
> 需要严格准点请用自建服务器。

### 方式 A：GitHub Actions（推荐）

已内置 [.github/workflows/daily.yml](./.github/workflows/daily.yml)，每天在
`profile.schedule.daily_at` 设定的时间（北京时间，默认 02:00）自动完成：

1. 校验 cron 与配置是否一致；
2. 抓取最新招聘会、合并进 `data/dataset.json`；
3. 若数据有变化，自动提交并推送到独立的 `data` 分支（主分支保持只读、只存核心代码）；
4. 重建站点并部署到 GitHub Pages；
5. （可选）配置了码上架 Token 时同步发布到码上架。

一次性配置（仓库页面上点选）：

1. 推送代码到 GitHub（见下方[发布到 GitHub Pages](#-发布到-github-pages)）；
2. `Settings → Actions → General → Workflow permissions` 选 **Read and write permissions**；
3. `Settings → Pages → Build and deployment → Source` 选 **GitHub Actions**。

之后每天到点自动运行；也可在 Actions 页面选 `daily-update` → **Run workflow** 手动触发。

**修改每日更新时间**：GitHub Actions 只认写死在 yml 里的 UTC cron，不能直接读 JSON，
改完配置后跑一次同步脚本并提交即可（CI 也会自动校验，忘记同步会直接报错提醒）：

```bash
# 1) 改 config/config.json 里的 profile.schedule.daily_at，例如 "07:30"
# 2) 自动把北京时间换算成 UTC cron 并回填 daily.yml
python scripts/sync_workflow.py
# 3) 提交
git add config/config.json .github/workflows/daily.yml
git commit -m "chore: 调整每日更新时间为 07:30"
```

### 方式 B：自建服务器 cron

时间与 `profile.schedule.daily_at`（北京时间）保持一致：

```bash
# 每天 02:00 抓取更新
0 2 * * * cd /srv/ahut-recruitment-calendar && python scripts/daily_update.py >> logs/daily.log 2>&1

# 需要同时发布到码上架时
0 2 * * * cd /srv/ahut-recruitment-calendar && python scripts/daily_update.py && python scripts/publish.py
```

### 方式 C：本地定时（macOS / Linux）

```bash
0 2 * * * cd /path/to/ahut-recruitment-calendar && python scripts/daily_update.py >> logs/daily.log 2>&1
```

### 方式 C：本地定时（Windows 任务计划程序）

```powershell
# -At 后的时间对齐 profile.schedule.daily_at
$action  = New-ScheduledTaskAction -Execute "python" `
             -Argument "scripts\daily_update.py" `
             -WorkingDirectory "E:\AI_Projects\ahut-recruitment-calendar"
$trigger = New-ScheduledTaskTrigger -Daily -At 02:00
Register-ScheduledTask -TaskName "AHUT-Recruit-Daily" -Action $action -Trigger $trigger
```

---

## 🌐 发布到 GitHub Pages

```bash
# 在 GitHub 新建一个空仓库（不要勾选 README / .gitignore），然后：
git remote add origin https://github.com/<用户名>/<仓库名>.git
git branch -M main
git push -u origin main
```

推送后到 `Settings → Pages → Build and deployment → Source` 选 **GitHub Actions**，
工作流第一次跑完（或手动 Run workflow）后即可访问：

```
https://<用户名>.github.io/<仓库名>/
```

地址永久固定，每天自动更新内容，**不需要任何 Token**。

---

## 🔗 发布到码上架（固定地址，可选）

码上架是另一条静态托管通道。相关配置全部在 `config/config.json` 的 **`publish` 段**，
仓库不含任何凭据：

```jsonc
"publish": {
  "provider": {
    "name": "mashangjia", "label": "码上架", "base_url": "https://mashangjia.com",
    "cli": {
      "command": "mashangjia",                    // 全局 CLI 名
      "npm_package": "mashangjia",
      "fallback": ["npx", "--yes", "mashangjia"]  // 没全局装就用 npx 临时拉
    },
    "credentials": {
      "login_token_env": "MASHANGJIA_LOGIN_TOKEN",   // 只存「环境变量名」，不存值
      "deploy_token_env": "MASHANGJIA_DEPLOY_TOKEN"
    }
  },
  "mode": "account",
  "project_dir": "site",
  "site": "ahut-recruitment-calendar",                             // ★ 目标站点 slug
  "site_url": "https://ahut-recruitment-calendar.mashangjia.com/",// ★ 固定访问地址
  "site_url_pattern": "https://{site}.mashangjia.com/"             // 换 slug 时自动推导
}
```

| 字段 | 作用 |
| --- | --- |
| `provider.cli` | CLI 命令名 / npm 包名；本机没有全局 CLI 时自动退回 `npx` 临时拉取（需安装 Node.js） |
| `provider.credentials.*_env` | **只存环境变量名**，Token 值永远不入库 |
| `site` | 目标站点 slug，`deploy <site> <zip>` 定向更新用 |
| `site_url` | 固定访问地址；留空则由 `site_url_pattern` 用 `{site}` 推导；CLI 实际返回地址与此不一致时脚本会告警 |
| `mode` / `project_dir` | 发布模式（account / anonymous / auto）与待发布目录 |

常用命令：

```bash
python scripts/publish.py --print-url       # 只查看将要更新的固定地址
python scripts/publish.py                    # 定向更新配置里的站点（推荐）
python scripts/publish.py --site <slug|id>   # 临时换站点发布
python scripts/publish.py --mode anonymous   # 按目录匿名发布（地址不固定、约 24h 过期）
```

> ⚠️ **绑定自定义域名后务必用「按站点更新」**：CLI 的 `deploy <目录>` 形式即使目录名相同，
> 也可能**新建一个站点**，导致固定域名收不到更新。`publish.py` 默认走
> `deploy <site> <zip>` 定向更新就是为了避免这个坑。

**凭据三选一**（优先级从高到低）：

1. 环境变量 `MASHANGJIA_LOGIN_TOKEN`——本地写在根目录 `.env` 里（见
   [.env 章节](#-env凭据与部署地址不入库)），CI 里配在 Actions Secrets；脚本检测到后会自动先
   `mashangjia login --token <token>` 再部署，Token 只活在进程环境里；
2. 本机已登录——本地执行过一次 `mashangjia login --token <token>`，之后可反复发布；
3. 都没有——只能匿名发布。

> 注意：控制台「API Token」页面生成的是**登录 Token**；CLI 另有「部署口令」
> （`MASHANGJIA_DEPLOY_TOKEN`），二者不是同一种凭据，格式校验不同，不要混用。

在 CI 中启用：`Settings → Secrets and variables → Actions` 添加一个 Secret，
**名字取 `publish.provider.credentials.login_token_env`**（默认
`MASHANGJIA_LOGIN_TOKEN`）。未配置时码上架相关步骤会自动跳过，不影响 GitHub Pages 主流程。

> ⚠️ Token 只放在 CI Secret 或环境变量里，**不要写进任何文件**。
> `.gitignore` 已屏蔽 `.env*` / `*.token` / 部署回执文件。

---

## 🔌 数据来源接口

页面是 JS 动态渲染的，数据实际来自 `/API/Web/Recruit.ashx`：

| 用途 | 方法 | 参数 |
| --- | --- | --- |
| 日历红点（哪些日期有招聘会） | POST | `action=cale&month=<offset>`（0=当月，1=次月…） |
| 某天的场次列表 | POST | `action=calelist&year=YYYY&mon=MM&day=DD` |
| 单场招聘简章全文 | GET | `action=info&rid=<ID>` |

请求需带 `Referer` 与 `X-Requested-With` 头，返回 JSON。抓取策略：

1. 先批量取未来 12 个月的日历红点，只对「有红点」的日期请求场次列表，大幅减少请求数；
2. 日历接口覆盖不到的月份（如已过去的月份）自动退化为**逐日扫描**兜底；
3. 每场的简章按 `rid` 缓存，重复运行只抓新增；
4. 每次请求间隔 0.15s，失败按指数退避重试 3 次。

简章里的时间段写法五花八门（如 `2026年10月8日18:30-20:00`、全角冒号 `10：30`），
`normalize_time()` 会统一清洗成 `18:30-20:00`。

---

## 🧪 可选依赖

核心功能零依赖。`requirements.txt` 中仅以注释形式列出可选项，需要时自行安装：

```bash
pip install requests   # 更友好的 HTTP 客户端（目前代码未使用，预留）
pip install pytest     # 运行测试（目前仓库未附带测试）
```

---

## 📄 免责声明

- 本项目仅用于**个人求职信息聚合与学习交流**，与安徽工业大学及安徽省大学生就业服务平台无关。
- 所有招聘信息的版权归原平台及各用人单位所有；本项目只做抓取、整理与本地展示，不做任何修改。
- 抓取频率已做限速（默认请求间隔 0.15s、失败指数退避重试），请勿提高频率影响对方服务。
- 招聘信息以学校就业网**实时发布为准**，本项目数据可能存在延迟或偏差。

---

## 📜 License

[MIT](./LICENSE) © 2026 AHUT Recruitment Calendar contributors
