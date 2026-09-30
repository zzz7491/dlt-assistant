# Lottery Analytics Platform v1.0 产品设计方案

> 任务：Task 17.0-Platform-Template · 阶段 2/3/4（纯只读分析 + 设计，未写任何代码）
> 日期：2026-08-19 ｜ 定位：把大乐透项目升级为「彩票数据分析平台基础模板」
> 前置文档：《dlt-assistant 当前架构分析报告》（DLT-ARCHITECTURE-ANALYSIS-2026-08-19.md）

---

## 一、当前大乐透项目资产

| 资产类别 | 内容 | 成熟度 |
| --- | --- | --- |
| 数据链路 | scraper → JSON → D1 双通道，1000 期 | 稳定 |
| 统计引擎 | analyzer.py 8+ 纯函数（热冷/遗漏/奇偶/大小/连号/区间/和值/跨度） | 稳定、纯函数、低耦合 |
| 评分模型 | scorer.py 双层因子（C-2-D-v1，权重 G0 可配置） | 稳定 |
| 策略系统 | A/B/C/D 四策略，`_STRATEGY_FUNCS` 注册制 | 稳定 |
| 验证体系 | validator/backtest/reflection 三件套 + weight 实验框架 | 稳定 |
| 前端 | 5 页面原生 JS 静态站，统一导航/品牌/免责声明 | 稳定，但页面结构写死 |
| 自动化 | GitHub Actions 双 cron + D1 增量 + 自动部署 | 稳定 |
| 只读 API | functions/api 四接口（D1 数据通道） | 已上线，仅大乐透 |

---

## 二、可复用模块（直接继承，无需重构）

1. **统计纯函数**：`analyze_number_temperature` / `analyze_missing_cycle` / `analyze_previous_overlap` / `analyze_sum_span`——接口 `(issues, cfg) → dict`，与彩票品种无关；
2. **评分模型 scorer.py**：单号四因子（heat/missing/trend/inherit）+ 组合五因子（inherit/odd_even/big_small/zone/sum_span），全部权重外部注入、缺失数据 NEUTRAL=50 安全降级；
3. **策略分发机制**：`_STRATEGY_FUNCS` 注册字典 + `recommend()` 统一入口（`stats` 可选，向后兼容）；
4. **验证三件套**：validator（命中比对）/ backtest（策略统计+因素分析）/ reflection（单期复盘+结论），读取统一推荐记录格式；
5. **配置体系**：settings.yaml 分层（scrape/database/analysis/recommend/report/notify/charts/validate），号码范围已参数化；
6. **前端基础件**：统一导航 `.site-nav`、品牌 header、风险横幅、免责声明、球号样式、`storage.js` 收藏工具、SEO/OG 模板；
7. **自动化模式**：workflow 步骤模板（分析→数据同步→推荐锁定→回写→部署）、推荐一期固定（D1 INSERT OR IGNORE）方案、双写容错模式；
8. **数据契约**：`issues[]` 结构（issue/date/front/back）、推荐记录结构、D1 四表设计范式。

---

## 三、需要重构部分（平台化的核心工作）

| # | 模块 | 现状耦合 | 重构方向 |
| --- | --- | --- | --- |
| R1 | **号码规则模型**（无） | 前/后区双组、数量/范围/分区散落在 settings 与代码 | 新增 `lottery_rule` 数据模型（组定义/数量/范围/可重复/是否有位） |
| R2 | **scraper 单一数据源** | 写死 500 彩票网 URL/HTML/期号/跨年 | 抽象 `lottery_data_provider` 接口，注册制多提供者 |
| R3 | **recommender 组数硬编码** | `len(front)<5`、`range(1,36)`、后区取 2 | 按 `lottery_rule` 动态生成（通用组合引擎） |
| R4 | **analyzer 双组假设** | front/back 双组贯穿 | 改为「按组遍历」，支持 1 组/2 组/多组 |
| R5 | **前端页面写死** | 5 页面文案/球数/区间硬编码 | 引入 runtime config（由 yaml 生成），模板渲染 |
| R6 | **reporter 章节写死** | 报告标题「大乐透」+ 固定章节 | 按规则模型动态生成标题与章节 |
| R7 | **D1 表名/字段** | `dlt_` 前缀、front1-5/back1-2 | 表结构按规则泛化（或保持每品种独立 schema） |
| R8 | **workflow 路径写死** | 项目名、数据文件名 | 参数化（workflow inputs / 多品种矩阵） |

---

## 四、彩票平台通用能力抽象设计

### 4.1 数据层：lottery_data_provider

**目标接口**（统一入口，多提供者注册）：

```
lottery_data_provider
├── registry.get_provider(lottery_id)          # 大乐透→500提供者 / 双色球→500提供者 / 福彩3D→官方源
├── provider.fetch_history(rule, range)         # → issues[]（统一结构）
├── provider.next_issue(latest_issue, rule)     # 期号推进（YYNNN 跨年 / 连续编号 / 每日）
└── provider.validate_row(raw)                  # 行级校验（范围/数量/重复）
```

**规则模型 lottery_rule**（核心抽象，yaml 描述）：

```yaml
lottery_id: dlt          # 大乐透
name: 大乐透
groups:                  # 1 或 2 组（3D 为 1 组 3 位）
  - key: front           # 组标识（大乐透/双色球用；单组可省略）
    count: 5             # 每期取几个
    min: 1
    max: 35
    unique: true         # 号码是否可重复（3D 可重复=false 场景）
    positional: false    # 是否有位置概念（3D/排列3 有）
  - key: back
    count: 2
    min: 1
    max: 12
    unique: true
issue:
  format: YYNNN          # YYNNN | 连续 | 每日
  yearly_reset: true
provider:                # 数据源
  name: "500彩票网"
  base_url: "https://datachart.500.com/dlt/history/newinc/history.php"
  parser: "500-history"  # 解析器注册名
analysis:
  zones_per_group:       # 每组区间划分（front:5, back:2）
  recent_window: 50
  big_small_boundary:    # 每组大小分界
recommend:
  combos_per_strategy: 1
  top_pool: {front: 15, back: 8}
  weights: G0            # 引用共享权重
schedule:                # 开奖频率（workflow cron 派生）
  draw_weekdays: [1,3,6]
```

**新增彩票 = 提供一份 yaml + 一个解析器**（若无现成解析器则注册 provider）。

### 4.2 分析引擎：statistics_engine

```
statistics_engine.analyze(issues, rule, cfg) → { per_group: {...}, cross: {...} }
```

| 指标 | 是否通用 | 说明 |
| --- | --- | --- |
| 热号 / 冷号 | ✅ | 按组统计频率，纯通用 |
| 遗漏分析 | ✅ | 当前/最大/平均遗漏，纯通用 |
| 奇偶分析 | ✅ | 按组，纯通用 |
| 大小分析 | ✅ | 分界来自 rule |
| 区间分析 | ✅ | 分区数来自 rule |
| 和值分析 | ✅ | 每组和值分位数（sum_span 已实现） |
| 跨度分析 | ✅ | 每组跨度分位数 |
| 连号分析 | ✅ | 升序集合型适用（3D 按位场景跳过） |
| 趋势分析 | ✅ | 轨迹矩阵按组生成 |
| **位置规律**（3D 新增） | ⚠️ 扩展 | `positional:true` 时按「位」统计每位号码分布（百/十/个） |

**改造原则**：现有 analyzer 函数保持签名，外层包一层「按组分发」；`positional` 品种增加位置维度输出（新增函数，不影响现有）。

### 4.3 策略系统：strategy_engine

```
strategy_engine.strategies = { A, B, C, D, ... }
strategy_engine.generate(lottery_id, analysis, cfg, stats, rng)
  → { strategy: [...combos] }   # combo 结构 = { groups: {front: [...], back: [...]} }
```

| 策略 | 通用化改造 | 3D 适配 |
| --- | --- | --- |
| A-均衡统计 | 组数量/候选数由 rule 驱动 | 按位加权抽样（位置规律替代集合均衡） |
| B-冷热组合 | 同上 | 按位热冷 |
| C-纯随机 | `range` 由 rule 驱动 | 按位可重复随机 |
| D-综合评分 | 组合遍历参数化（每组 TopN 候选池） | 位置版 scorer 或退化为单组结构评分 |

**未来扩展点**：
- **AI 策略**：接入 LLM/统计模型，输入历史统计特征 → 输出组合（策略接口不变）；
- **用户自定义策略**：前端规则编辑器（勾选指标/权重）→ 生成策略配置 → 后端执行；
- **历史回测策略**：将历史某期「获胜组合特征」作为生成模板（experiment.py 的 walk-forward 已打底）。

### 4.4 前端模板：Lottery Dashboard Template

**模板页面**（继承现有 5 页结构，全部配置驱动）：

| 页面 | 模板化内容 | 配置来源 |
| --- | --- | --- |
| 首页 | 最新开奖球（按组渲染）、推荐卡 2×2、热冷/奇偶/连号、报告索引 | rule + runtime config |
| 数据分析 | 时间范围 + 每组评分 TOP N | rule.groups |
| 智能选号 | 四策略 + 收藏 | rule + strategy_engine 输出 |
| 趋势分析 | 轨迹矩阵/热度/遗漏/奇偶/大小（2.0 升级，见阶段 3.2） | rule.groups |
| 我的方案 | localStorage 收藏/偏好（已通用） | 无 |

**runtime config 机制**（替代硬编码）：
- 构建期：`lottery_xxx.yaml` → `public/data/lottery-config.js`（`window.LOTTERY = {...}`）；
- 运行期：页面读取 `LOTTERY` 渲染标题、组数、球数、范围、分区、文案；
- 球组件 `<lottery-balls groups=...>`：按组渲染 N 球 + 颜色 + 升序/按位。

---

## 五、重点优化方向分析（阶段 3）

### 5.1 智能补全系统（设计，不开发）

**目标**：用户输入部分号码（如 `3,8,15,?,?`），系统按统计规律补全剩余号。

**输入解析**：
- 识别组（front/back）、已填号、空缺位置数；
- 校验：重复号/越界号/空缺数为 0 → 提示。

**补全算法（复用现有 scorer）**：
1. 约束过滤：剩余可选池 = 全池 − 已填号（unique 品种）;
2. 候选组合生成：对空缺位置做组合/排列枚举（按 `positional` 决定）;
3. 组合评分（复用 `calculate_combination_score` + 单号分）：
   - **和值范围**：补全后组合和值落入历史 p25–p75 高分；
   - **跨度**：同前（sum_span_stats 直接复用）；
   - **奇偶比例**：补全后比例贴近历史分布；
   - **大小比例**：分界由 rule 定；
   - **区间分布**：补全后各区覆盖度；
   - **热冷状态**：空缺号尽量热冷均衡（复用单号分）；
   - **位置规律**（3D）：每位历史频次加权；
4. 输出 Top N 补全方案 + 每方案 factor 明细（前端 basis 展示）。

**关键设计点**：
- 全量枚举在空缺 ≥3 时爆炸 → 用 scorer 的「候选池截断」（Top 15）+ 贪心/回溯；
- 实时性：前端调用静态数据本地计算（1000 期 JSON 足够）或 D1 API；
- 与 D 策略共用同一评分内核，保证一致性。

### 5.2 趋势分析 2.0 设计方案

**现状问题**：`trend-v2.js` 用 HTML 表格，命中格无号码、无连线、无 hover、无时间轴交互、无指标切换。

**目标（参考成熟数据分析站）**：

| 能力 | 设计 |
| --- | --- |
| 每个点显示号码 | 命中格内渲染 `02` 文本（替代空色块） |
| 趋势连线 | SVG `<polyline>` 连接各期命中点，突出号码轨迹走向 |
| 十字定位 | 跟随 hover 的十字参考线（当前列=当期，当前行=号码） |
| hover 详细数据 | tooltip：期号/日期/该期全部号码/该号当前遗漏/近 N 期频次 |
| 时间轴 | 底部期号刻度 + 日期，支持拖动/缩放窗口 |
| 热度颜色 | 命中格按频次分级着色（已有 miss-lvN 基础可扩展）；遗漏格按遗漏分级 |
| 可切换指标 | 轨迹 / 和值 / 跨度 / 奇偶 / 大小 多视图 tab |

**技术选型**：
- 渲染：原生 SVG（无依赖，兼容现有「零框架」约束）或轻量图表库（echarts 引入需评估体积）；
- 数据：`dlt_history.json`（1000 期 × 35 号 = 3.5 万格，SVG 直接渲染可行；超 3000 期需降采样/虚拟化）；
- 交互：事件委托 + 单 tooltip 复用（避免每格创建 DOM）。

**页面结构**：保留现有「时间范围/热度/遗漏/奇偶/大小」区块，轨迹区升级为 SVG 画布 + 指标 tab。

### 5.3 历史报告板块优化

**现状**：首页「历史报告」卡片列出静态链接（每日简报 + 验证报告），与顶部导航卡（数据分析/智能选号/趋势）内容有重复；报告链接硬编码日期（`report_20260816.md`）。

**结论：改造优于删除**，去重后分三块语义：

| 板块 | 内容 | 解决的重叠 |
| --- | --- | --- |
| **数据档案** | 数据覆盖/来源/期数/最新更新（动态读取 JSON） | 替代首页静态「数据覆盖」卡片文案 |
| **历史复盘** | 每日简报归档（按月折叠 + 最新一期置顶） | 移除硬编码日期链接，改为动态扫描 |
| **模型演进记录** | model_version（C-2-D-v1）/ 权重版本（G0）/ 算法变更日志 | 新增，体现平台成长 |

**删除项**：首页报告卡中的三个页面导航链接（与顶部导航重复，直接删）。

### 5.4 快速复制开发模板

**最终目标**：新增彩票 = `新增 lottery_xxx.yaml`（+ 必要时解析器）→ 自动生成全部页面/分析/推荐/报告。

**一键接入管线**：

```
① 提供 lottery_xxx.yaml（号码规则/数据接口/分析参数）
② 注册/复用 provider 解析器
③ 构建脚本生成：lottery-config.js（前端）+ 校验配置
④ 后端按 rule 跑 statistics_engine + strategy_engine（零代码）
⑤ 前端模板按 runtime config 渲染 5 页面（零代码）
⑥ 部署（多品种可复用同一 workflow，或矩阵并行）
```

**差异化清单**（各品种模板化难度）：
| 彩票 | 组结构 | 可复用度 | 特殊处理 |
| --- | --- | --- | --- |
| 双色球 | 6+1 | 高（同双组模型） | 后区取 1、开奖日 二四日 |
| 七乐彩 | 7 | 高（单组模型） | 无后区 |
| 福彩3D | 3 位 | 中 | `positional=true`、可重复、按位统计/策略 |
| 排列3/5 | 3/5 位 | 中 | 同 3D 位置模型 |
| 快乐8 | 20/80 | 中 | 单组大池、候选截断参数调大 |

---

## 六、未来开发路线

| 阶段 | 内容 | 依赖 | 建议排序 |
| --- | --- | --- | --- |
| P0 | **规则模型抽象**：`lottery_rule` 数据模型 + settings 迁移 + analyzer/recommender 参数化改造 | 无 | 1 |
| P0 | **数据层抽象**：lottery_data_provider 接口 + 500 解析器泛化 | P0-规则模型 | 2 |
| P1 | **前端模板化**：runtime config + 5 页面模板改造（保持大乐透线上不变） | P0 | 3 |
| P1 | **双色球试点接入**：新增 ssc.yaml + 解析器，验证全链路 | P0+P1 前端 | 4 |
| P1 | **趋势分析 2.0**：SVG 轨迹升级（号码/连线/hover/时间轴/指标切换） | 前端模板 | 5 |
| P2 | **智能补全系统**：输入解析 + scorer 复用 + Top N 方案 | P0 | 6 |
| P2 | **历史报告板块改造**：数据档案/历史复盘/模型演进 | 前端模板 | 7 |
| P3 | **健康检查**：health_check.py + 飞书告警（F-4，依赖用户 webhook） | 无 | 8 |
| P3 | **AI 策略 / 用户自定义策略 / 回测策略** | 策略引擎扩展 | 9 |

---

## 七、新增彩票接入流程（用户视角）

```
1. 复制模板配置    lottery_tpl.yaml → lottery_ssc.yaml
2. 修改规则字段    组数/数量/范围/期号格式/开奖日
3. 确认数据源      已有解析器？→ 复用；否则提供数据接口说明
4. 运行验证       python -m src.platform.validate --lottery ssc
5. 生成前端配置    自动产出 lottery-config.js
6. 部署            多品种共用 workflow 或独立站点
```

---

## 八、模板目录结构建议

```
lottery-platform/
├── lotteries/
│   ├── schema.yaml           # 规则模型 schema（字段约束/校验）
│   ├── dlt.yaml              # 大乐透（从 settings.yaml 迁移规则部分）
│   ├── ssc.yaml              # 双色球（试点）
│   └── fc3d.yaml             # 福彩3D（位置模型试点）
├── src/
│   ├── platform/
│   │   ├── rules.py          # lottery_rule 加载/校验
│   │   ├── provider.py       # lottery_data_provider 接口 + registry
│   │   ├── engine.py         # statistics_engine 按组分发
│   │   └── strategies.py     # strategy_engine 通用组合
│   ├── providers/            # 各数据源解析器（500/官方...）
│   ├── core/                 # 现有 analyzer/scorer/recommender/validator/backtest/reflection
│   └── scheduler.py          # 编排入口（--lottery 参数）
├── public/
│   ├── templates/            # 5 页面模板（lottery-config 驱动）
│   ├── data/                 # {lottery}/history.json + recommendations.json
│   └── lottery-config.js     # 构建产物
├── functions/api/            # 泛化只读 API（按 lottery_id 路由）
├── scripts/                  # 泛化 D1 脚本
└── workflows/                # 多品种自动化
```

**迁移策略**：保持大乐透线上稳定优先——先抽规则模型与参数化，前端用 runtime config 输出与现状等价的配置，逐步验证双色球，再上趋势 2.0。

---

## 九、开发优先级排序（最终建议）

| 优先级 | 任务 | 理由 |
| --- | --- | --- |
| **P0-1** | 规则模型抽象（lottery_rule + 参数化改造） | 一切模板化的地基；纯后端重构，线上行为不变可验证 |
| **P0-2** | 数据层抽象（lottery_data_provider + 解析器注册） | 支撑多品种数据接入 |
| **P1-1** | 前端模板化（runtime config 驱动 5 页） | 模板化的展示侧落地 |
| **P1-2** | 双色球试点接入 | 用真实第二品种验证全链路模板可行性 |
| **P1-3** | 趋势分析 2.0 | 用户感知最高的体验短板 |
| **P2-1** | 智能补全系统 | 强差异化功能，需规则模型就绪 |
| **P2-2** | 历史报告板块改造 | 低成本高整洁度 |
| **P3** | 健康检查 / 高级策略 | 长期演进 |

---

## 十、结论与下一步

dlt-assistant 已具备**分析层与策略层的高复用度**，升级为平台模板的核心工作是 **R1 规则模型抽象 + R2 数据层抽象 + R5 前端模板化** 三项重构，且均为「保持大乐透线上行为不变」的渐进式改造。

**建议的首个实施任务**：P0-1 规则模型抽象——新增 `lottery_rule` 数据模型，将 settings.yaml 的号码规则部分迁移为通用规则结构，使 analyzer/recommender/scorer 按组参数化运行，并以大乐透回归验证零行为变化。

---

*本方案为纯设计输出，未写任何代码、未修改任何文件。等待下一步指令确认后再进入实施。*
