# Task 17.1 Trend Analytics 2.0 S1 实施报告

> 任务：Task 17.1-Trend-Analytics-2.0 S1（基础框架重构）｜日期：2026-08-19
> 状态：**实施完成并验证通过，未 commit、未 deploy**
> 原则遵守：不开发 S2-S6；只做 loadData()、基础数据结构、renderOccurrenceMatrix 空框架 + HTML/CSS 调整

---

## 一、实施内容

### 1.1 旧连线方案移除（Task 17.1 产品调整落地）

| 位置 | 处理 |
| --- | --- |
| `trend-v2.js` `drawTrendLines` 函数 | **整函数删除**（原 193-237 行，polyline 连线） |
| `trend-v2.js` `renderTrajectoryHTML` | 移除 `<div class="trend-wrap">` 与 `<svg class="trend-lines">` 包裹 |
| `trend-v2.js` `draw()` 中两处 `drawTrendLines(...)` 调用 | 删除 |
| `trend-v2.js` API 导出 `drawTrendLines` | 删除 |
| `trend-v2.css` `.trend-wrap` / `.trend-lines` | 删除 |

**保留资产**（G-1 有价值部分，未退回）：命中格号码文本、表头期号/日期 title、遗漏色阶 miss-lv0-4、`bindTrendTooltip` hover 详情、`calculate*` 纯函数族。

### 1.2 新骨架（本阶段只做框架）

- **`GROUP_RULES`**：组规则参数化（front 5/35、back 2/12，含 `positional` 字段）——为双色球/3D/快乐8 扩展打基础；
- **`loadData()`**：统一数据加载入口，返回 `Promise<{ issues, meta }>`；
  - `issues`：按期号升序（排序逻辑内聚）；
  - `meta`：`{ cover, issueRange, frontTotal, backTotal, sourceName, updatedAt }`（源数据覆盖/数量等）；
- **`renderOccurrenceMatrix(container, data, opts)`**：空框架（S2 实现），带数据契约注释与「禁止装饰连线」约束注释，当前安全空操作不报错；
- **`init()` 改用 `loadData()`**（替代原内联 loadJSON 逻辑）。

### 1.3 HTML/CSS 调整

- `trend-v2.html`：预留 4 个新视图容器（`hidden`，不显示空内容，不影响用户体验）：
  ```
  occurrence-container  omission-container
  heat-container        sum-span-container
  ```
- `trend-v2.css`：仅移除旧连线样式，页面风格不变；
- 现有区块（概览/时间范围/前后区轨迹/热度/遗漏/奇偶/大小）原样保留，功能不回归。

---

## 二、验证结果（S1-4）

| # | 验证项 | 结果 |
| --- | --- | --- |
| 1 | trend 页面正常打开 | ✅ 本地服务器 trend-v2.html 200；页面级 init 模拟 8/8（概览/轨迹/热度/遗漏/奇偶/大小全部渲染，无报错） |
| 2 | 不存在 drawTrendLines | ✅ 全文件 grep 无残留（js/css/html） |
| 3 | 不存在 polyline 趋势连线 | ✅ 无 `polyline`/`createElementNS`/`trend-lines`/`trend-wrap` 残留 |
| 4 | 数据加载正常 | ✅ `loadData()` 真实数据 1000 期、升序、meta 正确 |
| 5 | hover tooltip 不受影响 | ✅ `bindTrendTooltip` 正常绑定与显示 |
| 6 | 其他页面无影响 | ✅ git diff 仅 trend-v2 三文件；index/pick/score/my 页面 200 |

**运行时套件 15/15 PASS**：loadData 契约、GROUP_RULES、renderOccurrenceMatrix 空框架、轨迹无 svg 包裹、tooltip 等。

---

## 三、改动范围

```
 M public/trend-v2.js   （+/- 净减：删除连线 + 新增骨架）
 M public/trend-v2.html （+6：4 个 hidden 容器）
 M public/trend-v2.css  （-13：移除 .trend-wrap/.trend-lines）
── 合计 3 文件，+59 / -76 ──
```

**未触碰**：其他前端页面、数据 JSON、workflow、Python、config。

---

## 四、下一步（S2 待指令）

- `renderOccurrenceMatrix` 空框架已就位，S2 实现号码出现轨迹矩阵（格内号码 + 遗漏小字 + 热冷色 + 重号框 + 行遗漏色阶，**无任何装饰连线**）；
- 数据契约：`{ groupRule, issues, hits: bool[rows][cols], perNumber: [...] }`。

---

*本报告为 S1 实施输出，未 commit、未 deploy、未开发 S2-S6。完成后停止。*
