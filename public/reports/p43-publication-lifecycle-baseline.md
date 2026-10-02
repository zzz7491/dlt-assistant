# P4-3 PUBLICATION LIFECYCLE BASELINE

Facts recorded from read-only code / production evidence at commit `89264ef`.
No inference beyond what is directly observed.

## Git / production
- HEAD / origin/master: `89264ef97d1c1ab598ec8cc3e2fc2ab3bb05f6b0`
- P4-2 production wording deploy URL: `https://334b5106.dlt-assistant.pages.dev`
- Production domain: `https://500wan.mootlsv.com/` (custom domain, Cloudflare Pages project `dlt-assistant`)
- Cloudflare account: `8770e4917f904aed5df91c883cf058af` (lsv3255@gmail.com), enforced by `scripts/check_cloudflare_account.py`

## Issues
- **latest history issue: `26112`** (`data/dlt_history.json`, 1000 issues, max `26112`)
- **latest published issue: `26113`** (`public/data/published_recommendations.json`)
- currently published issues: `26112` (C-纯随机娱乐型, `bea8ef87...`), `26113` (C-纯随机娱乐型, `40232f05...`)
- **history lag observed**: published latest (`26113`) > history latest (`26112`).

## Publication storage
- **Local immutable snapshot**: `public/data/published_recommendations.json`
  - schema_version `1.1`, list of `items`; one immutable record per issue.
- **Display/recommendation JSON**: `public/data/recommendations.json`
  - derived from the D1-locked values (`scripts/export_recommendations_json.py` reads D1 `dlt_recommendations` via wrangler), NOT re-randomized daily.
- **D1 (Cloudflare)**: database `dlt-draws` (id `d99a8443-...`, binding `DB`, wrangler.toml)
  - table `dlt_recommendations`: `UNIQUE(target_issue, strategy, idx)` + `INSERT OR IGNORE`
    → first write locks the period's candidate numbers; later daily re-randomizations are silently ignored ("一期固定").
  - other tables: `dlt_draws`, `dlt_analysis`, `dlt_scores` (read APIs).

## Entry points
- **scheduler**: `src/scheduler.py::run_once` — scrape→analyze→recommend→save `reports/recommendations.json` (P4-1 deterministic seed when `recommend.seed is None`). Does NOT itself publish to `public/data`.
- **publisher**: `src/publisher.py::publish` / `main --safe` — reads `reports/recommendations.json` + `public/data/recommendations.json` (D1-locked), builds `review`/`strategy_score`, and upserts the immutable snapshot via `upsert_published_snapshot`. Fail-closed: writes `public/data/recommendations.json` only when exactly one primary and no conflict.
- **D1 write**: `scripts/write_recommendations_d1.py` → `INSERT OR IGNORE` (idempotent).
- **D1 export**: `scripts/export_recommendations_json.py` → `public/data/recommendations.json` from D1 `MAX(target_issue)`.
- **API (Cloudflare Pages Functions, read-only)**: `functions/api/{issues,summary,analysis,scores}.ts` query D1 `dlt-draws`/`dlt_analysis`/`dlt_scores`.

## Hash / idempotency / conflict
- **snapshot hash**: `publisher.snapshot_hash` = SHA-256 over canonical JSON of
  `issue, primary_strategy, front, back, reason, final_score, final_breakdown, model_version, explanation`
  — **excludes `published_at` and `snapshot_hash`** (idempotent replay-stable). No wall-clock/PID/machine/random hash input.
- **idempotency**: `upsert_published_snapshot` returns `created` / `unchanged` (same hash, no write) / `conflict` (different payload for same issue → original preserved, never overwritten).
- **concurrency (CI)**: `analyze` and `weekly-experiment` share `concurrency.group: experiment-ci` (serialize jobs that write the experiment SQLite + push). D1 `INSERT OR IGNORE` + UNIQUE key makes recommendation writes idempotent.
- **frontend authority**: `public/app.js` reads static `data/*.json` (publisher-written) and only surfaces the single `is_primary` record; it does NOT recompute recommendations.

## Known invariants (to verify in P4-3)
I1 idempotent retry · I2 same-issue-different-payload conflict · I3 published not overwritten ·
I4 historical unchanged by rerun · I5 no half-publish · I6 concurrent publish single authoritative ·
I7 history-lag must not overwrite published · I8 frontend authoritative · I9 deploy does not generate ·
I10 hash canonical (no wall-clock/PID/machine/hash()) · I11 deterministic retry → no 2nd authoritative · I12 conflict preserves original.
