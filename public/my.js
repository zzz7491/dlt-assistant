/* =========================================================
   我的方案（my）· 本地存储 UI 层
   - 阶段 17（V4 用户体系 · 轻量本地版）前端展示
   - 仅依赖全局 StorageAPI（storage.js），纯前端、零后端
   - 所有读写包裹 try/catch：localStorage 异常不导致页面崩溃
   - 使用 createElement + textContent，避免数据内容注入
   ========================================================= */
(function () {
  "use strict";

  function $(id) { return document.getElementById(id); }

  /* 安全读取：StorageAPI 缺失或 localStorage 异常时返回空/降级 */
  function safe(fn, fallback) {
    try {
      if (typeof StorageAPI === "undefined" || !StorageAPI) return fallback;
      return fn(StorageAPI);
    } catch (e) {
      console.warn("[my] StorageAPI 读取失败，已降级：", e);
      return fallback;
    }
  }

  /* 渲染前区/后区号码球（复用 style.css 的 .ball.front/.ball.back） */
  function makeCombo(front, back) {
    var wrap = document.createElement("div");
    wrap.className = "my-combo";
    (Array.isArray(front) ? front : []).forEach(function (n) {
      var b = document.createElement("span");
      b.className = "ball front";
      b.textContent = String(n);
      wrap.appendChild(b);
    });
    (Array.isArray(back) ? back : []).forEach(function (n) {
      var b = document.createElement("span");
      b.className = "ball back";
      b.textContent = String(n);
      wrap.appendChild(b);
    });
    return wrap;
  }

  function fmtDate(iso) {
    if (!iso) return "";
    try {
      var d = new Date(iso);
      if (isNaN(d.getTime())) return iso;
      var p = function (x) { return (x < 10 ? "0" : "") + x; };
      return d.getFullYear() + "-" + p(d.getMonth() + 1) + "-" + p(d.getDate()) +
             " " + p(d.getHours()) + ":" + p(d.getMinutes());
    } catch (e) { return iso; }
  }

  function emptyState(text) {
    var p = document.createElement("p");
    p.className = "my-empty";
    p.textContent = text;
    return p;
  }

  function makeItem(opts) {
    // opts: { name, sub, front, back, onDelete, delLabel }
    var row = document.createElement("div");
    row.className = "my-item";

    var meta = document.createElement("div");
    meta.className = "my-meta";

    var name = document.createElement("div");
    name.className = "my-name";
    name.textContent = opts.name || "未命名";
    meta.appendChild(name);

    if (opts.sub) {
      var sub = document.createElement("div");
      sub.className = "my-date";
      sub.textContent = opts.sub;
      meta.appendChild(sub);
    }

    meta.appendChild(makeCombo(opts.front, opts.back));
    row.appendChild(meta);

    if (opts.onDelete) {
      var actions = document.createElement("div");
      actions.className = "my-actions";
      var btn = document.createElement("button");
      btn.className = "my-btn btn-danger";
      btn.type = "button";
      btn.textContent = opts.delLabel || "删除";
      btn.addEventListener("click", function () {
        try { opts.onDelete(); } catch (e) { console.warn("[my] 操作失败：", e); }
        renderAll();
      });
      actions.appendChild(btn);
      row.appendChild(actions);
    }
    return row;
  }

  /* ===== 渲染：我的收藏 ===== */
  function renderFavorites() {
    var el = $("fav-list");
    if (!el) return;
    el.innerHTML = "";
    var list = safe(function (api) { return api.getFavorites() || []; }, []);
    if (!list.length) { el.appendChild(emptyState("还没有收藏的号码。可在智能选号页收藏喜欢的组合。")); return; }
    list.forEach(function (f) {
      el.appendChild(makeItem({
        name: f.name || "收藏组合",
        sub: fmtDate(f.created_at) + (f.note ? " ｜ " + f.note : ""),
        front: f.front, back: f.back,
        onDelete: function () { StorageAPI.removeFavorite(f.id); },
        delLabel: "取消收藏"
      }));
    });
  }

  /* ===== 渲染：历史记录 ===== */
  function renderHistory() {
    var el = $("history-list");
    if (!el) return;
    el.innerHTML = "";
    var list = safe(function (api) { return api.getHistory() || []; }, []);
    if (!list.length) { el.appendChild(emptyState("暂无历史记录。")); return; }
    list.forEach(function (h) {
      el.appendChild(makeItem({
        name: (h.type === "record" ? "分析记录" : (h.type || "记录")),
        sub: fmtDate(h.created_at) + (h.result ? " ｜ " + h.result : ""),
        front: h.front, back: h.back,
        onDelete: null
      }));
    });
  }

  /* ===== 渲染：我的方案 ===== */
  function renderPlans() {
    var el = $("plans-list");
    if (!el) return;
    el.innerHTML = "";
    var list = safe(function (api) { return api.getPlans() || []; }, []);
    if (!list.length) { el.appendChild(emptyState("还没有自建方案。可在智能选号页保存方案。")); return; }
    list.forEach(function (p) {
      el.appendChild(makeItem({
        name: p.name || "未命名方案",
        sub: "创建 " + fmtDate(p.created_at) + (p.updated_at && p.updated_at !== p.created_at ? " ｜ 更新 " + fmtDate(p.updated_at) : "") + (p.note ? " ｜ " + p.note : ""),
        front: p.front, back: p.back,
        onDelete: function () { StorageAPI.deletePlan(p.id); },
        delLabel: "删除方案"
      }));
    });
  }

  /* ===== 渲染：偏好设置（只读展示） ===== */
  function renderPrefs() {
    var el = $("prefs-list");
    if (!el) return;
    el.innerHTML = "";
    var prefs = safe(function (api) { return api.getPreferences() || {}; }, {});
    var keys = [
      ["defaultPeriod", "默认分析期数"],
      ["defaultModel", "默认模型"],
      ["theme", "主题"],
      ["saveHistory", "记录历史"]
    ];
    keys.forEach(function (kv) {
      var row = document.createElement("div");
      row.className = "pref-row";
      var k = document.createElement("span");
      k.className = "pk";
      k.textContent = kv[1];
      var v = document.createElement("span");
      v.className = "pv";
      var val = prefs[kv[0]];
      v.textContent = (typeof val === "boolean") ? (val ? "开" : "关") : String(val);
      row.appendChild(k); row.appendChild(v);
      el.appendChild(row);
    });
  }

  function renderAll() {
    renderFavorites();
    renderHistory();
    renderPlans();
    renderPrefs();
  }

  /* ===== Tab 切换 ===== */
  function initTabs() {
    var tabs = document.querySelectorAll(".my-tab");
    tabs.forEach(function (tab) {
      tab.addEventListener("click", function () {
        var target = tab.getAttribute("data-tab");
        tabs.forEach(function (t) { t.setAttribute("aria-selected", t === tab ? "true" : "false"); });
        document.querySelectorAll(".my-panel").forEach(function (p) { p.hidden = true; });
        var panel = $("panel-" + target);
        if (panel) panel.hidden = false;
      });
    });
  }

  /* ===== 危险操作（二次确认） ===== */
  function initDanger() {
    var clearBtn = $("btn-clear-history");
    if (clearBtn) {
      clearBtn.addEventListener("click", function () {
        if (!window.confirm("确定清空全部历史记录？此操作不可恢复。")) return;
        try { if (StorageAPI && StorageAPI.clearHistory) StorageAPI.clearHistory(); } catch (e) {}
        renderAll();
      });
    }
    var resetBtn = $("btn-reset");
    if (resetBtn) {
      resetBtn.addEventListener("click", function () {
        if (!window.confirm("将清除本机全部收藏、历史、方案与偏好设置，且无法恢复。确定继续？")) return;
        try { if (StorageAPI && StorageAPI._reset) StorageAPI._reset(); } catch (e) {}
        renderAll();
      });
    }
  }

  function init() {
    try {
      if (typeof StorageAPI === "undefined" || !StorageAPI) {
        var main = $("content");
        if (main) {
          var warn = document.createElement("p");
          warn.className = "my-empty";
          warn.textContent = "本地存储模块未加载，无法显示我的方案。";
          main.insertBefore(warn, main.firstChild);
        }
        return;
      }
      initTabs();
      initDanger();
      renderAll();
    } catch (e) {
      console.warn("[my] 初始化失败：", e);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
