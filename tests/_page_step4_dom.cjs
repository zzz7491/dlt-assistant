// 纯 Node DOM 桩，用于真实加载 public/experiment.js 并断言渲染行为。
// 不依赖 jsdom：自建最小 document/fetch，定点验证「页面能加载 / fallback / random 基准 / validity / 不稳定 / 不出现错误状态」。
// 用法：
//   node tests/_page_step4_dom.cjs                 # 所有 JSON 正常
//   FAIL_FILE=phase16_step3_validation.json node tests/_page_step4_dom.cjs   # 模拟某份 JSON 缺失

const fs = require("fs");
const path = require("path");
const { execSync } = require("child_process");

const ROOT = path.join(__dirname, "..");
const PUBLIC = path.join(ROOT, "public");
const FAIL_FILE = process.env.FAIL_FILE || "";

const failures = [];
function assert(cond, msg) {
  if (!cond) {
    failures.push(msg);
    console.error("  ✗ " + msg);
  } else {
    console.log("  ✓ " + msg);
  }
}

// ---------- 最小 DOM ----------
class El {
  constructor(tag) {
    this.tagName = tag || "div";
    this.children = [];
    this._text = "";
    this._html = "";
    this.hidden = undefined;
    this.style = {};
    this._attrs = {};
    this.classList = { add() {}, remove() {}, contains() { return false; } };
  }
  set textContent(v) { this._text = v == null ? "" : String(v); this.children = []; }
  get textContent() { return this._text; }
  set innerHTML(v) { this._html = v == null ? "" : String(v); }
  get innerHTML() { return this._html; }
  appendChild(c) { this.children.push(c); return c; }
  setAttribute(k, v) { this._attrs[k] = v; }
  getAttribute(k) { return this._attrs[k]; }
  addEventListener() {}
  get fullText() {
    return (this._text || "") + " " + (this._html || "") + " " +
      this.children.map((c) => c.fullText || "").join(" ");
  }
}

const registry = {};
let domReady = null;
const document = {
  getElementById(id) {
    if (!registry[id]) registry[id] = new El("div");
    return registry[id];
  },
  createElement(tag) { return new El(tag); },
  addEventListener(ev, fn) { if (ev === "DOMContentLoaded") domReady = fn; },
};

// ---------- fetch 桩（读本地 public/data，FAIL_FILE 模拟 404）----------
const fetch = async (url) => {
  if (FAIL_FILE && url.endsWith(FAIL_FILE)) {
    return { ok: false, status: 404, json: async () => null };
  }
  let p = String(url).replace(/^\.?\//, "");
  if (p.startsWith("data/")) p = path.join("public", p);
  if (p.startsWith("api/")) return { ok: false, status: 404, json: async () => null };
  const fp = path.join(ROOT, p);
  if (!fs.existsSync(fp)) return { ok: false, status: 404, json: async () => null };
  const txt = fs.readFileSync(fp, "utf8");
  return { ok: true, status: 200, json: async () => JSON.parse(txt) };
};

global.document = document;
global.fetch = fetch;

// ---------- 加载页面脚本 ----------
require(path.join(PUBLIC, "experiment.js"));

// ---------- 触发 DOMContentLoaded 并等待异步渲染 ----------
(async () => {
  if (!domReady) {
    console.error("未捕获到 DOMContentLoaded 处理器");
    process.exit(1);
  }
  domReady();
  // 等待所有 fetch 微任务/宏任务完成
  for (let i = 0; i < 20; i++) await new Promise((r) => setTimeout(r, 20));

  const get = (id) => registry[id] || new El("div");
  const allText = Object.values(registry).map((e) => e.fullText).join(" ");

  if (FAIL_FILE) {
    console.log(`\n[场景] 缺失 ${FAIL_FILE} 时的 fallback 验证`);
    assert(get("error").hidden === true, "缺失单份 JSON 时整页错误框不显示（error.hidden=true）");
    assert(/随机基准/.test(get("model-overview").fullText), "缺失单份 JSON 时『模型研究总览』仍正常显示 random 基准");
    assert(/adaptive 覆盖率问题/.test(get("entertainment").fullText), "缺失单份 JSON 时『娱乐价值』仍正常渲染（含 adaptive 覆盖率问题）");
    assert(/稳定性验证数据暂未生成/.test(get("stability").fullText), "缺失 step3 JSON 时『稳定性验证』显示 fallback 提示而非崩溃");
    assert(!/自动调权已启用/.test(allText), "任意场景下页面不出现『自动调权已启用』错误状态");
  } else {
    console.log("\n[场景] 所有 JSON 正常加载");
    assert(/随机基准/.test(get("model-overview").fullText), "『模型研究总览』正常显示 random 基准");
    assert(get("model-overview").fullText.includes("不可区分"), "『模型研究总览』显示命中分布与随机不可区分");
    assert(/adaptive 覆盖率问题/.test(get("entertainment").fullText), "『娱乐价值』明确展示 adaptive 覆盖率问题");
    assert(/v1 小奖频率与空军问题/.test(get("entertainment").fullText), "『娱乐价值』明确展示 v1 小奖频率与空军问题");
    assert(/coverage_boost/.test(get("stability").fullText) && /不稳定/.test(get("stability").fullText), "『稳定性验证』明确显示 coverage_boost = 不稳定");
    assert(/未启用自动调权/.test(get("why-no-autotune").fullText), "『为什么没有自动调权』明确显示未启用自动调权");
    assert(/数据有效性|注意/.test(get("stability").fullText), "『稳定性验证』显示 validity / caveat 标记");
    assert(get("error").hidden === true, "正常加载时整页错误框隐藏（error.hidden=true）");
    assert(!/自动调权已启用/.test(allText), "页面不出现『自动调权已启用』错误状态");
  }

  console.log("");
  if (failures.length) {
    console.error(`DOM 断言失败 ${failures.length} 项：`);
    failures.forEach((f) => console.error(" - " + f));
    process.exit(1);
  }
  console.log("ALL DOM ASSERTIONS PASSED");
  process.exit(0);
})();
