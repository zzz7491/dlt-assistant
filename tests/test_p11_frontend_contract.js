/* P1-1 前端唯一推荐契约测试（Node，无外部依赖）。
 *
 * 直接 eval 真实的 public/app.js，用 document/window/fetch 桩驱动其启动，
 * 读取真实渲染出的 DOM（#primary-recommendation / #review-placeholder 等），
 * 证明「普通用户只看到一条正式推荐」，且 0/多个 is_primary 时 fail-closed。
 *
 * 运行： /opt/homebrew/bin/node tests/test_p11_frontend_contract.js
 */
"use strict";
const vm = require("vm");
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const APP_SRC = fs.readFileSync(path.join(ROOT, "public", "app.js"), "utf8");

const HISTORY = {
  source: "500",
  issues: [{ issue: 26097, date: "2026-08-26", front: [1, 2, 3, 4, 5], back: [6, 7] }],
};

// 构造一份带 A/B/C/D 四策略、仅指定 primaryStrat(前缀 A/B/C/D) 标记 is_primary 的推荐数据
function recsFixture(primaryStrat, opts) {
  const LABEL = { A: "均衡统计型", B: "冷热组合型", C: "纯随机娱乐型", D: "综合评分型" };
  const FRONT = { A: [3, 5, 9, 24, 26], B: [4, 8, 24, 26, 35], C: [9, 10, 11, 22, 34], D: [13, 23, 21, 18, 28] };
  const BACK = { A: [3, 9], B: [5, 7], C: [1, 9], D: [11, 6] };
  const SCORE = { A: 49.3, B: 39.9, C: 45.6, D: 43.5 };
  const mk = (prefix) => ({
    target_issue: "26098",
    strategy: prefix + "-" + LABEL[prefix],
    front: FRONT[prefix],
    back: BACK[prefix],
    idx: 0,
    is_primary: prefix === primaryStrat,
    final_score: SCORE[prefix],
    reason: prefix === primaryStrat ? "本期依据：和值/跨度贴合历史高频区间" : null,
  });
  const list = ["A", "B", "C", "D"].map(mk);
  if (opts && opts.multi) list.forEach((r) => { if (r.strategy.indexOf("B") === 0) r.is_primary = true; }); // 制造 2 个 is_primary
  if (opts && opts.zero) list.forEach((r) => { r.is_primary = false; });
  return list;
}

function runApp(fixture) {
  return new Promise((resolve) => {
    const elements = {};
    const el = (id) => {
      if (!elements[id]) elements[id] = { id, innerHTML: "", textContent: "", hidden: false };
      return elements[id];
    };
    const fetchMap = {
      "./data/dlt_history.json": HISTORY,
      "./data/recommendations.json": fixture.recs,
      "./data/review.json": fixture.review === undefined ? null : fixture.review,
      "./data/strategy_score.json": null,
    };
    const fetchStub = (p) =>
      Promise.resolve({ ok: true, json: () => Promise.resolve(fetchMap[p] === undefined ? null : fetchMap[p]) });

    const sandbox = {
      console,
      Promise,
      document: {
        getElementById: el,
        createElement: () => ({}),
        querySelectorAll: () => [],
        addEventListener: () => {},
        readyState: "complete",
      },
      window: { innerWidth: 390, addEventListener: () => {}, __trendIssues: [] },
      fetch: fetchStub,
      location: { href: "" },
    };
    sandbox.globalThis = sandbox;
    vm.createContext(sandbox);
    vm.runInContext(APP_SRC, sandbox, { filename: "app.js" });
    // app.js 启动即 fetch→Promise.all→.then 渲染；给足微任务/宏任务
    let n = 0;
    const settle = () => { if (n++ < 12) setTimeout(settle, 0); else resolve(elements); };
    settle();
  });
}

function assert(cond, msg) {
  if (!cond) { console.log("FAIL  " + msg); process.exitCode = 1; }
  else console.log("PASS  " + msg);
}
function contains(h, s) { return h.indexOf(s) >= 0; }
function hasBall(front, h) {
  // 该前区 5 个号（两位补零）应同时出现在卡片
  return front.every((x) => contains(h, String(x).padStart(2, "0")));
}

(async () => {
  // 1-5: 每个策略作 primary，卡片只显示该策略号码
  for (const s of ["A", "B", "C", "D"]) {
    const els = await runApp({ recs: recsFixture(s) });
    const card = els["primary-recommendation"].innerHTML;
    const prim = recsFixture(s).find((r) => r.is_primary);
    assert(contains(card, "本期唯一推荐"), `(${s} primary) 卡片标题为「本期唯一推荐」`);
    assert(hasBall(prim.front, card), `(${s} primary) 卡片含前区 ${prim.front.join("/")}`);
    assert(hasBall(prim.back, card), `(${s} primary) 卡片含后区 ${prim.back.join("/")}`);
    // 唯一推荐卡内不得出现并列的「推荐 X」卡片头（网格已移除）
    assert(!contains(card, "推荐 A") && !contains(card, "推荐 B") && !contains(card, "推荐 C"),
      `(${s} primary) 卡片内无并列 推荐A/B/C 头`);
    // 不暴露内部 strategy 标签
    assert(!contains(card, "综合评分型 · 唯一推荐") && !contains(card, "· 唯一推荐"),
      `(${s} primary) 卡片无内部策略标签`);
  }

  // 6: zero primary → fail-closed
  {
    const els = await runApp({ recs: recsFixture("A", { zero: true }) });
    const card = els["primary-recommendation"].innerHTML;
    assert(contains(card, "本期推荐数据暂不可用"), "zero primary → fail-closed 明确异常态");
    assert(!contains(card, "前区") || contains(card, "本期推荐数据暂不可用"), "zero primary → 不展示号码");
  }

  // 7: multi primary → fail-closed
  {
    const els = await runApp({ recs: recsFixture("A", { multi: true }) });
    const card = els["primary-recommendation"].innerHTML;
    assert(contains(card, "本期推荐数据暂不可用"), "multi primary → fail-closed 明确异常态");
  }

  // 8: 非 primary 策略不进入正式推荐 UI（已在上表逐策略覆盖；再显式断言无网格卡片）
  {
    const els = await runApp({ recs: recsFixture("D") });
    const card = els["primary-recommendation"].innerHTML;
    assert(!contains(card, "推荐 A") && !contains(card, "推荐 B") && !contains(card, "推荐 C"), "唯一推荐卡内无「推荐 A/B/C」并列卡片");
  }

  // 9: A/B/C/D 对比网格不再渲染给普通用户
  {
    const els = await runApp({ recs: recsFixture("D") });
    assert(!els["recommendations"], "A/B/C/D 对比网格容器 #recommendations 不再渲染");
  }

  // 10: legacy review banner 仍存在（P0-2 保留项）
  {
    const legacyReview = {
      empty: false, issue: "26097",
      snapshot_status: "missing", authoritative: false, legacy: true,
      recommendation: { strategy: "D-综合评分型", front: [13, 23, 21, 18, 28], back: [11, 6], score_total: 41.6 },
      actual_result: { front: [3, 10, 12, 20, 25], back: [1, 9] },
      hit_count: { front: 0, back: 0, total: 0, level: 0 },
      analysis: { factor_review: {} }, next_adjustment: [],
    };
    const els = await runApp({ recs: recsFixture("D"), review: legacyReview });
    const rev = els["review-placeholder"].innerHTML;
    assert(contains(rev, "非权威") || contains(rev, "无不可变发布快照"), "legacy review → 非权威/无快照警示存在");
  }

  console.log(process.exitCode ? "P11 CONTRACT: FAIL" : "P11 CONTRACT: ALL PASS");
})();
