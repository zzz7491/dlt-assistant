#!/usr/bin/env python3
"""P4-5 local pre-publish integrity gate (read-only, no Cloudflare auth).

Runs BEFORE `src.publisher` in the pipeline. Unlike
`check_production_readiness.py` (which touches HTTP + Cloudflare account),
this gate is strictly LOCAL:

  - published store is parseable JSON
  - every snapshot's stored snapshot_hash matches a recomputed hash
  - the known immutable 26112 snapshot is present with the exact expected hash
  - 26113 is present (immutable)
  - required local files exist
  - history / published relationship is EXPLICITLY reported (P4-5 P11 / D4):
      * HISTORY_LAG when published_latest > history_latest
      * target_already_published when next_issue(history_latest) is already in
        the published store (scheduler will hit conflict/unchanged; the gate
        NEVER auto-skips to a new issue — D4/D6)
  - if a validated backup manifest exists under reports/backups/, verify its
    hash chain (R3: restore source must be validated)

Optional strictness:
  --require-backup : fail if no valid backup manifest is present (used in CI
                     so a publisher write is always preceded by a verified
                     backup, D1/D2)

Failure classes emitted: PASS / PUBLICATION_CORRUPT / PUBLICATION_CONFLICT /
PREPUBLISH_READINESS_FAILURE / BACKUP_FAILURE / HISTORY_VALIDATION_FAILURE.

Exit codes: 0 = PASS, 1 = FAIL. No Cloudflare OAuth / Pages HTTP / deploy
auth is required (P4-5 P10). No secrets are ever read or printed.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.publisher import snapshot_hash  # read-only reuse of the canonical hasher

PUBLISHED = ROOT / "public" / "data" / "published_recommendations.json"
HISTORY = ROOT / "data" / "dlt_history.json"
BACKUP_DIR = ROOT / "reports" / "backups"
EXPECTED_26112_HASH = "bea8ef87f3f137238686ae52712f922956215408f0cf54187b9295d8f1ae5fad"

REQUIRED_FILES = [
    "public/data/published_recommendations.json",
    "public/data/recommendations.json",
    "public/index.html",
    "public/experiment.html",
]


def _max_issue(values) -> int | None:
    nums = [int(v) for v in values if str(v).isdigit()]
    return max(nums) if nums else None


def _next_issue(latest: int) -> int:
    nn = latest % 1000
    yy = latest // 1000
    if nn >= 353:
        return (yy + 1) * 1000 + 1
    return latest + 1


def _check() -> dict:
    r: dict = {"gate": "P4-5 pre-publish", "checks": {}, "failure_class": "PASS"}

    # required local files
    missing = [f for f in REQUIRED_FILES if not (ROOT / f).exists()]
    r["checks"]["required_files"] = "OK" if not missing else f"MISSING {missing}"
    if missing:
        r["failure_class"] = "PREPUBLISH_READINESS_FAILURE"

    # published store parse
    store = None
    if PUBLISHED.exists():
        try:
            store = json.loads(PUBLISHED.read_text(encoding="utf-8"))
            r["checks"]["published_parse"] = "OK"
        except (json.JSONDecodeError, OSError):
            r["checks"]["published_parse"] = "CORRUPT"
            r["failure_class"] = "PUBLICATION_CORRUPT"
            store = None
    else:
        r["checks"]["published_parse"] = "MISSING"
        r["failure_class"] = "PREPUBLISH_READINESS_FAILURE"

    # per-snapshot hash integrity + known immutable snapshots
    if isinstance(store, dict):
        items = [s for s in store.get("items", []) if isinstance(s, dict)]
        bad = []
        for s in items:
            stored = s.get("snapshot_hash")
            if stored is not None and snapshot_hash(s) != stored:
                bad.append(str(s.get("issue")))
        r["checks"]["snapshot_hashes_valid"] = "OK" if not bad else f"BAD {bad}"
        if bad:
            r["failure_class"] = "PUBLICATION_CORRUPT"

        issue_set = {str(s.get("issue")) for s in items}
        has_26112 = "26112" in issue_set
        r["checks"]["26112_present"] = has_26112
        if has_26112:
            s26112 = next(s for s in items if str(s.get("issue")) == "26112")
            ok = snapshot_hash(s26112) == EXPECTED_26112_HASH
            r["checks"]["26112_hash"] = "OK" if ok else "MISMATCH"
            if not ok:
                r["failure_class"] = "PUBLICATION_CORRUPT"
        r["checks"]["26113_present"] = "26113" in issue_set

        # history / published relationship (P11 / D4) — explicit, no auto-skip
        hist_latest = pub_latest = None
        if HISTORY.exists():
            try:
                h = json.loads(HISTORY.read_text(encoding="utf-8"))
                hist_latest = _max_issue((i.get("issue") for i in h.get("issues", [])))
            except (json.JSONDecodeError, OSError):
                r["checks"]["history_parse"] = "CORRUPT"
                r["failure_class"] = "HISTORY_VALIDATION_FAILURE"
        pub_latest = _max_issue([s.get("issue") for s in items])
        r["history_latest"] = hist_latest
        r["published_latest"] = pub_latest
        history_lag = (
            hist_latest is not None and pub_latest is not None
            and pub_latest > hist_latest
        )
        r["checks"]["history_lag"] = history_lag
        target = _next_issue(hist_latest) if hist_latest else None
        r["scheduler_target"] = target
        r["target_already_published"] = bool(target and str(target) in issue_set)
        if history_lag:
            r["state"] = "HISTORY_LAG"
            # Explicit: do NOT auto-skip to next-unpublished; scheduler target
            # (an already-published issue) will resolve to unchanged/conflict.
            r["note"] = ("history lags published; scheduler_target is already "
                         "published — expect unchanged/conflict; NOT auto-skipping "
                         "(D4/D6). No historical snapshot is regenerated.")
    else:
        r["history_latest"] = None
        r["published_latest"] = None
        r["target_already_published"] = False
        r["checks"]["history_lag"] = False

    # backup manifest validation (R3) if present
    if BACKUP_DIR.exists():
        mans = sorted(BACKUP_DIR.glob("*.manifest.json"))
        if mans:
            latest = mans[-1]
            man = None
            try:
                man = json.loads(latest.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                man = None
            if man and man.get("backup_sha256"):
                # manifest "xxx.manifest.json" pairs with backup "xxx.json"
                stem = latest.name[: -len(".manifest.json")] if latest.name.endswith(".manifest.json") else latest.stem
                paired = BACKUP_DIR / f"{stem}.json"
                ok = False
                if paired.exists():
                    import hashlib
                    ok = (hashlib.sha256(paired.read_bytes()).hexdigest()
                          == man["backup_sha256"])
                r["checks"]["backup_manifest_valid"] = ok
                r["backup_present"] = ok
                if not ok and r.get("failure_class") == "PASS":
                    r["failure_class"] = "BACKUP_FAILURE"
            else:
                r["checks"]["backup_manifest_valid"] = "MISSING"
                r["backup_present"] = False
        else:
            r["checks"]["backup_manifest_valid"] = "NONE"
            r["backup_present"] = False
    else:
        r["checks"]["backup_manifest_valid"] = "NONE"
        r["backup_present"] = False

    return r


def main() -> int:
    p = argparse.ArgumentParser(description="P4-5 local pre-publish integrity gate")
    p.add_argument("--require-backup", action="store_true",
                   help="fail if no valid backup manifest is present (CI use)")
    p.add_argument("--json", metavar="PATH", default=None,
                   help="also write the structured result to PATH")
    args = p.parse_args()

    r = _check()

    # --require-backup: a publisher write must be preceded by a verified backup
    if args.require_backup:
        if not r.get("backup_present"):
            r["failure_class"] = "BACKUP_FAILURE"
            r["checks"]["require_backup"] = "FAILED (no valid backup manifest)"

    print("═══ P4-5 LOCAL PRE-PUBLISH INTEGRITY GATE ═══")
    print(f"  required_files : {r['checks'].get('required_files')}")
    print(f"  published_parse: {r['checks'].get('published_parse')}")
    print(f"  hash integrity : {r['checks'].get('snapshot_hashes_valid')}")
    print(f"  26112          : present={r['checks'].get('26112_present')} "
          f"hash={r['checks'].get('26112_hash')}")
    print(f"  26113 present  : {r['checks'].get('26113_present')}")
    print(f"  history_latest : {r.get('history_latest')}   published_latest: {r.get('published_latest')}")
    print(f"  history_lag    : {r['checks'].get('history_lag')}   "
          f"scheduler_target: {r.get('scheduler_target')}   "
          f"target_already_published: {r.get('target_already_published')}")
    print(f"  backup manifest: {r['checks'].get('backup_manifest_valid')}")
    if r.get("note"):
        print(f"  note           : {r['note']}")
    print(f"  RESULT         : {'PASS' if r['failure_class'] == 'PASS' else 'FAIL'} "
          f"({r['failure_class']})")

    if args.json:
        Path(args.json).write_text(json.dumps(r, ensure_ascii=False, indent=2,
                                               sort_keys=True), encoding="utf-8")
    return 0 if r["failure_class"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
