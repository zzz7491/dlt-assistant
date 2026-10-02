# P4-5 DAILY PIPELINE BASELINE

Read-only audit of the actual scheduled pipeline at commit `f90f118`. All facts
are taken from `.github/workflows/dlt-analysis.yml` and the code it invokes —
not from assumptions.

## Triggers (`on:`)
| trigger | cron (UTC) | meaning |
|---|---|---|
| schedule #1 | `0 2 * * *` | daily 10:00 CST |
| schedule #2 | `45 13 * * 1,3,6` | post-draw (Mon/Wed/Sat 21:45 CST) |
| schedule #3 | `0 4 * * 0` | Sunday 12:00 CST (weekly heavy experiment) |
| workflow_dispatch | — | manual; input `experiment_mode` ∈ {none, daily, weekly} |

`permissions: contents: write` (bot can commit/push).

## Jobs

### Job `analyze` (daily + post-draw + manual non-weekly)
- runs-on ubuntu-latest · `timeout-minutes: 15`
- `concurrency.group: experiment-ci`, `cancel-in-progress: false` (serialize with weekly; queue, don't cancel)
- steps (in order):
  1. checkout `fetch-depth: 0` (full history for rebase-then-push)
  2. setup Python 3.13
  3. `pip install -r requirements.txt`
  4. `python -m src.scheduler --once`  ← **no `||` isolation**; step failure stops the job
  5. D1 history sync `scripts/update_dlt_d1.py` + `wrangler d1 execute` (`set +e`, `exit 0` on fail → non-blocking)
  6. D1 analysis write `scripts/analysis_run.py` + `wrangler d1 execute` (`set +e`, non-blocking)
  7. static sync `cp data/dlt_history.json public/data/`
  8. D1 recommendation lock `scripts/write_recommendations_d1.py` (`INSERT OR IGNORE`) + `wrangler d1 execute` (non-blocking)
  9. D1 → static export `scripts/export_recommendations_json.py` (non-blocking)
  10. **`python -m src.publisher --safe`** ← writes the authoritative published store; `|| echo` + `--safe` → never blocks
  11. experiment layer daily + data-quality + monitor + display (all `|| echo`, isolated, non-blocking)
  12. experiment pre/post production-file hash guard (blocks commit if frozen files changed)
  13. `cp reports/*.md public/reports/`
  14. **git commit/push**: `git add data reports public`; if dirty → `git pull --rebase origin $REF || true` → `git commit` → `git push` (no force)
  15. Cloudflare Account Guard (skip if no `CLOUDFLARE_API_TOKEN`; else `check_cloudflare_account.py`, fail-closed)
  16. **`wrangler pages deploy public`** (skip if no token)

### Job `weekly-experiment` (Sunday schedule / manual weekly only)
- runs-on ubuntu-latest · `timeout-minutes: 90` · same `concurrency.group: experiment-ci`
- `if: schedule=='0 4 * * 0' OR dispatch(experiment_mode=weekly)`
- steps: checkout → Python 3.13 → deps → `python -m src.scheduler --once` → experiment daily/quality/monitor/display (isolated) → pre/post hash guard → `git add data reports public` + commit/push → Account Guard → `wrangler pages deploy`
- **Does NOT call `src.publisher`** → does NOT write the authoritative published store.

## Where each surface lives
- **history ingestion**: scraper inside `src.scheduler --once` (updates `data/dlt_history.json`); D1 `update_dlt_d1.py`.
- **scheduler**: `src/scheduler.py::main` → `run_once`; top-level exception → `SystemExit(1)` (blocks the CI step).
- **publisher**: `src/publisher.py::main --safe` → `publish()`; upsert authoritative store (P4-3 F1 corrupt fail-closed + F2 atomic write); `--safe` → `exit 0` on any exception.
- **D1**: `wrangler d1 execute dlt-draws` (writes); `scripts/write_recommendations_d1.py` (INSERT OR IGNORE + UNIQUE).
- **deployment**: `wrangler pages deploy public`, guarded by `check_cloudflare_account.py`.
- **backup / readiness / recovery**: P4-4 `scripts/{backup_published_store,check_production_readiness,recovery_check}.py`.

## Failure behavior (as-implemented)
- scheduler step failure → job stops (publisher not reached). ✅ D5 already holds via step ordering.
- publisher `--safe` → always `exit 0`; conflict/corrupt → fail-closed (no display write). ✅ D6 holds.
- D1 writes → `set +e` + `exit 0` → non-blocking by design (double-write tolerance); a D1 failure is NOT surfaced as a structured state. ⚠️ D8 gap.
- git `pull --rebase || true` then `push` → no force; but rebase is not overlap-audited (blind). ⚠️ D14 gap.
- No backup exists before the publisher write. ⚠️ D1/D2 gap (P4-5 P9).
- No structured per-run status artifact. ⚠️ D12/P17 gap.
