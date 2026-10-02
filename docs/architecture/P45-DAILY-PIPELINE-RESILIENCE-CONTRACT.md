# P4-5 DAILY PIPELINE RESILIENCE CONTRACT

P4-5 is **scheduled-operations / daily-pipeline resilience**, NOT predictive
improvement. It may only touch: workflow resilience, scheduler/publisher
operational safety, pre-run backup, readiness gates, failure classification,
safe retry, CI concurrency, Git race protection, D1 readiness, history-lag
detection, structured run status, operational artifacts, tests, documentation.
It must NOT change recommendation semantics, strategy selection, scoring,
weights, analysis window, the deterministic RNG contract, or regenerate
historical publications.

## Frozen invariants (D1–D18)

- **D1** Before any run that may modify the authoritative published store, a
  validated backup (or equivalent protection) must exist.
- **D2** A backup failure MUST block the publication write.
- **D3** A readiness failure MUST fail closed, and MUST distinguish
  code/data failure from external-auth failure.
- **D4** History lag MUST be explicitly reported; it MUST NOT auto-skip to a
  next-unpublished issue.
- **D5** A scheduler failure MUST NOT continue to the publisher.
- **D6** Publisher conflict/corrupt MUST block downstream publication-dependent
  writes (no display divergence).
- **D7** An unchanged same-snapshot retry is a legitimate idempotent result.
- **D8** D1 failure and local publication state MUST be distinguishable
  (`LOCAL_PUBLISHED_D1_FAILED`).
- **D9** A Git push failure MUST NOT cause a different recommendation to be
  regenerated.
- **D10** A deployment failure MUST NOT trigger recommendation regeneration.
- **D11** A Cloudflare account mismatch MUST block deployment.
- **D12** A Cloudflare auth failure is a *deployment* failure, never a
  publication failure.
- **D13** A workflow retry MUST reuse the existing authoritative snapshot,
  never re-select a historical publication.
- **D14** Concurrent runs MUST be protected by concurrency/lock.
- **D15** No automatic retry MAY bypass conflict protection.
- **D16** Operational artifacts MUST NOT contain secrets.
- **D17** no-op / nothing-to-commit is a recognizable normal state, not a
  publication failure.
- **D18** Production deployment happens only when the actual deployment surface
  (or the daily site data) needs syncing; engineering phases must not deploy
  for form's sake.

## P4-5 tooling

- `scripts/ops_status.py` — structured per-run status + failure taxonomy
  (machine-readable, secret-scrubbed, atomic write). Writes the gitignored
  runtime artifact `reports/last-run-status.json`.
- `scripts/check_local_prepublish.py` — local pre-publish integrity gate
  (P10): parse, snapshot-hash, 26112/26113 immutable, required files,
  history-lag / target-already-published reporting (P11), optional backup
  manifest validation. No Cloudflare auth.
- `scripts/backup_published_store.py` (P4-4) — append-only backup + hash
  manifest; required as the pre-run backup.

## Workflow wiring (job `analyze`)
1. `ops_status init` → set scheduler/backup/prepublish/publisher/d1/git/deploy
   status → `classify` on failure.
2. scheduler step: on non-zero exit → `SCHEDULER_FAILURE` + exit 1 (publisher
   not reached).
3. backup step: `backup_published_store.py`; on failure → `BACKUP_FAILURE`,
   publisher NOT run (D2).
4. pre-publish gate: `check_local_prepublish.py --require-backup`; on failure →
   `PREPUBLISH_READINESS_FAILURE`, publisher NOT run (D6).
5. publisher: `--safe` (never blocks); conflict/corrupt → `PUBLICATION_CONFLICT`
   / `PUBLICATION_CORRUPT`, no display write.
6. D1 lock step: on failure → `LOCAL_PUBLISHED_D1_FAILED` + `D1_FAILURE`
   (visible, idempotent retry, no regeneration).
7. Git push: overlap-aware, fail-closed on overlap, **no force** (D9/D14).
8. Account Guard + deploy: `CLOUDFLARE_ACCOUNT_MISMATCH` /
   `CLOUDFLARE_AUTH_FAILURE` / `DEPLOY_FAILURE` distinguished (D11/D12).
9. Final `ops_status dump` (machine-readable run status, no secrets).

## Retry policy (P13)
Automatic retry is only for read-only / idempotent transient operations
(fetch, idempotent D1 INSERT OR IGNORE, deploy of the same committed static
bundle, safe Git fetch). Scheduler generation, publisher writes, and D1
publication writes are NOT auto-retried in a way that could create a second
authoritative snapshot (D13/D15) — P4-1 determinism + D1 lock + upsert
unchanged/conflict guarantee retries reuse the same snapshot.

## Deploy rule (P26 / D18)
P4-5 only modifies `.github/workflows/`, `scripts/`, `src/publisher.py`
(operational logging), tests, docs, reports. No `public/`, `functions/`, or
Pages-bundle change → **NO_DEPLOY_REQUIRED** for this engineering phase.
