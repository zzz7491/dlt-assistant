/* =========================================================
   大乐透历史走势图 · 数据处理与渲染
   - 纯数据逻辑（buildMatrices）与 DOM 渲染分离，便于测试
   - 读取 ./data/dlt_history.json，不修改任何现有文件/逻辑
   - 前区 01-35 / 后区 01-12，支持最近 100 / 300 / 1000 期切换
   ========================================================= */
(function (root) {
  "use strict";

  var PERIODS = [100, 300, 1000];
  var DEFAULT_PERIOD = 100;

  function pad2(n) { return String(n).padStart(2, "0"); }

  function loadJSON(path) {
    return fetch(path, { cache: "no-cache" }).then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status + " @ " + path);
      return r.json();
    });
  }

  /* ---------- 纯数据层：构建矩阵 ---------- */
  function buildMatrices(issues) {
    var sorted = issues.slice().sort(function (a, b) {
      return a.issue < b.issue ? -1 : a.issue > b.issue ? 1 : 0;
    });
    function mk(pmin, pmax, key) {
      var labels = [];
      for (var i = pmin; i <= pmax; i++) labels.push(i);
      var matrix = labels.map(function () {
        return new Array(sorted.length).fill(false);
      });
      sorted.forEach(function (it, ci) {
        it[key].forEach(function (x) { matrix[x - pmin][ci] = true; });
      });
      return { labels: labels, issues: sorted, matrix: matrix };
    }
    return { front: mk(1, 35, "front"), back: mk(1, 12, "back") };
  }

  /* ---------- DOM 渲染层 ---------- */
  function renderTableHTML(m, kind, n) {
    var issues = m.issues;
    var start = Math.max(0, issues.length - n);
    var cols = issues.slice(start);
    var rows = m.labels;
    var hitClass = kind === "front" ? "hit-f" : "hit-b";
    var numCls = kind === "front" ? "f" : "b";
    var parts = [];

    // 表头：期号（后 3 位，稀疏显示）
    parts.push('<table class="trend-table"><thead><tr><th class="corner"></th>');
    for (var c = 0; c < cols.length; c++) {
      var show = (c % 10 === 0) || (c === cols.length - 1);
      parts.push('<th class="issue-cell">' + (show ? cols[c].issue.slice(2) : "") + "</th>");
    }
    parts.push("</tr></thead><tbody>");

    // 数据行：号码行，命中标记圆点
    for (var r = 0; r < rows.length; r++) {
      var row = m.matrix[r];
      parts.push('<tr><th class="num-cell ' + numCls + '">' + pad2(rows[r]) + "</th>");
      for (var ci = 0; ci < cols.length; ci++) {
        parts.push(row[start + ci] ? '<td class="cell ' + hitClass + '"></td>' : "<td class='cell'></td>");
      }
      parts.push("</tr>");
    }
    parts.push("</tbody></table>");
    return parts.join("");
  }

  function showError(msg) {
    var box = document.getElementById("error");
    box.hidden = false;
    document.getElementById("error-detail").textContent = msg || "";
  }

  /* ---------- 页面启动 ---------- */
  function init() {
    var frontWrap = document.getElementById("front-table");
    var backWrap = document.getElementById("back-table");
    var matrix = null;
    var current = { front: DEFAULT_PERIOD, back: DEFAULT_PERIOD };

    function draw() {
      frontWrap.innerHTML = renderTableHTML(matrix.front, "front", current.front);
      backWrap.innerHTML = renderTableHTML(matrix.back, "back", current.back);
    }

    // 期数切换按钮绑定
    function bindSwitch(switchId, kind) {
      var sw = document.getElementById(switchId);
      sw.addEventListener("click", function (e) {
        var btn = e.target.closest("button");
        if (!btn) return;
        current[kind] = parseInt(btn.getAttribute("data-periods"), 10);
        sw.querySelectorAll("button").forEach(function (b) {
          b.classList.toggle("active", b === btn);
        });
        draw();
      });
    }
    bindSwitch("front-switch", "front");
    bindSwitch("back-switch", "back");

    loadJSON("./data/dlt_history.json").then(function (data) {
      var issues = data.issues || [];
      if (!issues.length) throw new Error("历史数据为空");
      matrix = buildMatrices(issues);
      draw();
    }).catch(function (err) {
      showError(String(err && err.message ? err.message : err));
    });
  }

  var api = { buildMatrices: buildMatrices, renderTableHTML: renderTableHTML, PERIODS: PERIODS };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;             // Node 测试用
  } else {
    root.TrendAPI = api;
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", init);
    } else {
      init();
    }
  }
})(typeof self !== "undefined" ? self : this);
