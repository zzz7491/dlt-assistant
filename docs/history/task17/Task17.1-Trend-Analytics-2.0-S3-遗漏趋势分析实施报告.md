# Task 17.1 S3 遗漏趋势分析 实施报告

> 阶段：Task 17.1 Trend Analytics 2.0 · S3（遗漏趋势分析）
> 日期：2026-08-19
> 范围：仅 `public/trend-v2.{js,html,css}`，纯前端，数据唯一来源 `./data/dlt_history.json`
> 状态：✅ 实施完成 · 验证通过 · **未部署 / 未 commit / 未进入 S4**

---

## 一、设计确认回顾（用户指令）

| # | 决策 | 本次落实 |
|---|------|----------|
| 1 | S2 前区遗漏表保留，S3 在其基础上增强，不破坏已有功能 | ✅ `sec-front-missing`（遗漏表）原样保留；S3 新增独立 `#sec-omission` 区域 |
| 2 | 新增后区遗漏镜像模块 | ✅ 前区 / 后区 6 个容器全部镜像渲染 |
| 3 | 遗漏变化图采用方案 A（横向条形/排名，无 SVG sparkline） | ✅ `renderOmissionRanking` 纯 HTML 条形排名，零 SVG |
| 4 | 时间范围保持 period 切换联动 | ✅ `renderMissingAnalysis()` 在 `draw()` 内、`period` 闭包驱动 |

**实施原则（禁止项）全部遵守**：未改 `dlt_history.json`、未改 workflow、未改推荐算法、未改选号页、未删 S2 轨迹矩阵、未加无意义动画。

---

## 二、实施内容

### 2.1 JS（`trend-v2.js`）

**新增 `buildOmissionProfile(issues, period, groupRule)`（纯函数）**
- 复用既有 `calculateMissing()` 与 `calculateHot()`，**未复制任何遗漏计算逻辑**；
- 仅额外补充「末次出现期号」（`lastAppearIssue`，窗口内反向位置检索，非重算）与「趋势」（`trend`，当前遗漏相对均值偏离方向）；
- 输出契约：
  ```js
  { number, currentOmission, maxOmission, avgOmission,
    lastAppearIssue, appearCount, trend /* up|down|flat */ }
  ```
- 已加入 `api` 导出供测试/复用。

**新增 `renderOmissionRanking(container, profiles, mode, kind)`（模块级渲染器）**
- `mode`：`"current"`（当前遗漏倒序，条形色阶=遗漏档位）/ `"change"`（当前−平均 倒序，正▲偏冷紫 / 负▼偏热琥珀）/ `"max"`（最大遗漏倒序，深紫）；
- `kind`：`"front"` / `"back"`，号码徽标红/蓝镜像；
- 纯横向条形排名，**无 SVG、无动画**。

**新增 `renderMissingAnalysis()`（init 内编排）**
- 调用 `buildOmissionProfile` 生成前后区画像，分别渲染 6 个容器；
- 在 `draw()` 末尾调用，自动跟随 `period` 联动；
- `window.__trendIssues` 复用 S2 已挂载的全量数据，无额外加载。

**`draw()` 变更**：在既然后区大小趋势渲染后新增 `renderMissingAnalysis();`（编号 ⑧）。

### 2.2 HTML（`trend-v2.html`）

- 将预留下的隐藏 `#omission-container` 替换为正式区域 `#sec-omission`，含三个子块：
  - ① **当前遗漏排行**：前区（01–35）/ 后区（01–12）
  - ② **遗漏变化排名**：前区 / 后区（附「正▲偏冷 / 负▼偏热」说明）
  - ③ **长期遗漏统计**：前区 / 后区
- `#heat-container` / `#sum-span-container` 仍 `hidden` 保留，供 S4/S5 启用；
- S2 矩阵 `#sec-occurrence` 结构**未改动**；
- 锚点导航新增「⏳ 遗漏趋势」→ `#sec-omission`。

### 2.3 CSS（`trend-v2.css`）

- `.sub-h` / `.sub-h2` 子标题层级（沿用品牌紫）；
- `.omission-scroll` 限定高度（340px / 移动 300px）内纵向滚动——兼顾信息密度与手机可读；
- `.om-row` / `.om-num` / `.om-track` / `.om-bar` / `.om-val` 条形排名布局；
- 色阶：**当前遗漏**沿用琥珀系（与遗漏表 `miss-lv0..4` 一致）；**变化排名**冷紫(`up`)/热琥珀(`down`)/灰(`flat`)；**长期遗漏**深紫(`long`)；
- 前后区镜像：`.om-num.f` 红 / `.om-num.b` 蓝；
- 表格优先、无 `transition` 动画、无 `transform` 装饰。

---

## 三、约束遵守自查

| 禁止项 | 结果 |
|--------|------|
| 修改 `dlt_history.json` | ✅ 未触 |
| 修改 workflow | ✅ 未触 |
| 修改推荐算法 | ✅ 未触 |
| 修改选号页 | ✅ 未触（`pick.*` 无改动） |
| 删除 S2 号码轨迹矩阵 | ✅ 保留（`#sec-occurrence` 完整） |
| 添加无意义动画 | ✅ 无动画 |

---

## 四、Phase 4 验证结果

### 4.1 数据套件（`node .verify_tmp/s3_verify.js`）：**24/24 PASS**
- 前区 35 / 后区 12 画像齐全，7 字段完整；
- `currentOmission` 与 `calculateMissing.cur` 一致、`appearCount` 与 `calculateHot.count` 一致（**复用正确性**）；
- `lastAppearIssue` 抽样正确、`trend` 计算逻辑正确；
- `renderOmissionRanking` 三模式均正确输出 35/12 行，色阶/箭头/符号值齐全；
- 回归：既有 `calculateMissing` / `calculateHot` / `buildOccurrenceMatrix` 未被破坏。

### 4.2 全页烟雾测试（`node .verify_tmp/s3_smoke.js`，vm + DOM stub，模拟 `fetch` 加载 1000 期真实数据）：**全部 PASS**
1. ✅ **S2 矩阵仍正常**：`#ocm-front` / `#ocm-back` 均渲染 `ocm-table`；
2. ✅ **前区遗漏正常**：`#omission-current-front` 等 6 容器均填充 `om-row`；
3. ✅ **后区遗漏正常**：前后区镜像渲染；
4. ✅ **period 切换有效**：模拟「最近50期」后，前区当前遗漏均 ≤50、矩阵列数 ≤50（联动生效强校验）；
5. ✅ **数据来源仍是 `dlt_history.json`**：`loadData()` 仍 `fetch('./data/dlt_history.json')`，无写死；
6. ✅ **5 个页面无回归**：仅 `trend-v2.html` 引用 `trend-v2.js`；`index/pick/score/my/trend(.html)` 均未引用，改动零外溢。

---

## 五、⚠️ 持续性风险提示（R1，待你决策）

S1 + S2 + S3 全部改动**仍未 commit**。今晚 21:45 GitHub Actions（开奖日自动部署）会用仓库 `master`（当前 HEAD = `0eaa1e7`，仅含 G-1）覆盖趋势页，使 S1/S2/S3 成果丢失。

本报告**按指令仅执行到「实施+验证+报告」，未部署、未 commit、未进入 S4**。如需固化，请在合适时机告知执行 Git 固化（commit + push）。

---

## 六、改动文件清单

| 文件 | 类型 | 说明 |
|------|------|------|
| `public/trend-v2.js` | 修改 | +`buildOmissionProfile` / +`renderOmissionRanking` / +`renderMissingAnalysis`；`draw()` 新增调用；api 导出补充 |
| `public/trend-v2.html` | 修改 | `#sec-omission` 区域（① 当前 ② 变化 ③ 长期，前后区镜像）；锚点新增 |
| `public/trend-v2.css` | 修改 | 条形排名样式（PC 清晰 / 手机可读 / 表格优先 / 无动画） |

> 验证脚本：`public/` 同级 `.verify_tmp/s3_verify.js`、`.verify_tmp/s3_smoke.js`（已被 `.gitignore` 忽略，不影响部署）。
