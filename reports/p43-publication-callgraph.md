# P4-3 PUBLICATION LIFECYCLE CALLGRAPH

Call-graph of the publication lifecycle (data flow + write/read/retry paths).
Symbols with line refs in `src/publisher.py` unless noted.

## 1. Ingestion / target-issue
- `scheduler.run_once` (src/scheduler.py:37):
  load issues → `latest_issue` → `target_issue = next_issue(latest_issue)` (src/recommendations.py:19)
  → P4-1 `publication_seed(target_issue)` when `recommend.seed is None` → `recommend(...)`.
- **history-lag note**: `target_issue` is derived from *history* latest. If published
  latest > history latest (observed: 26113 > 26112), the scheduler would re-target
  an already-published issue. Guarding that is the publisher conflict path below.

## 2. Recommendation generation
- `recommender.recommend` → A/B/C/D combos.
- `recommendations.save(log_path, all_recs)` (src/recommendations.py:40):
  merges into `reports/recommendations.json` by `_key=(target_issue,strategy,idx)`
  (keeps latest per key). Write path (reports/).

## 3. Explanation / snapshot construction
- `publisher.publish` (src/publisher.py:621):
  - `build_recommendations(current, source_recs)` (223)
  - `_apply_final_scores` (559) → sets `is_primary` (exactly one)
  - `pick_primary(recs)` (278): returns the single `is_primary` or None (fail-closed)
  - `_build_primary_explanation` (133): deterministic explanation from history
  - `build_snapshot(primary, published_at)` (97): freezes immutable record
  - `upsert_published_snapshot(snapshot_path, snap)` (160)

## 4. Snapshot hashing
- `snapshot_hash` (76): SHA-256 of canonical payload (I10: no wall-clock/PID/machine/hash()).

## 5. Local publication persistence (write path)
- `upsert_published_snapshot` (160):
  - `_load_published_store` (125) → existing item?
    - none → append + `_write_json` → **created**
    - same hash → **unchanged** (no write)
    - different hash → **conflict** (preserve original, no write)

## 6. Fail-closed display write
- `publish`: writes `public/data/recommendations.json` only if `snapshot_write_ok`
  (= exactly one primary AND not conflict). `--safe` (CI) swallows top-level errors, exit 0.

## 7. D1 publication persistence
- `scripts/write_recommendations_d1.py`: `INSERT OR IGNORE INTO dlt_recommendations`
  (UNIQUE(target_issue,strategy,idx)) → idempotent one-period lock.
- `scripts/export_recommendations_json.py`: D1 → `public/data/recommendations.json`.

## 8. Read paths (authoritative display)
- Frontend `public/app.js`: fetches static `data/*.json` (publisher-written);
  `selectPrimary` (app.js:282) surfaces exactly one `is_primary` (I8).
- API Functions (functions/api/*.ts): read-only D1 queries.

## 9. Retry / scheduled / CI paths
- GitHub Actions `dlt-analysis.yml`: daily + post-draw crons run scheduler+publisher;
  `concurrency.group: experiment-ci` serializes the two jobs.
- Publisher is a pure function of its inputs; re-running is safe because of
  upsert idempotency + conflict protection (I1/I2/I11).

## Confirmed integrity gaps (P4-3 findings)
- **G1 (CRITICAL)**: `_load_json` returns None on corrupt file → `_load_published_store`
  returns empty items → next `upsert` regenerates the store from scratch, **wiping all
  historical immutable snapshots** (violates I3/I4). No fail-closed on an existing-but
  unparseable published store.
- **G2 (HIGH)**: `_write_json` (484) is non-atomic (open "w" truncates then json.dump).
  A mid-write crash corrupts the store → triggers G1. No atomic replace / no fsync.
- Both are in P4-3 scope (publication integrity / atomicity / recovery safety) and are
  fixable WITHOUT changing recommendation semantics.
