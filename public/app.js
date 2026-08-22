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

  // 命中等级映射（前端展示层，不改数据）：level 0-4 → 文案
  var HIT_LEVEL_LABELS = ["未命中", "低等级命中", "中等级命中", "高等级命中", "极高等级命中"];
  // 因子三态映射
  var FACTOR_STATUS = {
    "positive": ["✅ 正向", "#16a34a"],
    "neutral": ["⚠️ 中性", "#d97706"],
    "negative": ["❌ 负向", "#dc2626"]
  };

  // 推荐理由：兼容 String（「；」切分多行）/ Array（逐条），一律 esc 转义防注入
  function renderReason(reason) {
    if (!reason || !String(reason).length) {
      return '<span style="opacity:.6">推荐理由：建设中</span>';
    }
    var items = Array.isArray(reason)
      ? reason.map(function (s) { return String(s).trim(); }).filter(Boolean)
      : String(reason).split(/[；;]/).map(function (s) { return s.trim(); }).filter(Boolean);
    if (!items.length) return '<span style="opacity:.6">推荐理由：建设中</span>';
    return items.map(function (s) {
      return '<div style="margin:2px 0;">· ' + esc(s) + "</div>";
    }).join("");
  }

  // 因子三态（positive/neutral/negative）徽标列表；无数据返回空串
  function renderFactorReview(factorReview) {
    if (!factorReview || !Object.keys(factorReview).length) return "";
    var keys = Object.keys(factorReview);
    var badges = keys.map(function (k) {
      var st = factorReview[k] || {};
      var status = st.status || "";
      var conf = FACTOR_STATUS[status] || ["· " + esc(status), "#94a3b8"];
      return '<span style="display:inline-block;padding:2px 8px;border-radius:999px;font-size:12px;' +
        'border:1px solid ' + conf[1] + ";color:" + conf[1] + '">' + esc(k) + " " + conf[0] + "</span>";
    }).join("");
    return '<div style="margin-top:10px;">' +
      '<div style="font-size:12px;color:var(--muted,#94a3b8);margin-bottom:4px;">因子回顾（相对历史中位数）</div>' +
      '<div style="display:flex;flex-wrap:wrap;gap:6px;">' + badges + "</div></div>";
  }

  // 上期推荐复盘：review.json → 首页③模块动态渲染
  function renderReview(container, review) {
    if (!container) return;
    if (!review || review.empty === true || !review.issue) {
      container.innerHTML = '<div style="padding:6px;">📭 暂无复盘数据（待开奖后自动生成）</div>';
      return;
    }
    var rec = review.recommendation || {};
    var act = review.actual_result || {};
    var hit = review.hit_count || {};
    var ana = review.analysis || {};
    var level = typeof hit.level === "number" ? hit.level : 0;
    var levelLabel = HIT_LEVEL_LABELS[level] || "未知等级";
    var fr = renderFactorReview(ana.factor_review);

    container.innerHTML =
      '<div style="text-align:left;">' +
        '<div style="font-size:13px;color:var(--accent,#6d28d9);font-weight:600;margin-bottom:10px;">' +
          "复盘期号：" + esc(review.issue) + " 期</div>" +
        '<div style="display:flex;flex-wrap:wrap;gap:16px;align-items:flex-start;">' +
          '<div style="flex:1;min-width:220px;">' +
            '<div style="font-size:12px;color:var(--muted,#94a3b8);margin-bottom:4px;">🤖 AI 上期推荐 · ' +
              esc(rec.strategy || "") + "</div>" +
            '<div style="display:flex;flex-wrap:wrap;align-items:center;gap:8px;">' +
              '<span style="color:#a78bfa;font-size:12px;">前区</span>' + balls(rec.front || [], "front") +
            "</div>" +
            '<div style="display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin-top:4px;">' +
              '<span style="color:#a78bfa;font-size:12px;">后区</span>' + balls(rec.back || [], "back") +
            "</div>" +
          "</div>" +
          '<div style="flex:1;min-width:220px;">' +
            '<div style="font-size:12px;color:var(--muted,#94a3b8);margin-bottom:4px;">🎲 实际开奖</div>' +
            '<div style="display:flex;flex-wrap:wrap;align-items:center;gap:8px;">' +
              '<span style="color:#a78bfa;font-size:12px;">前区</span>' + balls(act.front || [], "front") +
            "</div>" +
            '<div style="display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin-top:4px;">' +
              '<span style="color:#a78bfa;font-size:12px;">后区</span>' + balls(act.back || [], "back") +
            "</div>" +
          "</div>" +
        "</div>" +
        '<div style="display:flex;flex-wrap:wrap;gap:12px;margin-top:12px;font-size:13px;">' +
          '<span>前区命中 <strong style="color:#f59e0b">' + (hit.front == null ? 0 : hit.front) + "</strong></span>" +
          '<span>后区命中 <strong style="color:#f59e0b">' + (hit.back == null ? 0 : hit.back) + "</strong></span>" +
          '<span>总命中 <strong style="color:#f59e0b">' + (hit.total == null ? 0 : hit.total) + "</strong></span>" +
          '<span style="display:inline-block;padding:1px 8px;border-radius:999px;font-size:12px;' +
            'border:1px solid var(--accent,#6d28d9);color:var(--accent,#6d28d9);">' + esc(levelLabel) + "</span>" +
        "</div>" +
        (typeof ana.sum_diff === "number"
          ? '<div style="margin-top:8px;font-size:13px;">和值偏差：<strong>' + ana.sum_diff +
            "</strong>　距一等奖理论距离：" + (ana.distance_score == null ? "—" : ana.distance_score) + "</div>"
          : "") +
        fr +
        '<div style="margin-top:10px;font-size:11px;color:var(--muted,#94a3b8);">' +
          esc(review.disclaimer || "复盘仅为娱乐回顾，不代表预测中奖") + "</div>" +
      "</div>";
  }

  // 下一期模型调整方向（D2.2）：next_adjustment 数组 → 方向图标 + 文本 + 理由
  var ADJUST_ICONS = { "reduce": "↓", "increase": "↑", "keep": "→" };
  function renderNextAdjustment(list) {
    if (!Array.isArray(list) || !list.length) {
      return '<span style="color:var(--muted,#94a3b8)">暂无调整建议。</span>';
    }
    return list.map(function (it) {
      var t = it && it.type ? it.type : "keep";
      var icon = ADJUST_ICONS[t] || "→";
      var reason = (it && it.reason && String(it.reason).length)
        ? '<span style="color:var(--muted,#94a3b8)">（' + esc(it.reason) + "）</span>"
        : "";
      return '<div style="margin:3px 0;font-size:13px;"><span style="display:inline-block;width:18px;' +
        'font-weight:700;color:var(--accent,#6d28d9);">' + icon + "</span>" +
        esc((it && it.text) || "") + reason + "</div>";
    }).join("");
  }

  // 策略历史表现小字（唯一推荐卡底部；数据缺失整行隐藏，不新增首页模块）
  function renderStrategyHint(container, strategyScore, primaryStrategy) {
    if (!container || !strategyScore || strategyScore.empty === true) return;
    var list = Array.isArray(strategyScore.strategies) ? strategyScore.strategies : [];
    var group = (primaryStrategy || "").split("-")[0];
    var row = null;
    for (var i = 0; i < list.length; i++) {
      if (list[i] && list[i].strategy === group) { row = list[i]; break; }
    }
    if (!row) return;
    var label = row.label || group;
    container.innerHTML = "📈 策略历史表现：" + esc(label) +
      " 当前排名第" + (row.rank == null ? "—" : row.rank) +
      "（样本 " + (row.total_count == null ? 0 : row.total_count) + " 期）";
  }

  // 唯一推荐选择逻辑（兼容增强，不改变现有 D 结果）：
  // final 字段 > is_primary 标记 > score 降序 > D 策略 fallback > 首条
  function selectPrimary(recs) {
    if (!recs || !recs.length) return null;
    var byFinal = recs.filter(function (r) { return r.final === true; })[0];
    if (byFinal) return byFinal;
    var byPrimary = recs.filter(function (r) { return r.is_primary === true; })[0];
    if (byPrimary) return byPrimary;
    var withScore = recs.filter(function (r) { return typeof r.score === "number"; });
    if (withScore.length) {
      withScore.sort(function (a, b) { return b.score - a.score; });
      return withScore[0];
    }
    var byD = recs.filter(function (r) { return (r.strategy || "").split("-")[0] === "D"; })[0];
    return byD || recs[0];
  }

  // 评分拆解（D3.3）：final_breakdown → 小字分量列表；无数据返回空串
  var BD_LABELS = {
    "base": "策略基础", "history": "历史表现", "recent": "近期表现",
    "structure": "结构贴合", "risk": "风险调整"
  };
  var STAGE_LABELS = { "cold": "冷启动", "transition": "过渡期", "stable": "稳定期" };
  function renderScoreBreakdown(b) {
    if (!b || typeof b !== "object") return "";
    var chips = ["base", "history", "recent", "structure", "risk"].map(function (k) {
      if (typeof b[k] !== "number") return "";
      return '<span style="display:inline-block;padding:1px 7px;border-radius:999px;font-size:11px;' +
        'border:1px solid rgba(167,139,250,.35);color:#c4b5fd;">' + (BD_LABELS[k] || esc(k)) +
        " " + b[k].toFixed(1) + "</span>";
    }).filter(Boolean).join("");
    var meta = [];
    if (b.stage && STAGE_LABELS[b.stage]) meta.push("样本阶段：" + STAGE_LABELS[b.stage]);
    if (b.effective_sample != null) meta.push("有效样本 " + b.effective_sample + " 期");
    if (b.degraded) meta.push("样本不足降级");
    if (b.locked_cold_start) meta.push("冷启动锁定综合评分型");
    var metaHtml = meta.length
      ? '<div style="margin-top:4px;font-size:11px;color:var(--muted,#94a3b8);">' +
        meta.map(esc).join(" · ") + "</div>"
      : "";
    if (!chips && !metaHtml) return "";
    return '<div style="margin-top:8px;padding-top:8px;border-top:1px dashed rgba(109,40,217,.25);">' +
      '<div style="font-size:11px;color:var(--muted,#94a3b8);margin-bottom:4px;">评分拆解（模型分量，非概率）</div>' +
      '<div style="display:flex;flex-wrap:wrap;gap:5px;">' + chips + "</div>" + metaHtml + "</div>";
  }

  function renderPrimaryRecommendation(container, recs) {
    if (!container) return null;
    var p = selectPrimary(recs);
    if (!p) { container.innerHTML = ""; return null; }
    var label = (p.strategy || "综合评分型").split("-").slice(1).join("-") || "综合评分型";
    // 评分（D3.3）：优先 final_score（跨策略融合 0-100），旧 score 字段回退兼容；
    // 两者皆缺 → 建设中。量纲统一展示，非概率。
    var fs = (typeof p.final_score === "number") ? p.final_score
           : (typeof p.score === "number") ? p.score : null;
    var scoreHtml = (fs !== null)
      ? '<span title="综合评分为模型评价指标，不代表中奖概率">AI 综合评分：<strong style="color:#fbbf24">' +
        fs.toFixed(1) + " / 100</strong></span>"
      : '<span style="opacity:.6">AI 综合评分：建设中</span>';
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
        '<div style="margin:10px 0 0;font-size:13px;line-height:1.5;">💡 <span id="reason-root">' +
          renderReason(p.reason) + '</span></div>' +
        renderScoreBreakdown(p.final_breakdown) +
        '<p style="margin:8px 0 0;font-size:11px;opacity:.7;">综合评分为模型评价指标，不代表中奖概率</p>' +
        '<p style="margin:6px 0 0;font-size:12px;color:#fbbf24;">⚠️ 基于历史统计的娱乐产物，非中奖预测</p>' +
        '<div id="strategy-hint" style="margin-top:10px;padding-top:8px;border-top:1px dashed ' +
          'rgba(109,40,217,.25);font-size:12px;color:#c4b5fd;"></div>' +
      '</div>';
    return p;
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
    loadJSON("./data/recommendations.json").catch(function () { return []; }),
    loadJSON("./data/review.json").catch(function () { return null; }),
    loadJSON("./data/strategy_score.json").catch(function () { return null; })
  ]).then(function (res) {
    var history = res[0];
    var recs = res[1] || [];
    var review = res[2];
    var strategyScore = res[3];
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
      var primary = renderPrimaryRecommendation(document.getElementById("primary-recommendation"), recs);
      renderRecommendations(document.getElementById("recommendations"), recs);
      if (primary) {
        renderStrategyHint(document.getElementById("strategy-hint"), strategyScore, primary.strategy);
      }
    }

    /* ③ 上期推荐复盘：review.json 动态渲染（缺失/empty → 降级占位） */
    renderReview(document.getElementById("review-placeholder"), review);

    /* ③ 下一期模型调整方向（D2.2）：review 缺失/空 → 暂无建议 */
    var naBody = document.getElementById("next-adjustment-body");
    if (naBody) {
      naBody.innerHTML = renderNextAdjustment(review ? review.next_adjustment : null);
    }

    document.getElementById("content").hidden = false;
    } catch (e) {
      showError(String(e && e.message ? e.message : e));
    }
  }).catch(function (err) {
    showError(String(err && err.message ? err.message : err));
  });
})();
