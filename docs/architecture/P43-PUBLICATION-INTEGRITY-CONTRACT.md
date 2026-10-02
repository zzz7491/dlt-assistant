# P4-3 PUBLICATION INTEGRITY CONTRACT

P4-3 is **production integrity / publication lifecycle hardening**, NOT predictive
improvement. It may only touch: publication integrity, idempotency, conflict
protection, state-transition validation, issue-sequencing validation, fail-closed
behavior, atomicity, concurrency safety, auditability, recovery safety, deployment
integrity, tests, documentation. It must NOT change recommendation semantics,
strategy selection, scoring, weights, analysis window, RNG seed contract, or
regenerate any historical publication.

## State machine

```
UNPUBLISHED ──upsert(new)──▶ GENERATED_NOT_PUBLISHED
                              │
                    same hash upsert ─▶ UNCHANGED_RETRY (no write)
                    different hash upsert ─▶ CONFLICT (original preserved)
                              │
                              ▼
                         PUBLISHED (immutable)
```

Terminal failure states: `FAILED` (no write, recoverable by re-running; no
half-published snapshot). Corrupt store is NOT silently reset to `UNPUBLISHED`.

## Frozen invariants

- **I1** same issue + same snapshot → retry idempotent (`unchanged`, no write).
- **I2** same issue + different snapshot → `conflict`, fail closed.
- **I3** a PUBLISHED snapshot is never overwritten by later generation.
- **I4** historical publications are never altered by re-running the scheduler.
- **I5** a publish failure never leaves a "half-published" store; recovery is
  safe (atomic write + fail-closed on corrupt store).
- **I6** concurrent publish → at most one authoritative snapshot wins.
- **I7** issue sequencing: history lag must not overwrite a published issue.
- **I8** frontend/API show only the authoritative published snapshot.
- **I9** deployment never implicitly generates a recommendation.
- **I10** publication hash is a function of the canonical immutable payload only
  (no wall-clock / PID / machine / Python hash()).
- **I11** retry never produces a second different authoritative publication.
- **I12** conflict preserves the original snapshot.

## P4-3 fixes (scope-confirmed, no semantic change)

- **F1 (fixes G1)**: `upsert_published_snapshot` must FAIL CLOSED when the target
  file exists but is not a parseable published store (corrupt / missing items).
  It must NOT regenerate from scratch (which wipes history). It still creates a
  fresh store only when the path does not exist (true first publication).
  New return status `corrupt` (never written). Existing behaviors
  (created / unchanged / conflict on a *valid* store) are unchanged.
- **F2 (fixes G2)**: `_write_json` writes atomically — write to a temp file in the
  same directory, `fsync`, then `os.replace` over the target. No truncation of the
  live file. Applies to the published snapshot store and the display writes.

## Non-goals
- No schema migration. No destructive change to `dlt_recommendations`
  (`INSERT OR IGNORE` one-period lock retained). No new deployment generation.
