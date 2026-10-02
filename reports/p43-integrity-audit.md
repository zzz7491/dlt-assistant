# P4-3 INTEGRITY AUDIT (Markdown summary)

Machine-readable version: `reports/p43-integrity-audit.json`.

## Confirmed defects (in-scope, fixed)

### G1 — CRITICAL — corrupt published store silently wipes history (I3/I4/I12)
`upsert_published_snapshot` called `_load_json` (returns `None` on parse failure) and
`_load_published_store` coerced `None` → empty store. A corrupt
`public/data/published_recommendations.json` was silently reset on the next upsert,
deleting all historical immutable snapshots.
**Fix F1**: when the target file exists but is not a parseable published store
(non-dict / missing `items`), `upsert_published_snapshot` now returns `corrupt` and
does NOT write. `publish()` treats `corrupt` like `conflict` (fail-closed: no
display write). Only a truly missing file triggers first-publication creation.

### G2 — HIGH — non-atomic write enables corruption (I5)
`_write_json` used `open(path, "w") + json.dump`: `"w"` truncates the live file
first; a mid-write crash leaves a corrupt/empty file → the root enabler of G1.
**Fix F2**: `_write_json` now writes to a same-directory `tempfile.mkstemp`,
`fsync`, then `os.replace` (atomic). On failure the temp file is unlinked and the
exception propagates — never leaving a half-written target.

## Adversarial scenarios (A–L): all PASS
See `reports/p43-integrity-audit.json` for the per-scenario table.

## Defense-in-depth (existing, verified)
CI `concurrency.group: experiment-ci` job serialization · D1
`INSERT OR IGNORE` + `UNIQUE(target_issue,strategy,idx)` one-period lock ·
existing upsert conflict (I2/I12) · publisher fail-closed on 0/multiple primary
or conflict · `--safe` top-level exception isolation.

## Not a defect / out of scope
- history-lag re-targeting of a published issue: handled by conflict (no overwrite).
- recommendation algorithm / scoring / weights / analysis window / selector: untouched.
- regenerating historical snapshots: not done.

## Change surface
Only `src/publisher.py` (F1 + F2 + the `corrupt` branch in `publish()`) and
test/docs/reports. No semantic change to recommendation generation.
