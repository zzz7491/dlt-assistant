#!/usr/bin/env python3
"""P4-5 operational status + failure taxonomy (machine-readable, no secrets).

Supports the daily pipeline's structured run status:
  reports/last-run-status.json   (gitignored runtime artifact; ephemeral on the
  CI runner unless exported as an Actions artifact)

Design:
  - A fixed failure-class taxonomy (P4-5 P12). No framework.
  - Every value written is sanitized so a token / secret / credential string can
    never be recorded (D16 / stop-condition #11).
  - Atomic write (temp + fsync + os.replace) so a mid-write crash never leaves
    a corrupt status file.

CLI (used by workflow steps and by tests):
  python3 scripts/ops_status.py init [--trigger NAME]
  python3 scripts/ops_status.py set KEY VALUE ...
  python3 scripts/ops_status.py classify FAILURE_CLASS   # sets failure_class
  python3 scripts/ops_status.py dump                     # pretty-print JSON
  python3 scripts/ops_status.py path                     # print status file path

None of these run the scheduler/publisher or touch production D1.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PATH = ROOT / "reports" / "last-run-status.json"

# P4-5 P12 minimal failure-class taxonomy.
FAILURE_CLASSES = [
    "PASS", "NOOP_NO_CHANGE",
    "HISTORY_SOURCE_FAILURE", "HISTORY_VALIDATION_FAILURE",
    "BACKUP_FAILURE", "PREPUBLISH_READINESS_FAILURE",
    "SCHEDULER_FAILURE", "PUBLICATION_CONFLICT", "PUBLICATION_CORRUPT",
    "D1_FAILURE", "GIT_PUSH_FAILURE",
    "CLOUDFLARE_ACCOUNT_MISMATCH", "CLOUDFLARE_AUTH_FAILURE", "DEPLOY_FAILURE",
]

# Keys whose VALUES must never be persisted, and value patterns that mark a
# secret. (D16: operational artifacts must not contain secrets.)
SECRET_KEYS = {
    "token", "api_token", "api_key", "apikey", "secret", "password", "passwd",
    "oauth_token", "authorization", "credential", "credentials", "private_key",
}
SECRET_VALUE_RE = re.compile(r"(sk-[A-Za-z0-9]{10,}|eyJ[A-Za-z0-9._-]{20,}|ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16})")


def _scrub(value):
    """Remove secret-looking content from a status value (never raises)."""
    if isinstance(value, str):
        if SECRET_VALUE_RE.search(value):
            return "<redacted>"
        return value
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if str(k).lower() in SECRET_KEYS:
                out[str(k)] = "<redacted>"
            else:
                out[str(k)] = _scrub(v)
        return out
    if isinstance(value, list):
        return [_scrub(i) for i in value]
    return value


def _atomic_write(path: Path, data: dict) -> None:
    d = path.parent
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(d), prefix=".ops-status.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _load(path: Path) -> dict:
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _load_status(path: Path) -> dict:
    data = _load(path)
    data.setdefault("gate", "P4-5")
    data.setdefault("failure_class", "PASS")
    return data


def cmd_init(path: Path, trigger: str | None) -> int:
    data = _load_status(path)
    data["initialized"] = True
    if trigger:
        data["trigger"] = trigger
    _atomic_write(path, data)
    print(f"[ops_status] initialized {path.relative_to(ROOT)}")
    return 0


def cmd_set(path: Path, pairs: list[str]) -> int:
    data = _load_status(path)
    for pair in pairs:
        if "=" not in pair:
            print(f"[ops_status] WARN: ignoring malformed kv: {pair!r}")
            continue
        k, v = pair.split("=", 1)
        data[k.strip()] = _scrub(v)
    _atomic_write(path, data)
    return 0


def cmd_classify(path: Path, failure_class: str) -> int:
    if failure_class not in FAILURE_CLASSES:
        print(f"[ops_status] WARN: {failure_class!r} not in taxonomy; recording as-is")
    data = _load_status(path)
    data["failure_class"] = failure_class
    data["pass"] = (failure_class == "PASS")
    _atomic_write(path, data)
    print(f"[ops_status] failure_class={failure_class}")
    return 0


def cmd_dump(path: Path) -> int:
    data = _load_status(path)
    print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def cmd_path(_path: Path) -> int:
    print(str(DEFAULT_PATH))
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="P4-5 operational status (no secrets)")
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("path")
    i = sub.add_parser("init")
    i.add_argument("--trigger", default=None)
    s = sub.add_parser("set")
    s.add_argument("kv", nargs="+")
    c = sub.add_parser("classify")
    c.add_argument("failure_class")
    sub.add_parser("dump")
    args = p.parse_args()

    if args.cmd == "init":
        return cmd_init(DEFAULT_PATH, args.trigger)
    if args.cmd == "set":
        return cmd_set(DEFAULT_PATH, args.kv)
    if args.cmd == "classify":
        return cmd_classify(DEFAULT_PATH, args.failure_class)
    if args.cmd == "dump":
        return cmd_dump(DEFAULT_PATH)
    if args.cmd == "path":
        return cmd_path(DEFAULT_PATH)
    p.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
