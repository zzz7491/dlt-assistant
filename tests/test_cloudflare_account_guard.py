"""P4-1 Cloudflare Account Guard — comprehensive unit tests.

Tests the guard in all required modes (correct, wrong, no-account, malformed,
command-error, ambiguous, no-secret-leak).  Uses subprocess + importlib to
control the guard's internal constants; does NOT change the real Wrangler
identity.

Run: .venv/bin/python -m unittest tests.test_cloudflare_account_guard -v
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
GUARD_PATH = str(ROOT / "scripts" / "check_cloudflare_account.py")
WRANGLER_CACHE = ROOT / ".wrangler" / "cache" / "wrangler-account.json"

EXPECTED_ACCOUNT_ID = "8770e4917f904aed5df91c883cf058af"
WRONG_ACCOUNT_ID = "6bbedf3d4f904606559e551e6c19bc9a"


def _import_guard():
    """Import the guard module from its file path (scripts/ is not a package)."""
    spec = importlib.util.spec_from_file_location("cf_guard", GUARD_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_guard(*extra_args, env_overrides=None):
    env = os.environ.copy()
    env.pop("CLOUDFLARE_ACCOUNT_ID", None)
    if env_overrides:
        env.update(env_overrides)
    proc = subprocess.run(
        [sys.executable, GUARD_PATH, *extra_args],
        capture_output=True, text=True, timeout=180,
        env=env, cwd=str(ROOT),
    )
    return proc.returncode, proc.stdout, proc.stderr


# ------------------------------------------------------------------
# 1. correct account → PASS
# ------------------------------------------------------------------
class TestCorrectAccount(unittest.TestCase):
    def test_offline_correct(self):
        rc, out, _ = run_guard("--offline")
        self.assertEqual(rc, 0, out)
        self.assertIn("PASS", out)
        self.assertIn(EXPECTED_ACCOUNT_ID, out)

    def test_ci_correct(self):
        rc, out, _ = run_guard("--ci", env_overrides={"CLOUDFLARE_ACCOUNT_ID": EXPECTED_ACCOUNT_ID})
        self.assertEqual(rc, 0, out)
        self.assertIn("PASS", out)


# ------------------------------------------------------------------
# 2. wrong account → FAIL
# ------------------------------------------------------------------
class TestWrongAccount(unittest.TestCase):
    def test_ci_wrong(self):
        rc, out, _ = run_guard("--ci", env_overrides={"CLOUDFLARE_ACCOUNT_ID": WRONG_ACCOUNT_ID})
        self.assertEqual(rc, 1, out)
        self.assertIn("MISMATCH", out)
        self.assertIn("FAIL-CLOSED", out)

    def test_offline_wrong_cache(self):
        """Patch the cache file to hold a wrong account ID, then restore."""
        original = WRANGLER_CACHE.read_text(encoding="utf-8")
        try:
            data = json.loads(original)
            data["account"]["id"] = WRONG_ACCOUNT_ID
            WRANGLER_CACHE.write_text(json.dumps(data), encoding="utf-8")
            rc, out, _ = run_guard("--offline")
            self.assertEqual(rc, 1, out)
            self.assertIn("MISMATCH", out)
        finally:
            WRANGLER_CACHE.write_text(original, encoding="utf-8")

    def test_mismatch_via_imported_module(self):
        """Call main() in-process with a mocked check function returning a wrong ID."""
        guard = _import_guard()
        with mock.patch.object(guard, "check_account_ci",
                               return_value=("PASS", WRONG_ACCOUNT_ID, True)), \
             mock.patch.object(sys, "argv", ["guard", "--ci"]):
            rc = guard.main()
        self.assertEqual(rc, 1)


# ------------------------------------------------------------------
# 3. no account / no credentials → FAIL
# ------------------------------------------------------------------
class TestNoAccount(unittest.TestCase):
    def test_ci_missing_env(self):
        rc, out, _ = run_guard("--ci")  # no CLOUDFLARE_ACCOUNT_ID
        self.assertEqual(rc, 1, out)
        self.assertIn("FAIL", out)

    def test_offline_missing_cache(self):
        """Point WRANGLER_ACCOUNT_CACHE at a nonexistent path via mock."""
        guard = _import_guard()
        with mock.patch.object(guard, "WRANGLER_ACCOUNT_CACHE",
                               Path("/nonexistent/path/.wrangler/cache/wrangler-account.json")):
            status, actual, ok = guard.check_account_offline()
        self.assertFalse(ok, "must fail when cache file is missing")
        self.assertIn("FAIL", status)

    def test_live_no_wrangler_no_cache_no_env(self):
        """Simulate: no wrangler binary, no .wrangler cache, no CI env → FAIL-CLOSED."""
        guard = _import_guard()
        with mock.patch.object(guard, "_run_whoami",
                               return_value=("FAIL_NO_WRANGLER", None, False)), \
             mock.patch.object(guard, "check_account_offline",
                               return_value=("FAIL_NO_CACHE", None, False)), \
             mock.patch.object(guard, "check_account_ci",
                               return_value=("FAIL_NO_CLOUDFLARE_ACCOUNT_ID_ENV", None, False)), \
             mock.patch.object(sys, "argv", ["guard"]):
            rc = guard.main()
        self.assertEqual(rc, 1, "all three sources unavailable → must fail closed")


# ------------------------------------------------------------------
# 4. malformed Wrangler / env output → FAIL
# ------------------------------------------------------------------
class TestMalformed(unittest.TestCase):
    def test_malformed_ci_env(self):
        rc, out, _ = run_guard("--ci", env_overrides={"CLOUDFLARE_ACCOUNT_ID": "not-a-hex-string"})
        self.assertEqual(rc, 1, out)
        self.assertIn("MALFORMED", out)

    def test_malformed_cache(self):
        guard = _import_guard()
        with mock.patch.object(guard, "WRANGLER_ACCOUNT_CACHE",
                               Path("/nonexistent/path/.wrangler/cache/wrangler-account.json")):
            # Write a malformed JSON at the real cache path temporarily
            original = WRANGLER_CACHE.read_text(encoding="utf-8")
            try:
                WRANGLER_CACHE.write_text("not valid json", encoding="utf-8")
                # Now point guard at it
                with mock.patch.object(guard, "WRANGLER_ACCOUNT_CACHE", WRANGLER_CACHE):
                    status, actual, ok = guard.check_account_offline()
            finally:
                WRANGLER_CACHE.write_text(original, encoding="utf-8")
        self.assertFalse(ok, "malformed cache must fail closed")
        self.assertIn("FAIL", status)


# ------------------------------------------------------------------
# 5. Wrangler command error → FAIL
# ------------------------------------------------------------------
class TestWranglerError(unittest.TestCase):
    def test_wrangler_command_failure(self):
        guard = _import_guard()
        with mock.patch.object(guard, "_run_whoami",
                               return_value=("FAIL_WRANGLER_ERROR", None, False)), \
             mock.patch.object(guard, "check_account_offline",
                               return_value=("FAIL_NO_CACHE", None, False)), \
             mock.patch.object(guard, "check_account_ci",
                               return_value=("FAIL_NO_CLOUDFLARE_ACCOUNT_ID_ENV", None, False)), \
             mock.patch.object(sys, "argv", ["guard"]):
            rc = guard.main()
        self.assertEqual(rc, 1, "wrangler command error must fail closed")

    def test_no_wrangler_binary(self):
        """_wrangler_command returns None → _run_whoami returns FAIL_NO_WRANGLER."""
        guard = _import_guard()
        with mock.patch.object(guard, "_wrangler_command", return_value=None):
            status, actual, ok = guard._run_whoami()
        self.assertFalse(ok)
        self.assertEqual(status, "FAIL_NO_WRANGLER")


# ------------------------------------------------------------------
# 6. ambiguous multi-account output → FAIL (not a silent pass)
# ------------------------------------------------------------------
class TestAmbiguous(unittest.TestCase):
    def test_two_hex_strings_returns_none(self):
        guard = _import_guard()
        ambiguous = (
            "account A  8770e4917f904aed5df91c883cf058af\n"
            "account B  6bbedf3d4f904606559e551e6c19bc9a\n"
        )
        self.assertIsNone(
            guard._parse_whoami_output(ambiguous),
            "two 32-hex strings must be ambiguous → None → FAIL-CLOSED",
        )

    def test_single_hex_string_returns_id(self):
        guard = _import_guard()
        single = f"│ {EXPECTED_ACCOUNT_ID} │"
        self.assertEqual(guard._parse_whoami_output(single), EXPECTED_ACCOUNT_ID)

    def test_no_hex_strings_returns_none(self):
        guard = _import_guard()
        self.assertIsNone(guard._parse_whoami_output("no account info here"))


# ------------------------------------------------------------------
# 7. no secret / token leakage in any guard output
# ------------------------------------------------------------------
class TestNoSecretLeak(unittest.TestCase):
    def test_no_api_token_in_output(self):
        fake_token = "sk-test-secret-token-abc123"
        rc, out, err = run_guard("--offline",
                                 env_overrides={"CLOUDFLARE_API_TOKEN": fake_token})
        self.assertNotIn(fake_token, out, "stdout must not leak API token")
        self.assertNotIn(fake_token, err, "stderr must not leak API token")

    def test_no_jwt_or_sk_prefix_in_output(self):
        rc, out, err = run_guard("--offline")
        for stream, label in ((out, "stdout"), (err, "stderr")):
            self.assertNotIn("sk-", stream, f"{label} must not leak sk- token prefix")
            self.assertNotIn("eyJ", stream, f"{label} must not leak JWT prefix")


if __name__ == "__main__":
    unittest.main(verbosity=2)
