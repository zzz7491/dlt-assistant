# P4-5 DAILY PIPELINE CALLGRAPH

Nodes tagged: WRITE / READ / RETRY / LOCK / FAIL-CLOSED / EXTERNAL-DEPENDENCY.

## TRIGGER → pipeline (job `analyze`, daily + post-draw)

```
TRIGGER (cron 0 2 * * * / 45 13 Mon-Wed-Sat / dispatch)
  └─ JOB analyze   [LOCK: concurrency.group=experiment-ci, cancel-in-progress=false]
      1 checkout (fetch-depth 0)                       [EXTERNAL: GitHub]
      2 setup Python 3.13
      3 pip install -r requirements.txt                 [EXTERNAL: PyPI]
      4 python -m src.scheduler --once
            ├─ scrape → history ingestion               [WRITE data/dlt_history.json]
            ├─ analyze / recommend (A/B/C/D)            [WRITE reports/recommendations.json]
            │   [P4-1 deterministic seed when recommend.seed is None]
            ├─ validator/backtest/reflection            [FAIL-TOLERANT: each isolated, non-blocking]
            └─ main() top-level exception → SystemExit(1)   [FAIL-CLOSED: step stops the job]
      5 D1 history sync (update_dlt_d1 + wrangler d1 execute) [EXTERNAL: Cloudflare D1, set +e → non-blocking]
      6 D1 analysis write (analysis_run + wrangler d1 execute) [EXTERNAL, non-blocking]
      7 static sync: cp data/dlt_history.json public/data/    [WRITE]
      8 D1 recommendation lock (write_recommendations_d1: INSERT OR IGNORE + UNIQUE) [EXTERNAL, non-blocking]
      9 D1 → static export (export_recommendations_json) [EXTERNAL, WRITE public/data/recommendations.json]
      10 python -m src.publisher --safe                 [WRITE authoritative published store]
            ├─ upsert_published_snapshot  [FAIL-CLOSED on corrupt/conflict: P4-3 F1]
            ├─ _write_json atomic (temp+fsync+os.replace) [P4-3 F2]
            └─ --safe → top-level exception → exit 0 (non-blocking)
      11 experiment layer daily/quality/monitor/display   [FAIL-TOLERANT isolated]
      12 production-file hash guard (pre/post)            [FAIL-CLOSED: blocks commit if frozen file changed]
      13 cp reports/*.md public/reports/                  [WRITE]
      14 git commit/push                                    [EXTERNAL: GitHub, no force]
      15 Cloudflare Account Guard (check_cloudflare_account) [FAIL-CLOSED on mismatch]
      16 wrangler pages deploy public                      [EXTERNAL: Cloudflare Pages]
```

## Job `weekly-experiment` (Sunday / manual weekly)
```
TRIGGER (cron 0 4 * * 0 / dispatch weekly)
  └─ JOB weekly-experiment   [LOCK: same concurrency.group]
      checkout → Python → deps → scheduler --once → experiment layer (isolated)
      → hash guard (pre/post) → git commit/push → Account Guard → wrangler pages deploy
      (does NOT call src.publisher → does NOT write authoritative published store)
```

## WRITE / READ / RETRY / LOCK / FAIL-CLOSED / EXTERNAL summary
- WRITE: data/dlt_history.json, reports/*, public/data/* (static + published store), git.
- READ: frontend static data/*.json, Cloudflare Functions D1 read-only.
- RETRY: none automatic for scheduler/publisher/D1 write today; GitHub Actions manual re-run only
  (idempotent due to P4-1 determinism + D1 INSERT OR IGNORE + upsert unchanged/conflict).
- LOCK: `concurrency.group: experiment-ci` serializes the two jobs; D1 UNIQUE(target_issue,strategy,idx).
- FAIL-CLOSED: scheduler top-level exit 1 · upsert corrupt/conflict · hash guard · Account Guard.
- EXTERNAL-DEPENDENCY: GitHub (checkout/commit/push) · PyPI (deps) · Cloudflare D1 · Cloudflare Pages · 500彩票网 (scrape source).

## Gaps P4-5 addresses
- no pre-run backup before the publisher write (D1/D2)
- no local pre-publish integrity gate (P10/D6)
- history-lag not surfaced as explicit state (P11/D4)
- git push uses blind `pull --rebase || true` (P14/D9/D14)
- D1 failure swallowed without structured state (P15/D8)
- no machine-readable per-run status + failure taxonomy (P12/P17)
