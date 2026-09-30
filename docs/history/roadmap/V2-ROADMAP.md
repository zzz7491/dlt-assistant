# 大乐透娱乐分析助手 · v2.0 产品升级路线

> **依据**：未来产品发展规划（`PRODUCT-PLAN.md`）
> **状态**：规划文档，**暂不开发**；当前保持 **v1.3 稳定运行**
> **升级目标**：打造更专业的「大乐透历史数据智能分析平台」
> **定位升级**：从「历史统计 + 简单推荐」→「多维数据分析 + 趋势可视化 + 用户互动推荐」

---

## 一、历史走势图系统（重点）

目标：增加 1000 期真实开奖走势图。

### 1. 前区号码走势图
- 35 个号码
- 最近 1000 期开奖轨迹
- 每期开出号码位置
- 热冷变化
- 遗漏变化
- 每个号码出现轨迹 / 连续遗漏 / 出现频率 / 热度变化

形态：专业彩票走势图 —— **横轴：期号 / 纵轴：号码**；颜色区分：红球出现 / 遗漏周期 / 连续走势。

### 2. 后区走势图
- 12 个号码历史轨迹
- 高频号码
- 长遗漏号码
- 周期变化
- **蓝球冷热 / 奇偶趋势 / 大小趋势**

### 3. 时间维度（两图通用）
最近 **50 期 / 100 期 / 300 期 / 1000 期** 四档切换（阶段10.1 已实现 100/300/1000，未来补 50 档与更多分析维度）。

---

## 二、多源开奖数据系统

- **主源**：500彩票网
- **备用**：中国体彩网、其他公开历史数据源
- **目的**：避免单一数据源风险
- **设计**：数据源自动检测——正常使用主源，失败自动切换备用源
- **数据验证**（所有来源都必须通过）：
  - 期号验证
  - 日期验证
  - 红球数量验证（前区 = 5）
  - 蓝球数量验证（后区 = 2）
  - 重复号码验证

---

## 三、达人推荐数据综合分析（未来重点）

收集公开网络中的大乐透达人推荐数据：
- 彩票论坛公开推荐
- 彩票公众号公开推荐
- 网络公开分析文章

分析：
- 推荐号码统计：哪些号码被多人推荐？
- 哪些号码长期热门？
- 达人推荐集中区域？

输出：**「网络热度推荐指数」**

处理流程：
```
达人推荐数据（论坛 / 公众号 / 文章）
   ↓
号码统计（哪些号码被多人推荐）
   ↓
出现次数排行
   ↓
与历史模型结合
   ↓
综合娱乐推荐
```

输出示例：
```
本期热门推荐号码：12 16 19 28 33
来源：
  历史模型：12 出现概率较高
  达人推荐：12 被 15 个来源推荐
```

⚠️ **注意**：不能直接认为达人预测有效，只作为娱乐参考。

---

## 四、智能综合推荐系统升级

- **现状**：A/B/C 三策略（均衡统计 / 冷热组合 / 纯随机）
- **未来**：增加「综合推荐模型」

参考因素（8 项）：
1. 历史 1000 期统计
2. 当前冷热状态
3. 遗漏周期
4. 最近走势
5. 奇偶比例
6. 大小比例
7. 连号概率
8. 网络推荐热度

生成**综合评分**，例如：
```
号码：16
历史热度：★★★★★
近期遗漏：★★★
网络推荐：★★★★
```
评分公式：`号码评分 = 历史频率 + 近期热度 + 遗漏周期 + 冷热平衡 + 组合概率`
最终生成：**综合娱乐推荐 TOP10**。

> 💡 综合推荐模型由「**分析引擎**（第十二章）」承载：评分逻辑、权重配置、多模型与结果落库（`dlt_scores`）详见第十二章。

⚠️ 必须定位「娱乐分析」，不是预测。

---

## 五、用户选号功能

### 1. 手动选号
- 用户自己选择：前区 5 个号码 + 后区 2 个号码
- 系统分析：历史出现次数 / 当前冷热 / 遗漏情况 / 相似历史组合
- 输出：**号码分析报告**

### 2. 机选推荐
- 按钮：「随机生成」
- 生成：随机号码 / 智能过滤号码 / 娱乐组合
- 模式：
  - **普通机选**：纯随机生成
  - **智能机选**：根据冷热比例 / 奇偶比例 / 大小比例生成

### 3. 选号输出示例
用户选择前区 `01 05 12 20 33` + 后区 `03 09` → 系统分析：历史出现次数 / 最近遗漏 / 组合情况 → 输出「你的号码历史表现分析」。

### 4. 选号助手 v1.0 设计（阶段 15 Task 3.0 · 2026-08-16 规划）

> 定位：**非预测工具**，仅历史统计娱乐参考。全页面强制免责「仅娱乐分析，不代表预测中奖」；禁用「预测/必中/概率」术语。

**四大功能**：

1. **普通随机选号**：前区 35 选 5 + 后区 12 选 2（不重复、升序），纯随机无分析干预，支持 1~5 注；标注「随机生成，与历史数据无关」
2. **智能统计风格选号**：基于分析引擎指标做**风格化约束组合**（非预测）——前区冷热 2:2:1（🔥热/⚖平衡/❄冷三分位池）、奇偶 3:2 或 2:3、大小 2:3 或 3:2（01-17/18-35）、三区间（1-12/13-24/25-35）各 ≥1、连号 ≤1 组；后区奇偶 1:1、大小 1:1；标注「按历史统计风格组合，非预测」
3. **手动号码历史表现分析**：用户输入前区 5 + 后区 2（校验数量/范围/去重）→ 输出「号码历史表现报告」——每号码出现次数/最近遗漏/热冷标签 + 组合维度（奇偶/大小/区间/和值/连号）；口径与 score.js 一致；定位为历史统计而非中奖评估
4. **智能补全**：用户已选部分号码（前区 2-4、后区 0-1）→ 按低遗漏热门池 + 奇偶/大小/区间均衡约束补全为完整 5+2，附补全依据

**实现**：独立 `public/pick.html` + `pick.css` + `pick.js`（自包含选号引擎，复用分析引擎指标口径，node 可测）；不修改任何现有页面/后端/数据。

---

## 六、用户体验升级：首页仪表盘

首页展示（完整产品闭环）：
```
最新开奖
   ↓
数据覆盖
   ↓
趋势图
   ↓
智能推荐
   ↓
选号工具
```

---

## 七、技术路线要求（硬性约束）

**禁止：**
- ❌ 大规模重构
- ❌ 删除已有功能
- ❌ 改变 JSON 结构导致前端失效
- ❌ 引入复杂后端

**优先：**
- ✅ Python 自动任务
- ✅ JSON 数据
- ✅ 静态网页
- ✅ Cloudflare Pages
- ✅ GitHub Actions

---

## 开发纪律（v2.0 启动前必须）

下一阶段开发前，先重新评估：
1. 数据结构是否需要升级
2. 是否增加走势图数据层
3. 是否增加多源采集层
4. 是否增加用户交互模块

且必须按序执行：
```
读取项目结构 → 制定任务清单 → 只读检查 → 再修改
```

---

## 八、建议开发路线（阶段顺序，不要跳步）

| 阶段 | 内容 | 状态/方向 |
|------|------|----------|
| 阶段 11 | 产品规划记录（v1.4 规划文档） | ✅ 完成 |
| 阶段 12 | 走势图增强（trend-v2：前区轨迹/遗漏/热度、后区冷热/奇偶/大小） | ✅ 已完成上线 |
| 阶段 13 | 综合评分模型（score：7 维评分 + TOP10 + 透明分解） | ✅ 已完成上线 |
| 阶段 14 | **历史数据中心建设**（Cloudflare D1 全历史开奖数据库：dlt_draws/analysis/scores/recommendations 四表，全量导入 + 每日增量） | V3 主线 · 暂不开发 |
| 阶段 15 | **分析引擎升级**（综合评分模型基于全历史 + 多模型 standard/cold-hot/expert；选号助手 v1.8 方向；与 dlt_scores/dlt_analysis 打通） | 规划（见第十二章） |
| 阶段 16 | **数据增强与轨 B 服务端分析**（多源数据融合：官方校验 / 达人推荐热度；Python 分析任务 → dlt_analysis/dlt_scores/dlt_recommendations → /api 扩展；轨 A 即时 + 轨 B 缓存双轨） | 规划（见第十二章） |
| 阶段 17 | 用户系统建设（注册/登录/收藏号码/分析记录/个人方案/偏好） | 规划 · 暂不开发 |

## 九、产品定位与开发原则

**定位**：不是彩票预测软件、不是保证中奖工具；是 **大乐透历史数据分析工具 / 彩票爱好者数据研究工具 / 娱乐选号辅助工具**。所有页面必须保留免责声明。

**升级原则**：
1. 不影响当前稳定自动运行系统
2. 新功能优先独立模块
3. 尽量不修改核心数据流程
4. 前端展示优先独立页面
5. 所有数据必须来自真实开奖数据
6. 所有推荐必须标注「娱乐分析」

---

## 十、数据架构升级：Cloudflare D1 长期历史开奖数据库（V3 方向 · 暂不开发）

> **状态**：已纳入 V2/V3 路线规划，**当前阶段不开发**。2026-08-16 记录。

### 目标
- 将现有 1000 期 JSON 数据迁移至 **Cloudflare D1**（托管 SQLite 数据库）
- 导入**大乐透全部历史开奖数据**（2007 年至今，约 2700+ 期），建立长期历史开奖数据库
- 作为 **综合分析 / 评分模型 / 走势图 / 达人融合推荐 的唯一基础数据源**，不绑定固定期数

### 模式
- **一次性全量导入**：迁移脚本抓取全历史 → 写入 D1
- **每日增量更新**：GitHub Actions 每日抓最新开奖 → D1 upsert（按期号去重）

### D1 数据表设计（四表，2026-08-16 阶段 14 规划细化）

**① `dlt_draws`（全历史开奖数据 · 权威库）**
```
id INTEGER PRIMARY KEY
issue TEXT UNIQUE NOT NULL      -- 5 位期号（YYNNN）
date TEXT NOT NULL              -- 开奖日期
front1..front5 INTEGER NOT NULL -- 前区 5 码（01-35）
back1..back2 INTEGER NOT NULL   -- 后区 2 码（01-12）
source TEXT DEFAULT '500'       -- 数据来源
created_at / updated_at
```

**② `dlt_analysis`（分析缓存）**
```
id INTEGER PRIMARY KEY
period INTEGER NOT NULL          -- 分析窗口期数（如 50/100/300/1000/全部）
kind TEXT NOT NULL               -- front / back
metric TEXT NOT NULL             -- 指标名（frequency/omit/oddEven/bigSmall/consec...）
payload TEXT NOT NULL            -- JSON 结果缓存
computed_at TEXT
UNIQUE(period, kind, metric)
```

**③ `dlt_scores`（综合评分结果）**
```
id INTEGER PRIMARY KEY
period INTEGER NOT NULL
kind TEXT NOT NULL               -- front / back
num INTEGER NOT NULL             -- 号码 01-35 / 01-12
total INTEGER NOT NULL           -- 总分 0-100
parts TEXT NOT NULL              -- 七维分解 JSON（frequency/recentHot/missing/balance/oddEven/bigSmall/structure）
tag TEXT NOT NULL                -- 🔥热号 / ⚖平衡 / ❄冷号
weight_version TEXT              -- 权重版本（如 default）
computed_at TEXT
UNIQUE(period, kind, num, weight_version)
```

**④ `dlt_recommendations`（推荐历史记录）**
```
id INTEGER PRIMARY KEY
target_issue TEXT NOT NULL       -- 目标期号
strategy TEXT NOT NULL           -- A/B/C 及策略名
front TEXT NOT NULL / back TEXT  -- 推荐号码 JSON
score_total INTEGER              -- 可选：综合评分
date TEXT
UNIQUE(target_issue, strategy, idx)
```

### 迁移与更新模式
- **一次全量导入**：迁移脚本抓取 500 源 **2007 年至今**全部开奖记录 → 校验（期号/日期/前5/后2/去重）→ 写入 `dlt_draws`（`INSERT OR IGNORE` 按期号去重）
- **每日增量更新**：GitHub Actions 每日抓最新一期 → 与 `dlt_draws` 最新期号比对 → 仅插入新增期（upsert）
- `dlt_analysis` / `dlt_scores` / `dlt_recommendations` 随分析/评分/推荐任务写入（缓存 + 历史记录）

### 架构影响（启动前必须重新评估）
- 现状：纯静态 JSON + 浏览器 fetch（无后端）
- D1 方案：需 **Cloudflare Pages Functions / Worker 数据 API**（如 `/api/issues?range=…`），或保留 JSON 快照导出 + D1 为权威库
- ⚠️ **与「技术路线硬约束」存在张力**：当前原则禁止「引入复杂后端」；D1 引入数据库与 API 层，启动时需在路线层面裁决（是否将 D1 定位为轻量数据服务而非复杂后端）

### 影响面
- `src/scraper.py` / `database.py` / `scheduler.py`（写入与读取目标）
- 前端 `app.js` / `trend-v2.js` / `score.js`（fetch 路径 → API 或仍导 JSON）
- 各分析模块读取层（不绑定固定期数，支持任意窗口）

### 风险
- 打破纯静态架构（引入数据库/API 层）
- D1 免费额度与查询限制（每日增量写入量小，可承受；需验证）
- 全历史期号连续性、迁移正确性（需验证层）
- 需与「保持稳定架构 / 不引入复杂后台」原则的冲突裁决

### 启动前检查清单（纳入阶段 14 四要素）
1. 是否保留 JSON 快照作为静态降级（前端零改动路径）
2. D1 schema 与迁移脚本设计（四表：dlt_draws / dlt_analysis / dlt_scores / dlt_recommendations）
3. 每日增量写入在 GitHub Actions 的认证方式（CLOUDFLARE_API_TOKEN / D1 API）
4. 全历史数据源验证（500 源是否支持 2007 年起的全部期号）

### 详细设计（阶段 14 Task 2，2026-08-16 规划；Task 2.1 修订）

**DDL（四表，Task 2.1 修订版）**：`dlt_draws(issue TEXT UNIQUE, issue_num INTEGER UNIQUE【数字排序字段，避免字符串期号排序风险】, date, front1-5 CHECK 1-35, back1-2 CHECK 1-12, source, verified, created_at/updated_at)`；`dlt_analysis(period, kind, metric, version TEXT DEFAULT 'v1'【算法版本，缓存并存】, payload JSON, computed_at, UNIQUE(period,kind,metric,version))`；`dlt_scores(period, kind, num, total 0-100, parts JSON, tag, model_type TEXT DEFAULT 'standard'【standard/cold-hot/expert 多模型并存】, weight_version, UNIQUE(period,kind,num,model_type,weight_version))`；`dlt_recommendations(target_issue, strategy, idx, front JSON, back JSON, score_total, date, UNIQUE(target_issue,strategy,idx))`。索引：四 UNIQUE 即主查询索引；`dlt_draws` 可加 date 索引（按需）。

**全量导入**：抓 500 源 07001（2007-05-28 上市首期）~ 26365 → 解析（15 td 位置法）→ 五重校验 → `INSERT OR IGNORE` 分批执行（幂等可重跑）。

**每日增量**：workflow 每日抓最新一期 → 校验 → D1 upsert（INSERT OR IGNORE）→ 同步 `database.save` JSON（双写）→ 可选重算评分/分析缓存 → commit + Pages 部署。

**JSON 共存**：`public/data/dlt_history.json` 维持 1000 期快照（现有前端零改动降级层）；全历史能力经 `/api` 提供；`/api/issues` 返回与 JSON 同构 `{updated_at,source,count,issues[]}`。

**API 契约（Pages Functions 只读接口，游客可用）**：`GET /api/summary`（count/首末期/来源/时间）、`GET /api/issues?range=50|100|300|1000|all&after=期号`、`GET /api/scores?kind=front|back&period=…&model_type=standard|cold-hot|expert（默认 standard）`（按 total 降序，响应含 model_type）、`GET /api/recommendations?target=…`（与 recommendations.json 同构）、`GET /api/analysis?kind&period&metric&version`（缓存读，响应含 version）；错误 `{error}`，只读响应可 `Cache-Control: public, max-age=300`；写接口仅 CI/内部（令牌），`_middleware` 预留鉴权（用户系统阶段 17）。

---

## 十一、用户体系规划（V3/V4 方向 · 暂不开发）

> **状态**：2026-08-16 记录。当前保持**游客访问模式**（无需登录即可使用全部分析/评分/走势图功能），**不提前引入认证、数据库和权限复杂度**。

### 目标（未来用户注册管理系统）
- **账号体系**：注册 / 登录 / 个人中心
- **收藏号码**：保存用户关注的号码
- **历史分析记录**：保留用户查过的分析/评分结果
- **个性化偏好**：默认时间档、主题、展示偏好
- **方案管理**：保存 / 命名 / 对比自选号码方案

### 建设时机（明确前提）
- 用户系统**建立在历史数据库（D1，阶段 14）和分析模型稳定之后**；
- 与阶段 16/17 衔接：
  - 阶段 16（多源融合）之前可先行：**轻量本地版**——localStorage 收藏/历史/偏好，游客可用、零后端
  - 阶段 17（正式用户系统）：D1 用户表 + 认证层 + 权限分层（见路线表）

### 影响面（启动前评估）
- D1 扩展表：`users` / `favorites` / `history` / `preferences` / `plans`
- 认证层：第三方 OAuth 或邮箱密码（哈希存储 / 令牌过期 / 防滥用）
- 前端：登录页 / 个人中心 / 收藏 / 方案管理页
- **游客模式保持可用**（不强制登录）

### 风险
- 认证与账号安全（密码哈希、JWT、防爆破）
- D1 多表关联查询与配额
- 用户数据隐私合规

### 原则
不提前引入复杂度；游客功能优先；用户系统在数据与分析稳定后按独立阶段推进。

---

## 十二、分析引擎规划（阶段 15 主线 · 规划修订 2026-08-16）

> **状态**：规划修订——与阶段 14 已建成的 D1 全历史数据架构对齐，定义「分析引擎」为模块化计算层。**暂不开发**。
> **定位**：历史数据研究工具的核心计算层（非预测）；所有推荐必须标注「娱乐分析」。

### 1. 数据流（与 D1 架构对齐）

```
D1 dlt_draws（全历史 2910 期，07001~26092）
   ↓ 窗口化（50 / 100 / 300 / 1000 / all —— 不绑定固定期数）
分析引擎（模块化指标计算）
   ├── 频率/热冷      calculateHot          → {num, count, omit}
   ├── 遗漏周期       calculateMissing      → {num, cur, max, avg}
   ├── 奇偶比例       calculateOddEven      → {odd%, even%}
   ├── 大小比例       calculateBigSmall     → {small%, big%}
   ├── 连号/区间      calculateConsec/zones → 组合结构
   └── 综合评分       score()               → 7 维度加权 0-100（透明分解）
   ↓
产物落库（阶段 15 可选服务端计算）：
   dlt_analysis（分析缓存：period/kind/metric/version）
   dlt_scores（评分结果：period/kind/num/total/parts/tag/model_type/weight_version）
   dlt_recommendations（推荐历史：target_issue/strategy/front/back/score_total）
   ↓
API 读取（已上线，游客可用）：
   /api/analysis?kind&period&metric&version（缓存读）
   /api/scores?kind&period&model_type（按 total 降序）
   → 前端页面（trend-v2 / score / 首页推荐）
```

### 2. 模块化设计（地基已具备）

- **前端纯函数（已上线、node 可测）**：
  - `trend-v2.js`：`sliceWindow / calculateHot / calculateMissing / calculateOddEven / calculateBigSmall / buildMatrices`
  - `score.js`：`SCORE_WEIGHTS` 配置化评分引擎（`scoreAll(issues, period, kind)` → `[{num,total,tag,parts}]`），`SCORE_VERSION`（scoreVersion/weightVersion/generatedFrom）
- **阶段 15 目标**：同一套指标/评分逻辑可平移为服务端计算（Python/TS），批量写入 D1 缓存，供全历史大数据量场景读取（前端保留即时计算作为降级）。

### 3. 窗口与版本（对应 D1 字段）

| 维度 | 设计 | D1 字段 |
|------|------|---------|
| 时间窗口 | 50 / 100 / 300 / 1000 / **all（全历史）** | `dlt_analysis.period` / `dlt_scores.period` |
| 算法版本 | 分析指标算法升级时可并存 | `dlt_analysis.version`（默认 'v1'） |
| 评分模型 | **standard 标准 / cold-hot 冷热 / expert 专家** 多模型并存 | `dlt_scores.model_type`（默认 'standard'） |
| 权重版本 | 权重调整可追踪 | `dlt_scores.weight_version` |

### 4. 综合评分模型（与第四章衔接）

- 7 维度权重配置（`SCORE_WEIGHTS`，禁止硬编码）：`frequency .25 / recentHot .20 / missing .15 / balance .15 / oddEven .10 / bigSmall .10 / structure .05`（总和 = 1）
- 每号码总分 0-100，**七项贡献分之和 = 总分**（透明可核对）
- 标签：🔥热号 / ⚖平衡 / ❄冷号（按窗口频率排名三分位）
- 修正机制：遗漏倒 U 形回摆（避免追超长遗漏）、冷热平衡修正（防热门霸榜）
- 输出：前区 TOP10 / 后区 TOP10（`/api/scores` 或前端即时计算）

### 5. 执行形态（双轨，游客优先）

| 轨 | 说明 | 状态 |
|----|------|------|
| **轨 A：前端即时** | 浏览器 fetch JSON/API → 纯函数计算（现有 `score.js` / `trend-v2.js`） | ✅ 已上线，零后端依赖 |
| **轨 B：服务端缓存** | 分析任务写入 `dlt_analysis` / `dlt_scores` → `/api` 读取 | 阶段 15 可选增强（全历史/复杂模型） |

原则：轨 A 保持可用（游客零依赖、降级兜底）；轨 B 作为大数据量增强，不破坏轨 A。

### 6. 阶段 15 交付定义（更新路线表）

1. **综合评分模型升级**：支持全历史窗口（`all`）+ 多模型（standard/cold-hot/expert）+ 评分结果落 `dlt_scores`（model_type/weight_version 可追踪）
2. **选号助手**（v1.8 方向）：手动选号分析（历史次数/冷热/遗漏/组合）、机选（普通随机 / 智能按冷热·奇偶·大小）——均基于分析引擎
3. **缓存打通（可选）**：分析引擎服务端计算 → `dlt_analysis` / `dlt_scores` → `/api/analysis`、`/api/scores`

### 7. 与本阶段已建成能力的关系

- 阶段 12（trend-v2）与阶段 13（score）的纯函数 = 分析引擎**轨 A 的现成实现**，直接作为阶段 15 的算法地基
- 阶段 14（D1 + `/api`）已提供数据源与只读通道；阶段 15 在此基础上扩展**全历史窗口**与**多模型**
- 不重复造轮子：不重写指标逻辑，只做「窗口扩展 + 模型扩展 + 可选落库」

### 8. 详细设计（阶段 15 Task 1 · 2026-08-16 规划）

> 分析引擎详细设计（仅文档，未写代码）。地基 = 已上线 trend-v2.js（指标纯函数）/ score.js（评分引擎）/ D1 + /api。

**① 设计目标**：模块化分析计算层；任意窗口（50/100/300/1000/all）；多评分模型（standard/cold-hot/expert）；算法版本可追踪；双轨执行（轨 A 前端即时 + 轨 B 服务端缓存）；非预测定位。

**② 架构**
```
数据层   D1 dlt_draws（2910 期） ↔ JSON 快照（1000 期，降级）
              ↓ sliceWindow(issues, N)
计算层   分析引擎
         ├─ 指标  calculateHot / Missing / OddEven / BigSmall / Consec / Zones
         ├─ 评分  score(kind, period, model_type) → [{num,total,tag,parts{7}}]
         └─ 推荐  现有 A/B/C + 综合 TOP10（score_total 关联）
输出层   轨 A：前端纯函数即时渲染（现网）｜轨 B：服务端 → dlt_analysis/dlt_scores → /api
```

**③ 核心数据结构**（与现有一致）：输入 `issues[]{issue,date,front[5],back[2]}`；`sliceWindow(issues,N)` 最近 N 期（all=全部）；`calculateHot→[{num,count,omit}]`、`calculateMissing→[{num,cur,max,avg}]`、`calculateOddEven→{odd,even,total}`、`calculateBigSmall→{small,big,total,boundary}`（前区 18/后区 6）、`calculateConsec→{rate,avg}`；`score→[{num,total,tag,parts{7}}]`（parts 七项贡献分之和 = total）。

**④ 指标规格**：频率 count（前区 Σ=5N、后区 Σ=2N 校验）；最近遗漏 omit（最新一期出现=0）；当前/最大/平均遗漏（连续未出现段统计）；奇偶占比；大小占比（boundary 参数化）；连号率（前区相邻差=1 组合出现期占比）；区间分布（1-12/13-24/25-35，Zones 预留）。

**⑤ 评分模型权重（SCORE_WEIGHTS，禁硬编码）**

| 维度 | standard | cold-hot | expert |
|------|----------|----------|--------|
| frequency | .25 | .20 | .20 |
| recentHot | .20 | .25 | .20 |
| missing | .15 | .15 | .15 |
| balance | .15 | .20 | .10 |
| oddEven | .10 | .10 | .10 |
| bigSmall | .10 | .05 | .10 |
| structure | .05 | .05 | .15 |
| **合计** | **1.00** | **1.00** | **1.00** |

归一化（0-100）：历史频率围绕均值 50、近期热度相对极值、遗漏倒 U 回摆、冷热三分位基分±微调、奇偶/大小占比、组合结构加权——公式与阶段 13 上线版本一致（不改已验证逻辑）。`total = round(Σ 权重×归一化分)`；`tag`：🔥热号/⚖平衡/❄冷号（频率三分位）。

**⑥ 窗口与版本**：`period`（50/100/300/1000/all）、`version`（算法版本，默认 v1）、`model_type`（standard/cold-hot/expert）、`weight_version`——对应 D1 `dlt_analysis`/`dlt_scores` 唯一约束字段。

**⑦ 双轨执行**：轨 A 浏览器纯函数（score.js/trend-v2.js，已上线，扩展 period=all 即可，2910 期性能 <50ms 已验证）；轨 B 服务端计算落库（可选增强）；同一规格两端实现、单测对照保证一致。

**⑧ API 契约（读侧，游客可用）**
```
GET /api/scores?kind=front|back&period=…&model_type=standard|cold-hot|expert
  → {weight_version, model_type, period, kind, updated_at, scores:[{num,total,tag,parts{7}}]}  # total 降序
GET /api/analysis?kind&period&metric=hot|missing|oddEven|bigSmall|consec&version=v1
  → {period, kind, metric, version, computed_at, payload}
```
写侧仅 CI/内部（令牌）；`_middleware` 预留鉴权（阶段 17）。

**⑨ 验收标准**：指标与 score.js/trend-v2.js 现有结果逐项一致；period=all（2910 期）计算 <50ms；三模型可切换、权重和=1、结果有区分度；双轨结果一致（对照测试）；手机 360-412px 无横向滚动；页面标注「娱乐分析」。

### 9. 分析引擎输出层：选号引擎（阶段 15 Task 3.0 · 2026-08-16 规划）

选号助手是分析引擎的**输出层应用**（非独立算法体系）：

```
分析引擎（指标：频率/热冷/遗漏/奇偶/大小/连号 + 评分）
   ↓
号码池（按指标分池：🔥热 / ⚖平衡 / ❄冷 · 奇偶池 · 大小池 · 区间池）
   ↓
组合生成（普通随机 / 智能风格约束 / 手动号码 / 补全）
   ↓
结构校验（数量 5+2 · 范围 1-35/1-12 · 去重 · 冷热 2:2:1 · 奇偶 · 大小 · 区间 · 连号 ≤1）
   ↓
选号助手（pick 页：机选 / 手动分析 / 补全 + 免责标注）
```

- 与第十二章第 8 节「详细设计」衔接：选号引擎复用同一套指标纯函数（轨 A 前端），组合生成是其上层封装
- 定位重申：**非预测工具**——组合约束仅为统计风格，不产生「中奖概率」、不承诺结果

### 10. 分析引擎服务端增强层（轨 B · 阶段 16 Task 0 规划 2026-08-16）

> 状态：规划同步，**暂不开发**。轨 B = 服务端缓存分析，是轨 A（前端即时）的**增强通道**，不替代、不破坏。

**① 整体架构（六层）**
```
数据采集层  500 源抓取（现有）｜ 多源校验（官方/公开）｜ 达人推荐公开数据（娱乐维度）
   ↓
数据存储层  D1：dlt_draws（权威 2910 期）+ 预留源校验表；JSON 快照（降级，永久保留）
   ↓
分析计算层  Python 分析任务（同规格复用轨 A 纯函数逻辑：指标/三模型评分/推荐/融合热度）
   ↓
缓存层      dlt_analysis（指标缓存）/ dlt_scores（评分）/ dlt_recommendations（推荐历史）
   ↓
API 输出层  /api/issues（已上线）｜ /api/scores /api/analysis /api/recommendations（规划）
   ↓
前端展示层  score / pick / trend-v2 / 首页 —— 默认轨 A 即时；大数据量/融合结果读轨 B 缓存
```

**② 轨 B 三表规划（DDL 已就绪，阶段 14 建表，无需改结构）**
- `dlt_analysis`：`period / kind / metric / version(默认 v1) / payload / computed_at`，UNIQUE(period,kind,metric,version)
- `dlt_scores`：`period / kind / num / total / parts / tag / model_type(standard|cold-hot|expert) / weight_version / computed_at`，UNIQUE(period,kind,num,model_type,weight_version)
- `dlt_recommendations`：`target_issue / strategy / idx / front / back / score_total / date`，UNIQUE(target_issue,strategy,idx)

**③ 多源数据融合方向**
- 官方开奖数据 ↔ 500 源**交叉校验**（期号/号码一致性，不一致以官方为准并标记）
- 历史统计数据（D1 自身分析结果）作为融合基线
- 用户行为数据（**匿名聚合**：页面/功能使用统计，localStorage 本地、零个人信息上传，不引入用户系统）
- 达人推荐公开数据（论坛/公众号/文章）→ 号码出现次数 → **网络热度指数**（仅娱乐统计维度，明确不信任预测）

**④ 自动化计算流程（workflow 每日）**
```
抓取增量 → 五重校验 → D1 upsert（dlt_draws）
  → 【新增】Python 分析任务：全窗口指标 → dlt_analysis；三模型评分 → dlt_scores；推荐 → dlt_recommendations（INSERT OR REPLACE 幂等）
  → JSON 快照同步（1000 期）→ 提交 → Pages 部署
  → API 读 D1 自动反映
容错：分析任务失败仅日志，不阻断抓取/提交/部署
```

**⑤ API 扩展规划（读侧，游客可用）**
```
GET /api/scores?kind&period&model_type&weight_version  → 评分缓存（total 降序）
GET /api/analysis?kind&period&metric&version          → 指标缓存
GET /api/recommendations?target=…                     → 推荐历史
写侧仅 CI/内部（令牌）；_middleware 预留鉴权
```

**⑥ 风险控制**
- 不预测定位：轨 A/B/API 输出强制免责「仅娱乐分析，不代表预测中奖」
- 不输出中奖概率：任何页面/API 不提供中奖概率数字
- 数据可靠性：多源交叉校验 + 五重验证 + version/weight_version 版本追踪 + computed_at 审计
- 隐私边界：匿名聚合、localStorage 本地、零个人信息；用户系统（阶段 17）之前不引入
- 多源合规：公开数据仅统计展示并注明来源，不采集非公开信息

---

*本路线文档仅作规划记录，未随代码仓库提交；启动对应阶段时按约定确认后纳入版本管理。*
