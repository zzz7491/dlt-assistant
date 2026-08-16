# 大乐透 AI 娱乐分析助手

> 基于历史开奖数据的**统计娱乐分析**工具 · **不预测、不保证中奖**

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![GitHub Actions](https://github.com/zzz7491/dlt-assistant/actions/workflows/dlt-analysis.yml/badge.svg)](https://github.com/zzz7491/dlt-assistant/actions/workflows/dlt-analysis.yml)
[![Cloudflare Pages](https://img.shields.io/badge/Cloudflare%20Pages-已上线-blue)](https://dlt-assistant.pages.dev)
[![Python](https://img.shields.io/badge/Python-3.13-3776AB)](https://www.python.org)
[![DataSource](https://img.shields.io/badge/DataSource-500%E5%BD%A9%E7%A5%A8%E7%BD%91-orange)](https://datachart.500.com/dlt/history/newinc/history.php)

一个**完全开源、零运维、可复现**的「大乐透历史数据娱乐分析」项目：每日由 GitHub Actions 自动抓取中国体育彩票超级大乐透的历史开奖数据，做多维度统计娱乐分析，并生成可供公开访问的静态网页报告。**所有「推荐号码」均为算法随机产物，仅供娱乐与技术演示，不构成任何购彩建议。**

---

## 项目简介

本项目把「大乐透分析」做成了无需自建服务器的自动化管道：

- 数据源为公开的 500 彩票网历史开奖页面；
- 分析逻辑全部用 Python 实现，口径透明、代码可查；
- 调度由 GitHub Actions 托管，定时 + 手动均可触发；
- 展示由 Cloudflare Pages 托管，纯静态、全球 CDN、免运维。

> 🎯 **定位**：这是一个「历史数据的娱乐分析项目」，**不是、也不可能是彩票预测器**。任何历史统计都不能推导未来开奖结果。

---

## 在线体验

🌐 **https://dlt-assistant.pages.dev**

网页每日 **10:00（北京时间）** 随 GitHub Actions 自动更新，包含热门号码、冷号遗漏、奇偶 / 大小 / 连号走势，以及 A / B / C 三套娱乐推荐。

---

## 项目特点

- 🔄 **自动采集历史数据**：GitHub Actions 每日定时抓取 500 彩票网最近 1000 期开奖结果，支持增量更新。
- 📊 **多维度统计分析**：号码频率、热号 / 冷号、遗漏、奇偶、大小、连号、区间分布一站式统计。
- ⚙️ **GitHub Actions 自动运行**：定时（北京时间 10:00）+ 手动触发，无需服务器、无需值守。
- 🌐 **Cloudflare Pages 发布**：纯静态站点，全球 CDN 加速，构建命令留空、Output 目录为 `public`。

---

## 功能展示

| 功能 | 说明 |
|------|------|
| 历史数据分析 | 抓取并维护最近 1000 期 JSON 数据库，按期号去重、封顶 1000 期 |
| 热冷号统计 | 前区 Top10 / 后区 Top5 热号，前区 Top8 / 后区 Top4 当前遗漏（冷号） |
| 奇偶分析 | 前区奇偶组合分布统计 |
| 大小分析 | 以前区分界值 18 统计大小组合分布 |
| 连号分析 | 含连号期占比与平均每期连号对数 |
| 多策略推荐 | A 均衡型 / B 冷热型 / C 纯随机型，均明确标注「非预测」 |
| 自动生成报告 | 每日 Markdown 分析报告 + 开奖验证报告，随仓库提交 |
| 网页展示 | 移动优先的纯静态页面，由 Cloudflare Pages 公开托管 |

---

## 技术架构

```
        500彩票网历史数据页 (公开)
              │  HTTP 抓取（增量更新）
              ▼
┌─────────────────────────────────────────────┐
│  GitHub Actions（每日 02:00 UTC / 手动触发）    │
│  Python 3.13 分析流水线：                     │
│    scraper      抓取 / 增量更新               │
│    → database   写入 data/dlt_history.json    │
│    → analyzer   频率/热冷/遗漏/奇偶/大小/连号   │
│    → recommender A/B/C 娱乐推荐               │
│    → validator  推荐 vs 真实开奖（仅统计命中） │
│    → reporter   生成 Markdown 报告            │
│    → scheduler  串联全流程（--once）          │
│    → 自动 git commit 回仓库                    │
└─────────────────────────────────────────────┘
              │  同步 public/data + public/reports
              ▼
   public/ 静态站点（index.html + data/*.json）
              │  (可选) wrangler pages deploy
              ▼
    Cloudflare Pages → 公开访问 https://dlt-assistant.pages.dev
```

**技术栈**：Python 3.13 · GitHub Actions · Cloudflare Pages · HTML / CSS / JavaScript（纯前端复算，无框架、无构建步骤）。

> 💡 项目**无需任何密钥或环境变量即可运行**：数据源为公开页面，所有阈值均在 `config/settings.yaml` 配置；飞书通知等扩展功能仅在开启时才需填写对应 webhook。

---

## 自动运行流程

- **触发**：`cron: 0 2 * * *`（UTC）= 北京时间 10:00；亦支持 `workflow_dispatch` 手动触发。
- **步骤**：
  1. 检出代码（`actions/checkout@v4`）
  2. 配置 Python 3.13（`actions/setup-python@v5`）
  3. 安装依赖（`pip install -r requirements.txt`）
  4. 运行分析（`python -m src.scheduler --once`）
  5. 同步网页数据（`public/data`）+ 历史报告（`public/reports`）
  6. 自动提交回仓库（有变更才提交，避免空提交）
  7. （可选）配置 `CLOUDFLARE_API_TOKEN` 后自动 `wrangler pages deploy`

> 工作流文件：`.github/workflows/dlt-analysis.yml`，权限仅 `contents: write`。

---

## 部署方法

### 方式一：GitHub + Cloudflare Pages（推荐）

1. 将本项目推送到 GitHub 仓库。
2. Cloudflare Dashboard → `Workers & Pages` → `Create application` → `Pages` → `Connect to Git`。
3. 选择本项目对应的 GitHub 仓库。
4. 构建设置：**Framework preset = None**，**Build command 留空**，**Build output directory = `public`**。
5. 部署完成后，Cloudflare 分配公开网址即可访问。

### 方式二：CI 自动部署（可选）

在 GitHub 仓库 `Settings → Secrets → Actions` 添加 `CLOUDFLARE_API_TOKEN`（Cloudflare API Token，授予 Pages 编辑权限）。此后每次工作流运行，末步会自动 `wrangler pages deploy`，无需手动重新部署。

### 本地预览

```bash
python -m http.server --directory public 8080
# 浏览器打开 http://127.0.0.1:8080/
```

---

## 项目目录

```
dlt-assistant/
├── .github/workflows/dlt-analysis.yml  # GitHub Actions：每日自动运行 + 手动触发
├── requirements.txt                    # Python 依赖（核心三项）
├── config/settings.yaml                # 全部配置（期数/分析口径/扩展开关）
├── src/
│   ├── scraper.py        # 抓取最近 1000 期（支持增量更新）
│   ├── database.py       # JSON 数据库读写（去重、封顶 1000 期）
│   ├── analyzer.py       # 频率/热冷/遗漏/奇偶/大小/连号/区间
│   ├── recommender.py    # 娱乐推荐（A 均衡 / B 冷热 / C 随机）
│   ├── recommendations.py# 推荐记录落盘（供开奖验证比对）
│   ├── validator.py      # 开奖验证（推荐 vs 真实开奖，仅统计命中）
│   ├── reporter.py       # Markdown 报告生成
│   ├── scheduler.py      # 编排入口（串联全流程）
│   └── notifier/         # 通知接口（飞书已实现，默认关闭）
├── charts/generate.py    # 图表生成（扩展，默认关闭）
├── data/                 # JSON 数据库（运行生成，提交回仓库以支持增量）
├── reports/              # 每日 Markdown 报告 + 推荐记录 + 验证报告
└── public/               # 静态网页（Cloudflare Pages 直接部署）
    ├── index.html        # 移动端优先的分析主页（含 SEO / Open Graph）
    ├── style.css
    ├── app.js            # 纯 JS 复算分析（与 analyzer.py 口径一致）
    └── data/             # dlt_history.json + recommendations.json（站点数据）
```

---

## 数据来源

数据来自 **[500 彩票网历史数据页](https://datachart.500.com/dlt/history/newinc/history.php)**（500.com），为公开的历史开奖信息，仅用于统计分析与技术演示。本项目不采集、不存储任何个人隐私数据。

---

## 风险声明

> ⚠️ **郑重声明**：本项目仅用于历史开奖数据的**娱乐性统计分析**，**不预测、不保证、不暗示任何中奖可能**。
>
> - 彩票开奖为独立随机事件，任何历史规律都不能推导未来结果；
> - 所有「推荐号码」均为基于历史统计的随机娱乐产物，**不等于中奖预测**；
> - 本项目所有输出仅作技术娱乐演示，**不构成任何购彩建议**；
> - 请理性购彩、量力而行、切勿沉迷。

---

## License

本项目以 **MIT License** 开源，详见 [LICENSE](LICENSE)。

---

*仅供娱乐，不构成任何购彩建议。*
