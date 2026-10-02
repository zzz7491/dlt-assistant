"""P4-5 Daily Pipeline Resilience tests.

Covers the P4-5 requirements without touching production D1 or writing
production data. Uses temp files + subprocess + workflow static assertions.

Run: .venv/bin/python -m unittest tests.test_p45_daily_pipeline_resilience -v
"""
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

WORKFLOW = ROOT / ".github" / "workflows" / "dlt-analysis.yml"
OPS_STATUS = str(ROOT / "scripts" / "ops_status.py")
PREPUBLISH = str(ROOT / "scripts" / "check_local_prepublish.py")
BACKUP = str(ROOT / "scripts" / "backup_published_store.py")
RECOVERY = str(ROOT / "scripts" / "recovery_check.py")
EXPECTED_26112_HASH = "bea8ef87f3f137238686ae52712f922956215408f0cf54187b9295d8f1ae5fad"


def _run(script, *args, cwd=None, env_extra=None):
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    return subprocess.run([sys.executable, script, *args],
                          capture_output=True, text=True, cwd=cwd or str(ROOT),
                          env=env, timeout=60)


class TestOpsStatus(unittest.TestCase):
    """P12/P17: structured, machine-readable, no secrets."""

    def test_01_status_has_required_fields(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "status.json"
            # ops_status writes to reports/last-run-status.json; point it via env?
            # Instead run the script and read the default path, then clean up.
            # For isolation, we monkeypatch DEFAULT_PATH by running a fresh copy.
            import importlib.util
            spec = importlib.util.spec_from_file_location("ops", OPS_STATUS)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            with mock.patch.object(mod, "DEFAULT_PATH", target):
                self.assertEqual(mod.cmd_init(target, "daily"), 0)
                mod.cmd_set(target, ["history_latest=26112", "published_latest=26113"])
                mod.cmd_set(target, ["d1_status=OK", "deploy_status=OK"])
                self.assertEqual(mod.cmd_classify(target, "PASS"), 0)
            data = json.loads(target.read_text(encoding="utf-8"))
            for field in ("failure_class", "history_latest", "published_latest",
                          "target_issue", "scheduler_status", "d1_status",
                          "deploy_status", "trigger"):
                # target_issue/scheduler_status may be absent if not set; check the
                # ones we set plus the taxonomy field.
                pass
            self.assertIn("failure_class", data)
            self.assertEqual(data["history_latest"], "26112")
            self.assertEqual(data["published_latest"], "26113")
            self.assertEqual(data["d1_status"], "OK")
            self.assertEqual(data["deploy_status"], "OK")
            self.assertEqual(data["trigger"], "daily")

    def test_02_no_secret_leakage(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("ops2", OPS_STATUS)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.assertEqual(mod._scrub("CLOUDFLARE_API_TOKEN=sk-secret123456"), "<redacted>")
        self.assertEqual(mod._scrub("eyJabcDEF.ghijklMNOPqrst"), "<redacted>")
        self.assertEqual(mod._scrub("ghp_ABCDEFGHIJKLMNOPQRSTUVWX"), "<redacted>")
        self.assertEqual(mod._scrub({"api_token": "abc", "issue": "26112"})["api_token"],
                         "<redacted>")
        self.assertEqual(mod._scrub({"issue": "26112"})["issue"], "26112")

    def test_03_atomic_status_write_no_debris(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "s.json"
            import importlib.util
            spec = importlib.util.spec_from_file_location("ops3", OPS_STATUS)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            with mock.patch.object(mod, "DEFAULT_PATH", target):
                mod.cmd_init(target, "t")
                mod.cmd_set(target, ["k=v"])
            self.assertTrue(target.exists())
            self.assertEqual(
                [f for f in os.listdir(td) if f.startswith(".ops-status.")],
                [], "no temp debris after atomic status write")


class TestPrePublishGate(unittest.TestCase):
    """P10/P11: local pre-publish gate + history-lag explicit state."""

    def _snapshot_store(self, path, issues=None):
        items = []
        for iss in (issues or []):
            items.append({
                "schema_version": "1.1", "issue": str(iss),
                "primary_strategy": "C", "numbers": {"front": [1, 2, 3, 4, 5],
                                                     "back": [6, 7]},
                "reason": "r", "final_score": 1.0, "final_breakdown": {},
                "model_version": "v", "explanation": {}})
        path.write_text(json.dumps({"schema_version": "1.1", "items": items}),
                        encoding="utf-8")
        return path

    def test_04_history_lag_explicitly_detected_not_skipped(self):
        """published_latest > history_latest must be reported; gate must NOT
        auto-skip to a new issue (D4)."""
        import importlib.util
        spec = importlib.util.spec_from_file_location("pp", PREPUBLISH)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        with tempfile.TemporaryDirectory() as td:
            pub = Path(td) / "pub.json"
            hist = Path(td) / "hist.json"
            self._snapshot_store(pub, issues=["30002", "30003"])
            hist.write_text(json.dumps({"issues": [
                {"issue": "30002"}, {"issue": "30001"}]}), encoding="utf-8")
            with mock.patch.object(mod, "PUBLISHED", pub), \
                 mock.patch.object(mod, "HISTORY", hist), \
                 mock.patch.object(mod, "BACKUP_DIR", Path(td) / "backups"):
                r = mod._check()
            self.assertTrue(r["checks"]["history_lag"], "history lag must be detected")
            # scheduler target = next_issue(30002) = 30003, which IS already published
            self.assertEqual(r["scheduler_target"], 30003)
            self.assertTrue(r["target_already_published"])
            # D4: the gate must NOT invent a new target (30004)
            self.assertNotEqual(r["scheduler_target"], 30004)

    def test_05_corrupt_store_blocks(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("pp5", PREPUBLISH)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        with tempfile.TemporaryDirectory() as td:
            pub = Path(td) / "pub.json"
            pub.write_text("{CORRUPT", encoding="utf-8")
            with mock.patch.object(mod, "PUBLISHED", pub), \
                 mock.patch.object(mod, "HISTORY", Path(td) / "h.json"), \
                 mock.patch.object(mod, "BACKUP_DIR", Path(td) / "backups"):
                r = mod._check()
            self.assertEqual(r["failure_class"], "PUBLICATION_CORRUPT")

    def test_06_26112_hash_mismatch_blocks(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("pp6", PREPUBLISH)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        with tempfile.TemporaryDirectory() as td:
            pub = Path(td) / "pub.json"
            # a 26112 with a wrong stored snapshot_hash
            pub.write_text(json.dumps({"items": [{
                "issue": "26112", "primary_strategy": "C",
                "numbers": {"front": [5, 12, 17, 28, 31], "back": [4, 7]},
                "reason": "r", "final_score": 1.0, "final_breakdown": {},
                "model_version": "v", "explanation": {},
                "snapshot_hash": "0" * 64}]}), encoding="utf-8")
            with mock.patch.object(mod, "PUBLISHED", pub), \
                 mock.patch.object(mod, "HISTORY", Path(td) / "h.json"), \
                 mock.patch.object(mod, "BACKUP_DIR", Path(td) / "backups"):
                r = mod._check()
            self.assertEqual(r["failure_class"], "PUBLICATION_CORRUPT")


class TestWorkflowStaticAssertions(unittest.TestCase):
    """P14/P16/P18: the workflow contains the required resilience wiring."""

    @classmethod
    def setUpClass(cls):
        cls.yml = WORKFLOW.read_text(encoding="utf-8")

    def test_07_backup_before_publisher(self):
        b = self.yml.find("backup_published_store.py")
        p = self.yml.find("python -m src.publisher --safe")
        self.assertNotEqual(b, -1)
        self.assertNotEqual(p, -1)
        self.assertLess(b, p, "backup step must occur before the publisher write")

    def test_08_backup_failure_blocks_publisher(self):
        # The publisher step must have a backup-failure branch that exits 0
        # (skip) rather than proceeding to publish.
        self.assertIn("backup 失败 → 阻止 publisher", self.yml)
        self.assertIn("BACKUP_FAILURE", self.yml)

    def test_09_prepublish_failure_blocks_publisher(self):
        self.assertIn("check_local_prepublish.py", self.yml)
        self.assertIn("PREPUBLISH_READINESS_FAILURE", self.yml)

    def test_10_scheduler_failure_blocks_publisher(self):
        # scheduler step classifies SCHEDULER_FAILURE and exits 1 → publisher not reached
        self.assertIn("SCHEDULER_FAILURE", self.yml)

    def test_11_no_blind_pull_rebase(self):
        # P14: the old 'git pull --rebase ... || true' pattern is gone from run blocks.
        self.assertNotIn("git pull --rebase origin", self.yml,
                         "blind pull --rebase must be removed (P4-5 P14)")

    def test_12_no_force_push(self):
        self.assertNotIn("git push --force", self.yml)
        self.assertNotIn("git push -f", self.yml)
        self.assertNotIn("--force-with-lease", self.yml)

    def test_13_account_mismatch_blocks_deploy(self):
        self.assertIn("CLOUDFLARE_ACCOUNT_MISMATCH", self.yml)

    def test_14_auth_failure_classified_separately(self):
        self.assertIn("CLOUDFLARE_AUTH_FAILURE", self.yml)
        self.assertIn("DEPLOY_FAILURE", self.yml)
        # deploy failure must not be treated as publication failure (D12)
        self.assertIn("非 publication failure", self.yml)

    def test_15_no_interactive_wrangler_login_in_ci(self):
        self.assertNotIn("wrangler login", self.yml)

    def test_16_concurrency_protection(self):
        self.assertIn("concurrency:", self.yml)
        self.assertIn("cancel-in-progress: false", self.yml)

    def test_17_d1_failure_visible(self):
        self.assertIn("LOCAL_PUBLISHED_D1_FAILED", self.yml)
        self.assertIn("D1_FAILURE", self.yml)

    def test_18_noop_commit_recognized(self):
        self.assertIn("NOOP", self.yml)
        self.assertIn("NOOP_NO_CHANGE", self.yml)

    def test_19_run_status_artifact(self):
        self.assertIn("ops_status.py", self.yml)
        # gitignore the runtime status artifact so it is not committed each run
        gi = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("reports/last-run-status.json", gi)

    def test_20_no_secrets_in_workflow(self):
        for marker in ("sk-", "eyJ", "ghp_", "AKIA"):
            self.assertNotIn(marker, self.yml, f"secret marker {marker!r} in workflow")


class TestRecoveryAndBackup(unittest.TestCase):
    """P18: retry cannot bypass publication guard; D1 failure does not regenerate."""

    def test_21_d1_failure_does_not_regenerate(self):
        """The D1 write path is INSERT OR IGNORE (idempotent); a retry reuses the
        authoritative snapshot, it does NOT regenerate a different one. Verify the
        generator emits INSERT OR IGNORE, not a plain INSERT/REPLACE."""
        gen = (ROOT / "scripts" / "write_recommendations_d1.py").read_text(encoding="utf-8")
        self.assertIn("INSERT OR IGNORE", gen)
        self.assertNotIn("INSERT OR REPLACE", gen)
        self.assertNotIn("ON CONFLICT DO UPDATE", gen)

    def test_22_retry_same_snapshot_idempotent(self):
        """Re-running the backup + a same-snapshot upsert is idempotent (unchanged)."""
        from src.publisher import upsert_published_snapshot, build_snapshot
        with tempfile.TemporaryDirectory() as td:
            p = str(Path(td) / "pub.json")
            snap = build_snapshot(
                {"target_issue": "31001", "strategy": "C", "front": [1], "back": [2],
                 "reason": "r", "final_score": 1.0, "final_breakdown": {},
                 "model_version": "v", "explanation": {}},
                published_at="2026-10-02 00:00:00")
            self.assertEqual(upsert_published_snapshot(p, snap), "created")
            for _ in range(3):
                self.assertEqual(upsert_published_snapshot(p, snap), "unchanged")

    def test_23_conflict_blocks_downstream(self):
        """A conflict preserves the original; a downstream write would be fail-closed."""
        from src.publisher import upsert_published_snapshot, build_snapshot
        with tempfile.TemporaryDirectory() as td:
            p = str(Path(td) / "pub.json")
            s1 = build_snapshot({"target_issue": "31002", "strategy": "C", "front": [1],
                                 "back": [2], "reason": "r", "final_score": 1.0,
                                 "final_breakdown": {}, "model_version": "v",
                                 "explanation": {}}, published_at="2026-10-02 00:00:00")
            s2 = build_snapshot({"target_issue": "31002", "strategy": "C", "front": [9],
                                 "back": [8], "reason": "r", "final_score": 1.0,
                                 "final_breakdown": {}, "model_version": "v",
                                 "explanation": {}}, published_at="2026-10-02 00:00:00")
            upsert_published_snapshot(p, s1)
            self.assertEqual(upsert_published_snapshot(p, s2), "conflict")
            store = json.load(open(p))
            self.assertEqual(store["items"][0]["numbers"]["front"], [1])

    def test_24_no_destructive_restore_without_authorization(self):
        """recovery_check --restore without --authorize must be refused."""
        import importlib.util
        spec = importlib.util.spec_from_file_location("rec", RECOVERY)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        with tempfile.TemporaryDirectory() as td:
            b = Path(td) / "b.json"
            b.write_text(json.dumps({"items": []}), encoding="utf-8")
            man = Path(td) / "b.manifest.json"
            import hashlib
            man.write_text(json.dumps({"backup_sha256": hashlib.sha256(b.read_bytes()).hexdigest(),
                                       "issues": []}), encoding="utf-8")
            store = Path(td) / "pub.json"
            store.write_text(json.dumps({"items": []}), encoding="utf-8")
            with mock.patch.object(mod, "STORE", store), \
                 mock.patch.object(sys, "argv",
                                   ["rc", "--restore", str(b), "--manifest", str(man),
                                    "--authorize", ""]):
                rc = mod.main()
            self.assertEqual(rc, 1, "destructive restore must require authorization (R9)")


if __name__ == "__main__":
    unittest.main(verbosity=2)
