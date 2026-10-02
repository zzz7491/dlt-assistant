# P4-4 RECOVERY READINESS CONTRACT

P4-4 is **operational observability / recovery readiness**, NOT predictive
improvement. It may only touch: logging, structured diagnostics, health checks,
readiness checks, audit trail, failure classification, recovery tooling, backup
validation, restore verification, runbooks, alert surfaces, deployment
diagnostics, scheduler/publisher observability, safe operational tooling, tests,
documentation. It must NOT change recommendation semantics, strategy selection,
scoring, weights, analysis window, RNG contract, or regenerate historical
publications.

## Frozen invariants

- **R1** A published snapshot is never rewritten by recovery.
- **R2** A corrupt published store fails closed (P4-3 F1).
- **R3** Restore must come from a validated backup / Git-tracked source, never
  from recomputation of a historical publication.
- **R4** Same-issue retry is idempotent.
- **R5** A conflict is NOT resolved by "regenerating".
- **R6** History lag must not auto-skip to a different issue.
- **R7** Cloudflare account mismatch fails closed (Account Guard).
- **R8** Recovery tooling defaults to dry-run.
- **R9** Any destructive restore requires explicit human authorization.
- **R10** After any restore, immutable hashes must be re-verified.
- **R11** Recovery never runs predictive optimization.
- **R12** Deployment failure ≠ publication failure; the two states are distinct.

## P4-4 tooling (added)

- `scripts/check_production_readiness.py` — read-only operational checker.
  Emits a structured `PASS/FAIL` + `failure_class`. Writes
  `reports/last-run-status.json` (machine-readable). NEVER runs
  scheduler/publisher; NEVER writes D1; NEVER leaks tokens/secrets.
- `scripts/recovery_check.py` — dry-run-first recovery verifier.
  Default: inspect / validate / compare hashes / list snapshots / check
  backups. An actual restore requires `--restore <backup> --authorize <reason>`
  AND a validated hash manifest AND explicit human authorization; it never
  recomputes history.
- `scripts/backup_published_store.py` — minimal, append-only backup of the
  authoritative published store with a SHA-256 hash manifest + timestamp.
  Immutable; no auto-deletion (retention is manual / out of scope).

## What these tools must not do

- not change recommendation numbers or publication logic;
- not write to production D1;
- not delete backups automatically;
- not print OAuth/API tokens, secret values, or credentials;
- not auto-restore (dry-run default).
