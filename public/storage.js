/* =========================================================
   localStorage 用户体验层 · 存储模块（storage）
   - 阶段 17（V4 用户体系 · 轻量本地版）：收藏/历史/偏好/方案
   - 单 key `dlt_storage_v1` 存储全部数据（原子读写、迁移简单）
   - version 机制 + migrate 迁移表驱动
   - try/catch 异常保护（localStorage 禁用时内存降级，不崩溃）
   - 纯前端本地存储，零后端、零个人信息上传、游客可用
   - IIFE + root.StorageAPI（与 PickAPI/ScoreAPI 同模式），node 可测
   ========================================================= */
(function (root) {
  "use strict";

  var STORAGE_KEY = "dlt_storage_v1";   // 单 key 存储（含版本号，便于迁移）
  var STORAGE_VERSION = 1;              // 当前数据结构版本
  var HISTORY_LIMIT = 100;              // 历史记录上限（超出丢弃最旧）
  var DEFAULT_PREFS = {                 // 偏好默认值
    defaultPeriod: 100,
    defaultModel: "standard",
    theme: "light",
    saveHistory: true
  };

  /* ===== 存储后端：浏览器 localStorage，node/禁用时内存降级 ===== */
  var _mem = {};  // node 测试 / localStorage 不可用时的内存存储
  function _getBackend() {
    if (typeof localStorage !== "undefined") {
      try { localStorage.setItem(STORAGE_KEY + "_probe", "1"); localStorage.removeItem(STORAGE_KEY + "_probe"); return localStorage; }
      catch (e) { /* 隐私模式/禁用 → 内存降级 */ }
    }
    return _mem;
  }

  /* ===== 默认空结构 ===== */
  function emptyData() {
    return {
      version: STORAGE_VERSION,
      favorites: [],
      history: [],
      preferences: {},
      plans: []
    };
  }

  /* ===== 迁移表（版本 → 升级函数；当前 v1 无历史版本，占位供未来扩展）===== */
  var MIGRATIONS = {
    // 示例（未来 v1→v2）：1: function (d) { ...; return d; }
  };

  /* 迁移：将任意版本/损坏数据规整为当前版本结构（不抛异常） */
  function migrate(raw) {
    var data = raw;
    if (!data || typeof data !== "object") return emptyData();
    // 逐级升级（fromVersion → STORAGE_VERSION）
    var from = typeof data.version === "number" ? data.version : 0;
    for (var v = from; v < STORAGE_VERSION; v++) {
      if (MIGRATIONS[v]) data = MIGRATIONS[v](data) || data;
    }
    // 补全缺失字段（保证结构完整）
    var base = emptyData();
    data.version = STORAGE_VERSION;
    data.favorites = Array.isArray(data.favorites) ? data.favorites : base.favorites;
    data.history = Array.isArray(data.history) ? data.history : base.history;
    data.plans = Array.isArray(data.plans) ? data.plans : base.plans;
    data.preferences = data.preferences && typeof data.preferences === "object" ? data.preferences : base.preferences;
    return data;
  }

  /* ===== 内部读写（带 try/catch 异常保护）===== */
  function load() {
    var raw = null;
    try {
      raw = _getBackend().getItem(STORAGE_KEY);
    } catch (e) { raw = null; }
    if (!raw) return emptyData();
    var data = null;
    try {
      data = JSON.parse(raw);
    } catch (e) {
      // JSON 损坏 → 安全返回空结构（不覆盖原数据）
      return emptyData();
    }
    var migrated = migrate(data);
    // 迁移/结构修正后立即回写（保证持久层同步最新版本）
    if (raw !== JSON.stringify(migrated)) {
      save(migrated);
    }
    return migrated;
  }

  function save(data) {
    try {
      _getBackend().setItem(STORAGE_KEY, JSON.stringify(data));
    } catch (e) {
      /* 存储失败静默降级（内存中仍可用）*/
    }
  }

  /* ===== 工具 ===== */
  function genId(prefix) {
    return (prefix || "t") + "_" + Date.now() + "_" + Math.floor(Math.random() * 1e6);
  }
  function normArr(arr) {
    return (Array.isArray(arr) ? arr : []).slice().sort(function (a, b) { return a - b; });
  }
  function sameCombo(a, b) {
    if (!Array.isArray(a) || !Array.isArray(b) || a.length !== b.length) return false;
    var x = normArr(a), y = normArr(b);
    for (var i = 0; i < x.length; i++) { if (x[i] !== y[i]) return false; }
    return true;
  }

  /* ===== 收藏 favorites ===== */
  function getFavorites() { return load().favorites; }
  function isFavorite(front, back) {
    return load().favorites.some(function (f) {
      return sameCombo(f.front, front) && sameCombo(f.back, back || []);
    });
  }
  function addFavorite(item) {
    var d = load();
    if (!item || !Array.isArray(item.front)) return null;
    if (isFavorite(item.front, item.back || [])) return null; // 去重
    var fav = {
      id: genId("f"),
      name: item.name || "",
      front: normArr(item.front),
      back: normArr(item.back || []),
      source: item.source || "manual",
      created_at: new Date().toISOString(),
      note: item.note || ""
    };
    d.favorites.push(fav);
    save(d);
    return fav;
  }
  function removeFavorite(id) {
    var d = load();
    d.favorites = d.favorites.filter(function (f) { return f.id !== id; });
    save(d);
    return true;
  }

  /* ===== 历史 history ===== */
  function getHistory() { return load().history; }
  function addHistory(record) {
    var d = load();
    if (!record || !Array.isArray(record.front)) return null;
    var rec = {
      id: genId("h"),
      type: record.type || "record",
      front: normArr(record.front),
      back: normArr(record.back || []),
      result: record.result || "",
      created_at: new Date().toISOString()
    };
    d.history.unshift(rec);                       // 最新在前
    if (d.history.length > HISTORY_LIMIT) d.history = d.history.slice(0, HISTORY_LIMIT);
    save(d);
    return rec;
  }
  function clearHistory() {
    var d = load();
    d.history = [];
    save(d);
    return true;
  }

  /* ===== 偏好 preferences ===== */
  function getPreferences() {
    var prefs = load().preferences;
    var out = {};
    for (var k in DEFAULT_PREFS) { out[k] = prefs[k] !== undefined ? prefs[k] : DEFAULT_PREFS[k]; }
    return out;
  }
  function getPreference(key, def) {
    var prefs = load().preferences;
    return prefs[key] !== undefined ? prefs[key] : (def !== undefined ? def : DEFAULT_PREFS[key]);
  }
  function setPreference(key, value) {
    var d = load();
    d.preferences[key] = value;
    save(d);
    return value;
  }

  /* ===== 方案 plans ===== */
  function getPlans() { return load().plans; }
  function savePlan(plan) {
    var d = load();
    if (!plan || !Array.isArray(plan.front)) return null;
    if (plan.id) {
      // 更新已有方案
      var found = null;
      d.plans = d.plans.map(function (p) {
        if (p.id === plan.id) { found = p; return { id: p.id, name: plan.name !== undefined ? plan.name : p.name, front: normArr(plan.front), back: normArr(plan.back || []), created_at: p.created_at, updated_at: new Date().toISOString(), note: plan.note !== undefined ? plan.note : p.note }; }
        return p;
      });
      if (!found) return null;
      save(d);
      return found;
    }
    var np = {
      id: genId("p"),
      name: plan.name || "未命名方案",
      front: normArr(plan.front),
      back: normArr(plan.back || []),
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      note: plan.note || ""
    };
    d.plans.push(np);
    save(d);
    return np;
  }
  function deletePlan(id) {
    var d = load();
    d.plans = d.plans.filter(function (p) { return p.id !== id; });
    save(d);
    return true;
  }

  /* ===== 清空（测试辅助 + 「清除我的数据」功能预留）===== */
  function _reset() {
    try {
      _getBackend().removeItem(STORAGE_KEY);
    } catch (e) { /* ignore */ }
    return emptyData();
  }

  var api = {
    version: STORAGE_VERSION,
    key: STORAGE_KEY,
    // 收藏
    getFavorites: getFavorites,
    addFavorite: addFavorite,
    removeFavorite: removeFavorite,
    isFavorite: isFavorite,
    // 历史
    getHistory: getHistory,
    addHistory: addHistory,
    clearHistory: clearHistory,
    // 偏好
    getPreferences: getPreferences,
    getPreference: getPreference,
    setPreference: setPreference,
    // 方案
    getPlans: getPlans,
    savePlan: savePlan,
    deletePlan: deletePlan,
    // 工具（测试辅助）
    _reset: _reset
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;             // Node 测试用
  } else {
    root.StorageAPI = api;
  }
})(typeof self !== "undefined" ? self : this);
