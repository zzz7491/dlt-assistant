# Task 17.1 S4 热冷矩阵（Heat Map）产品设计方案

> **版本：** v1.0
> **日期：** 2026-08-20
> **范围：** 仅设计，不修改代码
> **产品约束：** 无装饰性图表 · 数据优先 · 参考成熟彩票网站

---

## 一、需求理解

### 1.1 设计目标
在现有 trend-v2.html 中新增「热冷矩阵」模块，以网格形式直观展示：
- **横向**：时间（期号）
- **纵向**：号码（前区 01-35 / 后区 01-12）
- **格内颜色**：当前周期内的出现频率（热→冷梯度）
- **额外标注**：升温/降温趋势箭头 + 当前排名

### 1.2 为什么需要热冷矩阵（差异化价值）
| 已有模块 | 信息覆盖 | 缺口 |
|---------|---------|------|
| S2 号码出现轨迹矩阵 | 某期是否命中（二元：是/否） | ❌ 无频率概念 |
| S3 遗漏趋势分析 | 当前遗漏量 / 变化方向 | ❌ 无历史频率对比 |
| 热度排行 | 按次数排序的列表 | ❌ 无时间维度 |

**热冷矩阵填补的核心缺口：在时间×号码二维平面上叠加频率强度信息。**

---

## 二、视觉设计规范

### 2.1 配色方案（参考 500彩票网 / 澳客网）

采用**单一色相深度渐变**（避免多色混淆），色相随"热→冷"递减：

```
热（高频）:  hsl(10, 85%, 55%)   ← 红色
           :  hsl(20, 80%, 62%)
           :  hsl(30, 75%, 68%)
温：        :  hsl(40, 60%, 75%)   ← 橙色偏黄
           :  hsl(50, 50%, 82%)
常温：      :  hsl(200, 30%, 90%)   ← 浅蓝灰
冷（低频）:  hsl(220, 20%, 95%)   ← 冷白
极冷：      :  #ffffff             ← 白色背景
```

**前区专用**：红橙梯度（hsl 10-40）
**后区专用**：蓝紫梯度（hsl 210-250），保持镜像对称

### 2.2 列宽与行高

| 元素 | 规格 |
|------|------|
| 每列宽度 | 22px（与 ocm 对齐） |
| 每行高度 | 26px |
| 表头 sticky | top: 0，白底，层级 z-index: 3 |
| 号码列 sticky | left: 0，宽 42px，层级 z-index: 2 |
| 最大列数 | 1000 期（横向滚动） |
| 最大行数 | 35（前区）/ 12（后区） |

### 2.3 响应式约束
- `max-height: 520px` + `overflow-y: auto`
- `overflow-x: auto` + `-webkit-overflow-scrolling: touch`
- 手机屏幕（≤480px）：列宽缩至 18px，行高缩至 22px

---

## 三、数据模型定义

### 3.1 输入
```js
// 复用 buildOccurrenceMatrix 的 w（窗口期号数组）
// GROUP_RULES[kind]（前区/后区规则）
// calculateHot(issues, period, kind) → [{num, count, omit}]
```

### 3.2 输出契约

```js
{
  groupRule: { key, label, min, max },  // 从 GROUP_RULES 复用
  period: number,                       // 当前窗口期数
  issues: [issue_obj],                  // 窗口期号升序
  numbers: [                            // 所有号码按 num 升序
    {
      num: number,                      // 号码 1-35 或 1-12
      cells: [                          // 每期一个格子数据
        { appeared: boolean, count: number, omit: number }
      ],
      totalAppear: number,              // 窗口期内出现总次数
      currentOmit: number,              // 当前遗漏
      freqRank: number,                 // 频率排名（1=最热）
      trend: "up" | "down" | "flat"     // 较上一周期升温/降温/持平
    }
  ]
}
```

### 3.3 频次计算逻辑
```
frequency = windowCount / expectedCount
expectedCount = windowSize / (groupRule.max - groupRule.min + 1)

colorLevel = floor(frequency * 6) → 映射到 6 级色阶
  0 = 极冷（白色）
  1 = 冷
  2 = 常温
  3 = 温
  4 = 偏热
  5 = 热（最深色）
```

### 3.4 趋势计算（相对上一周期）
```js
// 取 period*0.75 期作为"上一周期"基准
var prev = sliceWindow(issues, Math.floor(period * 0.75))
var currHot = calculateHot(issues, period, key)
var prevHot = calculateHot(prev, Math.floor(period * 0.75), key)
var prevMap = {}; prevHot.forEach(h => prevMap[h.num] = h.count)
// 比较当前 count 与上期 count
trend: curr > prev * 1.1 ? "up" : curr < prev * 0.9 ? "down" : "flat"
```

---

## 四、HTML 结构设计

### 4.1 插入位置
在 `<main id="content">` 内，紧跟 `#sec-occurrence` 之后：

```html
<!-- ② 热冷矩阵（S4） -->
<section class="card" id="sec-heatmap">
  <h2>🔥 热冷矩阵</h2>
  <p class="hint">横轴为期号 · 纵轴为号码 · 色深代表出现频率 · ▲升温 ▼降温</p>
  <div class="heatmap-wrapper">
    <div class="heatmap-section" id="hm-front"></div>
    <div class="heatmap-section" id="hm-back"></div>
  </div>
  <p class="trend-legend">
    <span class="legend-note">切换时间范围后下方联动更新 · 数据源：dlt_history.json</span>
  </p>
</section>
```

### 4.2 内部结构
```html
<div class="hm-group">
  <h3 class="sub-h">前区（01–35）</h3>
  <div class="hm-wrap" id="hm-front-table"></div>
</div>
<div class="hm-group">
  <h3 class="sub-h">后区（01–12）</h3>
  <div class="hm-wrap" id="hm-back-table"></div>
</div>
```

---

## 五、CSS 样式规范

### 5.1 核心样式

```css
/* ---- 热冷矩阵容器 ---- */
.heatmap-wrapper {
  display: flex;
  flex-direction: column;
  gap: 20px;
}
.heatmap-section:not(:first-child) { margin-top: 0; }

.hm-group { }
.hm-wrap {
  max-height: 520px;
  overflow: auto;
  -webkit-overflow-scrolling: touch;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: #fff;
}

/* ---- 热冷矩阵表格 ---- */
.hm-table {
  border-collapse: collapse;
  font-size: .7rem;
  white-space: nowrap;
}
.hm-table th, .hm-table td {
  width: 22px; min-width: 22px; height: 26px;
  text-align: center; padding: 0;
}
.hm-table thead th {
  position: sticky; top: 0; background: #fff; z-index: 3;
  font-size: .6rem; color: var(--muted);
  border-bottom: 1px solid var(--line);
}
.hm-table th.hm-issue.is-latest {
  color: var(--accent-deep); font-weight: 700;
  border-bottom: 2px solid var(--accent);
}
.hm-table th.corner {
  width: 42px; min-width: 42px;
  background: #fff; font-size: .66rem; color: var(--muted);
  position: sticky; left: 0; z-index: 2;
  border-right: 1px solid var(--line);
}
.hm-table th.num-cell {
  width: 42px; min-width: 42px;
  font-weight: 700; font-size: .68rem;
  position: sticky; left: 0; background: #fff; z-index: 2;
  border-right: 1px solid var(--line);
}
.hm-table th.num-cell.front { color: var(--front); }
.hm-table th.num-cell.back { color: var(--back); }

/* ---- 热力格子 ---- */
.hm-table td.hm-cell {
  border-bottom: 1px solid #f0f2f8;
  border-right: 1px solid #f0f2f8;
  cursor: default;
  transition: background .15s;
}
.hm-table td.hm-cell:hover {
  opacity: .85;
  box-shadow: inset 0 0 0 2px var(--accent-soft);
}
.hm-table td.hm-cell.is-latest {
  box-shadow: inset 0 0 0 2px var(--accent-soft);
}
.hm-table td.hm-cell .hm-num {
  display: block; font-size: .6rem; font-weight: 700; line-height: 1;
  color: rgba(255,255,255,.9);
}
.hm-table td.hm-cell .hm-rank {
  display: block; font-size: .5rem; line-height: 1;
  margin-top: 1px; opacity: .8;
}

/* ---- 色阶等级（前区：红橙梯度） ---- */
.hm-table[data-kind="front"] td.hm-lv5 { background: hsl(10, 85%, 55%); }
.hm-table[data-kind="front"] td.hm-lv4 { background: hsl(18, 80%, 62%); }
.hm-table[data-kind="front"] td.hm-lv3 { background: hsl(28, 75%, 68%); }
.hm-table[data-kind="front"] td.hm-lv2 { background: hsl(38, 60%, 75%); }
.hm-table[data-kind="front"] td.hm-lv1 { background: hsl(48, 50%, 84%); }
.hm-table[data-kind="front"] td.hm-lv0 { background: #fff; }

/* ---- 色阶等级（后区：蓝紫梯度） ---- */
.hm-table[data-kind="back"] td.hm-lv5 { background: hsl(220, 70%, 52%); }
.hm-table[data-kind="back"] td.hm-lv4 { background: hsl(228, 65%, 60%); }
.hm-table[data-kind="back"] td.hm-lv3 { background: hsl(236, 58%, 68%); }
.hm-table[data-kind="back"] td.hm-lv2 { background: hsl(242, 50%, 76%); }
.hm-table[data-kind="back"] td.hm-lv1 { background: hsl(248, 40%, 86%); }
.hm-table[data-kind="back"] td.hm-lv0 { background: #fff; }

/* ---- 趋势箭头 ---- */
.hm-arrow { font-size: .55rem; margin-left: 1px; }
.hm-arrow.up   { color: #e53e3e; }   /* 升温 → 红色箭头 */
.hm-arrow.down { color: #38a1db; }   /* 降温 → 蓝色箭头 */
.hm-arrow.flat { color: var(--muted); }

/* ---- Tooltip ---- */
.hm-tooltip {
  position: absolute;
  background: #1a1a2e;
  color: #fff;
  padding: 6px 10px;
  border-radius: 8px;
  font-size: .75rem;
  pointer-events: none;
  z-index: 100;
  white-space: nowrap;
  box-shadow: 0 4px 12px rgba(0,0,0,.25);
  display: none;
}
.hm-tooltip.show { display: block; }

/* ---- 小屏适配 ---- */
@media (max-width: 480px) {
  .hm-table th, .hm-table td { width: 18px; min-width: 18px; height: 22px; }
  .hm-table th.corner, .hm-table th.num-cell { width: 34px; min-width: 34px; }
  .hm-wrap { max-height: 360px; }
}
```

---

## 六、JavaScript 渲染逻辑

### 6.1 核心函数签名

```js
// 构建热冷数据模型
function buildHeatMap(issues, period, groupRule) {
  var w = sliceWindow(issues, period);
  var hot = calculateHot(issues, period, groupRule.key);
  var hotMap = {}; hot.forEach(h => hotMap[h.num] = h);
  
  // 计算上一周期热度（用于趋势判断）
  var prevPeriod = Math.max(50, Math.floor(period * 0.75));
  var prevHot = calculateHot(issues, prevPeriod, groupRule.key);
  var prevMap = {}; prevHot.forEach(h => prevMap[h.num] = h.count);
  
  // 按出现次数排序获取排名
  var sorted = hot.slice().sort((a,b) => b.count - a.count);
  var rankMap = {}; sorted.forEach((h,i) => rankMap[h.num] = i + 1);
  
  var out = { groupRule, period, issues: w, numbers: [] };
  for (var num = groupRule.min; num <= groupRule.max; num++) {
    var h = hotMap[num] || { count: 0, omit: period };
    var prev = prevMap[num] || 0;
    var trend = h.count > prev * 1.1 ? "up" :
                h.count < prev * 0.9 ? "down" : "flat";
    
    // 构造每期的格子数据
    var cells = [];
    var totalAppear = 0;
    for (var i = 0; i < w.length; i++) {
      var appeared = w[i][groupRule.key].indexOf(num) >= 0;
      if (appeared) totalAppear++;
      cells.push({ appeared, count: appeared ? 1 : 0 });
    }
    
    out.numbers.push({
      num, cells,
      totalAppear,
      currentOmit: h.omit,
      freqRank: rankMap[num] || 99,
      trend
    });
  }
  return out;
}

// 渲染热冷矩阵
function renderHeatMap(container, data, opts) {
  var rule = data.groupRule;
  var w = data.issues;
  var numCls = rule.key === "front" ? "front" : "back";
  var parts = ['<table class="hm-table" data-kind="' + rule.key + '"><thead><tr><th class="corner">' + rule.label + '</th>'];
  
  // 表头：期号（每5期显示后3位）
  for (var c = 0; c < w.length; c++) {
    var show = (c % 5 === 0) || (c === w.length - 1);
    var latest = c === w.length - 1;
    parts.push('<th class="hm-issue' + (latest ? ' is-latest' : '') + '" ' +
      'title="第' + w[c].issue + '期 · ' + w[c].date + '">' +
      (show ? w[c].issue.slice(2) : '') + '</th>');
  }
  parts.push('<th style="width:28px;min-width:28px">排名</th></tr></thead><tbody>');
  
  // 数据行
  data.numbers.forEach(function(row) {
    var colorLevel = calcColorLevel(row.totalAppear, w.length, rule.max - rule.min + 1);
    var arrowHtml = row.trend === "up" ? '<span class="hm-arrow up">▲</span>' :
                    row.trend === "down" ? '<span class="hm-arrow down">▼</span>' : '';
    parts.push('<tr>');
    parts.push('<th class="num-cell ' + numCls + '">' + pad2(row.num) + '</th>');
    
    row.cells.forEach(function(cell, ci) {
      var latest = ci === w.length - 1;
      if (cell.appeared) {
        parts.push('<td class="hm-cell hm-lv' + colorLevel + (latest ? ' is-latest' : '') + '"' +
          'data-issue="' + w[ci].issue + '" data-num="' + pad2(row.num) + '"' +
          'data-rank="' + row.freqRank + '"' +
          'data-trend="' + row.trend + '"' +
          ' title="第' + w[ci].issue + '期 · 号码' + pad2(row.num) + ' · 频率排名 #' + row.freqRank + '">' +
          '<span class="hm-num">' + pad2(row.num) + '</span></td>');
      } else {
        // 未出现：使用基础底色 + 透明度
        parts.push('<td class="hm-cell hm-lv' + colorLevel + '" style="background:' +
          getBaseColor(rule.key, colorLevel) + ';"></td>');
      }
    });
    
    parts.push('<td style="text-align:center;font-weight:700;font-size:.65rem;color:var(--muted)">' +
      row.freqRank + '</td></tr>');
  });
  
  parts.push('</tbody></table>');
  container.innerHTML = parts.join('');
}

// 辅助：计算色阶等级（0-5）
function calcColorLevel(count, windowSize, totalNums) {
  var expected = windowSize / totalNums;
  var ratio = expected > 0 ? count / expected : 0;
  if (ratio >= 1.5) return 5;
  if (ratio >= 1.2) return 4;
  if (ratio >= 0.9) return 3;
  if (ratio >= 0.7) return 2;
  if (ratio >= 0.5) return 1;
  return 0;
}

// 辅助：获取基础色（未出现时用的浅色）
function getBaseColor(kind, level) {
  if (kind === "front") {
    return ["#fff", "#fef3e2", "#fde0b0", "#fad088", "#f8b850", "#f59e0b"][level];
  }
  return ["#fff", "#e8f4fd", "#b8ddf5", "#8ec7f0", "#5eb0e8", "#3a9fdb"][level];
}
```

### 6.2 与 period 切换联动

在现有的 `renderAll()` 中追加：

```js
// 在 period 变化监听中
function onPeriodChange(newPeriod) {
  period = newPeriod;
  loadData().then(function(res) {
    // ...原有渲染...
    // S4：热冷矩阵
    renderHeatMap(document.getElementById("hm-front-table"),
      buildHeatMap(res.issues, period, GROUP_RULES.front), { latest: true });
    renderHeatMap(document.getElementById("hm-back-table"),
      buildHeatMap(res.issues, period, GROUP_RULES.back), { latest: true });
  });
}
```

### 6.3 Tooltip 交互

```js
// 在 renderHeatMap 完成后的 tbody 绑定
container.addEventListener("mouseover", function(e) {
  var cell = e.target.closest(".hm-cell");
  if (!cell) return hideTooltip();
  showTooltip(cell, e);
});
container.addEventListener("mouseout", hideTooltip);
container.addEventListener("mousemove", moveTooltip);
```

---

## 七、与现有模块的关系

```
sec-summary        （数据概览）
sec-period         （期数选择器）
sec-occurrence     （S2：号码出现轨迹矩阵）← 新增前
sec-heat-map       （S4：热冷矩阵）← 【新模块】
sec-front-hot      （前区热度排行）
sec-front-missing  （前区遗漏分析）
sec-back-hot       （后区冷热分析）
sec-odd-even       （奇偶·大小趋势）
sec-omission       （S3：遗漏趋势分析）
```

---

## 八、扩展性设计

### 8.1 支持其他彩票类型

只需修改 `GROUP_RULES`：

```js
// 双色球扩展（未来）
var GROUP_RULES = {
  red:  { key: "red",  label: "红球", min: 1, max: 33, count: 6, positional: false },
  blue: { key: "blue", label: "蓝球", min: 1, max: 16, count: 1, positional: false },
  front:{ key: "front",label: "前区",min: 1, max: 35, count: 5, positional: false },
  back: { key: "back", label: "后区",min: 1, max: 12, count: 2, positional: false }
};
```

### 8.2 复用能力

| 已有函数 | 热冷矩阵复用 |
|---------|------------|
| `sliceWindow(issues, period)` | ✅ 直接使用 |
| `calculateHot(issues, n, kind)` | ✅ 直接调用获取频率 |
| `GROUP_RULES` | ✅ 配置驱动 |
| `pad2(n)` | ✅ 格式化工具 |
| `loadData()` | ✅ 数据入口统一 |

---

## 九、验收标准

| # | 检查项 | 通过标准 |
|---|--------|---------|
| 1 | HTTP 状态 | 200 OK，页面正常加载 |
| 2 | 前区热冷矩阵 | 35行 × N列网格正确渲染，色阶符合规范 |
| 3 | 后区热冷矩阵 | 12行 × N列网格正确渲染，色阶符合规范 |
| 4 | 颜色语义 | 热号深色 / 冷号浅色，前后区各自独立色系 |
| 5 | 期号表头 | 每5期标注，最新一期高亮加粗 |
| 6 | 编号 sticky | 号码列左 sticky，期号行顶 sticky |
| 7 | Tooltip 交互 | hover 显示期号+号码+排名+趋势 |
| 8 | period 联动 | 切换50/100/300/1000期后矩阵重新渲染 |
| 9 | 响应式 | ≤480px 列宽/行高缩小，max-height 滚动 |
| 10 | 移动端触摸 | `-webkit-overflow-scrolling: touch` 生效 |

---

## 十、不做什么（反模式排除）

❌ 不使用 SVG/Canvas 绘制复杂图表  
❌ 不添加动画/过渡效果（性能优先）  
❌ 不使用第三方图表库（维持轻量原生 JS）  
❌ 不做预测性分析（仅展示历史统计）  
❌ 不硬编码任何开奖数据（全量来自 JSON）  
❌ 不添加装饰性边框或阴影（极简数据视觉）

---

**设计方案冻结，等待确认后进 Phase 3 实施。**
