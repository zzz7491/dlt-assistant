# P4-4 OPERATIONAL BASELINE

## Runtime pipeline (GitHub Actions)

### Scheduled entry points
- `analyze` job: daily + post-draw crons + Sunday weekly-experiment
  - `python -m src.scheduler --once` (line 63) → scrape→analyze→recommend→save `reports/recommendations.json`
  - D1 sync: `scripts/update_dlt_d1.py` + `scripts/analysis_run.py` (lines 77, 108)
  - D1 recommendation lock: `scripts/write_recommendations_d1.py` (line 151)
  - D1 → static export: `scripts/export_recommendations_json.py` (line 181)
  - Publisher: `python -m src.publisher --safe` (line 194, fail-safe exit 0)
  - Experiment: `src/experiment_scheduler --daily`, `--weekly` (lines 211, 338)
- **Deploy**: `wrangler pages deploy public` (lines 278, 389) → Cloudflare Pages

### Manual entry points
- `python -m src.publisher --safe` (CI only; local equivalent is `--safe` flag)
- `python -m src.scheduler --once` (CI only; no local manual cron)

### Write entry points
- `src/publisher.py::upsert_published_snapshot` → `public/data/published_recommendations.json`
- `src/publisher.py::publish` → `public/data/{recommendations,review,strategy_score}.json`
- `scripts/write_recommendations_d1.py` → D1 `dlt_recommendations` (INSERT OR IGNORE)
- `scripts/update_dlt_d1.py` → D1 `dlt-draws`
- `src/scheduler.py` → `reports/recommendations.json` (via `recommendations.save`)

### Read entry points
- Frontend: `public/app.js` reads `public/data/*.json` (static)
- Cloudflare Functions: `functions/api/{issues,summary,analysis,scores}.ts` read D1

### Logging
- `print()` to stdout; `src/publisher` uses `--safe` top-level exception → exit 0 (CI)
- No structured logging / JSON status artifacts

### Failure exit behavior
- `publisher --safe`: `sys.exit(0)` on any exception (CI non-blocking)
- `scheduler`: no explicit `sys.exit`; unhandled exception kills the CI step
- D1 scripts: individual `set +e` in workflow; failure logs but does not block

### Backup locations
- `.agnes/work/gate3-bak-audit/dlt-assistant.bak` (manual audit backup)
- No automated backup of `published_recommendations.json`

### Cloudflare
- Pages project: `dlt-assistant`, custom domain `500wan.mootlsv.com`
- D1: `dlt-draws` (database_id `d99a8443-...`)
- Account Guard: `scripts/check_cloudflare_account.py` (run before deploy)
- No `account_id` in `wrangler.toml` (relies on OAuth / CLOUDFLARE_API_TOKEN)
