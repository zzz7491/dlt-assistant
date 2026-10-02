# P4-4 OBSERVABILITY + RECOVERY AUDIT

## P6 OBSERVABILITY GAPS

Can the pipeline answer these questions from logs alone?

| # | Question | Current status | Gap |
|---|----------|---------------|-----|
| 1 | Which issue is being processed? | `print(f"[scheduler] 已记录推荐 {n} 组（A/B/C/D），目标期号 {target_issue}")` | ✅ partial |
| 2 | Target issue? | `next_issue(latest)` computed in scheduler; printed | ✅ |
| 3 | History latest? | Not printed explicitly | ⚠️ |
| 4 | Published latest? | Not tracked in logs | ⚠️ |
| 5 | Publication status (created/unchanged/conflict/corrupt)? | `upsert` returns string but `publish()` only prints summary, not per-issue status | ⚠️ |
| 6 | Snapshot hash? | Not printed | ⚠️ |
| 7 | Local write happened? | `_write_json_if_changed` returns bool; not printed | ⚠️ |
| 8 | D1 write status? | `write_recommendations_d1.py` prints count | ✅ partial |
| 9 | Deployment complete? | wrangler prints URL | ✅ |
| 10 | Cloudflare account? | Guard prints it | ✅ |
| 11 | Failure class? | `--safe` prints `Exception: msg` but no class taxonomy | ⚠️ |
| 12 | Enough info to recover? | No structured status artifact | ❌ |

**Identified gaps:**
- **G-OBS-1 (MEDIUM)**: No structured status artifact (`reports/last-run-status.json` or equivalent).
- **G-OBS-2 (MEDIUM)**: `publish()` does not log per-issue upsert status or snapshot hash.
- **G-OBS-3 (LOW)**: History latest / published latest not logged.
- **G-OBS-4 (LOW)**: No failure classification taxonomy (corrupt / conflict / missing / auth / network).
- **G-OBS-5 (INFO)**: No D1 read connectivity check in deploy path.

## P7 RECOVERY READINESS AUDIT (A–N)

All scenarios use temp fixtures; no production writes.

### A. Published JSON corrupt
- **DETECTION**: `upsert_published_snapshot` returns `corrupt` (P4-3 F1); `check_cloudflare_account` + manual curl.
- **FAILURE MODE**: File truncated / malformed JSON on disk.
- **DATA AT RISK**: All historical immutable snapshots in the store.
- **AUTOMATIC RECOVERY**: P4-3 F1 prevents overwrite. If file is truly lost → no automatic restore (no backup).
- **MANUAL RECOVERY**: Restore from Git (`public/data/published_recommendations.json` is tracked).
- **SAFE TO RETRY?**: Yes (upsert is idempotent).
- **REQUIRES RESTORE?**: Yes, if file missing.
- **REQUIRES HUMAN APPROVAL?**: Yes (destructive restore).

### B. Published JSON missing
- **DETECTION**: `upsert` creates fresh store; `check_production_readiness` (P4-4) detects.
- **FAILURE MODE**: File deleted / not committed.
- **DATA AT RISK**: All historical snapshots.
- **AUTOMATIC RECOVERY**: None (no backup mechanism in production).
- **MANUAL RECOVERY**: `git show HEAD:public/data/published_recommendations.json`.
- **SAFE TO RETRY?**: Yes.
- **REQUIRES RESTORE?**: Yes.
- **REQUIRES HUMAN APPROVAL?**: Yes.

### C. D1 unavailable
- **DETECTION**: `scripts/write_recommendations_d1.py` exit ≠ 0; workflow logs `推荐 D1 写入失败`.
- **FAILURE MODE**: Cloudflare API down / token expired / network.
- **DATA AT RISK**: D1 `dlt_recommendations` not updated; local JSON unaffected.
- **AUTOMATIC RECOVERY**: Workflow uses `set +e`; failure is logged but does not block. Next run retries.
- **MANUAL RECOVERY**: Re-run `scripts/write_recommendations_d1.py` after D1 is available.
- **SAFE TO RETRY?**: Yes (INSERT OR IGNORE is idempotent).
- **REQUIRES RESTORE?**: No.
- **REQUIRES HUMAN APPROVAL?**: No.

### D. Cloudflare auth mismatch
- **DETECTION**: `scripts/check_cloudflare_account.py` FAIL-CLOSED (wrong account → exit 1).
- **FAILURE MODE**: Wrong OAuth identity / wrong CLOUDFLARE_API_TOKEN.
- **DATA AT RISK**: Deployment to wrong Cloudflare account.
- **AUTOMATIC RECOVERY**: Guard blocks deploy.
- **MANUAL RECOVERY**: `wrangler login` or set correct `CLOUDFLARE_API_TOKEN`.
- **SAFE TO RETRY?**: No, fix auth first.
- **REQUIRES RESTORE?**: No.
- **REQUIRES HUMAN APPROVAL?**: Yes (credential management).

### E. Scheduler crash before publish
- **DETECTION**: CI step exit ≠ 0 (no `--safe` on scheduler).
- **FAILURE MODE**: Exception in `analyze` / `recommend` / `save`.
- **DATA AT RISK**: `reports/recommendations.json` may be incomplete.
- **AUTOMATIC RECOVERY**: None (scheduler has no `--safe` flag).
- **MANUAL RECOVERY**: Fix the crash, re-run scheduler.
- **SAFE TO RETRY?**: Yes (scheduler is re-runnable; recommendations.save merges by key).
- **REQUIRES RESTORE?**: No.
- **REQUIRES HUMAN APPROVAL?**: No.

### F. Crash during local write
- **DETECTION**: P4-3 F2 atomic write prevents partial files.
- **FAILURE MODE**: OOM / disk full / process kill during `json.dump`.
- **DATA AT RISK**: Target JSON file (now protected by atomic write).
- **AUTOMATIC RECOVERY**: Atomic write leaves either old file intact or new file complete.
- **MANUAL RECOVERY**: Re-run publisher.
- **SAFE TO RETRY?**: Yes.
- **REQUIRES RESTORE?**: No.
- **REQUIRES HUMAN APPROVAL?**: No.

### G. Crash after local write but before D1
- **DETECTION**: Workflow step boundary: local write step succeeds, D1 step fails.
- **FAILURE MODE**: D1 API down after local JSON is committed.
- **DATA AT RISK**: D1 out of sync with local JSON.
- **AUTOMATIC RECOVERY**: Next daily run will retry D1 write (INSERT OR IGNORE idempotent).
- **MANUAL RECOVERY**: Re-run D1 sync.
- **SAFE TO RETRY?**: Yes.
- **REQUIRES RESTORE?**: No.
- **REQUIRES HUMAN APPROVAL?**: No.

### H. Retry same issue
- **DETECTION**: `upsert` returns `unchanged`.
- **FAILURE MODE**: None (by design).
- **DATA AT RISK**: None.
- **AUTOMATIC RECOVERY**: Idempotent.
- **SAFE TO RETRY?**: Yes.
- **REQUIRES RESTORE?**: No.
- **REQUIRES HUMAN APPROVAL?**: No.

### I. Conflict same issue / different snapshot
- **DETECTION**: `upsert` returns `conflict`; `publish()` sets `fail_closed=True`.
- **FAILURE MODE**: Deterministic seed produces different numbers for same issue (should not happen post-P4-1, but possible if algorithm_version changes).
- **DATA AT RISK**: None (original preserved).
- **AUTOMATIC RECOVERY**: None needed; original is preserved.
- **MANUAL RECOVERY**: Investigate why different snapshot; do NOT overwrite.
- **SAFE TO RETRY?**: Yes (same result: conflict).
- **REQUIRES RESTORE?**: No.
- **REQUIRES HUMAN APPROVAL?**: Yes (investigate before any action).

### J. History lag
- **DETECTION**: Published latest > history latest (observable from JSON files).
- **FAILURE MODE**: Scheduler targets already-published issue → conflict.
- **DATA AT RISK**: None (conflict protection).
- **AUTOMATIC RECOVERY**: Conflict path preserves original.
- **SAFE TO RETRY?**: Yes.
- **REQUIRES RESTORE?**: No.
- **REQUIRES HUMAN APPROVAL?**: No.

### K. Workflow interrupted
- **DETECTION**: GitHub Actions step failure; `set +e` steps continue.
- **FAILURE MODE**: Network / timeout / cancel.
- **DATA AT RISK**: Partial artifacts (e.g., `reports/*.md` copied but not committed).
- **AUTOMATIC RECOVERY**: Re-run workflow.
- **MANUAL RECOVERY**: `git push` if local changes exist.
- **SAFE TO RETRY?**: Yes.
- **REQUIRES RESTORE?**: No.
- **REQUIRES HUMAN APPROVAL?**: No.

### L. Deployment failure
- **DETECTION**: wrangler exit ≠ 0; CI step fails.
- **FAILURE MODE**: Cloudflare API / network / auth.
- **DATA AT RISK**: None (local + D1 data intact; Pages just not updated).
- **AUTOMATIC RECOVERY**: Re-run deploy.
- **MANUAL RECOVERY**: `bash scripts/deploy_production.sh`.
- **SAFE TO RETRY?**: Yes.
- **REQUIRES RESTORE?**: No.
- **REQUIRES HUMAN APPROVAL?**: No.

### M. GitHub push race
- **DETECTION**: `git push` rejected (non-fast-forward).
- **FAILURE MODE**: Daily update pushed while local work in progress.
- **DATA AT RISK**: None.
- **AUTOMATIC RECOVERY**: `git pull --rebase` then push.
- **MANUAL RECOVERY**: Resolve conflicts.
- **SAFE TO RETRY?**: Yes.
- **REQUIRES RESTORE?**: No.
- **REQUIRES HUMAN APPROVAL?**: No.

### N. Malformed recommendation snapshot
- **DETECTION**: `build_snapshot` returns None (non-dict primary); `upsert` with `issue=None` creates with issue="None" (test_18).
- **FAILURE MODE**: Corrupt `reports/recommendations.json` → `pick_primary` returns None → no snapshot written.
- **DATA AT RISK**: None (fail-closed: no write).
- **AUTOMATIC RECOVERY**: Fix source data; re-run.
- **MANUAL RECOVERY**: Repair `reports/recommendations.json`.
- **SAFE TO RETRY?**: Yes.
- **REQUIRES RESTORE?**: No.
- **REQUIRES HUMAN APPROVAL?**: No.

## P7 SUMMARY

| Scenario | SAFE TO RETRY? | REQUIRES RESTORE? | REQUIRES HUMAN? |
|----------|---------------|-------------------|-----------------|
| A corrupt JSON | Yes | Yes | Yes |
| B JSON missing | Yes | Yes | Yes |
| C D1 down | Yes | No | No |
| D Auth mismatch | No | No | Yes |
| E Scheduler crash | Yes | No | No |
| F Crash during write | Yes | No | No (P4-3 F2) |
| G After local write | Yes | No | No |
| H Retry same | Yes | No | No |
| I Conflict | Yes | No | Yes |
| J History lag | Yes | No | No |
| K Workflow interrupted | Yes | No | No |
| L Deploy fail | Yes | No | No |
| M Push race | Yes | No | No |
| N Malformed snapshot | Yes | No | No |

## P4-4 GAPS TO CLOSE

| ID | Gap | Severity | Action |
|----|-----|----------|--------|
| G-OBS-1 | No structured status artifact | MEDIUM | Add `scripts/check_production_readiness.py` + `reports/last-run-status.json` template |
| G-OBS-2 | `publish()` doesn't log per-issue status + hash | MEDIUM | Enhance `publish()` print to include upsert status + snapshot hash |
| G-OBS-4 | No failure classification | LOW | Add error_class to status artifact |
| G-REC-1 | No backup mechanism for published store | MEDIUM | Add `scripts/backup_published_store.py` with hash manifest |
| G-REC-2 | No recovery verifier tool | MEDIUM | Add `scripts/recovery_check.py` (dry-run, hash compare, no auto-restore) |
| G-REC-3 | No runbook | LOW | Add `docs/runbooks/DLT-PRODUCTION-RECOVERY.md` |
