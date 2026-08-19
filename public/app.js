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

  function renderHot(container, items, kind) {
    container.innerHTML = items.map(function (e) {
      var num = e[0], cnt = e[1];
      return '<span class="rank-item"><span class="num ' + kind + '">' +
        pad2(num) + '</span><span class="cnt">出现 ' + cnt + " 次</span></span>";
    }).join("");
  }

  function renderCold(container, items, kind) {
    container.innerHTML = items.map(function (e) {
      var num = e[0], omit = e[1];
      return '<span class="rank-item"><span class="num ' + kind + '">' +
        pad2(num) + '</span><span class="omit">遗漏 ' + omit + " 期</span></span>";
    }).join("");
  }

  function renderBars(container, dist) {
    var entries = Object.keys(dist).map(function (k) {
      return [k, dist[k]];
    }).sort(function (a, b) {
      return a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0;
    });
    var max = Math.max.apply(null, entries.map(function (e) { return e[1]; }).concat([1]));
    container.innerHTML = entries.map(function (e) {
      var pct = Math.round((e[1] / max) * 100);
      return '<div class="bar-row"><span class="bar-label">' + e[0] +
        '</span><span class="bar-track"><span class="bar-fill" style="width:' +
        pct + '%"></span></span><span class="bar-val">' + e[1] + " 期</span></div>";
    }).join("");
  }

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

  /* ---------- 启动 ---------- */
  function showError(msg) {
    document.getElementById("content").hidden = true;
    var box = document.getElementById("error");
    box.hidden = false;
    if (msg) document.getElementById("error-detail").textContent = msg;
  }

  /* ---------- ⑤ 数据档案与复盘（历史报告区改造） ---------- */

  // 数据更新时间展示（ISO → 本地可读时间）
  function fmtUpdated(iso) {
    if (!iso) return "—";
    var d = new Date(iso);
    if (isNaN(d.getTime())) return iso;
    return d.toLocaleString("zh-CN", { hour12: false });
  }

  // 探测指定日期的简报是否已发布（HEAD 请求，失败返回 null）
  function probeReport(dateStr) {
    var fname = "report_" + dateStr.replace(/-/g, "") + ".md";
    var url = "./reports/" + fname;
    return fetch(url, { method: "HEAD", cache: "no-cache" }).then(function (r) {
      return r.ok ? url : null;
    }).catch(function () { return null; });
  }

  // 从最新推荐日期向前回退最多 3 天，找到最近一份已发布简报并展示
  function initArchive(history, recs) {
    var updatedEl = document.getElementById("archive-updated");
    if (updatedEl) {
      updatedEl.innerHTML = "数据更新时间：<strong>" + fmtUpdated(history && history.updated_at) + "</strong>";
    }
    var latestEl = document.getElementById("archive-latest");
    if (!latestEl) return;

    // 基准日期：优先推荐记录生成日期，回退到历史数据更新时间
    var base = "";
    if (recs && recs.length && recs[0].date) {
      base = recs[0].date;
    } else if (history && history.updated_at) {
      base = history.updated_at.slice(0, 10);
    }
    if (!base) { latestEl.innerHTML = '<span style="color:var(--muted)">暂无已发布简报</span>'; return; }

    var d = new Date(base);
    if (isNaN(d.getTime())) { latestEl.innerHTML = '<span style="color:var(--muted)">暂无已发布简报</span>'; return; }

    var attempts = [];
    for (var i = 0; i < 3; i++) {
      var t = new Date(d);
      t.setDate(t.getDate() - i);
      attempts.push(String(t.getFullYear()) + "-" + pad2(t.getMonth() + 1) + "-" + pad2(t.getDate()));
    }

    (function probe(idx) {
      if (idx >= attempts.length) {
        latestEl.innerHTML = '<span style="color:var(--muted)">暂无已发布简报（生成中）</span>';
        return;
      }
      var ds = attempts[idx];
      probeReport(ds).then(function (url) {
        if (url) {
          latestEl.innerHTML = '<a href="' + url + '">每日复盘简报（' + ds + "）</a>";
        } else {
          probe(idx + 1);
        }
      });
    })(0);
  }

  Promise.all([
    loadJSON("./data/dlt_history.json"),
    loadJSON("./data/recommendations.json").catch(function () { return []; })
  ]).then(function (res) {
    var history = res[0];
    var recs = res[1] || [];
    var issues = history.issues || [];
    if (!issues.length) { showError("历史数据为空"); return; }

    var a = analyze(issues);

    /* ① 最新开奖结果（issues 最后一条 = 最新一期，仅展示） */
    var lastIssue = issues[issues.length - 1];
    document.getElementById("latest-issue").textContent = lastIssue.issue + "期";
    document.getElementById("latest-date").textContent = lastIssue.date;
    document.getElementById("latest-front").innerHTML = balls(lastIssue.front, "front");
    document.getElementById("latest-back").innerHTML = balls(lastIssue.back, "back");

    document.getElementById("cover-count").textContent = a.n;
    document.getElementById("cover-range").textContent =
      a.firstDate + " 至 " + a.lastDate;
    var srcName = { "500": "500彩票网" }[history.source] || (history.source || "公开数据源");
    document.getElementById("cover-source").textContent = "数据来源：" + srcName;

    document.getElementById("meta-line").textContent =
      "最近 " + a.n + " 期历史统计 · 数据范围 " + a.firstIssue + " ~ " + a.lastIssue +
      "（截至 " + a.lastDate + "）" +
      (recs[0] ? " · 预测期号 " + recs[0].target_issue + "（推荐生成 " + recs[0].date + "）" : "");

    renderHot(document.getElementById("hot-front"), a.frontHot, "front");
    renderHot(document.getElementById("hot-back"), a.backHot, "back");
    renderCold(document.getElementById("cold-front"), a.frontCold, "front");
    renderCold(document.getElementById("cold-back"), a.backCold, "back");
    renderBars(document.getElementById("odd-even"), a.oddEven);
    renderBars(document.getElementById("big-small"), a.bigSmall);
    document.getElementById("consec").innerHTML =
      "含连号的期占比 <strong>" + (a.consecProb * 100).toFixed(1) + "%</strong>" +
      "，平均每期 <strong>" + a.consecAvg.toFixed(2) + "</strong> 对连号。";

    if (recs.length) {
      document.getElementById("rec-target").textContent = recs[0].target_issue || "—";
      renderRecommendations(document.getElementById("recommendations"), recs);
    }

    /* ⑤ 数据档案与复盘：动态化每日简报 + 模型档案 */
    initArchive(history, recs);

    document.getElementById("content").hidden = false;
  }).catch(function (err) {
    showError(String(err && err.message ? err.message : err));
  });
})();
