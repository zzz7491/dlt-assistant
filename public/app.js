/* 纯静态前端：读取 data/dlt_history.json 与 data/recommendations.json，
   在浏览器内复算分析指标并渲染页面。无后端、无构建步骤。 */
(function () {
  "use strict";

  var FRONT_MIN = 1, FRONT_MAX = 35;
  var BACK_MIN = 1, BACK_MAX = 12;
  var BOUNDARY = 18; // 大小分界：1-17 小，18-35 大

  function pad2(n) { return String(n).padStart(2, "0"); }

  function loadJSON(path) {
    return fetch(path, { cache: "no-cache" }).then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status + " @ " + path);
      return r.json();
    });
  }

  /* ---------- 分析（与 src/analyzer.py 口径一致） ---------- */
  function analyze(issues) {
    var sorted = issues.slice().sort(function (a, b) {
      return a.issue < b.issue ? -1 : a.issue > b.issue ? 1 : 0;
    });
    var n = sorted.length;

    var frontFreq = countFreq(sorted, "front", FRONT_MIN, FRONT_MAX);
    var backFreq = countFreq(sorted, "back", BACK_MIN, BACK_MAX);

    var frontHot = topN(frontFreq, 10);
    var backHot = topN(backFreq, 5);

    var frontOmit = currentOmission(sorted, "front", FRONT_MIN, FRONT_MAX);
    var backOmit = currentOmission(sorted, "back", BACK_MIN, BACK_MAX);
    var frontCold = topOmission(frontOmit, 8);
    var backCold = topOmission(backOmit, 4);

    var oddEven = {}, bigSmall = {};
    var consecIssues = 0, consecPairs = 0;
    sorted.forEach(function (it) {
      var f = it.front.slice().sort(function (a, b) { return a - b; });
      var odd = f.filter(function (x) { return x % 2 === 1; }).length;
      var oeKey = "奇" + odd + ":偶" + (5 - odd);
      oddEven[oeKey] = (oddEven[oeKey] || 0) + 1;
      var big = f.filter(function (x) { return x >= BOUNDARY; }).length;
      var bsKey = "大" + big + ":小" + (5 - big);
      bigSmall[bsKey] = (bigSmall[bsKey] || 0) + 1;
      var pairs = 0;
      for (var i = 0; i < f.length - 1; i++) if (f[i + 1] - f[i] === 1) pairs++;
      if (pairs > 0) consecIssues++;
      consecPairs += pairs;
    });

    return {
      n: n,
      firstIssue: sorted.length ? sorted[0].issue : "-",
      lastIssue: sorted.length ? sorted[sorted.length - 1].issue : "-",
      firstDate: sorted.length ? sorted[0].date : "-",
      lastDate: sorted.length ? sorted[sorted.length - 1].date : "-",
      frontHot: frontHot,
      backHot: backHot,
      frontCold: frontCold,
      backCold: backCold,
      oddEven: oddEven,
      bigSmall: bigSmall,
      consecProb: n ? consecIssues / n : 0,
      consecAvg: n ? consecPairs / n : 0
    };
  }

  function countFreq(issues, key, pmin, pmax) {
    var m = {};
    for (var i = pmin; i <= pmax; i++) m[i] = 0;
    issues.forEach(function (it) {
      it[key].forEach(function (x) { m[x] = (m[x] || 0) + 1; });
    });
    return m;
  }

  function topN(freq, N) {
    return Object.keys(freq).map(function (k) { return [parseInt(k, 10), freq[k]]; })
      .sort(function (a, b) { return b[1] - a[1]; }).slice(0, N);
  }

  function currentOmission(issues, key, pmin, pmax) {
    var cur = {};
    for (var i = pmin; i <= pmax; i++) cur[i] = 0;
    issues.forEach(function (it) {
      var s = {};
      it[key].forEach(function (x) { s[x] = true; });
      for (var j = pmin; j <= pmax; j++) {
        if (s[j]) cur[j] = 0; else cur[j]++;
      }
    });
    return cur;
  }

  function topOmission(omit, N) {
    return Object.keys(omit).map(function (k) { return [parseInt(k, 10), omit[k]]; })
      .filter(function (e) { return e[1] > 0; })
      .sort(function (a, b) { return b[1] - a[1]; }).slice(0, N);
  }

  /* ---------- 渲染 ---------- */
  function balls(nums, kind) {
    return nums.map(function (x) {
      return '<span class="ball ' + kind + '">' + pad2(x) + "</span>";
    }).join("");
  }

  /* 统计大屏渲染函数（renderHot/renderCold/renderBars）已随首页 V2 重构移除，
     对应区块迁移至 数据分析 / 趋势分析 页，本文件仅保留首页决策入口所需渲染。 */



  function renderRecommendations(container, recs) {
    var order = { "A": 1, "B": 2, "C": 3 };
    var groups = {};
    recs.forEach(function (r) {
      var prefix = (r.strategy || "").split("-")[0] || "?";
      (groups[prefix] = groups[prefix] || []).push(r);
    });
    var prefixes = Object.keys(groups).sort(function (a, b) {
      return (order[a] || 9) - (order[b] || 9);
    });
    container.innerHTML = prefixes.map(function (p) {
      var r = groups[p][0];
      var tag = (r.strategy || "").split("-").slice(1).join("-") || "娱乐型";
      return '<div class="rec-card"><h4>推荐 ' + p + '</h4>' +
        '<span class="tag">' + tag + "</span>" +
        '<div class="grp"><span class="lbl">前区</span>' + balls(r.front, "front") + "</div>" +
        '<div class="grp"><span class="lbl">后区</span>' + balls(r.back, "back") + "</div></div>";
    }).join("");
  }

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  // 唯一推荐选择逻辑（不写死 D）：final 字段 > score 降序 > D 策略 fallback > 首条
  function selectPrimary(recs) {
    if (!recs || !recs.length) return null;
    var byFinal = recs.filter(function (r) { return r.final === true; })[0];
    if (byFinal) return byFinal;
    var withScore = recs.filter(function (r) { return typeof r.score === "number"; });
    if (withScore.length) {
      withScore.sort(function (a, b) { return b.score - a.score; });
      return withScore[0];
    }
    var byD = recs.filter(function (r) { return (r.strategy || "").split("-")[0] === "D"; })[0];
    return byD || recs[0];
  }

  function renderPrimaryRecommendation(container, recs) {
    if (!container) return;
    var p = selectPrimary(recs);
    if (!p) { container.innerHTML = ""; return; }
    var label = (p.strategy || "综合评分型").split("-").slice(1).join("-") || "综合评分型";
    var scoreHtml = (typeof p.score === "number")
      ? '<span>AI 评分：<strong style="color:#fbbf24">' + p.score.toFixed(1) + "/10</strong></span>"
      : '<span style="opacity:.6">AI 评分：建设中</span>';
    var reason = (p.reason && String(p.reason).length)
      ? esc(p.reason)
      : '<span style="opacity:.6">推荐理由：建设中（Phase 2 数据就绪后展示）</span>';
    container.innerHTML =
      '<div style="border:1px solid var(--accent, #6d28d9);border-radius:14px;padding:18px;' +
      'background:linear-gradient(135deg, rgba(109,40,217,.14), rgba(109,40,217,.04));">' +
        '<div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;' +
        'font-size:13px;color:#c4b5fd;letter-spacing:.5px;margin-bottom:10px;">' +
          '<span>' + esc(label) + ' · 唯一推荐</span>' + scoreHtml +
        '</div>' +
        '<div style="display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin:6px 0;">' +
          '<span style="color:#a78bfa;font-size:13px;min-width:36px;">前区</span>' + balls(p.front, "front") +
        '</div>' +
        '<div style="display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin:6px 0;">' +
          '<span style="color:#a78bfa;font-size:13px;min-width:36px;">后区</span>' + balls(p.back, "back") +
        '</div>' +
        '<p style="margin:10px 0 0;font-size:13px;line-height:1.5;">💡 ' + reason + '</p>' +
        '<p style="margin:10px 0 0;font-size:12px;color:#fbbf24;">⚠️ 基于历史统计的娱乐产物，非中奖预测</p>' +
      '</div>';
  }

  /* ---------- 启动 ---------- */
  function showError(msg) {
    document.getElementById("content").hidden = true;
    var box = document.getElementById("error");
    box.hidden = false;
    if (msg) document.getElementById("error-detail").textContent = msg;
  }

  /* 数据档案与复盘（initArchive/fmtUpdated/probeReport）已随首页 V2 重构移除，
     该区块迁移至对应分析页；本期复盘模块以静态占位呈现，待 Phase 2 数据就绪后填充。 */



  Promise.all([
    loadJSON("./data/dlt_history.json"),
    loadJSON("./data/recommendations.json").catch(function () { return []; })
  ]).then(function (res) {
    var history = res[0];
    var recs = res[1] || [];
    try {
    var issues = history.issues || [];
    if (!issues.length) { showError("历史数据为空"); return; }

    var a = analyze(issues);

    /* ① 最新开奖结果（issues 最后一条 = 最新一期，仅展示） */
    var lastIssue = issues[issues.length - 1];
    document.getElementById("latest-issue").textContent = lastIssue.issue + "期";
    document.getElementById("latest-date").textContent = lastIssue.date;
    document.getElementById("latest-front").innerHTML = balls(lastIssue.front, "front");
    document.getElementById("latest-back").innerHTML = balls(lastIssue.back, "back");

    // ① 最新开奖：简短结果分析
    var fSorted = lastIssue.front.slice().sort(function (a, b) { return a - b; });
    var oddCnt = fSorted.filter(function (x) { return x % 2 === 1; }).length;
    var consecCnt = 0;
    for (var ci = 0; ci < fSorted.length - 1; ci++) {
      if (fSorted[ci + 1] - fSorted[ci] === 1) consecCnt++;
    }
    var laEl = document.getElementById("latest-analysis");
    if (laEl) {
      laEl.textContent = "前区奇偶比 " + oddCnt + ":" + (5 - oddCnt) +
        "，后区 " + lastIssue.back.join("/") +
        "；连号 " + (consecCnt > 0 ? "有 " + consecCnt + " 对" : "无") +
        "。纯历史统计，不构成预测。";
    }

    if (recs.length) {
      var recTargetEl = document.getElementById("rec-target");
      if (recTargetEl) recTargetEl.textContent = recs[0].target_issue || "—";
      renderPrimaryRecommendation(document.getElementById("primary-recommendation"), recs);
      renderRecommendations(document.getElementById("recommendations"), recs);
    }

    document.getElementById("content").hidden = false;
    } catch (e) {
      showError(String(e && e.message ? e.message : e));
    }
  }).catch(function (err) {
    showError(String(err && err.message ? err.message : err));
  });
})();
