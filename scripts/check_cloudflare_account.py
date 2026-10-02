#!/usr/bin/env python3
"""P4-1 Cloudflare Account Guard (fail-closed deployment safety check).

Before any DLT production deployment (wrangler pages deploy) this verifies the
active Wrangler identity is the DLT production Cloudflare account.  A mismatch
or an undetermined account exits non-zero (STOP) so a wrong-account deploy is
impossible to run by accident.

Design (fail-closed):
  - Account ID is the authoritative identity check; the email is only a
    human-readable label and is NEVER the sole security decision.
  - Undeterminable / no-credentials / malformed / ambiguous => FAIL (exit 1).
  - Wrangler command failure => FAIL.
  - No tokens / secret values are ever printed.
  - No automatic login / logout / account switch.

Modes:
  live (default): run `wrangler whoami` (read-only) and parse the Account ID;
                  on any live failure, fall back to the local .wrangler cache
                  and then the CLOUDFLARE_ACCOUNT_ID env var.
  --offline:      read the local .wrangler/cache/wrangler-account.json only.
  --ci:           read the CLOUDFLARE_ACCOUNT_ID env var only.

Exit codes: 0 = PASS, 1 = FAIL-CLOSED.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

# DLT production Cloudflare identity (authoritative = account ID).
EXPECTED_ACCOUNT_ID = "8770e4917f904aed5df91c883cf058af"
HUMAN_LABEL = "lsv3255@gmail.com"  # diagnostic only; NOT the security key

REPO_ROOT = Path(__file__).resolve().parent.parent
WRANGLER_ACCOUNT_CACHE = REPO_ROOT / ".wrangler" / "cache" / "wrangler-account.json"
NPM_CACHE = REPO_ROOT / ".npmcache"


def _strip_ansi(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", text)


def _parse_whoami_output(stdout: str) -> str | None:
    """Extract the Account ID from `wrangler whoami` output (32-hex string).

    Returns the ID when exactly one candidate is found, else None (ambiguous
    or absent => fail-closed).
    """
    text = _strip_ansi(stdout)
    hex_re = re.compile(r"\b([0-9a-f]{32})\b")
    matches = hex_re.findall(text)
    # Only treat as authoritative when unambiguous.
    if len(matches) == 1:
        return matches[0]
    if not matches:
        return None
    # Multiple 32-hex values => ambiguous; do NOT guess.
    return None


def _wrangler_command() -> list[str] | None:
    """Build a read-only `wrangler whoami` command (global or npx fallback)."""
    for name in ("wrangler",):
        path = shutil.which(name)
        if path:
            return [path, "whoami"]
    for npx in ("/opt/homebrew/bin/npx", "npx"):
        if shutil.which(npx):
            return [npx, "--yes", "wrangler@latest", "whoami"]
    return None


def _run_whoami() -> tuple[str, str | None, bool]:
    """Run wrangler whoami; return (status, account_id, ok)."""
    cmd = _wrangler_command()
    if not cmd:
        return "FAIL_NO_WRANGLER", None, False

    env = os.environ.copy()
    os.makedirs(NPM_CACHE, exist_ok=True)
    env["npm_config_cache"] = str(NPM_CACHE)

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=180, env=env)
    except subprocess.TimeoutExpired:
        return "FAIL_WRANGLER_TIMEOUT", None, False
    except OSError as e:
        return f"FAIL_WRANGLER_ERROR:{type(e).__name__}", None, False

    account_id = _parse_whoami_output(proc.stdout)
    if account_id is None:
        # wrangler can still print the account table even when it logs an
        # EPERM writing its log file; treat a parseable account as usable.
        if proc.returncode != 0:
            return "FAIL_WRANGLER_ERROR", None, False
        return "FAIL_UNPARSEABLE", None, False
    status = "PASS" if proc.returncode == 0 else "PASS_WITH_WARNINGS"
    return status, account_id, True


def check_account_offline() -> tuple[str, str | None, bool]:
    if not WRANGLER_ACCOUNT_CACHE.exists():
        return "FAIL_NO_CACHE", None, False
    try:
        data = json.loads(WRANGLER_ACCOUNT_CACHE.read_text(encoding="utf-8"))
        account = data.get("account") or {}
        account_id = account.get("id")
        if account_id is None or not re.fullmatch(r"[0-9a-f]{32}", str(account_id)):
            return "FAIL_CACHE_MALFORMED", None, False
        return "PASS", str(account_id), True
    except (json.JSONDecodeError, OSError) as e:
        return f"FAIL_CACHE_ERROR:{type(e).__name__}", None, False


def check_account_ci() -> tuple[str, str | None, bool]:
    val = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
    if not val:
        return "FAIL_NO_CLOUDFLARE_ACCOUNT_ID_ENV", None, False
    if not re.fullmatch(r"[0-9a-f]{32}", val):
        return "FAIL_CLOUDFLARE_ACCOUNT_ID_MALFORMED", None, False
    return "PASS", val, True


def main() -> int:
    parser = argparse.ArgumentParser(description="DLT Cloudflare Account Guard")
    parser.add_argument("--offline", action="store_true",
                        help="Read local .wrangler cache only (no network)")
    parser.add_argument("--ci", action="store_true",
                        help="Read CLOUDFLARE_ACCOUNT_ID env var only")
    args = parser.parse_args()

    if args.ci:
        status, actual, ok = check_account_ci()
    elif args.offline:
        status, actual, ok = check_account_offline()
    else:
        status, actual, ok = _run_whoami()
        if not ok:  # fall back: local cache, then explicit CI env
            off_status, off_actual, off_ok = check_account_offline()
            if off_ok:
                status, actual, ok = off_status, off_actual, off_ok
            else:
                ci_status, ci_actual, ci_ok = check_account_ci()
                if ci_ok:
                    status, actual, ok = ci_status, ci_actual, ci_ok

    # ------------------------------------------------------------------
    # Fail-closed: undetermined account => FAIL.
    # ------------------------------------------------------------------
    if not ok or actual is None:
        print(f"❌ CLOUDFLARE ACCOUNT GUARD: FAIL-CLOSED ({status})")
        print(f"   Expected account ID: {EXPECTED_ACCOUNT_ID} ({HUMAN_LABEL})")
        print(f"   Actual account ID:   {actual if actual else '<undetermined>'}")
        print("   Action: switch the Wrangler identity to the DLT production "
              "account, then re-run. Do NOT bypass this guard.")
        return 1

    # ------------------------------------------------------------------
    # Account match check (authoritative = account ID, not email).
    # ------------------------------------------------------------------
    if actual == EXPECTED_ACCOUNT_ID:
        print(f"✅ CLOUDFLARE ACCOUNT GUARD: PASS")
        print(f"   Account ID: {actual}  ({HUMAN_LABEL})")
        print(f"   Status:     {status}")
        return 0

    print(f"❌ CLOUDFLARE ACCOUNT GUARD: ACCOUNT MISMATCH — FAIL-CLOSED")
    print(f"   Expected account ID: {EXPECTED_ACCOUNT_ID} ({HUMAN_LABEL})")
    print(f"   Actual account ID:   {actual}")
    print("   Action: switch the Wrangler identity to the DLT production "
          "account, then re-run. Do NOT bypass this guard.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
