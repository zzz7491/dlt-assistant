/* P1-3B L2 连接轨迹视图契约测试（Node，无外部依赖，无 npm）。
 * 运行： /opt/homebrew/bin/node tests/test_p13b_trajectory_contract.js
 *
 * 覆盖 20 项：
 *  1 default L2 view = compact matrix
 *  2 trajectory switch works（HTML 含 view switch + 轨迹容器，默认 matrix）
 *  3 trajectory requires focus（无 focus → 空态提示）
 *  4 front focus trajectory correct
 *  5 back focus trajectory correct
 *  6 hit count matches fixture（hit marker 数 = 窗口内命中数）
 *  7 gap sequence matches computeFocusStats
 *  8 current omission matches computeFocusStats
 *  9 tap point opens existing detail sheet（事件委托 → #trend-detail-sheet）
 * 10 multi-focus 2 works
 * 11 multi-focus 3 works
 * 12 fourth focus rejected（≤3 + 提示）
 * 13 lanes are independent
 * 14 no cross-number connecting path
 * 15 no prediction-language banned terms
 * 16 trajectory causes no fetch
 * 17 P1-3A compact matrix still works
 * 18 L3 full matrix still collapsed
 * 19 front/back tab still works
 * 20 recommendation pipeline untouched
 */
"use strict";
const vm = require("vm");
const fs = require("fs");
const path = require("path");
const ROOT = path.resolve(__dirname, "..");
const api = require(path.join(ROOT, "public", "trend-v2.js"));
const TREND_HTML = fs.readFileSync(path.join(ROOT, "public", "trend-v2.html"), "utf8");
const TREND_JS = fs.readFileSync(path.join(ROOT, "public", "trend-v2.js"), "utf8");
const TREND_CSS = fs.readFileSync(path.join(ROOT, "public", "trend-v2.css"), "utf8");

const BANNED = ["上升趋势", "下降趋势", "即将出现", "即将回补", "强势", "弱势", "看涨", "看跌", "推荐关注", "值得关注", "预计出现", "概率增加"];
const CHART_LIBS = ["d3", "chart.js", "echarts", "chartjs", "plotly"];

function issuesSyn(frontHits, backHits, win) {
  win = win || 30;
  const out = [];
  for (let i = 1; i <= win; i++) {
    out.push({ issue: "26" + String(i).padStart(3, "0"), date: "2026-01-01",
      front: (frontHits[i] || []).slice(), back: (backHits[i] || []).slice() });
  }
  return out;
}

/* ---- 通用 DOM stub：id/attr 查找 + 事件委托（供 P1-3A 回归 + P1-3B 轨迹 tap） ---- */
function makeDom(customIds) {
  const els = Object.assign({}, customIds || {});
  const get = (id) => {
    if (!els[id]) els[id] = { id, innerHTML: "", textContent: "", hidden: false, open: false,
      addEventListener: (t, h) => { (els[id].handlers = els[id].handlers || []).push({ type: t, h }); },
      querySelectorAll: () => [], querySelector: () => null,
      classList: { toggle: () => {}, add: () => {}, remove: () => {} },
      appendChild: () => {}, scrollIntoView: () => {} };
    return els[id];
  };
  const dom = {
    readyState: "complete",
    location: { href: "" },
    getElementById: (id) => get(id),
    createElement: () => ({ innerHTML: "", setAttribute: () => {}, classList: { add: () => {} }, appendChild: () => {} }),
    querySelectorAll: (sel) => {
      if (typeof sel === "string" && sel.indexOf("data-focus-panel=") >= 0) {
        const m = sel.match(/data-focus-panel="([a-z]+)"/);
        if (m) return [get("focus-panel-" + m[1])];
      }
      return [];
    },
    querySelector: (sel) => {
      if (typeof sel === "string") {
        let m = sel.match(/id="([^"]+)"/) || sel.match(/^#([^" ]+)/);
        if (!m) m = sel.match(/data-focus-panel="([a-z]+)"/);
        if (m) return get(m[1]);
        m = sel.match(/^\.focus-hint\[data-focus-kind="([a-z]+)"\]$/);
        if (m) return get("focus-hint-" + m[1]);
      }
      return null;
    },
    addEventListener: (t, h) => { (dom.handlers = dom.handlers || []).push({ type: t, h }); }
  };
  dom.__get = get;
  return dom;
}

function runVm(opts) {
  const ISS = opts.issues || issuesSyn();
  const dom = makeDom();
  dom.__get("l2-view-switch").innerHTML = '<button data-l2view="matrix" class="active">命中矩阵</button><button data-l2view="trajectory">轨迹</button>';
  const fetchCalls = [];
  const sandbox = {
    console, Promise, Math, JSON, parseInt, parseFloat, isNaN, Infinity,
    document: dom,
    window: { innerWidth: opts.mobile ? 390 : 1024, addEventListener: () => {}, __trendIssues: [] },
    fetch: (p) => { fetchCalls.push(p); return Promise.resolve({ ok: true, json: () => Promise.resolve({ issues: ISS }) }); }
  };
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(path.join(ROOT, "public", "trend-v2.js"), "utf8"), sandbox);
  return new Promise((resolve) => {
    let n = 0;
    const s = () => { if (n++ < 16) setTimeout(s, 0); else resolve({ dom, sandbox, fetchCalls, ISS }); };
    s();
  });
}

function assert(cond, msg) {
  if (!cond) { console.log("FAIL  " + msg); process.exitCode = 1; } else console.log("PASS  " + msg);
}
function has(h, s) { return String(h).indexOf(s) >= 0; }
function cnt(h, s) { return String(h).split(s).length - 1; }
function hitCount(svg) { return cnt(svg, 'class="traj-hit"'); }

(async () => {
  const SYN = issuesSyn({ 2: [5], 7: [5], 13: [5], 22: [5], 29: [7] }, { 1: [9], 12: [9], 29: [5] });

  // ============ (1) default L2 view = compact matrix ============
  assert(has(TREND_HTML, 'id="l2-view-switch"'), "(1) HTML 含 L2 视图切换 #l2-view-switch");
  const l2v = (TREND_HTML.match(/id="l2-view-switch"[\s\S]*?<\/div>/) || [""])[0];
  assert(has(l2v, 'data-l2view="matrix" class="active"'), "(1b) 默认视图按钮 = 命中矩阵(active)");
  assert(has(TREND_HTML, 'id="cb-matrix-front" data-matrix="front"></div>'), "(1c) 命中矩阵容器默认可见(无 hidden)");
  assert(has(TREND_HTML, 'id="cb-trajectory-front" data-matrix="front" hidden'), "(1d) 轨迹容器默认 hidden");

  // ============ (2) trajectory switch works ============
  const r1 = await runVm({ issues: SYN });
  const fT = r1.dom.__get("cb-trajectory-front");
  api.renderTrajectoryView(fT, SYN, "front", 30);
  const viewHtml = api.buildTrajectoryViewHTML(SYN, "front", 30);
  assert(has(viewHtml, "traj-empty") && has(viewHtml, "未关注号码"), "(2) 无 focus 时轨迹视图渲染空态(点击切换轨迹可达)");
  assert(has(TREND_HTML, 'data-l2view="trajectory"'), "(2b) 轨迹切换按钮存在");

  // ============ (3) trajectory requires focus ============
  api.focusSet("front", []);
  assert(has(api.buildTrajectoryViewHTML(SYN, "front", 30), "traj-empty"), "(3) 无 focus → 空态提示(需 focus 才绘制 lane)");
  api.focusSet("front", [5]);

  // ============ (4) front focus trajectory correct ============
  const frontView = api.buildTrajectoryViewHTML(SYN, "front", 30);
  assert(has(frontView, 'data-traj-lane="05"') && has(frontView, "<svg") && has(frontView, "traj-hit"), "(4) 前区 focus 05 渲染 SVG lane + hit marker");

  // ============ (5) back focus trajectory correct ============
  api.focusSet("back", [9]);
  const backView = api.buildTrajectoryViewHTML(SYN, "back", 30);
  assert(has(backView, 'data-traj-lane="09"') && hitCount(backView) === 2, "(5) 后区 focus 09 渲染 2 hit（i=1,12）");
  api.focusSet("front", [5]);

  // ============ (6) hit count matches fixture ============
  const st5 = api.computeFocusStats(SYN, 5, "front", 30);
  const v6 = api.buildTrajectoryViewHTML(SYN, "front", 30);
  assert(hitCount(v6) === st5.recentCount && st5.recentCount === 4, "(6) hit marker 数 = fixture 命中数 = " + st5.recentCount);

  // ============ (7) gap sequence matches computeFocusStats ============
  assert(JSON.stringify(st5.gapSequence) === JSON.stringify([5, 6, 9]), "(7) gapSequence = [5,6,9]（i:2→7→13→22）");
  assert(has(v6, "5 → 6 → 9"), "(7b) 轨迹 lane 内展示间隔序列 5 → 6 → 9");

  // ============ (8) current omission matches computeFocusStats ============
  const st9 = api.computeFocusStats(SYN, 9, "back", 30);
  const v8 = api.buildTrajectoryViewHTML(SYN, "back", 30);
  assert(st5.currentOmit === 8 && has(v6, "当前遗漏 8 期"), "(8) 前区 05 当前遗漏=8 且 lane 展示（i22→30）");
  assert(st9.currentOmit === 18, "(8b) 后区 09 当前遗漏=18（i12→30，index 11→29）");

  // ============ (9) tap point opens existing detail sheet ============
  // 轨迹 hit tap 内容 = 复用 P1-3A detail sheet 结构（buildTrajectoryDetailSheet 纯函数，
  // DOM 事件委托 bindTrajectoryTap 在真实页面绑定 click → #trend-detail-sheet）
  const sheetStub = r1.dom.__get("trend-detail-sheet");
  sheetStub.hidden = true;
  const tapC = r1.dom.__get("cb-trajectory-front");
  api.renderTrajectoryView(tapC, SYN, "front", 30);
  const handler = tapC.handlers && tapC.handlers.find((x) => x.type === "click");
  assert(!!handler, "(9) 轨迹 hit 绑定 click（事件委托，非 hover）");
  // 05 的第 2 个 hit = i13（hit ordinal 2）→ 距上一次出现 = gap[0] = 5 期
  const sheetHtml = api.buildTrajectoryDetailSheet("front", "05", "26013", 2, SYN, 30);
  assert(has(sheetHtml, "第 26013 期") && has(sheetHtml, "该期开奖"), "(9b) sheet 显示第 26013 期 + 该期开奖");
  assert(has(sheetHtml, "距上一次出现 <strong>5 期</strong>"), "(9c) sheet 显示距上一次出现 5 期（05 hit ordinal 2 的前段 gap）");
  assert(has(sheetHtml, "tts-close"), "(9d) sheet 复用 P1-3A detail sheet 结构（tts-* 类，非第二套 modal）");

  // ============ (10) multi-focus 2 works ============
  api.focusSet("front", [5, 7]);
  const v10 = api.buildTrajectoryViewHTML(SYN, "front", 30);
  assert(has(v10, 'data-traj-lane="05"') && has(v10, 'data-traj-lane="07"') && v10.match(/<svg/g).length === 2,
    "(10) 2 focus → 2 个独立 SVG lane（05/07）");

  // ============ (11) multi-focus 3 works ============
  api.focusSet("front", [5, 7, 3]);
  const v11 = api.buildTrajectoryViewHTML(SYN, "front", 30);
  assert(has(v11, 'data-traj-lane="05"') && has(v11, 'data-traj-lane="07"') && has(v11, 'data-traj-lane="03"'),
    "(11) 3 focus → 3 个 lane");
  api.focusSet("front", [5]);

  // ============ (12) fourth focus rejected ============
  api.focusSet("front", [5, 7, 3]);
  api.toggleFocus("front", 4, SYN, 30); // 第 4 个
  assert(api.getFocusNumbers("front").length === 3, "(12) 第 4 个 focus 被拒绝（仍 3 个）：" + JSON.stringify(api.getFocusNumbers("front")));
  var fpStub12 = { innerHTML: "", querySelector: () => null, querySelectorAll: () => [] };
  api.renderFocusPanel(fpStub12, SYN, "front", 30);
  assert(has(fpStub12.innerHTML, "最多同时关注 3 个") && has(fpStub12.innerHTML, 'class="focus-hint"'),
    "(12b) 超限提示「最多同时关注 3 个号码」出现在 focus 面板");

  // ============ (13) lanes are independent ============
  api.focusSet("front", [5, 7]);
  const l5 = api.buildTrajectoryLaneHTML(api.buildTrajectory(SYN, 5, "front", 30), 0, "front");
  const l7 = api.buildTrajectoryLaneHTML(api.buildTrajectory(SYN, 7, "front", 30), 1, "front");
  assert(hitCount(l5) === 4 && hitCount(l7) === 1, "(13) 各 lane 独立：05=4 hit / 07=1 hit，互不共享 hit");
  assert(has(l5, 'data-traj-lane="05"') && !has(l5, 'data-traj-lane="07"'), "(13b) lane 05 仅含 05 的 hit，无 07");
  assert(has(l7, 'data-traj-lane="07"') && !has(l7, 'data-traj-lane="05"'), "(13c) lane 07 仅含 07 的 hit，无 05");

  // ============ (14) no cross-number connecting path ============
  const v14 = api.buildTrajectoryViewHTML(SYN, "front", 30);
  const laneBlocks = v14.split('data-traj-lane="').slice(1);
  let noCross = laneBlocks.length === 2;
  laneBlocks.forEach((blk) => {
    const num = blk.slice(0, 2);
    const inBlock = blk.match(/class="traj-seg"[^>]*?data-num="(\d+)"/g) || [];
    inBlock.forEach((s) => { if (s.indexOf('data-num="' + num + '"') < 0) noCross = false; });
    // 每个 lane 内的 hit 也必须只属于本号
    const hits = blk.match(/class="traj-hit"[^>]*?data-num="(\d+)"/g) || [];
    hits.forEach((s) => { if (s.indexOf('data-num="' + num + '"') < 0) noCross = false; });
  });
  assert(noCross, "(14) 无跨号码连接路径：每 lane 的 seg/hit 仅限本号（lane 数=" + laneBlocks.length + "）");

  // ============ (15) no prediction-language banned terms ============
  const allSrc = TREND_HTML + TREND_JS + TREND_CSS;
  const found = BANNED.filter((t) => allSrc.indexOf(t) >= 0);
  assert(found.length === 0, "(15) 无预测性文案：banned terms = " + (found.length ? found.join(",") : "clean"));

  // ============ (16) trajectory causes no fetch ============
  const before = r1.fetchCalls.length;
  api.buildTrajectoryViewHTML(SYN, "front", 30);
  api.buildTrajectoryViewHTML(SYN, "back", 30);
  api.renderTrajectoryView(r1.dom.__get("cb-trajectory-back"), SYN, "back", 30);
  assert(r1.fetchCalls.length === before, "(16) 轨迹渲染/切换 0 次 fetch（复用缓存 window.__trendIssues）");
  assert(r1.fetchCalls.length === 1 && has(r1.fetchCalls[0], "dlt_history.json"), "(16b) 整页仅首次加载 1 次 JSON");

  // ============ (17) P1-3A compact matrix still works ============
  const fM = r1.dom.__get("cb-matrix-front");
  api.renderCompactMatrix(fM, api.buildCompactMatrix(SYN, 30, api.GROUP_RULES.front));
  assert(has(fM.innerHTML, "cmt-table") && has(fM.innerHTML, "cmt-hit"), "(17) P1-3A 紧凑命中矩阵仍渲染 cmt-table/cmt-hit");
  assert(has(fM.innerHTML, 'data-num="05"') && has(fM.innerHTML, "cmt-dot"), "(17b) focus 号码 05 行在矩阵中可见");

  // ============ (18) L3 full matrix still collapsed ============
  assert(has(TREND_HTML, '<details id="l3-details">'), "(18) L3 完整矩阵仍包于 <details>");
  assert(!/<details[^>]*open/.test(TREND_HTML.match(/<details id="l3-details"[\s\S]*?<\/details>/)[0]), "(18b) L3 默认无 open 属性(折叠)");
  const l3btns = (TREND_HTML.match(/id="l3-period-switch"[\s\S]*?<\/div>/) || [""])[0];
  assert([50, 100, 300, 1000].every((p) => has(l3btns, 'data-periods="' + p + '"')), "(18c) L3 周期按钮 50/100/300/1000 保留");

  // ============ (19) front/back tab still works ============
  const bM = r1.dom.__get("cb-matrix-back");
  api.renderCompactMatrix(bM, api.buildCompactMatrix(SYN, 30, api.GROUP_RULES.back));
  assert(has(bM.innerHTML, 'data-matrix="back"') && has(bM.innerHTML, "cmt-table"), "(19) 后区 Tab 矩阵渲染 data-matrix=back");
  assert(has(TREND_HTML, 'id="cb-tabs"') && has(TREND_HTML, 'data-tab="front" class="active"'), "(19b) 前/后区 Tab 结构保留(默认前区)");

  // ============ (20) recommendation pipeline untouched ============
  const recDeps = TREND_JS.match(/recommender|final_score|is_primary|publisher|snapshot|explanation|A-均衡|B-冷热|C-纯随机|D-综合/i);
  assert(!recDeps, "(20) 轨迹代码无推荐管线依赖：" + (recDeps ? recDeps[0] : "clean"));
  const chartDeps = CHART_LIBS.filter((l) => new RegExp("(\\b|\\.)" + l, "i").test(TREND_JS + TREND_HTML));
  assert(chartDeps.length === 0, "(20b) 无第三方 chart 库（原生 SVG）：" + (chartDeps.length ? chartDeps.join(",") : "clean"));
  assert(has(TREND_JS, "preserveAspectRatio") && has(TREND_JS, "viewBox"), "(20c) 原生 SVG responsive viewBox 保留");

  console.log(process.exitCode ? "P13B CONTRACT: FAIL" : "P13B CONTRACT: ALL PASS");
  process.exit(process.exitCode || 0);
})();
