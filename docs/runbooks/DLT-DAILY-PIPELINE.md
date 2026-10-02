# DLT DAILY PIPELINE RUNBOOK

P4-5 operational runbook for the scheduled daily / post-draw / weekly pipeline.
All commands are read-only or safe-rerun. Nothing here rewrites historical
publications or forces a push.

## 0. Tools
| Tool | Use |
|------|-----|
| `scripts/ops_status.py` | structured run status (`init`/`set`/`classify`/`dump`), secret-scrubbed |
| `scripts/check_local_prepublish.py` | local pre-publish integrity gate (`--require-backup`) |
| `scripts/backup_published_store.py` | append-only backup + hash manifest |
| `scripts/recovery_check.py` | dry-run recovery verifier (P4-4) |
| `scripts/check_cloudflare_account.py` | Cloudflare account guard (fail-closed) |

Runtime status: `reports/last-run-status.json` (gitignored; ephemeral on the CI
runner — use an Actions artifact for persistent audit).

## 1. Normal daily run
```
cron 0 2 * * *  →  analyze job
  scheduler --once (history ingest + A/B/C/D recommend + backtest/reflection)
  D1 history + analysis (non-blocking, idempotent)
  D1 recommendation lock (INSERT OR IGNORE, one-period)
  backup → pre-publish gate → publisher --safe
  git commit/push (overlap-aware, no force)
  Account Guard → wrangler pages deploy
```
Healthy: `ops_status` `failure_class = PASS` or `NOOP_NO_CHANGE`.

## 2. HISTORY_LAG (history latest < published latest, e.g. 26112 vs 26113)
**Detection**: `check_local_prepublish.py` reports `history_lag=True`,
`scheduler_target=<already-published>`.
**Do NOT**: auto-skip to the next issue or regenerate the published one (D4).
**Behavior**: the scheduler target is already published → upsert resolves to
`unchanged`/`conflict`; no historical snapshot is touched. Re-sync history when
the source data catches up.

## 3. Backup failure
**Detection**: `backup_published_store.py` exit ≠ 0.
**Behavior**: `BACKUP_FAILURE` → publisher is **blocked** (D2). No publication
write occurs. Re-run after fixing disk/permission.

## 4. Scheduler failure
**Detection**: `scheduler --once` exit ≠ 0 → `SCHEDULER_FAILURE`, job stops.
**Behavior**: publisher is NOT reached (D5). Fix the crash, re-run. Partial
`reports/*` never reaches the D1-locked static display.

## 5. Publisher conflict
**Detection**: upsert → `conflict` → `PUBLICATION_CONFLICT`.
**Do NOT**: resolve by regenerating (D5/D15). Keep the original. Investigate
why a different payload appeared for the same issue (e.g. algorithm_version
bump).

## 6. Publisher corrupt store
**Detection**: upsert → `corrupt` → `PUBLICATION_CORRUPT`.
**Behavior**: fail-closed, no write. Restore from a validated backup or Git
(P4-4 R3/R9), then re-verify hashes.

## 7. D1 failure
**Detection**: `wrangler d1 execute` exit ≠ 0 → `LOCAL_PUBLISHED_D1_FAILED` +
`D1_FAILURE`.
**Behavior**: local JSON publication is intact and authoritative for the
static frontend; D1 is a mirror. Re-run the D1 step — `INSERT OR IGNORE` is
idempotent, so it reuses the same locked values (no new snapshot).

## 8. Git push failure / race
**Detection**: push rejected (non-fast-forward) or auth failure.
**Behavior**: the pipeline audits for a production-path overlap; on overlap it
fails closed; otherwise it rebases safely and pushes. **Never force push.**
On auth failure: `GIT_PUSH_FAILURE`; fix credentials and re-run.

## 9. Cloudflare account mismatch
**Detection**: `check_cloudflare_account.py` exit 1 →
`CLOUDFLARE_ACCOUNT_MISMATCH`.
**Do NOT**: deploy to the wrong account (D11). Switch the identity to
`lsv3255@gmail.com` (`8770e491...`) or set the correct `CLOUDFLARE_API_TOKEN`.

## 10. Cloudflare auth expired
**Detection**: wrangler auth error → `CLOUDFLARE_AUTH_FAILURE`.
**Behavior**: this is a **deployment** failure, NOT a publication failure (D12).
The local JSON + D1 data are intact. Refresh the token in an *interactive*
terminal (CI must use a valid secret — it never runs interactive login).

## 11. Pages deploy failure
**Detection**: `wrangler pages deploy` exit ≠ 0 → `DEPLOY_FAILURE`.
**Behavior**: Pages static bundle is not updated; local/D1 data is safe
(D10/D12). Re-run the deploy (guard-protected). Re-deploying the same committed
static bundle is safe and does not regenerate recommendations.

## 12. Safe re-run procedure
1. Read `reports/last-run-status.json` (or the Actions log) for the
   `failure_class`.
2. Read-only checks: `check_local_prepublish.py`, `recovery_check.py --validate`.
3. Confirm 26112 / 26113 hashes are unchanged.
4. Re-run the specific failed step (all publication paths are idempotent /
   conflict-protected). Verify the same authoritative snapshot is reused.

## Invariants reminder (D1–D18)
Backup-before-write; backup-failure blocks publish; readiness fails closed;
history-lag explicit (no auto-skip); scheduler-failure stops publisher;
conflict/corrupt block display; unchanged retry is legitimate; D1 vs local
distinguishable; push/deploy failures never regenerate recommendations;
account mismatch blocks deploy; auth ≠ publication failure; retry reuses the
authoritative snapshot; concurrency is lock-protected; no auto-retry bypasses
conflict; no secrets in artifacts; no-op is normal; deploy only when the
deployment surface actually changed.
