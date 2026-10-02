# DETERMINISTIC RNG SEED CONTRACT (P4-1)

Status: FROZEN at P4-1 code gate. This contract is a **reproducibility** contract,
**not** a performance selection. It guarantees that the same publication identity
always produces the same candidate bundle; it does NOT claim any hit-rate edge.

## 1. Purpose

`src/recommender.py::recommend()` builds a single `rng = random.Random(seed)` that
drives A/B/C (and D's rare fallback). In production `config/settings.yaml` sets
`recommend.seed: null`, so `random.Random(None)` seeds from OS entropy — the same
publication regenerated yields different A/B/C numbers. This contract removes that
non-determinism by binding the seed to a stable publication identity.

## 2. Seed identity (input components)

The seed is derived from **exactly** these components:

| component         | source                                          | example                 |
|-------------------|-------------------------------------------------|-------------------------|
| `game_id`         | constant, which lottery game                    | `"DLT"`                 |
| `target_issue`    | the period the recommendation is published for   | `26113`                 |
| `strategy_id`     | recommendation bundle namespace                  | `"BUNDLE"` (A/B/C/D)    |
| `algorithm_version`| frozen recommender algorithm version            | `"dlt-recommender-v1"`  |

## 3. Derivation

```
normalized = f"{game_id}|{target_issue}|{strategy_id}|{algorithm_version}"
digest     = hashlib.sha256(normalized.encode('utf-8')).digest()
seed       = int.from_bytes(digest[:32], 'big')     # 256-bit int, stdlib-only
```

Implemented in `src/deterministic_rng.py::derive_deterministic_seed(...)`.
Uses **only** `hashlib.sha256` (stdlib). No new dependencies.

## 4. Invariants

- **Same identity → same seed → same A/B/C/D bundle** (cross-process, cross-machine).
- **Different `target_issue` → different seed** (namespace separation per period).
- **Different `algorithm_version` → different seed** (namespace separation per
  algorithm generation). Future algorithm upgrades bump the version, get a new
  deterministic sequence, and every previously *published* (version, issue) pair
  remains exactly reproducible at the old version.
- **Different `strategy_id` / `game_id` → different seed** (namespace separation).
- The seed is a 256-bit integer (SHA-256 sized) so the namespace is large enough
  that accidental seed collision across distinct publications is negligible.

## 5. Excluded from the seed (prohibited inputs)

The digest must NOT include any of the following:
- draw result / future result / hit count / backtest performance,
- "best performing seed" from P2/P3 (seed 0, 20260930, percentiles, etc.),
- current time, process id, machine id, system entropy,
- Python's process-salted `hash()`.

`seed` is a reproducibility namespace key only. **No performance is read from it.**

## 6. Version contract (STEP 5)

`algorithm_version` is an integral part of the seed identity (not a free constant
you can ignore). Rule:

- A formally upgraded recommender **bumps** `ALGORITHM_VERSION`.
- New publications use the new version → a new deterministic sequence.
- Reproducing an old published bundle uses the old version string → identical
  old result. Both coexist; no publication is ever rewritten.

## 7. Explicit-seed backward compatibility (STEP 8)

The production call path only overrides the seed **when `recommend.seed is None`**.
Any explicit `seed` (research/tests, e.g. 0, 1, 20260930) is passed through
unchanged to `recommend()`, so `C(seed=0)`, `C(seed=1)`, `C(seed=20260930)`
behaviour is byte-for-byte identical before and after this patch.

## 8. Failure behavior (STEP 14)

If a required component (`game_id`, `target_issue`, `strategy_id`,
`algorithm_version`) is missing/empty, `derive_deterministic_seed` **fails closed**
(`SeedDerivationError`). It never silently falls back to `seed=None`.

## 9. Scope / non-goals

- Only affects **not-yet-published** new publication generation.
- Historical immutable snapshots (including **26112**,
  hash `bea8ef87f3f137238686ae52712f922956215408f0cf54187b9295d8f1ae5fad`) are
  **never regenerated** by this patch.
- No change to A/B/C/D algorithms, selector logic, weights, `recent_issues=1000`,
  or the immutable snapshot. No ML added. No UI change.
