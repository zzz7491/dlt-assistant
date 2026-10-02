#!/usr/bin/env python3
"""P4-4 minimal append-only backup of the authoritative published store.

Copies public/data/published_recommendations.json to a timestamped backup file
under reports/backups/ and writes a SHA-256 hash manifest alongside it.

Design (fail-closed, no auto-delete):
  - Each backup is immutable: <timestamp>.json + <timestamp>.manifest.json
  - The manifest records source SHA-256, backup SHA-256, issue count, and the
    per-issue snapshot hashes (so a future restore can verify integrity).
  - NO automatic deletion of old backups. Retention is an explicit, out-of-scope
    operator decision (R9: destructive ops require human authorization).
  - This tool NEVER modifies the production published store.

Usage:
  python3 scripts/backup_published_store.py            # create one backup
  python3 scripts/backup_published_store.py --list     # list existing backups

Exit codes: 0 = success, 1 = source missing/corrupt.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "public" / "data" / "published_recommendations.json"
BACKUP_DIR = ROOT / "reports" / "backups"


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _issue_hash(snapshot: dict) -> str:
    """Recompute a snapshot hash the same way publisher.snapshot_hash does."""
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


def create_backup() -> tuple[int, Path | None]:
    if not SOURCE.exists():
        print(f"❌ backup: source not found: {SOURCE}")
        return 1, None
    raw = SOURCE.read_bytes()
    try:
        data = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        print("❌ backup: source is not parseable JSON (refusing to back up corrupt data)")
        return 1, None

    ts = datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    snap_path = BACKUP_DIR / f"published_recommendations.{ts}.json"
    man_path = BACKUP_DIR / f"published_recommendations.{ts}.manifest.json"

    snap_path.write_bytes(raw)
    manifest = {
        "created_at": ts,
        "source_path": str(SOURCE.relative_to(ROOT)),
        "source_sha256": _sha256_bytes(raw),
        "backup_sha256": _sha256_bytes(snap_path.read_bytes()),
        "issue_count": len(data.get("items", [])),
        "issues": [
            {"issue": str(s.get("issue")), "snapshot_hash": _issue_hash(s)}
            for s in data.get("items", []) if isinstance(s, dict)
        ],
        "note": "Immutable backup; do NOT auto-delete. Restore requires human "
                "authorization + hash verification (P4-4 R3/R9/R10).",
    }
    # Verify the copy matches the source before writing the manifest.
    if manifest["source_sha256"] != manifest["backup_sha256"]:
        snap_path.unlink(missing_ok=True)
        man_path.unlink(missing_ok=True)
        print("❌ backup: copy verification failed (hash mismatch); backup not kept")
        return 1, None
    man_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ backup created: {snap_path.relative_to(ROOT)} "
          f"({manifest['issue_count']} issues)")
    print(f"   manifest:      {man_path.relative_to(ROOT)}")
    return 0, snap_path


def list_backups() -> int:
    if not BACKUP_DIR.exists():
        print("no backups yet")
        return 0
    for p in sorted(BACKUP_DIR.glob("published_recommendations.*.manifest.json")):
        try:
            m = json.loads(p.read_text(encoding="utf-8"))
            print(f"  {p.name}  created={m.get('created_at')} "
                  f"issues={m.get('issue_count')} src_sha={str(m.get('source_sha256'))[:16]}...")
        except Exception:
            print(f"  {p.name}  (unparseable manifest)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="DLT published-store backup (append-only)")
    parser.add_argument("--list", action="store_true", help="list existing backups")
    args = parser.parse_args()
    if args.list:
        return list_backups()
    rc, _ = create_backup()
    return rc


if __name__ == "__main__":
    sys.exit(main())
