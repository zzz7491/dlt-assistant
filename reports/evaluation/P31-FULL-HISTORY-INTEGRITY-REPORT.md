# P3-1 Full-History Acquisition & Data Integrity Report

Dataset `p31-full-history-v1` · source `500.com (datachart.500.com/dlt/history/newinc/history.php)` · secondary `none` · acquired 2026-09-30 21:47:34

**VALIDATION STATUS: PASS**

## Range

- earliest issue: **07001** (2007-05-30)
- latest issue: **26112** (2026-09-30)
- draw count: **2930**

## Integrity

- temporal sorted: PASS
- duplicate issues: 0 (benign 0 / conflict 0)
- missing-issue candidates: 0 (yearly gaps incl. natural holiday/suspension breaks)
- date inversions: 0
- year transitions: 19
- quarantined records: 0

## Production Overlap (critical gate)

- overlap count: **1000** (production 1000-draw window ∩ full history)
- overlap exact match: **1000** (EXACT 1000/1000 — PASS)
- mismatches: 0

## Cross-source validation

- status: **NO**
- secondary: none

## Dataset hash (immutable snapshot for P3-2)

- dataset_sha256: `ba4bfb09d46aa66ab72c2ba3f72057e37ffca293ac76e1e3a21dde77f1e4dbbf`
- verify matches file: True

## Production unchanged

- production fetch limit / analyzer limit / window / recommender: **UNCHANGED** (P3-1 research-only)
- 26112 published snapshot: **UNCHANGED**
