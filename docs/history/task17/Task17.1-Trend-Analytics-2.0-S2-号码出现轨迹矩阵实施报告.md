# Task 17.1 S2 号码出现轨迹矩阵实施报告

> 任务：Task 17.1-Trend-Analytics-2.0 S2（号码出现轨迹矩阵）｜日期：2026-08-19
> 状态：**实施完成并验证通过，未 commit、未 deploy**
> 约束遵守：未开发 S3-S6、未改 workflow、未改数据结构、前端即时计算

---

## 一、实施内容

### 1.1 数据模型（`buildOccurrenceMatrix`，纯函数）

```js
// 输出契约
{
  groupRule: { key, label, min, max, count, positional },  // 组规则参数化
  period: N,                                                // 窗口期数
  issues: [...窗口内升序],                                  // 横轴期号
  numbers: [                                                // 纵轴号码，每号一行
    { number, cells: [{appeared: bool}...], curOmit, count }
  ]
}
```
- 由 `GROUP_RULES` 驱动，支持前区（35 号）/后区（12 号）；未来双色球/3D/快乐8 改组规则即可复用；
- `curOmit` = 该号码当前连续未出现期数，`count` = 窗口内出现次数。

### 1.2 渲染（`renderOccurrenceMatrix`，HTML 表格）

| 设计点 | 实现 |
| --- | --- |
| 横轴 | 期号表头（每 5 期显示后 3 位，title 含完整期号+日期） |
| 纵轴 | 号码行（sticky 左列） |
| 命中格 | **号码（大字）+ 当前遗漏（小字）**，径向渐变圆点突出 |
| 未命中格 | 遗漏色阶行背景（前区紫系 / 后区蓝系） |
| 最新一期 | 表头 + 命中格 `is-latest` 高亮 |
| 当前遗漏 | 行尾「遗漏」汇总列（>0 琥珀高亮） |
| 无连线 | **无任何跨点连线 / SVG / polyline**（Task 17.1 产品约束） |
| 交互 | 命中格带 `data-issue/data-date/data-num/data-omit` → `bindTrendTooltip` 复用零改动 |
| 最近 N 期 | 复用 `period-switch`（50/100/300/1000）联动 |
| 移动端 | 外层 `.trend-scroll` 横向滚动 |

### 1.3 HTML/CSS 调整

- `trend-v2.html`：旧「前区/后区轨迹」两卡片 → 新「🔢 号码出现轨迹矩阵」卡片（`#sec-occurrence` + `occurrence-container`），锚点导航同步更新；
- `trend-v2.css`：新增 `.ocm-*` 系列样式 + 新图例色块（`#sec-occurrence .miss-s1/2/3`）；
- `occurrence-container` 由 S1 的 hidden 预留变为正式卡片；其余 3 个容器（omission/heat/sum-span）保持 hidden 预留。

---

## 二、验证结果（Phase 4）

| # | 验证项 | 结果 |
| --- | --- | --- |
| 1 | 语法 / HTML 平衡 | ✅ 通过 |
| 2 | 前区 35 行 × 100 期，每期恰 5 命中 | ✅ |
| 3 | 后区 12 行，每期恰 2 命中 | ✅ |
| 4 | 最新一期命中号 curOmit=0 | ✅ |
| 5 | 渲染：命中格含号码+遗漏小字、is-latest 高亮、无 svg/polyline | ✅ |
| 6 | 渲染行结构（1 表头 + 35 数据行） | ✅ |
| 7 | tooltip 在新矩阵命中格工作（data-* 属性兼容） | ✅ |
| 8 | 页面级 init：前后区矩阵渲染、其余区块（热度/遗漏/奇偶/大小）不回归 | ✅ 8/8 |
| 9 | 5 页面可达 | ✅ 全部 200 |
| 10 | 改动范围 | ✅ 仅 trend-v2 三文件 |
| 11 | workflow / Python / config / 数据 | ✅ 零改动 |

---

## 三、改动范围

```
 M public/trend-v2.js   # buildOccurrenceMatrix + renderOccurrenceMatrix 实现 + draw 接入
 M public/trend-v2.html # 旧轨迹卡片 → 号码出现轨迹矩阵卡片 + 锚点更新
 M public/trend-v2.css  # ocm 系列样式 + 图例色块
── 合计 3 文件 ──
```

---

## 四、下一步（S3 待指令）

- `omission-container` 已预留，S3 实现遗漏趋势分析（当前/最大/平均双条对比 + 遗漏排行）；
- 本轮矩阵已含每号当前遗漏列，S3 在此基础上扩展最大/平均与变化趋势。

---

*本报告为 S2 实施输出，未 commit、未 deploy、未开发 S3-S6。完成后停止。*
