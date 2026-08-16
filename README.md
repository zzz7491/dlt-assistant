# AI 大乐透娱乐分析助手

> ⚠️ **免责声明**：本项目仅用于历史开奖数据的**娱乐性统计分析**，**不预测、不保证中奖**。
> 彩票开奖为独立随机事件，任何历史规律都不能推导未来结果。请理性购彩、量力而行。

---

## 项目简介

本项目是一个**完全开源**的数据分析娱乐工具：每日自动抓取中国体育彩票超级大乐透的
历史开奖数据，进行统计娱乐分析，并基于「历史统计 + 随机扰动」生成**仅供娱乐讨论**的
号码组合。整个流程由 **GitHub Actions** 自动运行，生成的静态网页报告由
**Cloudflare Pages** 公开展示。

> 🎯 **定位**：这是一个**历史数据的娱乐分析项目**，不是、也不可能是「彩票预测器」。
> 所有「推荐号码」均为算法随机产物，仅供娱乐与技术演示。

---

## 功能

1. **自动抓取**：定时抓取超级大乐透最近 300 期开奖结果（数据源：500彩票网历史数据页）。
2. **JSON 数据库**：保存为 `data/dlt_history.json`，按期号去重合并、封顶最近 300 期，支持增量更新。
3. **历史分析（Python）**：
   - 号码出现频率
   - 热号 / 冷号
   - 遗漏次数（当前遗漏 + 历史最大遗漏）
   - 奇偶比例
   - 大小比例（分界值 18）
   - 连号概率
   - 区间分布
4. **多策略娱乐推荐**（明确标注**不预测中奖**）：
   - **A 均衡统计型**：热号 + 冷号混合抽样，强制奇偶平衡与大小平衡。
   - **B 冷热组合型**：约 60% 热号 + 40% 冷号。
   - **C 纯随机娱乐型**：合法大乐透规则下的纯随机生成。
5. **每日自动运行**：抓取 → 分析 → 推荐 → 生成报告（GitHub Actions 定时 + 手动触发）。
6. **开奖验证**：比对历史推荐与真实开奖，仅统计娱乐命中数（**不计算中奖**）。
7. **静态网页报告**：移动端友好的纯静态页面（`public/`），由 Cloudflare Pages 展示。

---

## 明确声明

- 本项目**不预测彩票结果**，所有「推荐号码」均为基于历史统计的随机娱乐产物。
- 彩票为独立随机游戏，**不存在可稳定盈利的「预测」**。
- 本项目所有输出仅作技术娱乐演示，请理性购彩、量力而行、切勿沉迷。

---

## 项目架构

```
          500彩票网历史数据页
                │  (HTTP 抓取)
                ▼
   ┌──────────────────────────────────┐
   │  GitHub Actions（每日定时 / 手动） │
   │  Python 分析流水线：              │
   │   抓取 → 解析                      │
   │   → 分析（频率/热冷/遗漏/奇偶/…）  │
   │   → 多策略推荐（A/B/C）           │
   │   → 生成报告（Markdown + JSON）   │
   │  → 自动提交回仓库                  │
   └──────────────────────────────────┘
                │
                ▼
      public/ 静态站点（index.html + data/*.json）
                │  (Cloudflare Pages 拉取发布)
                ▼
          公开访问的网页报告
```

---

## 目录结构

```
dlt-assistant/
├── .github/workflows/dlt-analysis.yml  # GitHub Actions：每日自动运行 + 手动触发
├── requirements.txt                    # Python 依赖（核心三项）
├── config/settings.yaml                # 全部配置（期数/分析口径/扩展开关）
├── src/
│   ├── scraper.py        # 抓取最近 300 期（支持增量更新）
│   ├── database.py       # JSON 数据库读写（去重、封顶 300 期）
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
    ├── index.html        # 移动端优先的分析主页
    ├── style.css
    ├── app.js            # 纯 JS 复算分析（与 analyzer.py 口径一致）
    └── data/             # dlt_history.json + recommendations.json（站点数据）
```

---

## 本地运行

仅需 Python 3.13+，无需 Docker、无需后端：

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 运行一次完整流程（抓取 → 分析 → 推荐 → 报告）
python -m src.scheduler --once
```

运行后产物：

- `data/dlt_history.json` — 最近 300 期数据库
- `reports/report_YYYYMMDD.md` — 当日 Markdown 分析报告
- `reports/recommendations.json` — 当日 A/B/C 娱乐推荐记录
- `public/data/*.json` — 同步给网页的数据

本地预览网页：

```bash
python -m http.server --directory public 8080
# 浏览器打开 http://127.0.0.1:8080/
```

---

## 配置（`config/settings.yaml`）

| 配置项 | 说明 |
|---|---|
| `scrape.recent_issues` | 抓取 / 分析期数（默认 300） |
| `scrape.base_url` | 500彩票网历史数据接口 |
| `analysis.recent_window` | 计算「近期热号」的窗口期数 |
| `analysis.front_zones / back_zones` | 前区 / 后区区间划分个数 |
| `recommend.combos_per_strategy` | 每个策略（A/B/C）生成几组娱乐号码 |
| `recommend.seed` | 随机种子；`null`=每次不同（可固定以便复现） |
| `schedule.cron` | 容器内每日运行时间（当前方案改用 GitHub Actions） |
| `report.dir / filename_fmt` | 报告输出目录与文件名格式 |
| `notify.feishu.enabled` | 飞书通知开关（扩展，默认关闭） |
| `charts.enabled` | 图表生成开关（扩展，默认关闭） |
| `validate.enabled` | 开奖验证开关（默认开启） |

> 本项目**无需任何密钥或环境变量**即可运行：数据源为公开页面，所有阈值均在
> `config/settings.yaml` 中配置。飞书通知等扩展功能如需开启才需填写对应 webhook。

---

## 扩展（默认关闭，保持开源友好）

- **飞书通知**：在 `config/settings.yaml` 填写 `notify.feishu.webhook`（及可选 `secret`），并设 `enabled: true`。
- **图表分析**：设 `charts.enabled: true`，报告生成时额外输出频率 / 区间等图片（需 `matplotlib`）。

---

## 理性购彩提示

彩票为随机游戏，不存在可稳定盈利的「预测」。本工具所有输出仅作技术娱乐演示，
请理性购彩、量力而行、切勿沉迷。

---

## 部署到 Cloudflare Pages

### 前置条件

需要：

- GitHub 账号
- Cloudflare 账号
- 已上传项目仓库

### 部署步骤

**步骤 1：创建 GitHub 仓库**

将本项目推送到 GitHub。

**步骤 2：进入 Cloudflare Pages**

创建项目：

`Workers & Pages` → `Create application` → `Pages` → `Connect to Git`

**步骤 3：选择 GitHub 仓库**

在授权列表中选择本项目对应的 GitHub 仓库。

**步骤 4：构建配置**

| 配置项 | 值 |
|---|---|
| Framework preset | None |
| Build command | 留空 |
| Build output directory | `public` |

说明：因为本项目已经提前生成静态文件 `public/index.html`，Cloudflare 无需执行构建。

**步骤 5：部署完成**

点击部署后，Cloudflare 会分配一个公开网址，访问该网址即可查看网页报告。

### 自动更新说明

GitHub Actions 每天自动执行以下流程：

1. 抓取最新大乐透数据
2. 执行 Python 分析
3. 生成报告
4. 更新 `public/data`
5. 自动提交仓库

Cloudflare Pages 检测到 GitHub 仓库变化后，会自动重新部署网页。

### 常见问题

**Q：为什么页面没有数据？**

A：检查 `public/data` 目录是否存在 JSON 文件（即 `dlt_history.json` 与 `recommendations.json`）。

**Q：是否需要 API Key？**

A：不需要，本项目无需任何密钥或环境变量即可运行。

**Q：是否需要服务器？**

A：不需要。GitHub Actions 负责计算，Cloudflare Pages 负责展示，二者均为托管服务。
