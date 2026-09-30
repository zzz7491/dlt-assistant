# dlt-assistant 当前架构分析报告

> 任务：Task 17.0-Platform-Template · 阶段 1（纯只读盘点）
> 日期：2026-08-19 ｜ 范围：仅大乐透项目 dlt-assistant ｜ 未修改任何代码/配置/部署

---

## 一、项目概况

| 项 | 值 |
| --- | --- |
| Git 版本 | `master @ d1417f2`（与远端一致） |
| 部署版本 | Cloudflare Pages Production `7b6a1b17` |
| 模型版本 | `C-2-D-v1`（D 综合评分策略） |
| 数据规模 | 1000 期历史开奖（最新 26093） |
| 自动化 | GitHub Actions 每日 + 开奖日双 cron |
| 运行时 | Python 3.13（分析端）+ 原生 JS（展示端）+ Cloudflare D1（只读 API 层） |

---

## 二、目录结构全景

```
dlt-assistant/
├── .github/workflows/dlt-analysis.yml   # 每日自动化（抓取→分析→推荐→D1→回写→部署）
├── config/settings.yaml                 # 唯一业务配置（号码规则/窗口/权重/开关）
├── data/dlt_history.json                # 主历史数据（JSON，1000 期）
├── public/                              # Cloudflare Pages 静态站点
│   ├── index.html / app.js              # 首页仪表盘（最新开奖/推荐/热冷/统计）
│   ├── score.html / score.js / score.css# 数据分析页（时间范围/前区后区评分 TOP10）
│   ├── pick.html / pick.js / pick.css   # 智能选号页（A/B/C/D 四策略）
│   ├── trend-v2.html / js / css         # 趋势分析 2.0（轨迹/热度/遗漏/奇偶/大小）
│   ├── trend.html / trend.js            # 旧版跳转壳（仅跳转 trend-v2）
│   ├── my.html / my.js                  # 我的方案（localStorage 收藏/偏好）
│   ├── style.css                        # 全局样式（统一导航 .site-nav / .site-header）
│   ├── storage.js                       # localStorage 工具
│   ├── data/                            # dlt_history.json + recommendations.json（前端数据源）
│   ├── reports/                         # 每日报告 md + validation_report.md
│   └── assets/og-cover.png
├── src/                                 # Python 核心
│   ├── scheduler.py                     # 编排入口（run_once 全链路）
│   ├── scraper.py                       # 数据抓取（500 彩票网 HTML）
│   ├── database.py                      # JSON 存取（load/save）
│   ├── analyzer.py                      # 统计引擎（analyze + 4 个专用分析函数）
│   ├── recommender.py                   # 推荐引擎（A/B/C/D 策略函数）
│   ├── scorer.py                        # 综合评分（number/combo 双层因子）
│   ├── recommendations.py               # 推荐记录管理（去重/落盘/next_issue）
│   ├── reporter.py                      # Markdown 报告生成
│   ├── validator.py                     # 开奖验证（推荐 vs 真实开奖）
│   ├── backtest.py                      # 回测（命中统计/因素分析）
│   ├── reflection.py                    # 复盘（单期复盘/因素三态/结论）
│   ├── experiment.py                    # 权重实验（walk-forward/grid/validation）
│   └── notifier/                        # 通知（base 抽象 + feishu 实现）
├── scripts/                             # D1 运维脚本（独立可跑，不污染 src）
│   ├── update_dlt_d1.py                 # 每日增量写 D1（dlt_draws）
│   ├── analysis_run.py                  # 分析结果写 D1（dlt_analysis/dlt_scores）
│   ├── write_recommendations_d1.py      # 推荐一期固定写入（INSERT OR IGNORE 锁定）
│   ├── export_recommendations_json.py   # D1 锁定值导出 public/data/recommendations.json
│   ├── import_full_history.py           # 全历史导入 D1
│   └── test_import_dlt.py               # 导入管道小规模测试
├── functions/api/                       # Cloudflare Pages Functions（只读 API）
│   ├── issues.ts                        # GET /api/issues 历史开奖（D1）
│   ├── analysis.ts                      # GET /api/analysis 指标缓存（D1）
│   ├── scores.ts                        # GET /api/scores 评分缓存（D1）
│   └── summary.ts                       # GET /api/summary 摘要（D1）
├── migrations/0001_init_dlt.sql         # D1 四表 DDL
├── charts/generate.py                   # matplotlib 图表（默认关闭）
├── reports/                             # backtest/reflection/weight 实验产物
├── wrangler.toml                        # Pages 项目 + D1 绑定（binding=DB）
└── requirements.txt                     # requests/bs4/pyyaml + 可选扩展
```

---

## 三、数据流

### 主链路（每日自动运行）

```
scraper.run(fetch 500彩票网)
  → database.save(data/dlt_history.json)
  → analyzer.analyze(热冷/遗漏/奇偶/大小/连号/区间)
  → analyzer 专用统计(overlap/temperature/missing/structure/sum_span)
  → recommender.recommend(A/B/C/D 四策略)
  → recommendations.save(reports/recommendations.json 完整版)
  → validator.validate(开奖验证)
  → backtest.run_backtest(回测)
  → reflection.run_reflect(复盘)
  → reporter.build_report(reports/report_YYYYMMDD.md)
  → workflow: cp data → public/data
  → scripts.update_dlt_d1 / analysis_run / write_recommendations_d1 / export_recommendations_json
  → workflow: git commit+push → wrangler pages deploy
```

### 展示链路

```
public/data/dlt_history.json + recommendations.json
  → app.js / score.js / pick.js / trend-v2.js / my.js 读取渲染
functions/api/*.ts（D1 只读 API，备用数据通道）
  → 与静态 JSON 同构，供未来长历史/大数据场景切换
```

### 双文件推荐体系

- `reports/recommendations.json`：完整版（含 D 策略 `model_version/score_total/basis`），供回测/复盘消费；
- `public/data/recommendations.json`：前端精简版（A/B/C/D 号码），由 D1 锁定值导出，避免每日重随机变化。

---

## 四、分析模块（statistics）

`src/analyzer.py` 全部为**纯函数**（输入 issues + cfg → 输出统计 dict），无副作用：

| 函数 | 分析内容 | 是否大乐透耦合 |
| --- | --- | --- |
| `analyze` | 频率/热号/冷号/当前遗漏/最大遗漏/奇偶/大小/连号/区间（front/back 双组） | 前/后区双组结构耦合 |
| `analyze_previous_overlap` | 上期号码继承统计 | 通用 |
| `analyze_number_temperature` | 近期热号（窗口） | 通用 |
| `analyze_missing_cycle` | 遗漏周期 | 通用 |
| `analyze_structure_distribution` | 奇偶/大小/区间分布 | 区间划分耦合规则 |
| `analyze_sum_span` | 和值/跨度分位数 | 通用（和值/跨度对任何彩票均适用） |

**关键发现**：分析层的大乐透耦合集中在「front/back 双组」假设与「区间划分（front_zones=5 / back_zones=2）」；号码上下限已参数化（`front_min/max`、`back_min/max`）。

---

## 五、推荐模块（strategies）

`src/recommender.py`：四策略函数统一签名 `(analysis, cfg, rng) → combo`，通过 `_STRATEGY_FUNCS` 字典分发：

| 策略 | 实现 | 耦合点 |
| --- | --- | --- |
| A-均衡统计型 | `_strategy_balanced` | 前区取 5、边界 18（大小分界） |
| B-冷热组合型 | `_strategy_hotcold` | 前区取 5 |
| C-纯随机娱乐型 | `_strategy_random` | `range(1,36)`/`range(1,13)` 硬编码 |
| D-综合评分型 | `_strategy_scored` | 候选池 `top_front=15/top_back=8` 参数化 |

`src/scorer.py`：双层评分（可完整复用）——
- 单号分：heat/missing/trend/inherit（inherit 硬上限 15%）
- 组合分：inherit_match/odd_even_match/big_small_match/zone_match/sum_span_match（各 0.20）
- 中性分 `NEUTRAL=50`，缺失数据安全降级

---

## 六、前端展示模块（5 页面）

| 页面 | 职责 | 数据依赖 | 大乐透耦合 |
| --- | --- | --- | --- |
| index | 首页仪表盘：最新开奖/数据覆盖/四策略推荐/热冷/奇偶/连号 | dlt_history + recommendations | 前 5 后 2 球渲染、文案 |
| score | 数据分析：时间范围 + 前/后区评分 TOP10 | dlt_history | 前后区 |
| pick | 智能选号：四策略选号 + 收藏 | dlt_history + recommendations + localStorage | 前后区、规则文案 |
| trend-v2 | 趋势分析：轨迹/热度/遗漏/奇偶/大小 | dlt_history | 前后区、边界值 |
| my | 我的方案：收藏/偏好（localStorage） | 本地存储 | 低 |

**趋势页现状（阶段 3 重点）**：`trend-v2.js` 用 HTML `<table>` 渲染轨迹——命中格为 `<td class="cell hit-f">`（无号码文本）、遗漏格为分级底色；**无连线、无 hover 详情、无十字定位、无时间轴交互、无号码显示**（视觉即「圆点/色块」），与成熟数据分析站差距明显。

**通用元素**：统一导航 `.site-nav`、统一 header、风险横幅、免责声明、品牌色 `#6d28d9`（紫）、球号样式 `.ball-row`、`storage.js` 收藏工具——这些均已组件化且与彩票品种无关，可直接继承。

---

## 七、自动化与配置

### GitHub Actions（.github/workflows/dlt-analysis.yml）

```
schedule: 每日 02:00 UTC(北京10:00) + 开奖日 13:45 UTC(北京21:45)
workflow_dispatch: 手动
步骤：checkout → python setup → pip install → scheduler --once
  → update_dlt_d1（增量写 D1，容错跳过）
  → analysis_run（分析/评分写 D1，容错跳过）
  → cp data→public/data
  → write_recommendations_d1（推荐一期固定，INSERT OR IGNORE）
  → export_recommendations_json（D1→public/data 精简版）
  → cp reports→public/reports
  → git commit+push（自动回写）
  → wrangler pages deploy（缺 token 则跳过）
```

### 配置（config/settings.yaml）

已参数化的通用项：`scrape.source/base_url/timeout`、`database.path`、`analysis.front_min/max/back_min/max/front_zones/back_zones/recent_window`、`recommend.combos_per_strategy/weights(完整 G0)/top_front/top_back`、`report.filename_fmt`、`notify.feishu`、`charts.enabled`、`validate.enabled`。

**耦合点**：`front/back` 双组字段命名、`front_zones=5/back_zones=2` 默认值、`source="500"` 单一数据源、报告标题「大乐透」。

---

## 八、数据格式定义

### dlt_history.json
```json
{ "updated_at": "...", "source": "500", "count": 1000,
  "issues": [ { "issue": "26093", "date": "2026-08-17",
                "front": [8,10,22,26,29], "back": [3,10] } ] }
```

### recommendations.json（完整版）
```json
[ { "date", "target_issue", "strategy", "idx", "front": [5], "back": [2],
    "model_version": "C-2-D-v1", "score_total": 38.87,
    "basis": { "heat", "missing", "trend", "inherit",
               "structure": { "inherit_match","odd_even_match",
                              "big_small_match","zone_match","sum_span_match" } } } ]
```

### D1 四表（migrations/0001_init_dlt.sql）
| 表 | 内容 | 备注 |
| --- | --- | --- |
| `dlt_draws` | 全历史开奖 | issue/issue_num 双字段、front1-5/back1-2 CHECK 约束 |
| `dlt_analysis` | 指标缓存 | UNIQUE(period,kind,metric,version) |
| `dlt_scores` | 评分结果 | UNIQUE(period,kind,num,model_type,weight_version) |
| `dlt_recommendations` | 推荐历史 | UNIQUE(target_issue,strategy,idx) 一期固定 |

---

## 九、架构评价

### 已具备的平台化基础（可直接继承）
1. **纯函数统计层**：analyzer/scorer 无副作用，输入数据输出统计，天然可复用；
2. **策略分发机制**：`_STRATEGY_FUNCS` 字典注册制，新增策略只需加函数+注册；
3. **配置集中化**：号码范围/权重/窗口全部在 settings.yaml，无散落硬编码；
4. **前后端数据契约**：JSON 结构统一，前端纯读取渲染；
5. **三层数据通路**：JSON 主库 + D1 只读 API + 前端静态数据，可平滑演进；
6. **自动化闭环**：抓取→分析→推荐→验证→报告→部署一条龙。

### 大乐透强耦合点（模板化必须处理）
1. **双组号码结构**（front/back）：贯穿 analyzer/recommender/scorer/前端/D1 表；
2. **scraper 单一数据源**：500 彩票网 HTML 解析、期号 YYNNN 与跨年逻辑；
3. **选号规则硬编码**：`range(1,36)`/`range(1,13)`、边界 18、组合选 5/2；
4. **前端文案与渲染**：5 页面全部写死「大乐透」、球数、区间；
5. **reporter 报告结构**：章节写死（频率/热冷/遗漏/奇偶/大小/连号/区间/推荐/验证）；
6. **workflow 路径写死**：dlt-assistant 项目名、data/dlt_history.json。

### 风险提示
- 全部为静态 JSON，1000 期上限（`recent_issues: 1000`）——长历史需 D1 通道；
- 无数据质量自动检测（F-3 已设计 health_check.py 未实施）；
- workflow 失败无主动告警（F-2 已分析）；
- 趋势页功能单薄，是用户感知度最高的短板。

---

## 十、结论

dlt-assistant 是**单品种（大乐透）垂直闭环**的成熟实现：分析层和策略层耦合度低、可复用度高，但**号码结构模型、抓取器、前端渲染三处强耦合**是升级为「彩票数据分析平台模板」的主要障碍。平台化的核心工作 = 抽象「号码规则模型」（lottery rule schema）+ 数据提供者接口 + 前端模板引擎，详见《Lottery Analytics Platform v1.0 产品设计方案》。
