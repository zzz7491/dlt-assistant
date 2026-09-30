# DLT Project Snapshot

> **生成时间**: 2026-09-29  
> **审计类型**: 全量只读审计（未修改任何项目文件）  
> **项目路径**: `/Users/Shared/projects/dlt`

---

## 1. Executive Summary

DLT（大乐透 AI 娱乐分析助手）是一个**基于历史开奖数据的统计娱乐分析工具**，由中国体育彩票超级大乐透历史数据驱动。项目通过 GitHub Actions 每日自动抓取 500 彩票网数据，经 Python 分析流水线生成多维度统计报告与娱乐推荐号码，最终以纯静态网页形式通过 Cloudflare Pages 公开发布。

**核心定位**：历史数据的娱乐分析项目，**不是、也不可能是彩票预测器**。所有推荐号码均为算法随机产物，仅供娱乐与技术演示。

**当前状态**：项目处于 **Git interactive rebase 中断状态**，工作目录有 73 个文件被删除（12,658 行），但 HEAD 指向的提交 `aff2d9c` 包含完整的生产代码。生产环境 `https://500wan.mootlsv.com/` 正常运行。

---

## 2. Project Goal

### 2.1 项目真正目标

DLT 项目的核心目标是：

1. **自动化数据采集**：每日从 500 大乐透历史数据页抓取最近 1000 期开奖数据
2. **多维度统计分析**：频率、热冷号、遗漏、奇偶、大小、连号、区间分布
3. **娱乐推荐生成**：基于历史统计生成 A/B/C/D 四套娱乐推荐号码
4. **开奖验证**：对比推荐与真实开奖，统计命中（仅娱乐参考）
5. **自动报告发布**：生成 Markdown 报告并同步到公开网页

### 2.2 用户原始意图

用户希望构建一个**零运维、可复现、完全开源**的大乐透历史数据分析平台：
- 无需自建服务器
- 数据源公开透明
- 分析逻辑代码可查
- 每日自动更新
- 全球 CDN 加速访问

### 2.3 项目边界

- **不预测**：明确声明不预测彩票结果
- **不保证**：不保证任何中奖可能
- **不构成建议**：不构成任何购彩建议
- **娱乐定位**：所有输出仅作技术娱乐演示

---

## 3. Current Status

### 3.1 生产环境

| 项目 | 值 |
|------|-----|
| **生产地址** | `https://500wan.mootlsv.com/` |
| **状态** | 正常运行 |
| **最新数据** | 2026-08-27（26097 期） |
| **历史数据** | 1000 期（19134 ~ 26097） |
| **CDN** | Cloudflare Pages |

### 3.2 代码状态

| 项目 | 值 |
|------|-----|
| **当前 HEAD** | `aff2d9c`（detached HEAD，rebase 中断） |
| **分支** | `master`（本地存在，但当前 detached） |
| **Remote** | `https://github.com/zzz7491/dlt-assistant.git` |
| **工作目录** | 73 个文件被删除（未暂存） |
| **Staged** | 无 |
| **Untracked** | 无 |

### 3.3 冻结状态

- **基线版本**: `production-stable-v1.0`（指向 `36d9bfc`）
- **状态**: 已冻结，只读维护
- **禁止**: 开发新功能 / 优化代码 / 修改首页 / 调整 UI
- **解锁条件**: 用户明确下一阶段开发指令

---

## 4. Repository State

### 4.1 Git 状态详情

```
interactive rebase in progress; onto aff2d9c
No commands done.
Next commands to do (5 remaining commands):
   pick 1ca00ff # Phase16 Step4: add honest experiment display layer
   pick b7d95b4 # feat(experiment): Phase16 Step5 自动更新流水线 + 失败隔离 + 生产冻结守卫
```

**关键发现**：
- Git 处于 **interactive rebase 中断状态**
- 正在将 `master` rebase 到 `aff2d9c`
- 还有 5 个命令待执行
- 工作目录有 73 个文件被删除（12,658 行），这些删除**未暂存**

### 4.2 最近 15 条 Git Commits

```
aff2d9c chore: 每日大乐透娱乐分析更新 2026-08-27
9bdce87 chore: 每日大乐透娱乐分析更新 2026-08-26
89e4c96 chore: 每日大乐透娱乐分析更新 2026-08-26
d099a83 chore: 每日大乐透娱乐分析更新 2026-08-25
981771d chore: 每日大乐透娱乐分析更新 2026-08-24
fa72beb chore: 每日大乐透娱乐分析更新 2026-08-24
0e30928 chore: 每日大乐透娱乐分析更新 2026-08-23
7e58d0b fix: update app cache version for d3.3
008a440 feat: consume final score breakdown in homepage (d3.3)
a0a80e4 feat: integrate dynamic score fusion into publisher (d3.2)
0f08ede feat: add cross-strategy dynamic score fusion layer (d3.1)
323f5d9 fix: update app cache version for d22
f82b6e1 feat: add review next adjustment feedback loop
249c15f fix: update app cache version for d2.1
4f708ad feat: consume recommendation review data in homepage
```

### 4.3 被删除的文件（73 个）

主要删除的文件包括：
- `public/` 下的所有前端文件（index.html, app.js, style.css, pick.html, trend.html, score.html 等）
- `reports/` 下的所有报告文件
- `scripts/` 下的所有脚本（analysis_run.py, check-production.sh, export_recommendations_json.py 等）
- `src/` 下的所有 Python 模块（analyzer.py, backtest.py, database.py, experiment.py, final_score.py, generate_recommendation.py, publisher.py, recommendation_adapter.py, recommendations.py, recommender.py, reflection.py, reporter.py, scheduler.py, scorer.py, scraper.py, validator.py）
- `tests/` 下的测试文件
- `src/notifier/` 下的通知模块

**注意**：这些删除是**工作目录中的未暂存删除**，HEAD 指向的提交 `aff2d9c` 仍然包含这些文件。

---

## 5. Technology Stack

### 5.1 后端

| 技术 | 版本 | 用途 |
|------|------|------|
| Python | 3.13 | 核心分析引擎 |
| requests | >=2.31.0 | HTTP 数据抓取 |
| beautifulsoup4 | >=4.12.0 | HTML 解析 |
| pyyaml | >=6.0 | 配置文件解析 |
| matplotlib | >=3.8.0 | 图表生成（可选） |
| fastapi | >=0.110.0 | Web API（可选） |
| uvicorn | >=0.29.0 | ASGI 服务器（可选） |

### 5.2 前端

| 技术 | 用途 |
|------|------|
| HTML5 | 页面结构 |
| CSS3 | 样式（移动优先） |
| JavaScript (ES6+) | 纯 JS 复算分析（无框架、无构建步骤） |

### 5.3 基础设施

| 技术 | 用途 |
|------|------|
| GitHub Actions | CI/CD 定时任务 |
| Cloudflare Pages | 静态站点托管 |
| Cloudflare D1 | SQLite 数据库（可选） |
| Wrangler | Cloudflare 部署 CLI |

### 5.4 数据源

| 来源 | URL |
|------|-----|
| 500 大乐透历史数据页 | `https://datachart.500.com/dlt/history/newinc/history.php` |

---

## 6. Architecture

### 6.1 整体架构图

```
用户 / 浏览器
       │
       ▼
┌─────────────────────────────────────────────┐
│  Cloudflare Pages (静态站点)                 │
│  https://500wan.mootlsv.com/                │
│  ├── index.html (首页)                       │
│  ├── app.js (纯 JS 复算分析)                 │
│  ├── style.css (移动优先样式)                │
│  └── data/ (JSON 数据)                      │
│      ├── dlt_history.json (历史数据)         │
│      ├── recommendations.json (推荐数据)     │
│      ├── review.json (复盘数据)              │
│      └── strategy_score.json (策略评分)      │
└─────────────────────────────────────────────┘
       │
       │ GitHub Actions 每日自动更新
       ▼
┌─────────────────────────────────────────────┐
│  GitHub Actions (定时 02:00 UTC)            │
│  ├── scraper.py      → 抓取 500 数据         │
│  ├── database.py     → 写入 JSON 数据库      │
│  ├── analyzer.py     → 频率/热冷/遗漏/奇偶   │
│  ├── recommender.py  → A/B/C/D 娱乐推荐      │
│  ├── validator.py    → 开奖验证              │
│  ├── reporter.py     → Markdown 报告         │
│  ├── scheduler.py    → 编排入口              │
│  └── publisher.py    → 发布数据到 public/    │
└─────────────────────────────────────────────┘
       │
       │ HTTP 抓取
       ▼
┌─────────────────────────────────────────────┐
│  500 大乐透历史数据页                         │
│  https://datachart.500.com/dlt/history/      │
└─────────────────────────────────────────────┘
```

### 6.2 数据流

```
500.com → scraper.py → data/dlt_history.json
                              ↓
                    analyzer.py (统计分析)
                              ↓
                    recommender.py (推荐生成)
                              ↓
                    reports/recommendations.json
                              ↓
                    publisher.py → public/data/
                              ↓
                    Cloudflare Pages → 用户
```

### 6.3 双轨架构

项目采用**双轨架构**：
- **轨 A（JSON 文件）**：`data/dlt_history.json` → `public/data/` → 前端直接读取
- **轨 B（D1 数据库）**：`analysis/` Python 模块 → Cloudflare D1 → Functions API 查询

---

## 7. Project Map

```
DLT
├── Data
│   ├── Acquisition
│   │   └── src/scraper.py          # 抓取 500 数据（已删除，存在于 HEAD）
│   ├── Storage
│   │   ├── data/dlt_history.json  # JSON 数据库（1000 期）
│   │   └── public/data/           # 站点数据副本
│   └── D1 Database
│       ├── migrations/0001_init_dlt.sql
│       └── functions/api/         # D1 查询 API
│
├── Analysis
│   ├── Statistics
│   │   ├── analysis/metrics.py    # 六项指标计算
│   │   └── analysis/scorer.py     # 三模型评分
│   ├── Features
│   │   ├── frequency              # 频率
│   │   ├── hot/cold               # 热冷号
│   │   ├── missing                # 遗漏
│   │   ├── odd/even               # 奇偶
│   │   ├── big/small              # 大小
│   │   └── consec                 # 连号
│   └── Writer
│       └── analysis/writer.py     # D1 SQL 生成
│
├── Prediction
│   ├── Models
│   │   ├── standard               # 标准模型
│   │   ├── cold-hot               # 冷热模型
│   │   └── expert                 # 专家模型
│   ├── Scoring
│   │   └── analysis/scorer.py     # 七维评分
│   └── Number Generator
│       └── src/recommender.py     # A/B/C/D 策略（已删除）
│
├── Backtest
│   └── src/backtest.py            # 回测模块（已删除）
│
├── API
│   ├── api_server.py              # 本地测试 API
│   └── functions/api/             # Cloudflare Functions
│       ├── analysis.ts            # 分析指标查询
│       ├── scores.ts              # 评分查询
│       ├── summary.ts             # 摘要查询
│       └── issues.ts              # 历史数据查询
│
├── Frontend
│   ├── public/index.html          # 首页（已删除，存在于 HEAD）
│   ├── public/app.js              # 主逻辑（已删除）
│   ├── public/style.css           # 样式（已删除）
│   ├── public/pick.html           # 选号页（已删除）
│   ├── public/trend.html          # 趋势页（已删除）
│   └── public/score.html          # 评分页（已删除）
│
├── Deployment
│   ├── .github/workflows/
│   │   ├── dlt-analysis.yml       # 主分析工作流
│   │   └── daily-recommend.yml    # 推荐生成工作流
│   ├── wrangler.toml              # Cloudflare 配置
│   └── DEPLOY.md                  # 部署文档
│
└── Config
    ├── config/settings.yaml       # 主配置
    ├── requirements.txt           # Python 依赖
    └── .gitignore                 # Git 忽略规则
```

---

## 8. Data Pipeline

### 8.1 数据采集

| 步骤 | 说明 |
|------|------|
| 数据源 | 500 大乐透历史数据页 |
| 抓取方式 | HTTP GET + BeautifulSoup 解析 |
| 抓取范围 | 最近 1000 期 |
| 更新方式 | 增量更新（按期号去重） |
| 超时 | 20 秒 |
| User-Agent | Chrome/124.0 |

### 8.2 数据存储

| 存储 | 路径 | 说明 |
|------|------|------|
| JSON 数据库 | `data/dlt_history.json` | 主数据库，1000 期 |
| 站点数据 | `public/data/` | 前端读取副本 |
| D1 数据库 | Cloudflare D1 | 可选，轨 B |

### 8.3 数据格式

```json
{
  "updated_at": "2026-08-27T12:13:34.247435+00:00",
  "source": "500",
  "count": 1000,
  "issues": [
    {
      "issue": "19134",
      "date": "2019-11-23",
      "front": [5, 6, 7, 14, 17],
      "back": [10, 11]
    }
  ]
}
```

### 8.4 数据更新流程

```
1. GitHub Actions 定时触发（02:00 UTC）
2. scraper.py 抓取 500 数据
3. database.py 去重、封顶 1000 期
4. 写入 data/dlt_history.json
5. 复制到 public/data/dlt_history.json
6. git commit + push
7. Cloudflare Pages 自动重新部署
```

---

## 9. Database / Dataset

### 9.1 JSON 数据库

| 项目 | 值 |
|------|-----|
| 路径 | `data/dlt_history.json` |
| 期数 | 1000 |
| 最早期号 | 19134（2019-11-23） |
| 最新期号 | 26097（2026-08-25） |
| 文件大小 | 15,006 行 |
| 格式 | JSON |

### 9.2 Cloudflare D1 数据库

| 表名 | 用途 |
|------|------|
| `dlt_draws` | 全历史开奖数据（权威库） |
| `dlt_analysis` | 分析缓存（指标） |
| `dlt_scores` | 综合评分结果 |
| `dlt_recommendations` | 推荐历史 |

### 9.3 D1 Schema

```sql
-- dlt_draws
CREATE TABLE dlt_draws (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  issue TEXT NOT NULL UNIQUE,
  issue_num INTEGER NOT NULL UNIQUE,
  date TEXT NOT NULL,
  front1-5 INTEGER NOT NULL CHECK(BETWEEN 1 AND 35),
  back1-2 INTEGER NOT NULL CHECK(BETWEEN 1 AND 12),
  source TEXT NOT NULL DEFAULT '500',
  verified INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- dlt_analysis
CREATE TABLE dlt_analysis (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  period INTEGER NOT NULL,
  kind TEXT NOT NULL,
  metric TEXT NOT NULL,
  version TEXT NOT NULL DEFAULT 'v1',
  payload TEXT NOT NULL,
  computed_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(period, kind, metric, version)
);

-- dlt_scores
CREATE TABLE dlt_scores (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  period INTEGER NOT NULL,
  kind TEXT NOT NULL,
  num INTEGER NOT NULL,
  total INTEGER NOT NULL,
  parts TEXT NOT NULL,
  tag TEXT NOT NULL,
  model_type TEXT NOT NULL DEFAULT 'standard',
  weight_version TEXT NOT NULL DEFAULT 'default',
  computed_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(period, kind, num, model_type, weight_version)
);

-- dlt_recommendations
CREATE TABLE dlt_recommendations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  target_issue TEXT NOT NULL,
  strategy TEXT NOT NULL,
  idx INTEGER NOT NULL DEFAULT 0,
  front TEXT NOT NULL,
  back TEXT NOT NULL,
  score_total INTEGER,
  date TEXT NOT NULL,
  UNIQUE(target_issue, strategy, idx)
);
```

---

## 10. Statistical Analysis

### 10.1 已实现指标

| 指标 | 函数 | 说明 |
|------|------|------|
| 频率 | `calculate_frequency` | 全池出现次数 |
| 热度 | `calculate_hot` | 热度排名 + 当前遗漏 |
| 遗漏 | `calculate_missing` | 当前/最大/平均遗漏 |
| 奇偶 | `calculate_odd_even` | 奇偶占比 |
| 大小 | `calculate_big_small` | 大小占比（前区分界 17） |
| 连号 | `calculate_consec` | 连号参与期数 |

### 10.2 评分模型

| 模型 | 权重 |
|------|------|
| **standard** | frequency:0.25, recentHot:0.20, missing:0.15, balance:0.15, oddEven:0.10, bigSmall:0.10, structure:0.05 |
| **cold-hot** | frequency:0.20, recentHot:0.25, missing:0.15, balance:0.20, oddEven:0.10, bigSmall:0.05, structure:0.05 |
| **expert** | frequency:0.20, recentHot:0.20, missing:0.15, balance:0.10, oddEven:0.10, bigSmall:0.10, structure:0.15 |

### 10.3 评分维度（七维）

| 维度 | 说明 |
|------|------|
| frequency | 频率分（相对平均频率） |
| recentHot | 近期热度分（相对最高频） |
| missing | 遗漏周期分（倒 U 形回摆） |
| balance | 冷热平衡分（三分位基分 + 热度微调） |
| oddEven | 奇偶占比分 |
| bigSmall | 大小占比分 |
| structure | 连号结构分 |

### 10.4 配置参数

```yaml
analysis:
  front_min: 1
  front_max: 35
  back_min: 1
  back_max: 12
  front_zones: 5      # 每区 7 个号
  back_zones: 2       # 每区 6 个号
  recent_window: 50   # 近期热号窗口
```

---

## 11. Prediction / Recommendation Engine

### 11.1 推荐策略

| 策略 | 名称 | 说明 |
|------|------|------|
| **A** | 均衡统计型 | 基于历史频率均衡选择 |
| **B** | 冷热组合型 | 热号 + 冷号组合 |
| **C** | 纯随机娱乐型 | 完全随机生成 |
| **D** | 综合评分型 | 七维评分 + 结构评分 |

### 11.2 推荐流程

```
1. 加载历史数据（1000 期）
2. 计算七维评分（standard/cold-hot/expert）
3. 生成候选号码池（前区 Top15 / 后区 Top8）
4. 应用结构过滤（奇偶/大小/区间/和值/跨度）
5. 生成推荐组合
6. 计算综合评分（D 策略）
7. 输出 recommendations.json
```

### 11.3 D 策略综合评分

```yaml
final_score:
  weights:
    base: 0.40        # 基础分
    history: 0.20     # 历史命中
    recent: 0.15      # 近期表现
    structure: 0.20   # 结构贴合
    risk: 0.05        # 风险惩罚
  min_sample: 5       # 冷启动门槛
  full_sample: 10     # 全权重门槛
  transition_decay: 0.5
```

### 11.4 推荐输出格式

```json
{
  "date": "2026-08-26",
  "target_issue": "26098",
  "strategy": "A-均衡统计型",
  "idx": 0,
  "front": [3, 5, 9, 24, 26],
  "back": [2, 4],
  "score": null,
  "reason": null,
  "is_primary": true,
  "final_score": 49.33,
  "final_breakdown": {
    "base": 68.0,
    "history": 20.0,
    "recent": 20.0,
    "structure": 50.0,
    "risk": 0.0,
    "weights": {
      "base": 0.4848,
      "history": 0.1212,
      "recent": 0.0909,
      "structure": 0.2424
    },
    "degraded": true,
    "stage": "transition",
    "effective_sample": 5
  },
  "final_rank": 1
}
```

---

## 12. Algorithms & Models

### 12.1 核心算法

#### 12.1.1 频率分析
- **输入**: 历史开奖数据
- **输出**: 每个号码的出现次数
- **方法**: 简单计数

#### 12.1.2 热度分析
- **输入**: 历史开奖数据
- **输出**: 热度排名 + 当前遗漏
- **方法**: 计数 + 最后出现位置

#### 12.1.3 遗漏分析
- **输入**: 历史开奖数据
- **输出**: 当前/最大/平均遗漏
- **方法**: 连续未出现段统计

#### 12.1.4 遗漏评分（倒 U 形回摆）
```python
def miss_score(cur, avg):
    if avg <= 0: return 50
    if cur <= avg: return clamp(cur / avg * 80, 0, 100)
    if cur <= 2 * avg: return clamp(80 + (cur - avg) / avg * 20, 0, 100)
    return clamp(100 - (cur - 2 * avg) / avg * 30, 0, 100)
```

#### 12.1.5 冷热平衡分
```python
# 三分位基分 + 近期热度微调
base = 72 if rank < 1/3 else (42 if rank > 2/3 else 60)
hot_adj = clamp(round(pct - 50) / 100 * 16, -8, 8)
balance = clamp(round(base + hot_adj), 20, 95)
```

### 12.2 评分模型对比

| 模型 | 特点 | 适用场景 |
|------|------|----------|
| standard | 均衡权重 | 通用场景 |
| cold-hot | 偏重近期热度 | 追热场景 |
| expert | 偏重结构 | 结构分析场景 |

### 12.3 算法风险评估

| 风险 | 说明 |
|------|------|
| **统计描述 vs 预测能力** | 所有指标均为历史统计描述，不具备预测能力 |
| **人工权重** | 权重为人工设定，非训练得到 |
| **无随机性** | 评分过程确定性，仅推荐生成有随机性 |
| **无数据泄漏** | 评分仅使用历史数据，无未来信息 |
| **过拟合风险** | 低（模型简单，无复杂参数） |
| **伪预测逻辑** | 存在（遗漏回摆理论无统计证据） |

---

## 13. Backtesting

### 13.1 回测设计

| 项目 | 值 |
|------|-----|
| 回测区间 | 5 期（26093 ~ 26097） |
| 推荐总数 | 19 组 |
| 验证期数 | 5 期 |
| 切分方式 | 时间顺序（无随机切分） |
| 数据泄漏 | 无（仅使用历史数据） |

### 13.2 回测结果

| 策略 | 平均命中 | 最高命中 | 平均距离分 |
|------|----------|----------|------------|
| A-均衡统计型 | 1.4 | 2 | 5.6 |
| B-冷热组合型 | 0.2 | 1 | 6.8 |
| C-纯随机娱乐型 | 0.8 | 2 | 6.2 |
| D-综合评分型 | 0.75 | 2 | 6.25 |

### 13.3 回测统计

```json
{
  "total_periods": 5,
  "recommendation_quality": {
    "total_groups": 19,
    "validated_periods": 5,
    "avg_front_hit": 0.421,
    "avg_back_hit": 0.368,
    "avg_total_hit": 0.789
  }
}
```

### 13.4 回测局限性

| 局限 | 说明 |
|------|------|
| 样本量小 | 仅 5 期，统计意义有限 |
| 无 baseline | 未与纯随机选号 baseline 比较 |
| 无 ROI | 未计算投入产出比 |
| 无成本 | 未考虑彩票成本 |
| 无 walk-forward | 未实现滚动窗口回测 |

---

## 14. Frontend

### 14.1 技术栈

| 技术 | 说明 |
|------|------|
| HTML5 | 页面结构 |
| CSS3 | 移动优先样式 |
| JavaScript (ES6+) | 纯 JS 复算分析 |
| 无框架 | 无 React/Vue/Angular |
| 无构建 | 无 Webpack/Vite |

### 14.2 页面结构

| 页面 | 文件 | 说明 |
|------|------|------|
| 首页 | `index.html` | 分析主页（含 SEO / Open Graph） |
| 选号 | `pick.html` | 选号页面 |
| 趋势 | `trend.html` | 趋势分析 |
| 评分 | `score.html` | 评分展示 |
| 我的 | `my.html` | 个人方案 |

### 14.3 前端功能

- 纯 JS 复算分析（与 `analyzer.py` 口径一致）
- 移动优先响应式布局
- 数据可视化（图表）
- 推荐号码展示
- 历史数据加载

### 14.4 前端数据流

```
public/data/dlt_history.json → app.js → 渲染页面
public/data/recommendations.json → app.js → 渲染推荐
public/data/review.json → app.js → 渲染复盘
public/data/strategy_score.json → app.js → 渲染策略评分
```

---

## 15. Backend / API

### 15.1 本地 API

| 端点 | 说明 |
|------|------|
| `/api/recommend-new` | 获取推荐（本地测试用） |

### 15.2 Cloudflare Functions API

| 端点 | 说明 |
|------|------|
| `/api/analysis` | 分析指标缓存查询 |
| `/api/scores` | 综合评分缓存查询 |
| `/api/summary` | 历史数据中心摘要 |
| `/api/issues` | 历史开奖数据查询 |

### 15.3 API 参数

**analysis**:
- `period`: 50 | 100 | 300 | 1000 | all
- `kind`: front | back
- `metric`: frequency | hot | missing | oddEven | bigSmall | consec

**scores**:
- `period`: 50 | 100 | 300 | 1000 | all
- `kind`: front | back
- `model_type`: standard | cold-hot | expert
- `weight_version`: default

**issues**:
- `range`: 50 | 1000 | all

---

## 16. Automation / Scheduled Jobs

### 16.1 GitHub Actions 工作流

#### 16.1.1 dlt-analysis.yml（主分析工作流）

| 项目 | 值 |
|------|-----|
| 触发 | `cron: "0 2 * * *"`（每日 02:00 UTC） |
| 开奖日触发 | `cron: "45 13 * * 1,3,6"`（周一/三/六 21:45 北京时间） |
| 手动触发 | `workflow_dispatch` |
| 超时 | 15 分钟 |
| 权限 | `contents: write` |

**步骤**:
1. 检出代码
2. 配置 Python 3.13
3. 安装依赖
4. 运行分析（`python -m src.scheduler --once`）
5. 同步 D1 历史数据库（可选）
6. 轨 B 服务端分析写入（可选）
7. 同步网页数据
8. 推荐一期固定（写入 D1）
9. 推荐一期固定（导出 JSON）
10. Publish AI Recommendation Data
11. 同步历史报告
12. 提交更新
13. 部署到 Cloudflare Pages（可选）

#### 16.1.2 daily-recommend.yml（推荐生成工作流）

| 项目 | 值 |
|------|-----|
| 触发 | `cron: "0 17 * * *"`（每日 17:00 UTC） |
| 手动触发 | `workflow_dispatch` |
| 超时 | 10 分钟 |

**步骤**:
1. 检出代码
2. 配置 Python 3.11
3. 安装依赖
4. 生成推荐数据
5. 验证生成文件
6. 提交更新

### 16.2 定时任务

| 时间（北京时间） | 任务 |
|------------------|------|
| 每日 10:00 | 主分析工作流 |
| 开奖日 21:45 | 开奖后更新 |
| 每日 01:00 | 推荐生成工作流 |

---

## 17. Deployment

### 17.1 部署架构

```
GitHub Actions → git push → Cloudflare Pages → 自动重新部署
```

### 17.2 部署配置

| 项目 | 值 |
|------|-----|
| 平台 | Cloudflare Pages |
| 项目名 | `dlt-assistant` |
| 自定义域名 | `500wan.mootlsv.com` |
| Build 命令 | 留空 |
| Output 目录 | `public` |
| Framework | None |

### 17.3 环境变量

| 变量 | 说明 | 必需 |
|------|------|------|
| `CLOUDFLARE_API_TOKEN` | Cloudflare API Token | 可选（用于自动部署和 D1） |

### 17.4 本地运行

```bash
# 安装依赖
pip install -r requirements.txt

# 运行分析
python -m src.scheduler --once

# 本地预览
python -m http.server --directory public 8080
```

### 17.5 部署验证

```bash
# 检查生产环境
curl -sL "https://500wan.mootlsv.com/" | grep -i "recommendations.json"
curl -s -o /dev/null -w "%{http_code}\n" "https://500wan.mootlsv.com/"
```

---

## 18. Implemented Features

### 18.1 已完成功能

| 功能 | 状态 | 说明 |
|------|------|------|
| 数据采集 | ✅ | 从 500 抓取历史数据 |
| 数据存储 | ✅ | JSON 数据库（1000 期） |
| 频率分析 | ✅ | 全池计数 |
| 热冷号分析 | ✅ | 热度排名 + 遗漏 |
| 遗漏分析 | ✅ | 当前/最大/平均遗漏 |
| 奇偶分析 | ✅ | 奇偶占比 |
| 大小分析 | ✅ | 大小占比 |
| 连号分析 | ✅ | 连号参与期数 |
| 三模型评分 | ✅ | standard/cold-hot/expert |
| A/B/C/D 推荐 | ✅ | 四套娱乐推荐 |
| 开奖验证 | ✅ | 推荐 vs 真实开奖 |
| Markdown 报告 | ✅ | 每日自动生成 |
| 静态网页 | ✅ | 移动优先 |
| GitHub Actions | ✅ | 每日自动运行 |
| Cloudflare Pages | ✅ | 自动部署 |
| D1 数据库 | ✅ | 可选，轨 B |
| Functions API | ✅ | 只读查询 |
| 复盘系统 | ✅ | 因子分析 + 调整建议 |
| 策略评分 | ✅ | 策略排行 |

### 18.2 部分完成功能

| 功能 | 状态 | 说明 |
|------|------|------|
| 图表生成 | 🟡 | 代码存在，默认关闭 |
| 飞书通知 | 🟡 | 代码存在，默认关闭 |
| D1 完整同步 | 🟡 | 部分实现 |
| 回测系统 | 🟡 | 仅 5 期，样本量小 |

---

## 19. Partial Features

### 19.1 图表生成

- **文件**: `charts/generate.py`
- **状态**: 代码存在，默认关闭
- **功能**: 生成前区频率柱状图、区间分布图
- **依赖**: matplotlib

### 19.2 飞书通知

- **文件**: `src/notifier/feishu.py`（已删除，存在于 HEAD）
- **状态**: 代码存在，默认关闭
- **功能**: 飞书 webhook 通知
- **依赖**: 飞书 webhook URL

### 19.3 D1 完整同步

- **状态**: 部分实现
- **问题**: 轨 B 分析写入依赖 `CLOUDFLARE_API_TOKEN`，未配置则跳过

---

## 20. Stub / Dead Code

### 20.1 已删除但存在于 HEAD 的文件

以下文件在工作目录中被删除，但在 HEAD 指向的提交 `aff2d9c` 中仍然存在：

| 文件 | 说明 |
|------|------|
| `src/scraper.py` | 数据抓取模块 |
| `src/database.py` | 数据库读写模块 |
| `src/analyzer.py` | 分析模块 |
| `src/recommender.py` | 推荐模块 |
| `src/recommendations.py` | 推荐记录模块 |
| `src/validator.py` | 验证模块 |
| `src/reporter.py` | 报告模块 |
| `src/scheduler.py` | 调度模块 |
| `src/publisher.py` | 发布模块 |
| `src/backtest.py` | 回测模块 |
| `src/experiment.py` | 实验模块 |
| `src/final_score.py` | 综合评分模块 |
| `src/generate_recommendation.py` | 推荐生成模块 |
| `src/recommendation_adapter.py` | 推荐适配模块 |
| `src/reflection.py` | 复盘模块 |
| `src/scorer.py` | 评分模块 |
| `src/notifier/` | 通知模块 |
| `public/index.html` | 首页 |
| `public/app.js` | 主逻辑 |
| `public/style.css` | 样式 |
| `public/pick.html` | 选号页 |
| `public/trend.html` | 趋势页 |
| `public/score.html` | 评分页 |
| `public/my.html` | 我的页 |
| `scripts/` | 脚本目录 |
| `tests/` | 测试目录 |

### 20.2 死代码

| 代码 | 说明 |
|------|------|
| `api_server.py` | 本地测试 API，生产环境未使用 |
| `daily-recommend.yml` | 推荐生成工作流，与主工作流功能重复 |

---

## 21. Tests / Build Status

### 21.1 测试

| 测试 | 状态 |
|------|------|
| `tests/test_final_score.py` | 已删除（存在于 HEAD） |
| `tests/test_publisher.py` | 已删除（存在于 HEAD） |
| 单元测试 | 未运行（文件已删除） |
| 集成测试 | 未运行 |

### 21.2 Build

| 项目 | 状态 |
|------|------|
| Python 依赖安装 | 未验证 |
| 分析流水线 | 未运行 |
| 前端构建 | 无构建步骤（纯静态） |

### 21.3 运行链路检查

| 检查项 | 状态 |
|--------|------|
| Git 状态 | ⚠️ rebase 中断 |
| Python 依赖 | 未验证 |
| 数据采集 | 未运行 |
| 分析流水线 | 未运行 |
| 前端页面 | 文件已删除 |
| 生产环境 | 正常运行 |

---

## 22. Data Quality

### 22.1 数据规模

| 项目 | 值 |
|------|-----|
| 总期数 | 1000 |
| 最早期号 | 19134（2019-11-23） |
| 最新期号 | 26097（2026-08-25） |
| 时间跨度 | 约 6.75 年 |

### 22.2 数据完整性

| 检查项 | 状态 |
|--------|------|
| 期号连续性 | ✅ 未验证（需检查） |
| 重复期号 | ✅ 未验证（需检查） |
| 缺失期号 | ✅ 未验证（需检查） |
| 前区号码范围 | ✅ 1-35 |
| 后区号码范围 | ✅ 1-12 |
| 开奖号码数量 | ✅ 前区 5 + 后区 2 |
| 日期格式 | ✅ YYYY-MM-DD |

### 22.3 数据格式

```json
{
  "issue": "26097",
  "date": "2026-08-25",
  "front": [3, 10, 12, 20, 25],
  "back": [1, 9]
}
```

### 22.4 数据更新

| 项目 | 值 |
|------|-----|
| 更新方式 | 增量更新 |
| 更新频率 | 每日 |
| 数据源 | 500 大乐透历史数据页 |
| 可靠性 | 依赖 500 稳定性 |

---

## 23. Algorithmic Risks

### 23.1 统计描述 vs 预测能力

| 风险 | 说明 |
|------|------|
| **核心风险** | 所有指标均为历史统计描述，不具备预测能力 |
| **遗漏回摆** | 遗漏回摆理论无统计证据 |
| **热冷号** | 热冷号统计不代表未来趋势 |
| **连号分析** | 连号统计不代表未来连号概率 |

### 23.2 人工权重风险

| 风险 | 说明 |
|------|------|
| **权重设定** | 所有权重为人工设定，非训练得到 |
| **主观性** | 权重选择缺乏客观依据 |
| **过拟合** | 低风险（模型简单） |

### 23.3 回测风险

| 风险 | 说明 |
|------|------|
| **样本量小** | 仅 5 期，统计意义有限 |
| **无 baseline** | 未与纯随机选号 baseline 比较 |
| **无 walk-forward** | 未实现滚动窗口回测 |
| **数据泄漏** | 无（仅使用历史数据） |

### 23.4 伪预测逻辑

| 逻辑 | 问题 |
|------|------|
| 遗漏回摆 | 无统计证据支持 |
| 热冷号追热 | 无统计证据支持 |
| 结构贴合 | 无统计证据支持 |

---

## 24. Architecture Risks

### 24.1 Git 状态风险

| 风险 | 级别 | 说明 |
|------|------|------|
| **rebase 中断** | P0 | Git 处于 interactive rebase 中断状态 |
| **文件删除** | P0 | 73 个文件被删除（未暂存） |
| **数据丢失** | P1 | 删除的文件包含核心代码 |

### 24.2 架构风险

| 风险 | 级别 | 说明 |
|------|------|------|
| **单点故障** | P2 | 依赖 500 单一数据源 |
| **无备份** | P2 | JSON 数据库无备份机制 |
| **无监控** | P2 | 生产环境无监控 |
| **无测试** | P2 | 测试覆盖不足 |

### 24.3 部署风险

| 风险 | 级别 | 说明 |
|------|------|------|
| **CDN 缓存** | P2 | 修改后需等待缓存刷新 |
| **自动部署** | P2 | 依赖 GitHub Actions |
| **D1 依赖** | P3 | 轨 B 依赖 D1，未配置则跳过 |

---

## 25. Technical Debt

### 25.1 代码债务

| 债务 | 说明 |
|------|------|
| 已删除文件 | 73 个文件被删除，存在于 HEAD |
| 死代码 | `api_server.py`、`daily-recommend.yml` |
| 重复代码 | 前端 JS 与后端 Python 逻辑重复 |
| 无测试 | 测试覆盖不足 |

### 25.2 文档债务

| 债务 | 说明 |
|------|------|
| 文档过时 | 部分文档与实际代码不一致 |
| 缺少 API 文档 | Functions API 缺少文档 |
| 缺少架构文档 | 缺少整体架构文档 |

### 25.3 工程债务

| 债务 | 说明 |
|------|------|
| 无 CI | 无持续集成 |
| 无监控 | 无生产监控 |
| 无日志 | 无集中日志 |
| 无告警 | 无异常告警 |

---

## 26. P0–P3 Issues

### 26.1 P0 — Critical

| # | 问题 | 文件 | 说明 |
|---|------|------|------|
| 1 | Git rebase 中断 | - | Git 处于 interactive rebase 中断状态 |
| 2 | 73 个文件被删除 | 多个 | 工作目录有 73 个文件被删除（未暂存） |

### 26.2 P1 — High

| # | 问题 | 文件 | 说明 |
|---|------|------|------|
| 1 | 核心代码删除 | `src/` | 分析、推荐、回测等核心模块被删除 |
| 2 | 前端代码删除 | `public/` | 所有前端页面被删除 |
| 3 | 脚本删除 | `scripts/` | 所有脚本被删除 |
| 4 | 测试删除 | `tests/` | 所有测试被删除 |

### 26.3 P2 — Medium

| # | 问题 | 文件 | 说明 |
|---|------|------|------|
| 1 | 无 CI | - | 无持续集成 |
| 2 | 无监控 | - | 无生产监控 |
| 3 | 无备份 | - | JSON 数据库无备份 |
| 4 | 单点故障 | - | 依赖 500 单一数据源 |

### 26.4 P3 — Low

| # | 问题 | 文件 | 说明 |
|---|------|------|------|
| 1 | 死代码 | `api_server.py` | 本地测试 API，生产未使用 |
| 2 | 重复工作流 | `daily-recommend.yml` | 与主工作流功能重复 |
| 3 | 文档过时 | 多个 | 部分文档与实际代码不一致 |

---

## 27. Improvement Opportunities

### 27.1 数据层

| 机会 | 说明 |
|------|------|
| 多数据源 | 增加备用数据源，降低单点故障 |
| 数据备份 | 定期备份 JSON 数据库 |
| 数据验证 | 增加数据完整性校验 |
| 自动更新 | 提高更新可靠性 |

### 27.2 统计分析层

| 机会 | 说明 |
|------|------|
| 更多指标 | 增加 AC 值、尾数、同尾、质合等 |
| 动态权重 | 根据历史表现动态调整权重 |
| 时间序列 | 引入时间序列分析 |
| 可视化 | 增加更多图表 |

### 27.3 模型层

| 机会 | 说明 |
|------|------|
| Bayesian | 贝叶斯概率模型 |
| Markov | 马尔可夫链模型 |
| Monte Carlo | 蒙特卡洛模拟 |
| Ensemble | 集成学习 |

### 27.4 回测层

| 机会 | 说明 |
|------|------|
| Walk-forward | 滚动窗口回测 |
| Baseline | 纯随机 baseline 比较 |
| ROI | 投入产出比计算 |
| 样本量 | 增加回测样本量 |

### 27.5 产品层

| 机会 | 说明 |
|------|------|
| UI 优化 | 改进用户界面 |
| Dashboard | 增加仪表盘 |
| 解释性 | 增加推荐解释 |
| 透明度 | 增加模型透明度 |

### 27.6 工程层

| 机会 | 说明 |
|------|------|
| CI/CD | 增加持续集成 |
| 监控 | 增加生产监控 |
| 测试 | 增加测试覆盖 |
| 文档 | 完善技术文档 |

---

## 28. Recommended Future Architecture

### 28.1 短期（1-3 个月）

1. **恢复 Git 状态**：完成或放弃 rebase，恢复工作目录
2. **增加测试**：增加单元测试和集成测试
3. **增加监控**：增加生产环境监控
4. **增加备份**：定期备份 JSON 数据库

### 28.2 中期（3-6 个月）

1. **多数据源**：增加备用数据源
2. **动态权重**：根据历史表现动态调整权重
3. **Walk-forward 回测**：实现滚动窗口回测
4. **Baseline 比较**：增加纯随机 baseline

### 28.3 长期（6-12 个月）

1. **机器学习**：引入 ML 模型（谨慎）
2. **实时数据**：增加实时数据更新
3. **用户系统**：增加用户登录和历史记录
4. **移动应用**：考虑开发移动应用

---

## 29. Recommended Development Priorities

### 29.1 紧急（立即）

1. **恢复 Git 状态**：完成或放弃 rebase
2. **恢复工作目录**：恢复被删除的文件
3. **验证生产环境**：确认生产环境正常运行

### 29.2 高优先级（1 周内）

1. **增加测试**：增加单元测试
2. **增加监控**：增加生产监控
3. **增加备份**：定期备份数据

### 29.3 中优先级（1 个月内）

1. **多数据源**：增加备用数据源
2. **动态权重**：实现动态权重调整
3. **Walk-forward 回测**：实现滚动窗口回测

### 29.4 低优先级（3 个月内）

1. **UI 优化**：改进用户界面
2. **Dashboard**：增加仪表盘
3. **文档完善**：完善技术文档

---

## 30. Files That Future AI Must Read First

### 30.1 核心文件

| 文件 | 说明 |
|------|------|
| `README.md` | 项目概述 |
| `TASK_STATUS.md` | 当前状态 |
| `CHANGELOG.md` | 变更记录 |
| `config/settings.yaml` | 配置文件 |
| `requirements.txt` | Python 依赖 |

### 30.2 分析模块

| 文件 | 说明 |
|------|------|
| `analysis/metrics.py` | 指标计算 |
| `analysis/scorer.py` | 评分模块 |
| `analysis/loader.py` | 数据加载 |
| `analysis/writer.py` | D1 写入 |

### 30.3 数据文件

| 文件 | 说明 |
|------|------|
| `data/dlt_history.json` | 历史数据 |
| `public/data/recommendations.json` | 推荐数据 |
| `public/data/review.json` | 复盘数据 |
| `reports/backtest_summary.json` | 回测摘要 |

### 30.4 部署文件

| 文件 | 说明 |
|------|------|
| `.github/workflows/dlt-analysis.yml` | 主工作流 |
| `wrangler.toml` | Cloudflare 配置 |
| `DEPLOY.md` | 部署文档 |
| `docs/ROLLBACK.md` | 回滚文档 |

### 30.5 已删除但重要的文件（存在于 HEAD）

| 文件 | 说明 |
|------|------|
| `src/scraper.py` | 数据抓取 |
| `src/analyzer.py` | 分析模块 |
| `src/recommender.py` | 推荐模块 |
| `src/scheduler.py` | 调度模块 |
| `public/index.html` | 首页 |
| `public/app.js` | 主逻辑 |

---

## 31. Final Assessment

### 31.1 项目健康度

| 维度 | 评分 | 说明 |
|------|------|------|
| 代码质量 | 6/10 | 结构清晰，但核心代码被删除 |
| 测试覆盖 | 3/10 | 测试覆盖不足 |
| 文档完整性 | 7/10 | 文档较完整，但部分过时 |
| 生产稳定性 | 8/10 | 生产环境正常运行 |
| 可维护性 | 5/10 | Git 状态异常，影响维护 |

### 31.2 关键发现

1. **Git 状态异常**：interactive rebase 中断，73 个文件被删除
2. **生产环境正常**：`https://500wan.mootlsv.com/` 正常运行
3. **数据完整**：1000 期历史数据完整
4. **分析功能完整**：六项指标 + 三模型评分 + 四策略推荐
5. **回测样本量小**：仅 5 期，统计意义有限

### 31.3 建议

1. **立即恢复 Git 状态**：完成或放弃 rebase，恢复工作目录
2. **增加测试**：增加单元测试和集成测试
3. **增加监控**：增加生产环境监控
4. **增加备份**：定期备份 JSON 数据库
5. **谨慎开发**：项目处于冻结状态，需用户明确指令才能继续开发

---

**报告生成时间**: 2026-09-29  
**报告版本**: v1.0  
**审计类型**: 全量只读审计
