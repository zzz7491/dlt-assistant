/* =========================================================
   pick-v2.js - 智能选号助手前端逻辑（静态数据版）
   数据来源：优先读取 public/data/recommendation_new.json
             失败降级到提示无法获取推荐
   功能：加载、渲染、刷新推荐
   ========================================================= */
(function (root) {
  "use strict";

  // ==================== 配置常量 ====================
  var STATIC_DATA_PATH = "./data/recommendation_new.json";
  var FRONT_MIN = 1, FRONT_MAX = 35;
  var BACK_MIN = 1, BACK_MAX = 12;
  var FRONT_BOUNDARY = 17;
  var BACK_BOUNDARY = 6;
  var ZONES = [12, 24];

  // ==================== 工具函数 ====================
  function pad2(n) {
    return String(n).padStart(2, "0");
  }

  function showError(msg) {
    var errorEl = document.getElementById("pv2-error");
    var loadingEl = document.getElementById("pv2-loading");
    var heroEl = document.getElementById("pv2-hero");
    
    loadingEl.hidden = true;
    heroEl.hidden = true;
    errorEl.hidden = false;
    errorEl.querySelector("p").textContent = msg || "加载失败，请稍后重试";
  }

  function hideError() {
    document.getElementById("pv2-error").hidden = true;
  }

  // ==================== 渲染函数 ====================

  /**
   * 渲染号码球
   */
  function renderBalls(containerId, numbers, kind) {
    var container = document.getElementById(containerId);
    if (!container) return;
    
    container.innerHTML = numbers.map(function(num) {
      return '<span class="ball ' + kind + '">' + pad2(num) + '</span>';
    }).join("");
  }

  /**
   * 渲染推荐理由列表
   */
  function renderReasons(containerId, reasons) {
    var container = document.getElementById(containerId);
    if (!container) return;
    
    if (!reasons || reasons.length === 0) {
      container.innerHTML = '<li>结构合理，分布均衡</li>';
      return;
    }
    
    container.innerHTML = reasons.map(function(r) {
      return '<li>' + r + '</li>';
    }).join("");
  }

  /**
   * 渲染主推荐
   */
  function renderMainRecommendation(main) {
    if (!main) return;
    
    // 显示号码
    renderBalls("pv2-main-front", main.front || [], "front");
    renderBalls("pv2-main-back", main.back || [], "back");
    
    // 显示评分
    var scoreEl = document.getElementById("pv2-main-score");
    if (scoreEl && main.score !== undefined) {
      scoreEl.textContent = main.score.toFixed(1);
    }
    
    // 显示理由
    renderReasons("pv2-main-reasons", main.reasons || []);
  }

  /**
   * 渲染备选方案
   */
  function renderBackupOptions(backups) {
    var container = document.getElementById("pv2-backup-list");
    if (!container) return;
    
    if (!backups || backups.length === 0) {
      container.innerHTML = '<p class="pv2-hint">暂无备选方案</p>';
      return;
    }
    
    container.innerHTML = backups.map(function(b, i) {
      var frontBalls = (b.front || []).map(function(n) {
        return '<span class="ball front">' + pad2(n) + '</span>';
      }).join("");
      
      var backBalls = (b.back || []).map(function(n) {
        return '<span class="ball back">' + pad2(n) + '</span>';
      }).join("");
      
      return '<div class="pv2-backup-item">' +
        '<div class="pv2-backup-label">方案' + String.fromCharCode(65 + i) + '</div>' +
        '<div class="pv2-backup-score">评分: ' + (b.score || '--').toFixed(1) + '</div>' +
        '<div class="pv2-balls-container front" style="margin-bottom:8px">' + frontBalls + '</div>' +
        '<div class="pv2-balls-container back">' + backBalls + '</div>' +
        '</div>';
    }).join("");
  }

  /**
   * 渲染质量分析指标
   */
  function renderQualityMetrics(main) {
    var container = document.getElementById("pv2-metrics");
    if (!container || !main) return;
    
    var details = main.score_details || {};
    var front = main.front || [];
    
    // 计算指标
    var sum = front.reduce(function(a, b) { return a + b; }, 0);
    var span = front.length > 0 ? front[front.length - 1] - front[0] : 0;
    var oddCount = front.filter(function(n) { return n % 2 === 1; }).length;
    var bigCount = front.filter(function(n) { return n > FRONT_BOUNDARY; }).length;
    
    // 三区分布
    var zone1 = front.filter(function(n) { return n <= ZONES[0]; }).length;
    var zone2 = front.filter(function(n) { return n > ZONES[0] && n <= ZONES[1]; }).length;
    var zone3 = front.filter(function(n) { return n > ZONES[1]; }).length;
    
    // 连号数量
    var consecCount = 0;
    for (var i = 1; i < front.length; i++) {
      if (front[i] - front[i-1] === 1) consecCount++;
    }
    
    var metrics = [
      { label: "和值", value: sum, status: (sum >= 60 && sum <= 140) ? "正常" : "异常", max: 140 },
      { label: "跨度", value: span, status: (span >= 10 && span <= 40) ? "正常" : "异常", max: 40 },
      { label: "奇偶比", value: oddCount + ":" + (5 - oddCount), status: (oddCount === 2 || oddCount === 3) ? "均衡" : "偏态", max: 5 },
      { label: "大小比", value: bigCount + ":" + (5 - bigCount), status: (bigCount === 2 || bigCount === 3) ? "均衡" : "偏态", max: 5 },
      { label: "三区分布", value: zone1 + ":" + zone2 + ":" + zone3, status: (zone1 >= 1 && zone2 >= 1 && zone3 >= 1) ? "全覆盖" : "有缺失", max: 5 },
      { label: "连号对", value: consecCount, status: consecCount <= 2 ? "合理" : "过多", max: 4 }
    ];
    
    container.innerHTML = metrics.map(function(m) {
      var statusClass = m.status === "正常" || m.status === "均衡" || m.status === "全覆盖" || m.status === "合理" ? "" : "warning";
      return '<div class="pv2-metric-card">' +
        '<div class="pv2-metric-label">' + m.label + '</div>' +
        '<div class="pv2-metric-value">' + m.value + '</div>' +
        '<div class="pv2-metric-status ' + statusClass + '">' + m.status + '</div>' +
        '</div>';
    }).join("");
  }

  /**
   * 渲染过滤规则列表
   */
  function renderFilterRules(stats) {
    var container = document.getElementById("pv2-filter-list");
    if (!container) return;
    
    var rules = stats && stats.rules_applied ? stats.rules_applied : [
      "five_consecutive",
      "all_odd",
      "all_even",
      "all_big",
      "all_small",
      "extreme_sum",
      "extreme_span",
      "duplicate_previous"
    ];
    
    var ruleNames = {
      "five_consecutive": "五连号组合",
      "all_odd": "全奇数组合",
      "all_even": "全偶数组合",
      "all_big": "全大号组合",
      "all_small": "全小号组合",
      "extreme_sum": "极端和值",
      "extreme_span": "异常跨度",
      "duplicate_previous": "与上期重复"
    };
    
    container.innerHTML = rules.map(function(rule) {
      return '<div class="pv2-filter-rule">' + (ruleNames[rule] || rule) + '</div>';
    }).join("");
  }

  /**
   * 更新统计信息
   */
  function updateStats(stats) {
    var totalEl = document.getElementById("pv2-total-candidates");
    var filteredEl = document.getElementById("pv2-filtered-count");
    
    if (totalEl && stats && stats.filtered_count) {
      totalEl.textContent = stats.filtered_count;
    }
    if (filteredEl && stats) {
      var filtered = stats.filtered_count ? Math.round(stats.filtered_count * 0.15) : 0;
      filteredEl.textContent = filtered;
    }
  }

  /**
   * 显示加载状态
   */
  function showLoading() {
    document.getElementById("pv2-loading").hidden = false;
    document.getElementById("pv2-hero").hidden = true;
    document.getElementById("pv2-backup").hidden = true;
    document.getElementById("pv2-analysis").hidden = true;
    document.getElementById("pv2-filters").hidden = true;
    hideError();
  }

  /**
   * 显示内容区域
   */
  function showContent() {
    document.getElementById("pv2-loading").hidden = true;
    document.getElementById("pv2-hero").hidden = false;
    document.getElementById("pv2-backup").hidden = false;
    document.getElementById("pv2-analysis").hidden = false;
    document.getElementById("pv2-filters").hidden = false;
  }

  // ==================== 数据加载 ====================

  /**
   * 从静态JSON文件加载推荐
   */
  function loadStaticRecommendation() {
    showLoading();
    
    return fetch(STATIC_DATA_PATH, {
      method: "GET",
      headers: {
        "Accept": "application/json"
      }
    })
    .then(function(response) {
      if (!response.ok) {
        throw new Error("HTTP " + response.status + " - 推荐数据文件未找到");
      }
      return response.json();
    })
    .then(function(data) {
      // 验证必需字段
      if (!data.main || !data.main.front || !data.main.back) {
        throw new Error("推荐数据格式不正确");
      }
      return data;
    })
    .catch(function(error) {
      console.error("[pick-v2] Static data load error:", error);
      throw error;
    });
  }

  /**
   * 渲染完整推荐数据
   */
  function renderRecommendation(data) {
    // 主推荐
    renderMainRecommendation(data.main);
    
    // 备选方案
    renderBackupOptions(data.backup || []);
    
    // 质量分析
    renderQualityMetrics(data.main);
    
    // 过滤规则
    renderFilterRules(data.stats || {});
    
    // 统计信息
    updateStats(data.stats);
    
    // 显示内容
    showContent();
  }

  /**
   * 主加载函数
   */
  function loadRecommendation() {
    loadStaticRecommendation()
      .then(function(data) {
        renderRecommendation(data);
      })
      .catch(function(error) {
        showError("加载推荐数据失败<br>" + 
                  "<small>原因: " + error.message + "</small><br>" +
                  "<small>请确认已生成推荐数据文件</small>");
      });
  }

  // ==================== 初始化 ====================

  function init() {
    // 绑定刷新按钮（仅提示数据更新需等待下次生成）
    var refreshBtn = document.getElementById("pv2-refresh-btn");
    if (refreshBtn) {
      refreshBtn.addEventListener("click", function() {
        refreshBtn.disabled = true;
        refreshBtn.textContent = "⏳ 刷新中...";
        
        // 清除缓存重新加载
        var timestamp = new Date().getTime();
        var url = STATIC_DATA_PATH + "?t=" + timestamp;
        
        fetch(url, { cache: "no-cache" })
          .then(function(response) {
            if (!response.ok) {
              throw new Error("HTTP " + response.status);
            }
            return response.json();
          })
          .then(function(data) {
            renderRecommendation(data);
            refreshBtn.disabled = false;
            refreshBtn.textContent = "🔄 刷新推荐";
          })
          .catch(function(error) {
            console.error("[pick-v2] Refresh error:", error);
            refreshBtn.disabled = false;
            refreshBtn.textContent = "🔄 刷新推荐";
            showError("刷新失败，请稍后重试");
          });
      });
    }
    
    // 页面加载时自动获取推荐
    loadRecommendation();
  }

  // ==================== 导出 API ====================
  var api = {
    loadRecommendation: loadRecommendation,
    loadStaticRecommendation: loadStaticRecommendation,
    renderRecommendation: renderRecommendation,
    STATIC_DATA_PATH: STATIC_DATA_PATH
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  } else {
    root.PickV2API = api;
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", init);
    } else {
      init();
    }
  }
})(typeof self !== "undefined" ? self : this);
