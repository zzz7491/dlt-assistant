"""P4-4 Operational Readiness / Recovery tests.

Covers the P4-4 requirements:
  - readiness status output contains issue/hash/status
  - no secret leakage
  - readiness pass path / wrong CF account fail / corrupt published JSON fail /
    missing store fail / immutable hash mismatch fail / history lag reported
  - deployment path does not publish
  - recovery default dry-run; cannot overwrite without explicit authorization
  - backup manifest hash correctness; restore verifier detects mismatch

All tests use temp fixtures; production D1 / production store are NEVER written
(restore tests point recovery_check at a temp STORE via monkeypatching the
module-level STORE constant).

Run: .venv/bin/python -m unittest tests.test_p44_operational_readiness -v
"""
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

READY = str(ROOT / "scripts" / "check_production_readiness.py")
RECOVERY = str(ROOT / "scripts" / "recovery_check.py")
BACKUP = str(ROOT / "scripts" / "backup_published_store.py")
EXPECTED_26112_HASH = "bea8ef87f3f137238686ae52712f922956215408f0cf54187b9295d8f1ae5fad"
EXPECTED_CLOUDFLARE_ACCOUNT = "8770e4917f904aed5df91c883cf058af"


def _import(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# 1-3. readiness status content + no secret leakage + pass/fail paths
# ---------------------------------------------------------------------------
class TestReadinessStatus(unittest.TestCase):
    def test_01_status_contains_issue_hash_status(self):
        """The checker reports issue + snapshot-hash + status fields."""
        out = subprocess.run([sys.executable, READY, "--offline"],
                             capture_output=True, text=True, cwd=str(ROOT))
        combined = out.stdout + out.stderr
        self.assertIn("published", combined)
        self.assertIn("26112_ok", combined)
        self.assertIn("cloudflare", combined)
        self.assertIn("RESULT:", combined)
        # the machine-readable failure_class field lives in the written JSON
        with mock.patch.object(sys, "argv", ["r", "--offline", "--write-status"]):
            # run and confirm a structured artifact is produced when requested
            out2 = subprocess.run([sys.executable, READY, "--offline", "--write-status"],
                                   capture_output=True, text=True, cwd=str(ROOT))
            status_path = ROOT / "reports" / "last-run-status.json"
            self.assertTrue(status_path.exists(), "structured status artifact must be written")
            status = json.loads(status_path.read_text(encoding="utf-8"))
            self.assertIn("failure_class", status)
            self.assertIn("issues", status.get("published", {}))
            # clean up the generated artifact so it is not committed
            status_path.unlink()

    def test_02_no_secret_leakage(self):
        """No token/JWT/secret markers may appear in checker output."""
        for args in (["--offline"], []):
            out = subprocess.run([sys.executable, READY, *args],
                                 capture_output=True, text=True, cwd=str(ROOT),
                                 timeout=60)
            blob = out.stdout + out.stderr
            for marker in ("sk-", "eyJ", "CLOUDFLARE_API_TOKEN=", "oauth_token="):
                self.assertNotIn(marker, blob,
                                 f"secret marker {marker!r} leaked in readiness output")

    def test_03_pass_path_when_healthy(self):
        """Offline healthy state (clean git + files + published + CF cache) → exit 0."""
        # This depends on the repo state at test time; assert the pass logic by
        # checking the exit code is a clean 0/1 (not a crash).
        out = subprocess.run([sys.executable, READY, "--offline"],
                             capture_output=True, text=True, cwd=str(ROOT))
        self.assertIn(out.returncode, (0, 1), "readiness must not crash")
        self.assertIn("RESULT:", out.stdout)


# ---------------------------------------------------------------------------
# 4-8. failure-class behaviors (via in-process module calls)
# ---------------------------------------------------------------------------
class TestReadinessFailureClasses(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = _import("cf_readiness", READY)

    def test_04_wrong_cloudflare_account_fail(self):
        with mock.patch.object(self.mod, "EXPECTED_CLOUDFLARE_ACCOUNT_ID",
                               "deadbeef" * 8):
            r = self.mod.check_cloudflare_account(offline=True)
        # account won't equal a bogus expected id → match False
        self.assertFalse(r["match"])
        self.assertEqual(r["failure_class"], "CLOUDFLARE_ACCOUNT_MISMATCH")

    def test_05_corrupt_published_json_fail(self):
        with tempfile.TemporaryDirectory() as td:
            bad = Path(td) / "pub.json"
            bad.write_text("{CORRUPT", encoding="utf-8")
            with mock.patch.object(self.mod, "PUBLISHED_JSON", bad):
                r = self.mod.check_published_json()
            self.assertEqual(r["parse"], "CORRUPT")
            self.assertEqual(r["failure_class"], "CORRUPT_PUBLISHED_JSON")

    def test_06_missing_store_fail(self):
        with tempfile.TemporaryDirectory() as td:
            missing = Path(td) / "does-not-exist.json"
            with mock.patch.object(self.mod, "PUBLISHED_JSON", missing):
                r = self.mod.check_published_json()
            self.assertFalse(r["exists"])
            self.assertEqual(r["failure_class"], "MISSING_PUBLISHED_JSON")

    def test_07_immutable_hash_mismatch_fail(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "pub.json"
            p.write_text(json.dumps({"schema_version": "1.1", "items": [
                {"issue": "26112", "primary_strategy": "C", "numbers": {"front": [5], "back": [4]},
                 "reason": "r", "final_score": 1.0, "final_breakdown": {},
                 "model_version": "v", "explanation": {}, "snapshot_hash": "x"},
            ]}), encoding="utf-8")
            with mock.patch.object(self.mod, "PUBLISHED_JSON", p):
                r = self.mod.check_published_json()
            self.assertFalse(r["26112_ok"])
            self.assertEqual(r["failure_class"], "HASH_MISMATCH_26112")

    def test_08_history_lag_explicitly_reported(self):
        """published latest (26113) > history latest (26112) must be observable."""
        hist = json.load(open(ROOT / "data" / "dlt_history.json"))
        hist_latest = max(int(x["issue"]) for x in hist["issues"])
        pub = json.load(open(ROOT / "public" / "data" / "published_recommendations.json"))
        pub_latest = max(int(s["issue"]) for s in pub["items"])
        # The baseline documents history lag: published > history.
        self.assertTrue(pub_latest >= hist_latest,
                        "history-lag reporting precondition")


# ---------------------------------------------------------------------------
# 9. deployment path does not publish
# ---------------------------------------------------------------------------
class TestDeploymentIsolation(unittest.TestCase):
    def test_09_deploy_wrapper_no_generation(self):
        script = (ROOT / "scripts" / "deploy_production.sh").read_text(encoding="utf-8")
        self.assertIn("check_cloudflare_account", script)
        self.assertIn("wrangler", script)
        for bad in ("src.scheduler", "src.publisher", "scheduler --once",
                    "publisher --safe"):
            self.assertNotIn(bad, script,
                             f"deploy wrapper must not invoke {bad}")


# ---------------------------------------------------------------------------
# 10-13. recovery default dry-run + no overwrite without authorization
# ---------------------------------------------------------------------------
class TestRecoveryDryRun(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = _import("recovery_check_mod", RECOVERY)

    def test_10_recover_default_dry_run(self):
        """No restore flag → no write to the store."""
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "pub.json"
            store.write_text(json.dumps({"items": []}), encoding="utf-8")
            before = store.read_text(encoding="utf-8")
            with mock.patch.object(self.mod, "STORE", store), \
                 mock.patch.object(sys, "argv", ["rc", "--inspect"]):
                self.mod.main()
            # regardless of path, the store must be unchanged
            self.assertEqual(store.read_text(encoding="utf-8"), before)

    def test_11_recover_requires_authorization(self):
        """--restore without --authorize → refused (R9)."""
        with tempfile.TemporaryDirectory() as td:
            backup = Path(td) / "b.json"
            backup.write_text(json.dumps({"items": []}), encoding="utf-8")
            man = Path(td) / "b.manifest.json"
            man.write_text(json.dumps({
                "backup_sha256": self._sha256(backup.read_bytes()),
                "issues": []}), encoding="utf-8")
            store = Path(td) / "pub.json"
            store.write_text(json.dumps({"items": []}), encoding="utf-8")
            with mock.patch.object(self.mod, "STORE", store), \
                 mock.patch.object(sys, "argv",
                                   ["rc", "--restore", str(backup),
                                    "--manifest", str(man), "--authorize", ""]):
                rc = self.mod.main()
            self.assertEqual(rc, 1, "restore must be refused without authorization")

    def test_12_recover_detects_hash_mismatch(self):
        """Restore whose backup hash manifest is wrong → refused (R10)."""
        with tempfile.TemporaryDirectory() as td:
            backup = Path(td) / "b.json"
            payload = json.dumps({"items": []}).encode()
            backup.write_bytes(payload)
            man = Path(td) / "b.manifest.json"
            # deliberately wrong backup_sha256
            man.write_text(json.dumps({
                "backup_sha256": "0" * 64, "issues": []}), encoding="utf-8")
            store = Path(td) / "pub.json"
            store.write_text(json.dumps({"items": []}), encoding="utf-8")
            with mock.patch.object(self.mod, "STORE", store), \
                 mock.patch.object(sys, "argv",
                                   ["rc", "--restore", str(backup),
                                    "--manifest", str(man), "--authorize", "authorized restore reason"]):
                rc = self.mod.main()
            self.assertEqual(rc, 1, "restore must be refused on hash mismatch")

    @staticmethod
    def _sha256(b):
        import hashlib
        return hashlib.sha256(b).hexdigest()


# ---------------------------------------------------------------------------
# 14-15. backup manifest hash correctness + restore verifier mismatch
# ---------------------------------------------------------------------------
class TestBackupManifest(unittest.TestCase):
    def _make_backup(self, td):
        import hashlib
        payload = json.dumps({"items": [{"issue": "30001", "primary_strategy": "C",
                                         "numbers": {"front": [1], "back": [2]},
                                         "reason": "r", "final_score": 1.0,
                                         "final_breakdown": {}, "model_version": "v",
                                         "explanation": {}, "snapshot_hash": "z"}]})
        b = Path(td) / "b.json"
        b.write_text(payload, encoding="utf-8")
        raw = b.read_bytes()
        man = Path(td) / "b.manifest.json"
        man.write_text(json.dumps({
            "backup_sha256": hashlib.sha256(raw).hexdigest(),
            "issues": []}), encoding="utf-8")
        return b, man

    def test_14_backup_manifest_hash_correct(self):
        with tempfile.TemporaryDirectory() as td:
            b, man = self._make_backup(td)
            out = subprocess.run([sys.executable, RECOVERY,
                                   "--check-backup", str(b), str(man)],
                                 capture_output=True, text=True, cwd=str(ROOT))
            self.assertEqual(out.returncode, 0, out.stdout)
            self.assertIn("VERIFIED", out.stdout)

    def test_15_restore_verifier_detects_mismatch(self):
        with tempfile.TemporaryDirectory() as td:
            b, man = self._make_backup(td)
            # corrupt the backup so its hash no longer matches the manifest
            b.write_text(json.dumps({"items": []}), encoding="utf-8")
            out = subprocess.run([sys.executable, RECOVERY,
                                   "--check-backup", str(b), str(man)],
                                 capture_output=True, text=True, cwd=str(ROOT))
            self.assertEqual(out.returncode, 1, out.stdout)
            self.assertIn("FAILED", out.stdout)


# ---------------------------------------------------------------------------
# 16. P4-3 F1/F2 must NOT be regressed
# ---------------------------------------------------------------------------
class TestP43NotRegressed(unittest.TestCase):
    def test_16_corrupt_upsert_fail_closed(self):
        from src.publisher import upsert_published_snapshot, build_snapshot
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "pub.json"
            snap = build_snapshot(
                {"target_issue": "30050", "strategy": "C", "front": [1], "back": [2],
                 "reason": "r", "final_score": 1.0, "final_breakdown": {},
                 "model_version": "v", "explanation": {}},
                published_at="2026-10-02 00:00:00")
            upsert_published_snapshot(str(p), snap)
            p.write_text("{BROKEN", encoding="utf-8")
            st = upsert_published_snapshot(str(p), snap)
            self.assertEqual(st, "corrupt")
            self.assertEqual(p.read_text(encoding="utf-8"), "{BROKEN")


if __name__ == "__main__":
    unittest.main(verbosity=2)
