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
    var parts = ['<div class="trend-wrap"><table class="trend-table" data-kind="' + kind + '"><thead><tr><th class="corner"></th>'];
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
    parts.push("</tbody></table><svg class=\"trend-lines\" aria-hidden=\"true\"></svg></div>");
    return parts.join("");
  }

  // 趋势连线：基于固定 22px 格坐标绘制每行命中 polyline（纯增量，不改数据结构）
  function drawTrendLines(container, kind) {
    var wrap = container.querySelector(".trend-wrap");
    var table = container.querySelector(".trend-table");
    var svg = container.querySelector(".trend-lines");
    if (!wrap || !table || !svg) return;
    var body = table.tBodies && table.tBodies[0];
    if (!body) return;

    var CELL = 22, CORNER = 40, HALF = CELL / 2;
    var headH = (table.tHead && table.tHead.rows && table.tHead.rows[0])
      ? table.tHead.rows[0].offsetHeight : 22;
    var nCols = (table.tHead && table.tHead.rows[0]) ? table.tHead.rows[0].cells.length - 1 : 0;
    var nRows = body.rows.length;
    var W = CORNER + nCols * CELL;
    var H = headH + nRows * CELL;

    svg.setAttribute("viewBox", "0 0 " + W + " " + H);
    svg.style.width = W + "px";
    svg.style.height = H + "px";
    svg.innerHTML = "";

    var svgns = "http://www.w3.org/2000/svg";
    // SVG presentation attribute 不解析 CSS 变量，改用 style 属性（支持 var()）保证连线颜色
    var stroke = kind === "front" ? "var(--front)" : "var(--back)";
    for (var r = 0; r < nRows; r++) {
      var row = body.rows[r];
      var y = headH + r * CELL + HALF;
      var pts = [];
      for (var ci = 1; ci < row.cells.length; ci++) {
        var td = row.cells[ci];
        if (td.classList.contains("hit-f") || td.classList.contains("hit-b")) {
          pts.push((CORNER + (ci - 1) * CELL + HALF) + "," + y);
        }
      }
      if (pts.length >= 2) {
        var line = document.createElementNS(svgns, "polyline");
        line.setAttribute("points", pts.join(" "));
        line.setAttribute("fill", "none");
        line.style.stroke = stroke;
        line.setAttribute("stroke-width", "1");
        line.setAttribute("opacity", "0.5");
        svg.appendChild(line);
      }
    }
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

  /* ================= S3 遗漏趋势分析（新增，复用既有分析函数，不改 S2 矩阵） ================= */

  // 遗漏档案：复用 calculateMissing（cur/max/avg）+ calculateHot（appearCount），
  // 仅新增 lastAppearIssue / trend 计算，不复制遗漏逻辑。
  // 输出：{number, currentOmission, maxOmission, avgOmission, lastAppearIssue, appearCount, trend}
  function buildOmissionProfile(issues, n, kind) {
    var w = sliceWindow(issues, n);
    var missing = calculateMissing(issues, n, kind); // [{num,cur,max,avg}]
    var hot = calculateHot(issues, n, kind);          // [{num,count,omit}]
    var countMap = {};
    hot.forEach(function (h) { countMap[h.num] = h.count; });
    // 最近出现期号：从窗口末尾向前扫描，记录每个号码首次（=最近）命中的期号
    var lastAppear = {};
    for (var i = w.length - 1; i >= 0; i--) {
      w[i][kind].forEach(function (x) {
        if (lastAppear[x] == null) lastAppear[x] = w[i].issue;
      });
    }
    return missing.map(function (m) {
      var cur = m.cur, avg = m.avg;
      var trend = (cur > avg * 1.15) ? "high" : (cur < avg * 0.85 ? "low" : "normal");
      return {
        number: m.num,
        currentOmission: cur,
        maxOmission: m.max,
        avgOmission: avg,
        lastAppearIssue: (lastAppear[m.num] != null) ? String(lastAppear[m.num]) : null,
        appearCount: countMap[m.num] || 0,
        trend: trend
      };
    });
  }

  // ① 当前遗漏排行（按 currentOmission 倒序；号码 | 当前遗漏 | 最大遗漏 | 最近出现 | 状态）
  function renderOmissionCurrent(profile, kind) {
    var numCls = kind === "front" ? "f" : "b";
    var rows = ['<thead><tr><th>号码</th><th>当前遗漏</th><th>最大遗漏</th><th>最近出现</th><th>状态</th></tr></thead><tbody>'];
    profile.sort(function (a, b) { return b.currentOmission - a.currentOmission; });
    profile.forEach(function (p) {
      var status = p.trend === "high" ? "遗漏偏高" : (p.trend === "low" ? "近期活跃" : "常态");
      var stCls = p.trend === "high" ? "st-high" : (p.trend === "low" ? "st-low" : "st-normal");
      rows.push('<tr><td class="num ' + numCls + '">' + pad2(p.number) + "</td>" +
        '<td class="val-omit miss-lv' + missLevel(p.currentOmission) + '">' + p.currentOmission + "</td>" +
        "<td>" + p.maxOmission + "</td>" +
        "<td>" + (p.lastAppearIssue || "—") + "</td>" +
        '<td class="' + stCls + '">' + status + "</td></tr>");
    });
    rows.push("</tbody>");
    document.getElementById(kind === "front" ? "omission-current-front" : "omission-current-back").innerHTML = rows.join("");
  }

  // ② 遗漏变化排名（按 当前−平均 偏差降序；横向条形，长度 ∝ |偏差|，不做连线/动画）
  function renderOmissionChange(profile, kind) {
    var sorted = profile.slice().sort(function (a, b) {
      return (b.currentOmission - b.avgOmission) - (a.currentOmission - a.avgOmission);
    });
    var maxDev = 1;
    sorted.forEach(function (p) {
      var dev = Math.abs(p.currentOmission - p.avgOmission);
      if (dev > maxDev) maxDev = dev;
    });
    var parts = ['<div class="bar-rank-list">'];
    sorted.forEach(function (p) {
      var dev = p.currentOmission - p.avgOmission;
      var pct = Math.max(6, Math.round(Math.abs(dev) / maxDev * 100));
      var dir = dev >= 0 ? "pos" : "neg";
      var sign = dev >= 0 ? "+" : "";
      parts.push('<div class="bar-rank-row">' +
        '<span class="br-num">' + pad2(p.number) + "</span>" +
        '<span class="br-track"><span class="br-fill ' + dir + '" style="width:' + pct + '%"></span></span>' +
        '<span class="br-val">当前 ' + p.currentOmission + ' · 平均 ' + p.avgOmission +
        ' · <strong>' + sign + dev + "</strong></span></div>");
    });
    parts.push("</div>");
    document.getElementById(kind === "front" ? "omission-change-front" : "omission-change-back").innerHTML = parts.join("");
  }

  // ③ 长期遗漏统计（最大遗漏 TOP5 + 平均遗漏 + 当前超均值号码）
  function renderOmissionLong(fp, bp) {
    function maxTop(list, kind) {
      var numCls = kind === "front" ? "f" : "b";
      var top = list.slice().sort(function (a, b) { return b.maxOmission - a.maxOmission; }).slice(0, 5);
      var rows = ['<thead><tr><th>号码</th><th>最大遗漏</th></tr></thead><tbody>'];
      top.forEach(function (p) {
        rows.push('<tr><td class="num ' + numCls + '">' + pad2(p.number) + "</td>" +
          '<td class="val-omit miss-lv' + missLevel(p.maxOmission) + '">' + p.maxOmission + "</td></tr>");
      });
      rows.push("</tbody>");
      return rows.join("");
    }
    document.getElementById("omission-maxtop-front").innerHTML = maxTop(fp, "front");
    document.getElementById("omission-maxtop-back").innerHTML = maxTop(bp, "back");

    function avgOf(list) { var s = 0; list.forEach(function (p) { s += p.avgOmission; }); return list.length ? Math.round(s / list.length * 10) / 10 : 0; }
    function overAvg(list) { return list.filter(function (p) { return p.currentOmission > p.avgOmission; }); }
    var fOver = overAvg(fp), bOver = overAvg(bp);
    var summary = '<div class="long-stats">' +
      '<div class="ls-item"><span class="ls-label">前区平均遗漏</span><span class="ls-value">' + avgOf(fp) + "</span></div>" +
      '<div class="ls-item"><span class="ls-label">后区平均遗漏</span><span class="ls-value">' + avgOf(bp) + "</span></div>" +
      '<div class="ls-item"><span class="ls-label">前区超均值号码</span><span class="ls-value">' + fOver.length + " 个</span>" +
        '<span class="ls-detail">' + (fOver.length ? fOver.map(function (p) { return pad2(p.number); }).join(" ") : "无") + "</span></div>" +
      '<div class="ls-item"><span class="ls-label">后区超均值号码</span><span class="ls-value">' + bOver.length + " 个</span>" +
        '<span class="ls-detail">' + (bOver.length ? bOver.map(function (p) { return pad2(p.number); }).join(" ") : "无") + "</span></div>" +
      "</div>";
    document.getElementById("omission-stats-summary").innerHTML = summary;
  }

  // S3 总渲染入口（在 draw() 中随 period 联动调用）
  function renderMissingAnalysis(issues, period) {
    var fp = buildOmissionProfile(issues, period, "front");
    var bp = buildOmissionProfile(issues, period, "back");
    renderOmissionCurrent(fp, "front");
    renderOmissionCurrent(bp, "back");
    renderOmissionChange(fp, "front");
    renderOmissionChange(bp, "back");
    renderOmissionLong(fp, bp);
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

      // ① ② 轨迹（2.0：号码文本 + hover tooltip + SVG 连线）
      document.getElementById("front-trajectory").innerHTML =
        renderTrajectoryHTML(matrix.front, "front", period);
      drawTrendLines(document.getElementById("front-trajectory"), "front");
      document.getElementById("back-trajectory").innerHTML =
        renderTrajectoryHTML(matrix.back, "back", period);
      drawTrendLines(document.getElementById("back-trajectory"), "back");

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

      // ⑧ S3 遗漏趋势分析（随 period 联动；复用 S2 同一 issues 数据）
      renderMissingAnalysis(issues, period);
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

    loadJSON("./data/dlt_history.json").then(function (data) {
      var issues = data.issues || [];
      if (!issues.length) throw new Error("历史数据为空");
      var srcName = { "500": "500彩票网" }[data.source] || (data.source || "公开数据源");
      meta = {
        cover: issues.length + " 期",
        issueRange: issues[0].issue + " - " + issues[issues.length - 1].issue,
        frontTotal: (issues.length * 5) + " 个号码",
        backTotal: (issues.length * 2) + " 个号码",
        sourceName: srcName
      };
      matrix = buildMatrices(issues);
      draw();
    }).catch(function (err) {
      showError(String(err && err.message ? err.message : err));
    });
  }

  var api = {
    PERIODS: PERIODS,
    sliceWindow: sliceWindow,
    calculateHot: calculateHot,
    calculateMissing: calculateMissing,
    calculateOddEven: calculateOddEven,
    calculateBigSmall: calculateBigSmall,
    buildMatrices: buildMatrices,
    calculateCellMissing: calculateCellMissing,
    renderTrajectoryHTML: renderTrajectoryHTML,
    drawTrendLines: drawTrendLines,
    bindTrendTooltip: bindTrendTooltip,
    buildOmissionProfile: buildOmissionProfile,
    renderMissingAnalysis: renderMissingAnalysis
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
