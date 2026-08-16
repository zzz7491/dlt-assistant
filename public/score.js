/* =========================================================
   综合评分分析 · 评分引擎（score）
   - 数据唯一来源：./data/dlt_history.json（无模拟、无写死、无外部 API）
   - 权重配置化：SCORE_WEIGHTS（禁止硬编码权重）
   - 评分版本信息：SCORE_VERSION
   - 结构：loadJSON() → scoreAll() → render()
   - 自包含纯函数（不依赖其他 JS），node 可测
   ========================================================= */
(function (root) {
  "use strict";

  /* ===== 评分版本信息 ===== */
  var SCORE_VERSION = {
    scoreVersion: "v1.0",
    weightVersion: "default",
    generatedFrom: "1000期历史开奖数据"
  };

  /* ===== 权重配置（配置化，禁止硬编码） =====
     总和 = 1.0；修改此处即可调整评分倾向 */
  var SCORE_WEIGHTS = {
    frequency: 0.25,   // 历史出现频率
    recentHot: 0.20,   // 近期热度（窗口内出现次数）
    missing: 0.15,     // 遗漏周期（当前/平均/最大）
    balance: 0.15,     // 冷热平衡（过热衰减 / 过冷补偿）
    oddEven: 0.10,     // 奇偶结构
    bigSmall: 0.10,    // 大小结构
    structure: 0.05    // 组合结构（连号 / 和值 / 分布）
  };

  var PERIODS = [50, 100, 300, 1000];
  var DEFAULT_PERIOD = 100;
  var FRONT_MIN = 1, FRONT_MAX = 35;
  var BACK_MIN = 1, BACK_MAX = 12;
  var FRONT_BOUNDARY = 17; // 前区：01-17 小 / 18-35 大
  var BACK_BOUNDARY = 6;   // 后区：01-06 小 / 07-12 大
  var TOP_N = 10;

  function pad2(n) { return String(n).padStart(2, "0"); }
  function range(a, b) { var out = []; for (var i = a; i <= b; i++) out.push(i); return out; }
  function clamp(v, lo, hi) { return Math.min(hi, Math.max(lo, v)); }
  function round1(v) { return Math.round(v * 10) / 10; }

  function loadJSON(path) {
    return fetch(path, { cache: "no-cache" }).then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status + " @ " + path);
      return r.json();
    });
  }

  /* ================= 基础分析纯函数（与 trend-v2 同口径，自包含实现） ================= */

  function sliceWindow(issues, n) { return issues.slice(Math.max(0, issues.length - n)); }

  // 热度：{num, count, omit} 按 count 倒序；omit=当前连续未开出期数
  function calculateHot(issues, n, kind) {
    var w = sliceWindow(issues, n);
    var freq = {}, last = {};
    w.forEach(function (it, idx) {
      it[kind].forEach(function (x) { freq[x] = (freq[x] || 0) + 1; last[x] = idx; });
    });
    var lastIdx = w.length - 1;
    var out = [];
    Object.keys(freq).forEach(function (k) {
      out.push({ num: parseInt(k, 10), count: freq[k], omit: lastIdx - (last[k] != null ? last[k] : lastIdx) });
    });
    out.sort(function (a, b) { return b.count - a.count; });
    return out;
  }

  // 遗漏：{num, cur, max, avg}
  function calculateMissing(issues, n, kind) {
    var w = sliceWindow(issues, n);
    var pool = kind === "front" ? range(FRONT_MIN, FRONT_MAX) : range(BACK_MIN, BACK_MAX);
    return pool.map(function (num) {
      var cur = 0;
      for (var i = w.length - 1; i >= 0; i--) { if (w[i][kind].indexOf(num) >= 0) break; cur++; }
      var run = 0, max = 0, totalRun = 0, runCount = 0;
      for (var j = 0; j < w.length; j++) {
        if (w[j][kind].indexOf(num) >= 0) {
          if (run > 0) { totalRun += run; runCount++; if (run > max) max = run; run = 0; }
        } else { run++; }
      }
      if (run > 0) { totalRun += run; runCount++; if (run > max) max = run; }
      return { num: num, cur: cur, max: max, avg: runCount ? round1(totalRun / runCount) : 0 };
    });
  }

  // 奇偶占比 {odd, even, total}
  function calculateOddEven(issues, n, kind) {
    var w = sliceWindow(issues, n);
    var odd = 0, even = 0;
    w.forEach(function (it) { it[kind].forEach(function (x) { if (x % 2 === 1) odd++; else even++; }); });
    var t = odd + even;
    return { odd: t ? round1(odd / t * 100) : 50, even: t ? round1(even / t * 100) : 50, total: t };
  }

  // 大小占比 {small, big, total}
  function calculateBigSmall(issues, n, kind, boundary) {
    var w = sliceWindow(issues, n);
    var small = 0, big = 0;
    w.forEach(function (it) { it[kind].forEach(function (x) { if (x <= boundary) small++; else big++; }); });
    var t = small + big;
    return { small: t ? round1(small / t * 100) : 50, big: t ? round1(big / t * 100) : 50, total: t };
  }

  // 连号参与率：{num: 参与连号的期数占比*100}（前区相邻号码同开）
  function calculateConsec(issues, n, kind) {
    var w = sliceWindow(issues, n);
    var nLen = w.length;
    var counts = {};
    w.forEach(function (it) {
      var s = it[kind].slice().sort(function (a, b) { return a - b; });
      s.forEach(function (x, i) {
        if ((i > 0 && s[i - 1] === x - 1) || (i < s.length - 1 && s[i + 1] === x + 1)) {
          counts[x] = (counts[x] || 0) + 1;
        }
      });
    });
    return counts;
  }

  /* ================= 评分引擎 ================= */

  // 遗漏周期分：倒 U 形回摆（0~2avg 升到 100，超长回落，避免追超长遗漏）
  function missScore(cur, avg) {
    if (avg <= 0) return 50;
    if (cur <= avg) return clamp(Math.round(cur / avg * 80), 0, 100);
    if (cur <= 2 * avg) return clamp(Math.round(80 + (cur - avg) / avg * 20), 0, 100);
    return clamp(Math.round(100 - (cur - 2 * avg) / avg * 30), 0, 100);
  }

  // 对单个号码评分：返回 {num, total, tag, parts:{...}}，parts 七项贡献分之和 = total
  function scoreNumber(num, ctx) {
    var w = ctx.window;
    var n = w.length;
    var hm = ctx.hotMap[num] || null;
    var count = hm ? hm.count : 0;
    var omit = ctx.missMap[num] ? ctx.missMap[num].cur : 0;
    var avg = ctx.missMap[num] ? ctx.missMap[num].avg : 0;
    var avgCount = n * 5 / (ctx.kind === "front" ? 35 : 12);
    var maxCount = ctx.maxCount;
    var oddPct = num % 2 === 1 ? ctx.oddPct : ctx.evenPct;          // 奇偶结构分
    var smallPct = num <= ctx.boundary ? ctx.smallPct : ctx.bigPct; // 大小结构分
    var consecCount = ctx.consecMap[num] || 0;

    // 各维度归一化（0-100）
    var sFrequency = clamp(Math.round(count / avgCount * 50), 0, 100);                 // 历史频率
    var sRecentHot = clamp(Math.round(maxCount ? count / maxCount * 100 : 50), 0, 100); // 近期热度
    var sMissing = missScore(omit, avg);                                               // 遗漏周期
    var sBalance = ctx.balanceMap[num];                                                // 冷热平衡（预计算）
    var sOddEven = clamp(Math.round(oddPct), 0, 100);                                  // 奇偶结构
    var sBigSmall = clamp(Math.round(smallPct), 0, 100);                               // 大小结构
    var sStructure = clamp(Math.round(n ? consecCount / n * 150 : 50), 0, 100);        // 组合结构

    // 加权贡献分（四舍五入，保证七项之和 = 总分）
    var parts = {
      frequency: Math.round(SCORE_WEIGHTS.frequency * sFrequency),
      recentHot: Math.round(SCORE_WEIGHTS.recentHot * sRecentHot),
      missing: Math.round(SCORE_WEIGHTS.missing * sMissing),
      balance: Math.round(SCORE_WEIGHTS.balance * sBalance),
      oddEven: Math.round(SCORE_WEIGHTS.oddEven * sOddEven),
      bigSmall: Math.round(SCORE_WEIGHTS.bigSmall * sBigSmall),
      structure: Math.round(SCORE_WEIGHTS.structure * sStructure)
    };
    var total = parts.frequency + parts.recentHot + parts.missing + parts.balance +
                parts.oddEven + parts.bigSmall + parts.structure;
    return { num: num, total: total, tag: ctx.tagMap[num], parts: parts };
  }

  // 批量评分：kind = "front" | "back"，返回按 total 降序的数组
  function scoreAll(issues, n, kind) {
    var w = sliceWindow(issues, n);
    var nLen = w.length;
    var pool = kind === "front" ? range(FRONT_MIN, FRONT_MAX) : range(BACK_MIN, BACK_MAX);
    var boundary = kind === "front" ? FRONT_BOUNDARY : BACK_BOUNDARY;

    var hot = calculateHot(issues, n, kind);
    var missMap = {};
    calculateMissing(issues, n, kind).forEach(function (m) { missMap[m.num] = m; });
    var hotMap = {}, hotOrder = [];
    hot.forEach(function (h) { hotMap[h.num] = h; hotOrder.push(h.num); });
    var oe = calculateOddEven(issues, n, kind);
    var bs = calculateBigSmall(issues, n, kind, boundary);
    var consecMap = calculateConsec(issues, n, kind);
    var maxCount = hot.length ? hot[0].count : 0;

    // 冷热平衡分：按窗口频率排名三分位基分 + 近期热度微调（过热衰减/过冷补偿）
    var rankMap = {};
    hotOrder.forEach(function (num, idx) { rankMap[num] = idx / Math.max(1, hotOrder.length - 1); });
    var balanceMap = {};
    pool.forEach(function (num) {
      var base = rankMap[num] != null
        ? (rankMap[num] < 1 / 3 ? 72 : rankMap[num] > 2 / 3 ? 42 : 60)
        : 50;
      var hotAdj = clamp(Math.round((hotMap[num] && maxCount ? hotMap[num].count / maxCount * 100 : 50) - 50) / 100 * 16, -8, 8);
      balanceMap[num] = clamp(Math.round(base + hotAdj), 20, 95);
    });

    // 冷热标签：按窗口频率排名三分位（🔥热号 / ⚖平衡 / ❄冷号）
    var tagMap = {};
    pool.forEach(function (num) {
      var r = rankMap[num];
      tagMap[num] = r == null ? "⚖平衡" : r < 1 / 3 ? "🔥热号" : r > 2 / 3 ? "❄冷号" : "⚖平衡";
    });

    var ctx = {
      window: w, kind: kind, boundary: boundary,
      hotMap: hotMap, missMap: missMap, consecMap: consecMap,
      maxCount: maxCount,
      oddPct: oe.odd, evenPct: oe.even, smallPct: bs.small, bigPct: bs.big,
      balanceMap: balanceMap, tagMap: tagMap
    };
    var out = pool.map(function (num) { return scoreNumber(num, ctx); });
    out.sort(function (a, b) { return b.total - a.total; });
    return out;
  }

  /* ================= 渲染层 ================= */

  var PART_LABELS = {
    frequency: "历史频率", recentHot: "近期热度", missing: "遗漏周期",
    balance: "冷热平衡", oddEven: "奇偶结构", bigSmall: "大小结构", structure: "组合结构"
  };

  function renderScoreList(container, items, kind) {
    var numCls = kind === "front" ? "f" : "b";
    var rankCls = kind === "front" ? "front" : "back";
    var top = items.slice(0, TOP_N);
    var html = top.map(function (it, i) {
      var p = it.parts;
      var partsHtml = Object.keys(PART_LABELS).map(function (k) {
        return '<span class="part"><span class="part-lbl">' + PART_LABELS[k] +
          '</span><span class="part-val ' + (p[k] >= 0 ? "plus" : "") + '">' +
          (p[k] >= 0 ? "+" : "") + p[k] + "</span></span>";
      }).join("");
      return '<div class="score-card" data-num="' + it.num + '">' +
        '<div class="score-card-head">' +
        '<span class="rank">' + (i + 1) + "</span>" +
        '<span class="ball ' + numCls + '">' + pad2(it.num) + "</span>" +
        '<span class="score-total">' + it.total + "</span>" +
        '<span class="tag ' + tagCls(it.tag) + '">' + it.tag + "</span>" +
        '<span class="expand-hint">详情 ▾</span></div>' +
        '<div class="score-parts hidden">' + partsHtml + "</div></div>";
    }).join("");
    container.innerHTML = html;
    container.querySelectorAll(".score-card").forEach(function (card) {
      card.addEventListener("click", function () {
        card.querySelector(".score-parts").classList.toggle("hidden");
        card.querySelector(".expand-hint").textContent =
          card.querySelector(".score-parts").classList.contains("hidden") ? "详情 ▾" : "收起 ▴";
      });
    });
  }

  function tagCls(tag) {
    if (tag.indexOf("🔥") >= 0) return "hot";
    if (tag.indexOf("❄") >= 0) return "cold";
    return "mid";
  }

  function showError(msg) {
    document.getElementById("error").hidden = false;
    document.getElementById("error-detail").textContent = msg || "";
  }

  /* ================= 页面启动：loadJSON → scoreAll → render ================= */
  function init() {
    var period = DEFAULT_PERIOD;

    // 版本信息
    document.getElementById("score-version").textContent = SCORE_VERSION.scoreVersion;
    document.getElementById("weight-version").textContent = SCORE_VERSION.weightVersion;
    document.getElementById("generated-from").textContent = SCORE_VERSION.generatedFrom;

    function draw(issues) {
      renderScoreList(document.getElementById("front-scores"), scoreAll(issues, period, "front"), "front");
      renderScoreList(document.getElementById("back-scores"), scoreAll(issues, period, "back"), "back");
    }

    document.getElementById("period-switch").addEventListener("click", function (e) {
      var btn = e.target.closest("button");
      if (!btn) return;
      period = parseInt(btn.getAttribute("data-periods"), 10);
      this.querySelectorAll("button").forEach(function (b) { b.classList.toggle("active", b === btn); });
      draw(this._issues);
    });

    loadJSON("./data/dlt_history.json").then(function (data) {
      var issues = data.issues || [];
      if (!issues.length) throw new Error("历史数据为空");
      document.getElementById("period-switch")._issues = issues;
      draw(issues);
    }).catch(function (err) {
      showError(String(err && err.message ? err.message : err));
    });
  }

  var api = {
    SCORE_VERSION: SCORE_VERSION,
    SCORE_WEIGHTS: SCORE_WEIGHTS,
    PERIODS: PERIODS,
    sliceWindow: sliceWindow,
    calculateHot: calculateHot,
    calculateMissing: calculateMissing,
    calculateOddEven: calculateOddEven,
    calculateBigSmall: calculateBigSmall,
    calculateConsec: calculateConsec,
    scoreAll: scoreAll
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;             // Node 测试用
  } else {
    root.ScoreAPI = api;
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", init);
    } else {
      init();
    }
  }
})(typeof self !== "undefined" ? self : this);
