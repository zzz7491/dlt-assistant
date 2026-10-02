#!/usr/bin/env python3
"""P4-4 dry-run-first recovery verifier for the authoritative published store.

DEFAULT (dry-run / read-only) modes — safe to run anytime:
  --inspect            show current published store state (issues, hashes)
  --validate           recompute + verify every snapshot_hash (integrity check)
  --list-snapshots     list issue -> snapshot_hash
  --check-backup FILE  verify a backup + manifest hash chain
  --compare A B        compare two stores (e.g. git version vs working tree)

EXPLICIT RESTORE mode (fail-closed, human-authorized) — never default:
  --restore <backup.json> --manifest <manifest.json> --authorize "<reason>"
    Verifies the backup hash manifest, verifies no issue would lose its
    existing snapshot (R1/R5), verifies immutable hashes (R10), and ONLY then
    writes the store atomically. Refuses to recompute history (R3).

No mode writes to production D1; no mode leaks tokens/secrets.

Exit codes: 0 = success/verified, 1 = verification failed / refused.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STORE = ROOT / "public" / "data" / "published_recommendations.json"


def _canon_hash(snapshot: dict) -> str:
    numbers = snapshot.get("numbers") or {}
    d = {
        "issue": str(snapshot.get("issue")),
        "primary_strategy": snapshot.get("primary_strategy"),
        "front": numbers.get("front"),
        "back": numbers.get("back"),
        "reason": snapshot.get("reason"),
        "final_score": snapshot.get("final_score"),
        "final_breakdown": snapshot.get("final_breakdown"),
        "model_version": snapshot.get("model_version"),
        "explanation": snapshot.get("explanation"),
    }
    canon = json.dumps(d, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def _load_store(path: Path):
    if not path.exists():
        return None, "MISSING"
    try:
        return json.loads(path.read_text(encoding="utf-8")), "OK"
    except (json.JSONDecodeError, OSError) as e:
        return None, f"CORRUPT ({type(e).__name__})"


def _issues(store) -> list[str]:
    if not isinstance(store, dict):
        return []
    return [str(s.get("issue")) for s in store.get("items", []) if isinstance(s, dict)]


def cmd_inspect() -> int:
    store, parse = _load_store(STORE)
    print(f"store: {STORE.relative_to(ROOT)}  parse={parse}")
    if parse == "OK":
        print(f"issues: {_issues(store)}")
    return 0 if parse == "OK" else 1


def cmd_validate() -> int:
    store, parse = _load_store(STORE)
    if parse != "OK":
        print(f"❌ validate: store {parse}; cannot verify hashes")
        return 1
    bad = []
    for s in store.get("items", []):
        if not isinstance(s, dict):
            bad.append(("<non-dict>", "malformed item"))
            continue
        stored = s.get("snapshot_hash")
        computed = _canon_hash(s)
        if stored != computed:
            bad.append((str(s.get("issue")), f"stored={str(stored)[:12]}.. computed={computed[:12]}.."))
    if bad:
        print(f"❌ validate: {len(bad)} snapshot(s) with hash mismatch:")
        for iss, why in bad:
            print(f"   - {iss}: {why}")
        return 1
    print(f"✅ validate: all {len(_issues(store))} snapshot hashes verified")
    return 0


def cmd_list_snapshots() -> int:
    store, parse = _load_store(STORE)
    if parse != "OK":
        print(f"❌ list: store {parse}")
        return 1
    for s in store.get("items", []):
        print(f"  {s.get('issue')}: {str(s.get('snapshot_hash'))[:24]}...")
    return 0


def cmd_check_backup(backup: str, manifest: str) -> int:
    b = Path(backup)
    m = Path(manifest)
    if not b.exists() or not m.exists():
        print("❌ check-backup: backup or manifest file missing")
        return 1
    man = json.loads(m.read_text(encoding="utf-8"))
    braw = b.read_bytes()
    src_ok = man.get("backup_sha256") == hashlib.sha256(braw).hexdigest()
    issues_ok = all(
        _canon_hash(s) == rec.get("snapshot_hash")
        for s, rec in zip(
            (it for it in json.loads(braw.decode("utf-8")).get("items", [])),
            man.get("issues", []),
        )
    ) if src_ok else False
    print(f"backup hash match: {src_ok}")
    print(f"issue hashes consistent: {issues_ok}")
    ok = src_ok and issues_ok
    print(f"{'✅' if ok else '❌'} check-backup: {'VERIFIED' if ok else 'FAILED'}")
    return 0 if ok else 1


def cmd_compare(a: str, b: str) -> int:
    pa, pb = Path(a), Path(b)
    sa, _ = _load_store(pa)
    sb, _ = _load_store(pb)
    ia, ib = _issues(sa), _issues(sb)
    same = ia == ib
    print(f"A issues: {ia}")
    print(f"B issues: {ib}")
    print(f"issue sets identical: {same}")
    return 0 if same else 1


def cmd_restore(backup: str, manifest: str, authorize: str) -> int:
    """Explicit, fail-closed restore. Requires backup + manifest + authorization reason."""
    if not (Path(backup).exists() and Path(manifest).exists()):
        print("❌ restore: backup/manifest missing")
        return 1
    if not authorize or len(authorize.strip()) < 8:
        print("❌ restore: --authorize '<reason>' is required (R9: explicit human authorization)")
        return 1
    # Step 1: verify the backup integrity (reuse check-backup logic).
    man = json.loads(Path(manifest).read_text(encoding="utf-8"))
    braw = Path(backup).read_bytes()
    if man.get("backup_sha256") != hashlib.sha256(braw).hexdigest():
        print("❌ restore: backup hash verification FAILED (R10). Aborting.")
        return 1
    new_store = json.loads(braw.decode("utf-8"))
    new_issues = _issues(new_store)
    # Step 2: R1/R5 — restore must not lose an existing issue's snapshot.
    cur, _cur_parse = _load_store(STORE)
    cur_issues = _issues(cur)
    lost = [i for i in cur_issues if i not in new_issues]
    if lost:
        print(f"❌ restore: would LOSE existing issues {lost} (R1). Aborting — use a backup that "
              f"supersedes the current store, not one that drops history.")
        return 1
    # Step 3: re-verify every snapshot hash in the backup (R10).
    bad = [str(s.get("issue")) for s in new_store.get("items", [])
           if isinstance(s, dict) and _canon_hash(s) != s.get("snapshot_hash")]
    if bad:
        print(f"❌ restore: snapshot hash mismatch on {bad} (R10). Aborting.")
        return 1
    # Step 4: write atomically (P4-3 F2 pattern).
    d = str(STORE.parent)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".recovery.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(braw.decode("utf-8"))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, STORE)
    except BaseException:
        os.unlink(tmp) if os.path.exists(tmp) else None
        raise
    # Step 5: post-restore verification.
    post, post_parse = _load_store(STORE)
    if post_parse != "OK" or _issues(post) != new_issues:
        print("❌ restore: post-restore verification FAILED. Store may be inconsistent.")
        return 1
    print(f"✅ restore complete: {new_issues} verified. Authorization: '{authorize}'")
    print(f"   ⚠️ Re-run: python3 scripts/recovery_check.py --validate (R10)")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="DLT dry-run-first recovery verifier")
    p.add_argument("--inspect", action="store_true")
    p.add_argument("--validate", action="store_true")
    p.add_argument("--list-snapshots", action="store_true")
    p.add_argument("--check-backup", nargs=2, metavar=("BACKUP", "MANIFEST"))
    p.add_argument("--compare", nargs=2, metavar=("A", "B"))
    p.add_argument("--restore", metavar="BACKUP")
    p.add_argument("--manifest", default=None, help="manifest for --restore")
    p.add_argument("--authorize", default=None, help="authorization reason for --restore")
    args = p.parse_args()

    if args.check_backup:
        return cmd_check_backup(args.check_backup[0], args.check_backup[1])
    if args.compare:
        return cmd_compare(args.compare[0], args.compare[1])
    if args.restore:
        if not args.manifest:
            print("❌ --restore requires --manifest")
            return 1
        return cmd_restore(args.restore, args.manifest, args.authorize or "")
    if args.validate:
        return cmd_validate()
    if args.list_snapshots:
        return cmd_list_snapshots()
    if args.inspect:
        return cmd_inspect()
    p.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
