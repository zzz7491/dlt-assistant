const UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36";
const TIMEOUT_MS = 20000;
const SOURCES = [
  { game: "dlt", url: "https://datachart.500.com/dlt/history/newinc/history.php?start=26100&end=26130", kind: "html" },
  { game: "ssq", url: "https://datachart.500.com/ssq/history/newinc/history.php?start=26090&end=26130", kind: "html" },
  { game: "fc3d", url: "https://kaijiang.500.com/static/info/kaijiang/xml/sd/list.xml", kind: "xml" },
  { game: "pl5", url: "https://kaijiang.500.com/static/info/kaijiang/xml/plw/list.xml", kind: "xml" },
  { game: "pl3", url: "https://kaijiang.500.com/static/info/kaijiang/xml/pls/list.xml", kind: "xml" },
];
async function probeOne(src) {
  const t0 = Date.now();
  const out = { game: src.game, ok: 0, http: 0, bytes: 0, ms: 0, rows: 0, tail: "", err: "" };
  try {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
    const res = await fetch(src.url, { headers: { "User-Agent": UA }, signal: ctrl.signal });
    clearTimeout(timer);
    out.http = res.status;
    const text = await res.text();
    out.bytes = text.length;
    if (res.ok && text.length > 100) {
      out.ok = 1;
      if (src.kind === "xml") {
        out.rows = text.split("<row").length - 1;
        const idx = text.lastIndexOf("expect=");
        out.tail = idx >= 0 ? text.slice(idx, idx + 40) : text.slice(-40);
      } else {
        const m = text.match(/>\s*(2\d{4,5})\s*</g);
        out.rows = m ? m.length : 0;
        out.tail = m && m.length ? m[m.length - 1].replace(/[<>\s]/g, "") : "";
      }
    } else {
      out.err = ("http_or_short:" + text.slice(0, 80)).replace(/\s+/g, " ");
    }
  } catch (e) {
    out.err = String((e && e.message) || e).slice(0, 120);
  }
  out.ms = Date.now() - t0;
  return out;
}
async function runProbe(env) {
  await env.DB.prepare(
    "CREATE TABLE IF NOT EXISTS shadow_probe_runs (id INTEGER PRIMARY KEY AUTOINCREMENT, run_at TEXT, game TEXT, ok INTEGER, http INTEGER, bytes INTEGER, ms INTEGER, rows INTEGER, tail TEXT, err TEXT)"
  ).run();
  const runAt = new Date().toISOString();
  const results = [];
  for (const src of SOURCES) {
    const r = await probeOne(src);
    results.push(r);
    await env.DB.prepare(
      "INSERT INTO shadow_probe_runs (run_at, game, ok, http, bytes, ms, rows, tail, err) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
    ).bind(runAt, r.game, r.ok, r.http, r.bytes, r.ms, r.rows, r.tail, r.err).run();
  }
  return { run_at: runAt, results };
}
export default {
  async scheduled(event, env, ctx) {
    ctx.waitUntil(runProbe(env).then((r) => console.log(JSON.stringify(r))));
  },
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/run") {
      const r = await runProbe(env);
      return Response.json(r);
    }
    const rows = await env.DB.prepare(
      "SELECT run_at, game, ok, http, bytes, ms, rows, tail, err FROM shadow_probe_runs ORDER BY id DESC LIMIT 40"
    ).all().catch((e) => ({ results: [], error: String(e) }));
    return Response.json(rows.results || rows);
  },
};
