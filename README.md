# AHUT 招聘日历 · 自动抓取与个性化匹配

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Python](https://img.shields.io/badge/Python-3.9%2B-blue.svg)](https://www.python.org/)
[![Dependencies](https://img.shields.io/badge/dependencies-stdlib%20only-green.svg)](./requirements.txt)

每天自动抓取 **安徽工业大学就业服务平台** 的校园招聘会信息，覆盖 **2026 年 9—12 月**，
生成一个纯静态网页：第一级是**招聘会总览**，第二级是**与我相关**（按你的专业 + 意向城市画像自动匹配）。

已结束的场次**不会删除**，而是标记为「已过期」灰显后继续罗列，方便回看与复盘。

> 零第三方依赖，只用 Python 标准库。

---

## ✨ 特性

| 特性 | 说明 |
| --- | --- |
| 🗓 **全量区间抓取** | 覆盖 2026-09-01 ~ 2026-12-31，日历接口拿不到的月份自动退化为逐日扫描，保证不漏 |
| 📄 **深入招聘简章** | 不只抓标题，还抓每场招聘会的完整简章，从中提取「需求专业」与「工作地点」 |
| ⏰ **每日 02:00 自动更新** | 定时任务拉取新数据、合并数据集、重建页面 |
| ♻️ **过期不删除** | 当天之前的场次照常列出，仅标记为「已过期」并灰显 |
| 🎯 **画像驱动匹配** | 改 `config/profile.json` 即可换成任何专业 / 城市组合，无需改一行代码 |
| 🔍 **匹配有据可查** | 每家单位展示命中的专业关键词与城市关键词，并附上简章原文片段 |
| 📦 **纯静态产物** | 输出单个 `index.html`，可直接托管到任意静态空间 |
| 🧠 **增量抓取** | 招聘简章按 ID 本地缓存，重复运行只抓新增场次 |

---

## 🚀 快速开始

```bash
git clone <your-repo-url>
cd recruitment-summary

# 1) 抓取 + 匹配 + 生成页面（首次运行）
python scripts/daily_update.py

# 2) 打开产物
#    Windows: start site\index.html
#    macOS  : open site/index.html
```

常用参数：

```bash
python scripts/daily_update.py --no-detail       # 跳过简章抓取，速度最快（只出列表，不做匹配）
python scripts/daily_update.py --rebuild-cache   # 忽略本地缓存，重新抓全部简章
```

---

## 📁 目录结构

```
.
├── LICENSE                  # MIT 许可证
├── README.md
├── .gitignore
├── requirements.txt         # 仅列可选依赖，核心零依赖
├── config/
│   ├── config.json          # 站点地址、抓取区间、请求参数、输出路径
│   └── profile.json         # ★ 个人画像：专业关键词 + 意向城市 + 权重阈值
├── src/
│   ├── scraper.py           # 抓取：日历红点 → 当日场次 → 招聘简章全文
│   ├── matcher.py           # 匹配：按画像打分、抽取证据、标记过期状态
│   └── generate.py          # 渲染：生成单页静态站点 site/index.html
├── scripts/
│   └── daily_update.py      # 每日更新入口（抓取 → 合并 → 匹配 → 生成）
├── data/
│   ├── dataset.json         # 累计数据集（已过期场次永久保留）
│   ├── snapshot/            # 每日原始快照 YYYY-MM-DD.json
│   └── cache/               # 招聘简章缓存（按 ID）
└── site/                    # ★ 发布产物：index.html + data.json
```

---

## ⚙️ 配置

### `config/config.json`

```jsonc
{
  "site":  { "base_url": "https://ahut.ahbys.com", "api_path": "/API/Web/Recruit.ashx" },
  "range": { "start": "2026-09-01", "end": "2026-12-31" },   // 抓取区间
  "request": { "timeout": 30, "retries": 3, "delay_seconds": 0.15 }
}
```

### `config/profile.json`（★ 想换人用，只改这里）

```jsonc
{
  "major": "材料科学与工程",
  "major_keywords": {
    "strong": ["材料科学与工程", "材料类", "金属材料工程", "复合材料", ...],
    "weak":   ["冶金", "高分子", "焊接", ...]
  },
  "cities": {
    "primary": ["南京", "徐州"],                              // 意向城市
    "belt": { "南京": ["无锡","常州","镇江",...],              // 可通勤的周边城市
              "徐州": ["淮北","宿州","枣庄",...] }
  },
  "weights":    { "major_strong": 3.0, "city_primary": 3.0, "city_belt": 1.5, ... },
  "thresholds": { "tier1": 4.0, "tier2": 2.0, "tier3": 0.1 }
}
```

**打分规则**

```
score = 专业分 + 城市分 × 1.2
专业分 = 命中 strong 关键词数 × 3.0 + 命中 weak 关键词数 × 1.0
城市分 = 命中意向城市数 × 3.0 + 命中周边城市数 × 1.5
```

| 总分 | 档位 | 页面分组 |
| --- | --- | --- |
| ≥ 4.0 | `tier1` | 强相关 |
| ≥ 2.0 | `tier2` | 相关 |
| ≥ 0.1 | `tier3` | 沾边 |
| = 0 | `tier0` | 不相关（只在明细表出现） |

---

## 🕑 定时更新（每天 02:00）

三种方式，**二选一即可**。区别在于"谁在跑"：

| 方式 | 谁在跑 | 电脑要开机吗 | 地址是否固定 | 成本 |
| --- | --- | --- | --- | --- |
| **GitHub Actions**（推荐） | GitHub 服务器 | ❌ 不需要 | ✅ `*.github.io` 永久固定 | 免费 |
| 自建服务器 cron | 你的 VPS | ❌ 不需要 | ✅ 自己掌控 | 服务器费用 |
| 本地定时 | 你的电脑 | ✅ 必须开机 | 取决于发布方式 | 免费 |

> GitHub Actions 的 `schedule` **不保证准点**，高峰时可能延迟几分钟到半小时；
> 要严格准点请用自建服务器。

### 方案 A：GitHub Actions（推荐）

已内置 [`.github/workflows/daily.yml`](./.github/workflows/daily.yml)，每天 02:00（UTC+8）
在 GitHub 服务器上抓取 → 提交 `data/dataset.json` → 部署到 GitHub Pages。

一次性配置：

1. 推送到 GitHub（见下方"发布到 GitHub Pages"）
2. `Settings → Actions → General → Workflow permissions` 选 **Read and write**
3. `Settings → Pages → Build and deployment → Source` 选 **GitHub Actions**

之后每天 02:00 自动更新，也可以在 Actions 页面点 **Run workflow** 手动触发。

可选的码上架同步发布：在 `Settings → Secrets and variables → Actions` 添加
`MASHANGJIA_API_TOKEN` 即可；**未配置时该步骤会自动跳过**，不影响主流程。

### 方案 B：自建服务器 cron

```bash
# 每天 02:00
0 2 * * * cd /srv/recruitment-summary && python scripts/daily_update.py >> logs/daily.log 2>&1

# 需要同时发布时，追加发布命令
0 2 * * * cd /srv/recruitment-summary && python scripts/daily_update.py && python scripts/publish.py
```

### 方案 C：本地定时（macOS / Linux）

```bash
0 2 * * * cd /path/to/recruitment-summary && python scripts/daily_update.py >> logs/daily.log 2>&1
```

### 方案 C：本地定时（Windows 任务计划程序）

```powershell
$action  = New-ScheduledTaskAction  -Execute "python" `
             -Argument "scripts\daily_update.py" -WorkingDirectory "E:\AI_Projects\Recruitment Summary"
$trigger = New-ScheduledTaskTrigger -Daily -At 02:00
Register-ScheduledTask -TaskName "AHUT-Recruit-Daily" -Action $action -Trigger $trigger
```

---

## 🚀 发布到 GitHub Pages

```bash
git init && git add . && git commit -m "feat: 初始化 AHUT 招聘日历"

# 在 GitHub 上新建一个空仓库（不要勾选 README / .gitignore），然后：
git remote add origin https://github.com/<用户名>/<仓库名>.git
git branch -M main
git push -u origin main
```

推送后到 `Settings → Pages → Source` 选 **GitHub Actions**，
第一次工作流跑完（或手动 Run workflow）就会给出地址：

```
https://<用户名>.github.io/<仓库名>/
```

这个地址**永久固定**，每天自动更新内容，不需要任何 Token。

---

## 🔌 数据来源接口

页面是 JS 动态渲染的，数据实际来自 `/API/Web/Recruit.ashx`：

| 用途 | 方法 | 参数 |
| --- | --- | --- |
| 日历红点（哪些日期有招聘会） | POST | `action=cale&month=<offset>`（0=当月，1=次月…） |
| 某天的场次列表 | POST | `action=calelist&year=YYYY&mon=MM&day=DD` |
| 单场招聘简章全文 | GET | `action=info&rid=<ID>` |

请求需带 `Referer` 与 `X-Requested-With` 头。

---

## 📄 免责声明

- 本项目仅用于**个人求职信息聚合**，与安徽工业大学及安徽省大学生就业服务平台无关。
- 所有招聘信息的版权归原平台及各用人单位所有；本项目只做抓取、整理与本地展示，不做任何修改。
- 抓取频率已做限速（默认每次请求间隔 0.15s，失败指数退避重试），请勿提高频率影响对方服务。
- 招聘信息以学校就业网**实时发布为准**，本项目数据可能存在延迟或偏差。

---

## 📜 License

[MIT](./LICENSE) © 2026 AHUT Recruitment Calendar contributors
