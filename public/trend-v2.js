/* =========================================================
   专业走势图 · 数据处理与渲染（trend-v2）
   - 数据唯一来源：./data/dlt_history.json（无模拟、无写死、无外部 API）
   - 结构：loadJSON() → calculate() → render()
   - 分析函数独立（calculateHot / calculateMissing /
     calculateOddEven / calculateBigSmall），便于阶段 13 综合评分复用
   - 原生 JS，无框架
   ========================================================= */
(function (root) {
  "use strict";

  var PERIODS = [50, 100, 300, 1000];
  var DEFAULT_PERIOD = 100;
  var FRONT_MIN = 1, FRONT_MAX = 35;
  var BACK_MIN = 1, BACK_MAX = 12;
  var BACK_BOUNDARY = 6; // 后区大小分界：01-06 小 / 07-12 大

  // S1：组规则参数化（为双色球/3D/快乐8 扩展打基础；本轮仅大乐透）
  var GROUP_RULES = {
    front: { key: "front", label: "前区", min: 1, max: 35, count: 5, positional: false },
    back:  { key: "back",  label: "后区", min: 1, max: 12, count: 2, positional: false }
  };

  function pad2(n) { return String(n).padStart(2, "0"); }

  function range(a, b) {
    var out = [];
    for (var i = a; i <= b; i++) out.push(i);
    return out;
  }

  function loadJSON(path) {
    return fetch(path, { cache: "no-cache" }).then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status + " @ " + path);
      return r.json();
    });
  }

  // S1：统一数据加载入口。返回 Promise<{ issues, meta }>
  //   issues: 按期号升序的 {issue, date, front[5], back[2]}
  //   meta:   { cover, issueRange, frontTotal, backTotal, sourceName, updatedAt }
  function loadData() {
    return loadJSON("./data/dlt_history.json").then(function (data) {
      var issues = data.issues || [];
      if (!issues.length) throw new Error("历史数据为空");
      var sorted = issues.slice().sort(function (a, b) {
        return a.issue < b.issue ? -1 : a.issue > b.issue ? 1 : 0;
      });
      var srcName = { "500": "500彩票网" }[data.source] || (data.source || "公开数据源");
      return {
        issues: sorted,
        meta: {
          cover: sorted.length + " 期",
          issueRange: sorted[0].issue + " - " + sorted[sorted.length - 1].issue,
          frontTotal: (sorted.length * GROUP_RULES.front.count) + " 个号码",
          backTotal: (sorted.length * GROUP_RULES.back.count) + " 个号码",
          sourceName: srcName,
          updatedAt: data.updated_at || ""
        }
      };
    });
  }

  /* ================= 纯数据层（分析函数，独立可复用） ================= */

  // 取最近 n 期
  function sliceWindow(issues, n) {
    return issues.slice(Math.max(0, issues.length - n));
  }

  // 热度：{num, count, omit}，按 count 倒序；omit=当前连续未开出期数
  function calculateHot(issues, n, kind) {
    var w = sliceWindow(issues, n);
    var freq = {}, last = {};
    w.forEach(function (it, idx) {
      it[kind].forEach(function (x) {
        freq[x] = (freq[x] || 0) + 1;
        last[x] = idx;
      });
    });
    var lastIdx = w.length - 1;
    var out = [];
    Object.keys(freq).forEach(function (k) {
      out.push({ num: parseInt(k, 10), count: freq[k], omit: lastIdx - (last[k] != null ? last[k] : lastIdx) });
    });
    out.sort(function (a, b) { return b.count - a.count; });
    return out;
  }

  // 遗漏分析：{num, cur, max, avg}；cur=当前遗漏，max=最大连续遗漏，avg=平均连续遗漏
  function calculateMissing(issues, n, kind) {
    var w = sliceWindow(issues, n);
    var pool = kind === "front" ? range(FRONT_MIN, FRONT_MAX) : range(BACK_MIN, BACK_MAX);
    return pool.map(function (num) {
      var cur = 0;
      for (var i = w.length - 1; i >= 0; i--) {
        if (w[i][kind].indexOf(num) >= 0) break;
        cur++;
      }
      var run = 0, max = 0, totalRun = 0, runCount = 0;
      for (var j = 0; j < w.length; j++) {
        if (w[j][kind].indexOf(num) >= 0) {
          if (run > 0) { totalRun += run; runCount++; if (run > max) max = run; run = 0; }
        } else {
          run++;
        }
      }
      if (run > 0) { totalRun += run; runCount++; if (run > max) max = run; }
      return { num: num, cur: cur, max: max, avg: runCount ? Math.round((totalRun / runCount) * 10) / 10 : 0 };
    });
  }

  /* ================= S4：热冷矩阵（Heat Map）================= */

  // 计算色阶等级 0-5（基于实际频率相对期望频率的比例）
  // 期望频率 = windowSize / totalNums
  // ratio >= 1.5 → 极热(5); >= 1.2 → 热(4); >= 0.9 → 温(3); >= 0.7 → 常温(2); >= 0.5 → 冷(1); else → 极冷(0)
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

  // 构建热冷数据模型（纯函数）
  // 返回 { groupRule, period, issues, numbers: [{num, cells, totalAppear, freqRank, trend}] }
  function buildHeatMap(issues, period, groupRule) {
    var w = sliceWindow(issues, period);
    var key = groupRule.key;
    var hot = calculateHot(issues, period, key);
    var hotMap = {};
    hot.forEach(function (h) { hotMap[h.num] = h; });

    // 排名映射（按 count 倒序）
    var sorted = hot.slice().sort(function (a, b) { return b.count - a.count; });
    var rankMap = {};
    sorted.forEach(function (h, i) { rankMap[h.num] = i + 1; });

    // 上一周期热度（用于趋势判断，取当前期的 75% 作为基准）
    var prevPeriod = Math.max(50, Math.floor(period * 0.75));
    var prevHot = calculateHot(issues, prevPeriod, key);
    var prevMap = {};
    prevHot.forEach(function (h) { prevMap[h.num] = h.count; });

    var out = { groupRule: groupRule, period: period, issues: w, numbers: [] };
    for (var num = groupRule.min; num <= groupRule.max; num++) {
      var h = hotMap[num] || { count: 0, omit: period };
      var prev = prevMap[num] || 0;
      var trend = h.count > prev * 1.1 ? "up" :
                  h.count < prev * 0.9 ? "down" : "flat";

      // 构造每期的格子数据
      var cells = [];
      var totalAppear = 0;
      for (var i = 0; i < w.length; i++) {
        var appeared = w[i][key].indexOf(num) >= 0;
        if (appeared) totalAppear++;
        cells.push({ appeared: appeared });
      }

      out.numbers.push({
        num: num,
        cells: cells,
        totalAppear: totalAppear,
        currentOmit: h.omit,
        freqRank: rankMap[num] || 99,
        trend: trend
      });
    }
    return out;
  }

  // 渲染热冷矩阵到容器
  function renderHeatMap(container, data, opts) {
    if (!container) return;
    opts = opts || {};
    var rule = data.groupRule;
    var w = data.issues;
    var numCls = rule.key === "front" ? "front" : "back";
    var parts = ['<table class="hm-table" data-kind="' + rule.key + '"><thead><tr><th class="corner">' + rule.label + '</th>'];

    // 表头：期号（每5期显示后3位）
    for (var c = 0; c < w.length; c++) {
      var show = (c % 5 === 0) || (c === w.length - 1);
      var latest = c === w.length - 1;
      parts.push('<th class="hm-issue' + (latest ? " is-latest" : "") + '" title="第' + w[c].issue + '期 · ' + w[c].date + '">' + (show ? w[c].issue.slice(2) : "") + '</th>');
    }
    parts.push('<th class="hm-rank-h">排名</th></tr></thead><tbody>');

    // 数据行
    data.numbers.forEach(function (row) {
      var colorLevel = calcColorLevel(row.totalAppear, w.length, rule.max - rule.min + 1);
      var arrowHtml = row.trend === "up" ? '<span class="hm-arrow up">▲</span>' :
                      row.trend === "down" ? '<span class="hm-arrow down">▼</span>' : '';

      parts.push('<tr>');
      parts.push('<th class="num-cell ' + numCls + '">' + pad2(row.num) + '</th>');

      row.cells.forEach(function (cell, ci) {
        var latest = ci === w.length - 1;
        if (cell.appeared) {
          parts.push('<td class="hm-cell hm-lv' + colorLevel + (latest ? " is-latest" : "") + '"' +
            'data-issue="' + w[ci].issue + '" data-num="' + pad2(row.num) + '"' +
            'data-rank="' + row.freqRank + '"' +
            'data-trend="' + row.trend + '"' +
            'title="第' + w[ci].issue + '期 · 号码' + pad2(row.num) + ' · 频率排名 #' + row.freqRank + '">' +
            '<span class="hm-num">' + pad2(row.num) + '</span>' +
            '<span class="hm-rank">' + row.freqRank + '</span></td>');
        } else {
          // 未出现：使用极冷底色
          var missClass = rule.key === "front" ? "hm-miss-f" : "hm-miss-b";
          parts.push('<td class="hm-cell hm-lv0 ' + missClass + (latest ? " is-latest" : "") + '" ' +
            'data-issue="' + w[ci].issue + '" data-num="' + pad2(row.num) + '"' +
            'data-rank="' + row.freqRank + '"' +
            'data-trend="' + row.trend + '" ' +
            'title="第' + w[ci].issue + '期 · 号码' + pad2(row.num) + ' · 频率排名 #' + row.freqRank + '">-</td>');
        }
      });

      parts.push('<td class="hm-rank-c">' + row.freqRank + '</td></tr>');
    });

    parts.push("</tbody></table>");
    container.innerHTML = parts.join("");

    // 绑定 hover tooltip
    bindHeatMapTooltip(container);
  }

  // 渲染图例
  function renderHeatLegend(container, kind) {
    if (!container) return;
    var colors = kind === "front"
      ? ["hsl(10,85%,96%)", "hsl(48,50%,84%)", "hsl(38,60%,75%)", "hsl(28,75%,68%)", "hsl(18,80%,62%)", "hsl(10,85%,55%)"]
      : ["hsl(220,70%,96%)", "hsl(248,40%,86%)", "hsl(242,50%,76%)", "hsl(236,58%,68%)", "hsl(228,65%,60%)", "hsl(220,70%,52%)"];
    var labels = ["极冷", "冷", "温", "偏热", "热", "极热"];
    var parts = ['<div class="hm-legend">'];
    for (var i = 0; i < 6; i++) {
      parts.push('<span class="hm-swatch" style="background:' + colors[i] + '"></span>' +
        '<span class="hm-label">' + labels[i] + '</span>');
    }
    parts.push('</div>');
    container.innerHTML = parts.join("");
  }

  // 热冷矩阵 tooltip
  function bindHeatMapTooltip(container) {
    var tip = document.getElementById("hm-tooltip");
    if (!tip || !container) return;
    container.addEventListener("mouseover", function (e) {
      var cell = e.target.closest && e.target.closest("td[data-issue]");
      if (!cell) { tip.classList.remove("show"); return; }
      var issue = cell.getAttribute("data-issue");
      var num = cell.getAttribute("data-num");
      var rank = cell.getAttribute("data-rank");
      var trend = cell.getAttribute("data-trend");
      var arrow = trend === "up" ? "▲升温" : trend === "down" ? "▼降温" : "—持平";
      tip.innerHTML = '<div class="tt-title">第' + issue + '期 · 号码' + num + '</div>' +
        '<div class="tt-line">频率排名：<strong>#' + rank + '</strong> · ' + arrow + '</div>';
      tip.classList.add("show");
      var pad = 12;
      tip.style.left = (e.clientX + pad) + "px";
      tip.style.top = (e.clientY + pad) + "px";
    });
    container.addEventListener("mouseout", function () { tip.classList.remove("show"); });
    container.addEventListener("mousemove", function (e) {
      var pad = 12;
      document.getElementById("hm-tooltip").style.left = (e.clientX + pad) + "px";
      document.getElementById("hm-tooltip").style.top = (e.clientY + pad) + "px";
    });
  }

  // S3：遗漏画像（纯函数）。复用 calculateMissing / calculateHot，不复制遗漏计算逻辑。
  // 仅额外补充「末次出现期号」（位置检索，非遗漏重算）与「趋势」（当前遗漏相对均值的偏离方向）。
  // 输出每个号码：当前遗漏 / 最大遗漏 / 平均遗漏 / 末次出现期号 / 出现次数 / 趋势
  function buildOmissionProfile(issues, period, groupRule) {
    var key = groupRule.key;
    var w = sliceWindow(issues, period);
    var miss = calculateMissing(issues, period, key); // [{num,cur,max,avg}]
    var hot = calculateHot(issues, period, key);       // [{num,count,omit}]
    var hotMap = {};
    hot.forEach(function (h) { hotMap[h.num] = h; });
    // 末次出现期号（仅位置检索，从窗口末尾反向找到首个命中即止）
    var lastMap = {};
    for (var i = w.length - 1; i >= 0; i--) {
      w[i][key].forEach(function (x) { if (lastMap[x] == null) lastMap[x] = w[i].issue; });
    }
    return miss.map(function (m) {
      var h = hotMap[m.num] || { count: 0 };
      var cur = m.cur, avg = m.avg;
      var diff = avg ? cur - avg : 0;
      var trend;
      if (diff >= avg * 0.5) trend = "up";        // 当前遗漏明显高于均值 → 遗漏走高（偏冷）
      else if (diff <= -avg * 0.5) trend = "down"; // 当前遗漏明显低于均值 → 遗漏走低（偏热）
      else trend = "flat";
      return {
        number: m.num,
        currentOmission: cur,
        maxOmission: m.max,
        avgOmission: avg,
        lastAppearIssue: lastMap[m.num] != null ? lastMap[m.num] : null,
        appearCount: h.count,
        trend: trend
      };
    });
  }

  // 奇偶占比（按号码个数统计），返回 {odd, even, total} 百分比
  function calculateOddEven(issues, n, kind) {
    var w = sliceWindow(issues, n);
    var odd = 0, even = 0;
    w.forEach(function (it) {
      it[kind].forEach(function (x) { if (x % 2 === 1) odd++; else even++; });
    });
    var t = odd + even;
    return { odd: t ? Math.round((odd / t) * 1000) / 10 : 0, even: t ? Math.round((even / t) * 1000) / 10 : 0, total: t };
  }

  // 大小占比（按号码个数统计；boundary 为分界，x<=boundary 为小），返回 {small, big, total}
  function calculateBigSmall(issues, n, kind, boundary) {
    var w = sliceWindow(issues, n);
    var small = 0, big = 0;
    w.forEach(function (it) {
      it[kind].forEach(function (x) { if (x <= boundary) small++; else big++; });
    });
    var t = small + big;
    return { small: t ? Math.round((small / t) * 1000) / 10 : 0, big: t ? Math.round((big / t) * 1000) / 10 : 0, total: t };
  }

  // 轨迹矩阵：{labels, issues, matrix}
  function buildMatrices(issues) {
    var sorted = issues.slice().sort(function (a, b) {
      return a.issue < b.issue ? -1 : a.issue > b.issue ? 1 : 0;
    });
    function mk(pmin, pmax, key) {
      var labels = range(pmin, pmax);
      var matrix = labels.map(function () { return new Array(sorted.length).fill(false); });
      sorted.forEach(function (it, ci) {
        it[key].forEach(function (x) { matrix[x - pmin][ci] = true; });
      });
      return { labels: labels, issues: sorted, matrix: matrix };
    }
    return { front: mk(FRONT_MIN, FRONT_MAX, "front"), back: mk(BACK_MIN, BACK_MAX, "back") };
  }

  /* ================= 渲染层 ================= */

  // S2：号码出现轨迹矩阵数据模型（纯函数）。
  // 输出契约：
  //   { groupRule, period, issues(窗口升序), numbers: [
  //       { number, cells: [{appeared}...], curOmit, count } ] }
  // 支持任意组（大乐透前区/后区；未来双色球/3D/快乐8 由 groupRule 驱动）。
  function buildOccurrenceMatrix(issues, period, groupRule) {
    var w = sliceWindow(issues, period);
    var key = groupRule.key;
    var out = { groupRule: groupRule, period: period, issues: w, numbers: [] };
    for (var num = groupRule.min; num <= groupRule.max; num++) {
      var cells = [];
      var count = 0;
      for (var i = 0; i < w.length; i++) {
        var appeared = w[i][key].indexOf(num) >= 0;
        if (appeared) count++;
        cells.push({ appeared: appeared });
      }
      var curOmit = 0;
      for (var j = w.length - 1; j >= 0; j--) {
        if (cells[j].appeared) break;
        curOmit++;
      }
      out.numbers.push({ number: num, cells: cells, curOmit: curOmit, count: count });
    }
    return out;
  }

  // 遗漏档位（仅服务 UI）：与轨迹空格 / 遗漏表共用同一阈值语义
  // 0 = 1-2 期, 1 = 3-5, 2 = 6-10, 3 = 11-20, 4 = 21+
  function missLevel(miss) {
    if (miss <= 2) return 0;
    if (miss <= 5) return 1;
    if (miss <= 10) return 2;
    if (miss <= 20) return 3;
    return 4;
  }

  // 热度档位（仅服务 UI）：按行内最大值归一化到 1-4（最大值恒为 4）
  function hotLevel(count, max) {
    if (!max) return 0;
    return Math.min(4, Math.max(1, Math.round((count / max) * 4)));
  }

  // 遗漏计算辅助（仅服务 UI）：返回每个号码在当前窗口内的当前遗漏期数
  // 输入 buildMatrices() 输出 matrix 对象，输出 [{ number, miss }]
  function calculateCellMissing(m, n) {
    var issues = m.issues;
    var start = Math.max(0, issues.length - (n || issues.length));
    return m.labels.map(function (num, r) {
      var miss = 0;
      for (var ci = issues.length - 1; ci >= start; ci--) {
        if (m.matrix[r][ci]) break;
        miss++;
      }
      return { number: num, miss: miss };
    });
  }

  // 轨迹渲染：命中格显示号码 + data 属性（供 hover tooltip/连线定位），表头带完整期号与日期
  // 趋势 2.0 第一阶段：号码文本 / 日期标识 / hover 提示 / SVG 连线（坐标基于固定 22px 格）
  function renderTrajectoryHTML(m, kind, n) {
    var issues = m.issues;
    var start = Math.max(0, issues.length - n);
    var cols = issues.slice(start);
    var hitClass = kind === "front" ? "hit-f" : "hit-b";
    var numCls = kind === "front" ? "f" : "b";
    // 每号当前遗漏（仅服务 UI）：空格输出 miss-lvN 分级 class，命中格保留 hit-f / hit-b
    var missMap = {};
    calculateCellMissing(m, n).forEach(function (it) { missMap[it.number] = it.miss; });
    var parts = ['<table class="trend-table" data-kind="' + kind + '"><thead><tr><th class="corner"></th>'];
    for (var c = 0; c < cols.length; c++) {
      var show = (c % 10 === 0) || (c === cols.length - 1);
      parts.push('<th class="issue-cell" title="第 ' + cols[c].issue + ' 期 · ' + cols[c].date + '">' +
        (show ? cols[c].issue.slice(2) : "") + "</th>");
    }
    parts.push("</tr></thead><tbody>");
    for (var r = 0; r < m.labels.length; r++) {
      var row = m.matrix[r];
      var rowMissLv = missLevel(missMap[m.labels[r]]);
      parts.push('<tr><th class="num-cell ' + numCls + '">' + pad2(m.labels[r]) + "</th>");
      for (var ci = 0; ci < cols.length; ci++) {
        if (row[start + ci]) {
          var miss = missMap[m.labels[r]];
          parts.push('<td class="cell ' + hitClass + '" data-issue="' + cols[ci].issue +
            '" data-date="' + cols[ci].date + '" data-num="' + pad2(m.labels[r]) +
            '" data-omit="' + miss + '" title="第 ' + cols[ci].issue + ' 期 · 号码 ' +
            pad2(m.labels[r]) + " · 遗漏 " + miss + " 期\">" + pad2(m.labels[r]) + "</td>");
        } else {
          parts.push('<td class="cell miss-lv' + rowMissLv + '"></td>');
        }
      }
      parts.push("</tr>");
    }
    parts.push("</tbody></table>");
    return parts.join("");
  }

  // hover 详情：命中格 → tooltip（期号/日期/号码/遗漏/该期全部号码）；fixed 跟随鼠标
  function bindTrendTooltip() {
    var tip = document.getElementById("trend-tooltip");
    if (!tip) return;
    document.addEventListener("mouseover", function (e) {
      var td = e.target && e.target.closest ? e.target.closest("td[data-issue]") : null;
      if (!td) { tip.hidden = true; return; }
      var issue = td.getAttribute("data-issue");
      var cur = null;
      var all = window.__trendIssues || [];
      for (var i = 0; i < all.length; i++) { if (all[i].issue === issue) { cur = all[i]; break; } }
      var kind = td.classList.contains("hit-f") ? "前区" : "后区";
      var num = td.getAttribute("data-num");
      var omit = td.getAttribute("data-omit");
      var date = td.getAttribute("data-date");
      var head = '<div class="tt-title">第 ' + issue + " 期 · " + date + "</div>";
      var line1 = '<div class="tt-line">' + kind + '号码 <strong>' + num + '</strong> · 当前遗漏 <strong>' + omit + " 期</strong></div>";
      var line2 = "";
      if (cur) {
        line2 = '<div class="tt-line">该期开奖：前区 ' + cur.front.map(pad2).join(" ") +
          " · 后区 " + cur.back.map(pad2).join(" ") + "</div>";
      }
      tip.innerHTML = head + line1 + line2;
      tip.hidden = false;
      var pad = 14;
      tip.style.left = (e.clientX + pad) + "px";
      tip.style.top = (e.clientY + pad) + "px";
    });
  }

  // S2：号码出现轨迹矩阵渲染（HTML 表格）。
  // 横轴=期号（表头，每 5 期显示后 3 位），纵轴=号码；
  // 命中格=号码 + 当前遗漏小字，未命中格=遗漏色阶行背景；
  // 最新一期列高亮（is-latest）；无任何跨点连线（Task 17.1 产品约束）。
  // data: buildOccurrenceMatrix() 输出；opts: { latest: bool }
  function renderOccurrenceMatrix(container, data, opts) {
    opts = opts || {};
    var rule = data.groupRule;
    var w = data.issues;
    var numCls = rule.key === "front" ? "f" : "b";
    var hitClass = rule.key === "front" ? "hit-f" : "hit-b";
    var parts = ['<table class="ocm-table" data-kind="' + rule.key + '"><thead><tr><th class="corner">' + rule.label + '</th>'];
    for (var c = 0; c < w.length; c++) {
      var show = (c % 5 === 0) || (c === w.length - 1);
      var latest = c === w.length - 1;
      parts.push('<th class="ocm-issue' + (latest ? " is-latest" : "") + '" title="第 ' + w[c].issue +
        " 期 · " + w[c].date + '">' + (show ? w[c].issue.slice(2) : "") + "</th>");
    }
    parts.push('<th class="ocm-cur">遗漏</th></tr></thead><tbody>');
    data.numbers.forEach(function (row) {
      parts.push('<tr><th class="num-cell ' + numCls + '">' + pad2(row.number) + "</th>");
      for (var ci = 0; ci < w.length; ci++) {
        var cell = row.cells[ci];
        var latest = ci === w.length - 1;
        if (cell.appeared) {
          parts.push('<td class="ocm-cell ' + hitClass + (latest ? " is-latest" : "") + '" data-issue="' +
            w[ci].issue + '" data-date="' + w[ci].date + '" data-num="' + pad2(row.number) +
            '" data-omit="' + row.curOmit + '" title="第 ' + w[ci].issue + " 期 · 号码 " +
            pad2(row.number) + " · 当前遗漏 " + row.curOmit + ' 期">' +
            '<span class="ocm-num">' + pad2(row.number) + "</span>" +
            '<span class="ocm-omit">' + row.curOmit + "</span></td>");
        } else {
          parts.push('<td class="ocm-cell miss-lv' + missLevel(row.curOmit) + (latest ? " is-latest" : "") + '"></td>');
        }
      }
      parts.push('<td class="ocm-cur-val' + (row.curOmit > 0 ? " omit" : "") + '">' + row.curOmit + "</td></tr>");
    });
    parts.push("</tbody></table>");
    container.innerHTML = parts.join("");
  }

  function renderHotTable(items, kind) {
    var numCls = kind === "front" ? "f" : "b";
    var maxCount = 0;
    items.forEach(function (it) { if (it.count > maxCount) maxCount = it.count; });
    var rows = ['<thead><tr><th>号码</th><th>出现次数</th><th>最近遗漏</th></tr></thead><tbody>'];
    items.forEach(function (it) {
      rows.push('<tr><td class="num ' + numCls + '">' + pad2(it.num) + "</td>" +
        '<td class="val-hot hot-lv' + hotLevel(it.count, maxCount) + '">' + it.count + "</td>" +
        '<td class="val-omit">' + it.omit + "</td></tr>");
    });
    rows.push("</tbody>");
    return rows.join("");
  }

  function renderMissingTable(items, kind) {
    var numCls = kind === "front" ? "f" : "b";
    var rows = ['<thead><tr><th>号码</th><th>当前遗漏</th><th>最大遗漏</th><th>平均遗漏</th></tr></thead><tbody>'];
    items.forEach(function (it) {
      rows.push('<tr><td class="num ' + numCls + '">' + pad2(it.num) + "</td>" +
        '<td class="val-omit miss-lv' + missLevel(it.cur) + '">' + it.cur + "</td>" +
        "<td>" + it.max + "</td><td>" + it.avg + "</td></tr>");
    });
    rows.push("</tbody>");
    return rows.join("");
  }

  // S3：遗漏排行条形渲染（横向条形 / 排名形式，无 SVG sparkline，无动画；表格优先）。
  // mode: "current" | "change" | "max"；kind: "front" | "back"
  //   current: 按当前遗漏倒序（条形色阶 = 遗漏档位）
  //   change : 按「当前遗漏 − 平均遗漏」倒序（正=遗漏走高/偏冷→紫，负=遗漏走低/偏热→琥珀）
  //   max    : 按窗口内最大连续遗漏倒序（深紫，反映历史最冷极值）
  function renderOmissionRanking(container, profiles, mode, kind) {
    if (!container) return;
    var numCls = kind === "front" ? "f" : "b";
    var valOf = function (p) {
      if (mode === "current") return p.currentOmission;
      if (mode === "change") return p.currentOmission - p.avgOmission;
      return p.maxOmission; // max
    };
    var arr = profiles.slice().sort(function (a, b) { return valOf(b) - valOf(a); });
    var maxAbs = 1;
    arr.forEach(function (p) { var v = Math.abs(valOf(p)); if (v > maxAbs) maxAbs = v; });
    var parts = ['<div class="om-list">'];
    arr.forEach(function (p) {
      var v = valOf(p);
      var abs = Math.abs(v);
      var wpct = Math.max(4, Math.round((abs / maxAbs) * 100));
      var cls = "", valCls = "", arrow = "";
      if (mode === "current") {
        cls = "lv" + missLevel(v);
      } else if (mode === "change") {
        if (v > 0) { cls = "up"; valCls = "up"; }
        else if (v < 0) { cls = "down"; valCls = "down"; }
        else { cls = "flat"; }
        arrow = p.trend === "up" ? "▲" : p.trend === "down" ? "▼" : "—";
      } else { // max
        cls = "long";
      }
      var valTxt = mode === "change" ? (v > 0 ? "+" + v : String(v)) : String(v);
      parts.push('<div class="om-row">' +
        '<span class="om-num ' + numCls + '">' + pad2(p.number) + "</span>" +
        (arrow ? '<span class="om-arrow ' + valCls + '">' + arrow + "</span>" : "") +
        '<span class="om-track"><span class="om-bar ' + cls + '" style="width:' + wpct + '%"></span></span>' +
        '<span class="om-val ' + valCls + '">' + valTxt + "</span></div>");
    });
    parts.push("</div>");
    container.innerHTML = parts.join("");
  }

  // 奇偶/大小：当前档大条形 + 四档对比小条形
  function renderRatioBars(el, cur, labelCur, four) {
    var parts = [];
    parts.push('<div class="bar-row"><span class="bar-label">' + labelCur + "</span>" +
      '<span class="bar-track"><span class="bar-fill" style="width:' + cur.pct + '%"></span></span>' +
      '<span class="bar-val">' + cur.txt + "</span></div>");
    four.forEach(function (f) {
      parts.push('<div class="bar-row"><span class="bar-label">' + f.label + "</span>" +
        '<span class="bar-track"><span class="bar-fill" style="width:' + f.pct + '%;background:linear-gradient(90deg,#8b5cf6 0%,#6d28d9 100%)"></span></span>' +
        '<span class="bar-val">' + f.txt + "</span></div>");
    });
    el.innerHTML = parts.join("");
  }

  function showError(msg) {
    document.getElementById("error").hidden = false;
    document.getElementById("error-detail").textContent = msg || "";
  }

  /* ================= 页面启动：loadJSON → calculate → render ================= */
  function init() {
    // 期数自适应：大屏（≥760px）默认 300 期展示更完整趋势，移动端保持 100 期低密度易读
    var period = window.innerWidth >= 760 ? 300 : DEFAULT_PERIOD;
    var matrix = null;
    var meta = { cover: "—", issueRange: "—", frontTotal: "—", backTotal: "—", sourceName: "—" };

    // 📊 数据概览（动态读 JSON；分析范围随当前期数联动）
    function renderSummary() {
      document.getElementById("sum-range").textContent = "最近 " + period + " 期";
      document.getElementById("sum-cover").textContent = meta.cover;
      document.getElementById("sum-issue").textContent = meta.issueRange;
      document.getElementById("sum-front").textContent = meta.frontTotal;
      document.getElementById("sum-back").textContent = meta.backTotal;
      document.getElementById("sum-source").textContent = meta.sourceName;
    }

    function draw() {
      var issues = matrix.front.issues;
      window.__trendIssues = issues;
      renderSummary();

      // ① 号码出现轨迹矩阵（S2：替代旧轨迹视觉；矩阵展示号码/出现/遗漏，无连线）
      var occ = document.getElementById("occurrence-container");
      if (occ) {
        occ.innerHTML =
          '<h3 class="ocm-group">前区（01–35）</h3><div class="ocm-wrap" id="ocm-front"></div>' +
          '<h3 class="ocm-group">后区（01–12）</h3><div class="ocm-wrap" id="ocm-back"></div>';
        renderOccurrenceMatrix(document.getElementById("ocm-front"),
          buildOccurrenceMatrix(issues, period, GROUP_RULES.front), { latest: true });
        renderOccurrenceMatrix(document.getElementById("ocm-back"),
          buildOccurrenceMatrix(issues, period, GROUP_RULES.back), { latest: true });
      }

      // ③ 前区热度排行
      document.getElementById("front-hot").innerHTML =
        renderHotTable(calculateHot(issues, period, "front"), "front");

      // ④ 前区遗漏分析
      document.getElementById("front-missing").innerHTML =
        renderMissingTable(calculateMissing(issues, period, "front"), "front");

      // ⑤ 后区冷热分析
      document.getElementById("back-hot").innerHTML =
        renderHotTable(calculateHot(issues, period, "back"), "back");

      // ⑥ 后区奇偶趋势（当前档 + 50/100/300/1000 对比）
      var oeCur = calculateOddEven(issues, period, "back");
      var oeFour = PERIODS.map(function (p) {
        var r = calculateOddEven(issues, p, "back");
        return { label: p + "期", pct: r.odd, txt: "奇" + r.odd + "% 偶" + r.even + "%" };
      });
      renderRatioBars(document.getElementById("back-odd-even"),
        { pct: oeCur.odd, txt: "奇数 " + oeCur.odd + "%" },
        "当前(" + period + "期)奇占比",
        oeFour);

      // ⑦ 后区大小趋势
      var bsCur = calculateBigSmall(issues, period, "back", BACK_BOUNDARY);
      var bsFour = PERIODS.map(function (p) {
        var r = calculateBigSmall(issues, p, "back", BACK_BOUNDARY);
        return { label: p + "期", pct: r.big, txt: "小" + r.small + "% 大" + r.big + "%" };
      });
      renderRatioBars(document.getElementById("back-big-small"),
        { pct: bsCur.big, txt: "大 " + bsCur.big + "%" },
        "当前(" + period + "期)大占比",
        bsFour);

      // ② 热冷矩阵（S4：前后区独立展示；联动 period）
      renderHeatMap(document.getElementById("hm-front"),
        buildHeatMap(issues, period, GROUP_RULES.front), { latest: true });
      renderHeatLegend(document.getElementById("hm-legend-front"), "front");
      renderHeatMap(document.getElementById("hm-back"),
        buildHeatMap(issues, period, GROUP_RULES.back), { latest: true });
      renderHeatLegend(document.getElementById("hm-legend-back"), "back");

      // ⑧ 遗漏趋势分析（S3：前/后区遗漏排行 + 遗漏变化排名 + 长期遗漏统计；跟随 period 联动）
      renderMissingAnalysis();
    }

    // S3：遗漏趋势分析渲染（前区/后区镜像；横向条形排名，无 SVG，无动画）
    function renderMissingAnalysis() {
      var issues = window.__trendIssues;
      if (!issues) return;
      var front = buildOmissionProfile(issues, period, GROUP_RULES.front);
      var back = buildOmissionProfile(issues, period, GROUP_RULES.back);
      renderOmissionRanking(document.getElementById("omission-current-front"), front, "current", "front");
      renderOmissionRanking(document.getElementById("omission-current-back"), back, "current", "back");
      renderOmissionRanking(document.getElementById("omission-change-front"), front, "change", "front");
      renderOmissionRanking(document.getElementById("omission-change-back"), back, "change", "back");
      renderOmissionRanking(document.getElementById("omission-long-front"), front, "max", "front");
      renderOmissionRanking(document.getElementById("omission-long-back"), back, "max", "back");
    }

    // 时间范围切换（联动）
    document.getElementById("period-switch").addEventListener("click", function (e) {
      var btn = e.target.closest("button");
      if (!btn) return;
      period = parseInt(btn.getAttribute("data-periods"), 10);
      this.querySelectorAll("button").forEach(function (b) {
        b.classList.toggle("active", b === btn);
      });
      draw();
    });

    // 页内锚点导航：平滑滚动（仅 UI，不影响渲染逻辑）
    document.querySelectorAll(".anchor-nav a").forEach(function (a) {
      a.addEventListener("click", function (e) {
        var id = this.getAttribute("href").slice(1);
        var target = document.getElementById(id);
        if (target) {
          e.preventDefault();
          target.scrollIntoView({ behavior: "smooth", block: "start" });
        }
      });
    });

    // 趋势 2.0：hover 详情提示（事件委托，全局一次绑定）
    bindTrendTooltip();

    // S1：统一数据加载入口（loadData → 排序 + meta）
    loadData().then(function (res) {
      var issues = res.issues;
      meta = res.meta;
      matrix = buildMatrices(issues);
      draw();
    }).catch(function (err) {
      showError(String(err && err.message ? err.message : err));
    });
  }

  var api = {
    PERIODS: PERIODS,
    GROUP_RULES: GROUP_RULES,
    loadData: loadData,
    sliceWindow: sliceWindow,
    calculateHot: calculateHot,
    calculateMissing: calculateMissing,
    calculateOddEven: calculateOddEven,
    calculateBigSmall: calculateBigSmall,
    buildMatrices: buildMatrices,
    calculateCellMissing: calculateCellMissing,
    buildOmissionProfile: buildOmissionProfile,
    buildOccurrenceMatrix: buildOccurrenceMatrix,
    renderTrajectoryHTML: renderTrajectoryHTML,
    renderOccurrenceMatrix: renderOccurrenceMatrix,
    renderOmissionRanking: renderOmissionRanking,
    bindTrendTooltip: bindTrendTooltip
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;             // Node 测试用
  } else {
    root.TrendV2API = api;
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", init);
    } else {
      init();
    }
  }
})(typeof self !== "undefined" ? self : this);
