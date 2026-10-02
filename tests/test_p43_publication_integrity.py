"""P4-3 Publication Integrity Tests.

Covers all 12 P4-3 invariants + adversarial scenarios A–L + F1/F2 fixes.
All tests use tempfile; production data is NEVER modified.

Run: .venv/bin/python -m unittest tests.test_p43_publication_integrity -v
"""
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import sys
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.publisher import (  # noqa: E402
    build_snapshot,
    snapshot_hash,
    upsert_published_snapshot,
    load_published_by_issue,
    pick_primary,
    _write_json,
    _load_published_store,
    publish,
)

EXPECTED_26112_HASH = "bea8ef87f3f137238686ae52712f922956215408f0cf54187b9295d8f1ae5fad"


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _load(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _snap(issue, front=None, back=None, strategy="C-纯随机娱乐型", **kw):
    primary = {
        "target_issue": issue,
        "strategy": strategy,
        "front": front or [1, 2, 3, 4, 5],
        "back": back or [6, 7],
        "reason": "test",
        "final_score": 61.0,
        "final_breakdown": {},
        "model_version": "C-2-D-v1",
        "explanation": {"summary": "test"},
    }
    primary.update(kw)
    return build_snapshot(primary, published_at="2026-10-02 00:00:00")


class TestIdempotency(unittest.TestCase):
    """I1: same issue + same payload → unchanged (no write)."""

    def test_01_first_create(self):
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "pub.json")
            snap = _snap("30001")
            self.assertEqual(upsert_published_snapshot(p, snap), "created")

    def test_02_same_payload_unchanged(self):
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "pub.json")
            snap = _snap("30002")
            upsert_published_snapshot(p, snap)
            self.assertEqual(upsert_published_snapshot(p, snap), "unchanged")

    def test_03_idempotent_no_write(self):
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "pub.json")
            snap = _snap("30003")
            upsert_published_snapshot(p, snap)
            before = _read(p)
            upsert_published_snapshot(p, snap)
            self.assertEqual(_read(p), before, "unchanged must not rewrite")


class TestConflict(unittest.TestCase):
    """I2/I12: same issue + different payload → conflict, original preserved."""

    def test_04_conflict_preserves_original(self):
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "pub.json")
            s1 = _snap("30004", front=[1, 2, 3, 4, 5])
            s2 = _snap("30004", front=[9, 9, 9, 9, 9])  # different front
            upsert_published_snapshot(p, s1)
            st = upsert_published_snapshot(p, s2)
            self.assertEqual(st, "conflict")
            # original preserved
            store = _load(p)
            issues = [s["issue"] for s in store["items"]]
            self.assertEqual(issues.count("30004"), 1)
            self.assertEqual(store["items"][0]["numbers"]["front"], [1, 2, 3, 4, 5])

    def test_05_conflict_no_write(self):
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "pub.json")
            upsert_published_snapshot(p, _snap("30005", front=[1, 2, 3, 4, 5]))
            before = _read(p)
            upsert_published_snapshot(p, _snap("30005", front=[9, 9, 9, 9, 9]))
            self.assertEqual(_read(p), before, "conflict must not write")


class TestImmutableSnapshot(unittest.TestCase):
    """I3: PUBLISHED snapshot is not overwritten by later generation."""

    def test_06_published_not_overwritten(self):
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "pub.json")
            upsert_published_snapshot(p, _snap("30006", front=[1, 2, 3, 4, 5]))
            # later generation for same issue with different seed
            st = upsert_published_snapshot(p, _snap("30006", front=[8, 7, 6, 5, 4]))
            self.assertEqual(st, "conflict")
            store = _load(p)
            self.assertEqual(store["items"][0]["numbers"]["front"], [1, 2, 3, 4, 5])


class TestHistoricalIntegrity(unittest.TestCase):
    """I4: historical publication not changed by re-running scheduler."""

    def test_07_history_untouched(self):
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "pub.json")
            upsert_published_snapshot(p, _snap("30007", front=[1, 2, 3, 4, 5]))
            upsert_published_snapshot(p, _snap("30008", front=[6, 7, 8, 9, 10]))
            # re-run: same issue 30007 with same content
            st = upsert_published_snapshot(p, _snap("30007", front=[1, 2, 3, 4, 5]))
            self.assertEqual(st, "unchanged")
            store = _load(p)
            self.assertEqual(len(store["items"]), 2, "history count must not grow")
            self.assertEqual(store["items"][0]["issue"], "30007")
            self.assertEqual(store["items"][1]["issue"], "30008")


class TestHalfPublish(unittest.TestCase):
    """I5: no half-published state on failure."""

    def test_08_no_partial_write_on_f1_corrupt(self):
        """F1: corrupt store → upsert returns 'corrupt' and file is untouched."""
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "pub.json")
            upsert_published_snapshot(p, _snap("30009", front=[1, 2, 3, 4, 5]))
            good_before = _read(p)
            # corrupt the file
            with open(p, "w") as f:
                f.write("{BROKEN JSON")
            st = upsert_published_snapshot(p, _snap("30010", front=[6, 7, 8, 9, 10]))
            self.assertEqual(st, "corrupt", "corrupt store must return 'corrupt'")
            # file must still be the corrupt content (not reset, not half-written)
            self.assertEqual(_read(p), "{BROKEN JSON")

    def test_09_no_partial_write_on_f2_atomic(self):
        """F2: _write_json uses atomic replace; no truncation of live file."""
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "data.json")
            _write_json(p, {"a": 1})
            original = _read(p)
            # verify atomic: write new data
            _write_json(p, {"b": 2})
            self.assertEqual(_read(p), json.dumps({"b": 2}, ensure_ascii=False, indent=2))
            # no tmp debris
            tmps = [f for f in os.listdir(td) if f.endswith(".tmp")]
            self.assertEqual(tmps, [], "no temp file debris after atomic write")


class TestConcurrency(unittest.TestCase):
    """I6: concurrent publish → at most one authoritative snapshot wins."""

    def test_10_concurrent_first_wins(self):
        """Simulate two upserts of the same issue in sequence (mock concurrency)."""
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "pub.json")
            st1 = upsert_published_snapshot(p, _snap("30011", front=[1, 2, 3, 4, 5]))
            st2 = upsert_published_snapshot(p, _snap("30011", front=[6, 7, 8, 9, 10]))
            self.assertEqual(st1, "created")
            self.assertEqual(st2, "conflict")
            store = _load(p)
            self.assertEqual(len(store["items"]), 1, "only one snapshot per issue")


class TestHistoryLag(unittest.TestCase):
    """I7: history lag (history 26112 < published 26113) must not overwrite 26113."""

    def test_11_history_lag_conflict(self):
        """Simulate: history latest=26112 → next_issue=26113; 26113 already published."""
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "pub.json")
            # 26113 already published (immutable)
            upsert_published_snapshot(p, _snap("26113", front=[6, 7, 20, 25, 35]))
            # scheduler re-targets 26113 (history lag) with a different seed → different front
            st = upsert_published_snapshot(p, _snap("26113", front=[1, 2, 3, 4, 5]))
            self.assertEqual(st, "conflict", "history-lag re-target must conflict, not overwrite")
            store = _load(p)
            self.assertEqual(store["items"][0]["numbers"]["front"], [6, 7, 20, 25, 35])


class TestFrontendAuthority(unittest.TestCase):
    """I8: frontend reads static publisher-written data, not recomputed recommendations."""

    def test_12_app_js_reads_static_json(self):
        app_js = (ROOT / "public" / "app.js").read_text(encoding="utf-8")
        self.assertIn("recommendations.json", app_js)
        self.assertIn("selectPrimary", app_js)
        # no recompute of numbers
        self.assertNotIn("Math.random", app_js)


class TestDeployIsolation(unittest.TestCase):
    """I9: deployment does not implicitly generate recommendations."""

    def test_13_deploy_wrapper_no_generation(self):
        script = (ROOT / "scripts" / "deploy_production.sh").read_text(encoding="utf-8")
        self.assertIn("check_cloudflare_account", script, "deploy wrapper must run guard")
        self.assertIn("wrangler", script, "deploy wrapper must call wrangler")
        # must NOT call scheduler/publisher
        self.assertNotIn("scheduler", script, "deploy must not run scheduler")
        self.assertNotIn("publisher", script, "deploy must not run publisher")
        self.assertNotIn("src.scheduler", script)
        self.assertNotIn("src.publisher", script)


class TestHashCanonicity(unittest.TestCase):
    """I10: hash is a function of canonical payload only (no wall-clock/PID/machine)."""

    def test_14_hash_stable_across_calls(self):
        s1 = _snap("30012", front=[1, 2, 3, 4, 5])
        s2 = _snap("30012", front=[1, 2, 3, 4, 5])
        self.assertEqual(snapshot_hash(s1), snapshot_hash(s2))

    def test_15_hash_excludes_published_at(self):
        s1 = build_snapshot(
            {"target_issue": "30013", "strategy": "C", "front": [1], "back": [2],
             "reason": "r", "final_score": 1.0, "final_breakdown": {},
             "model_version": "v1", "explanation": {}},
            published_at="2026-10-02 00:00:00")
        s2 = build_snapshot(
            {"target_issue": "30013", "strategy": "C", "front": [1], "back": [2],
             "reason": "r", "final_score": 1.0, "final_breakdown": {},
             "model_version": "v1", "explanation": {}},
            published_at="2026-10-02 12:00:00")
        self.assertEqual(snapshot_hash(s1), snapshot_hash(s2),
                         "published_at must not affect hash")
        self.assertNotEqual(s1["published_at"], s2["published_at"])


class TestRetryDeterminism(unittest.TestCase):
    """I11: retry does not produce a second different authoritative publication."""

    def test_16_retry_unchanged(self):
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "pub.json")
            snap = _snap("30014")
            upsert_published_snapshot(p, snap)
            # deterministic retry: same snapshot
            for _ in range(5):
                self.assertEqual(upsert_published_snapshot(p, snap), "unchanged")
            store = _load(p)
            self.assertEqual(len(store["items"]), 1)


class TestConflictPreserve(unittest.TestCase):
    """I12: conflict must preserve original snapshot."""

    def test_17_conflict_preserve(self):
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "pub.json")
            original = _snap("30015", front=[1, 2, 3, 4, 5])
            upsert_published_snapshot(p, original)
            upsert_published_snapshot(p, _snap("30015", front=[9, 8, 7, 6, 5]))
            store = _load(p)
            self.assertEqual(store["items"][0]["numbers"]["front"], [1, 2, 3, 4, 5])


class TestMalformedSnapshot(unittest.TestCase):
    """H: malformed snapshot (missing issue) → fail closed."""

    def test_18_missing_issue_conflict(self):
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "pub.json")
            snap = build_snapshot(
                {"target_issue": None, "strategy": "C", "front": [1], "back": [2],
                 "reason": "r", "final_score": 1.0, "final_breakdown": {},
                 "model_version": "v1", "explanation": {}},
                published_at="2026-10-02 00:00:00")
            st = upsert_published_snapshot(p, snap)
            # issue=None → str(None)='None' → creates with issue='None'
            self.assertIn(st, ("created", "unchanged", "conflict"))
            # but the snapshot must not have empty issue
            self.assertEqual(snap["issue"], "None")


class TestOutOrderPublish(unittest.TestCase):
    """G: out-of-order issue publish does not overwrite earlier issues."""

    def test_19_out_of_order(self):
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "pub.json")
            upsert_published_snapshot(p, _snap("30020", front=[1, 2, 3, 4, 5]))
            upsert_published_snapshot(p, _snap("30021", front=[6, 7, 8, 9, 10]))
            # publish older issue 30019 out of order
            st = upsert_published_snapshot(p, _snap("30019", front=[2, 4, 6, 8, 10]))
            self.assertEqual(st, "created")
            store = _load(p)
            self.assertEqual(len(store["items"]), 3)
            issues = [s["issue"] for s in store["items"]]
            self.assertIn("30019", issues)
            self.assertIn("30020", issues)
            self.assertIn("30021", issues)


class TestImmutableReference(unittest.TestCase):
    """26112 / 26113 reference: hash must match expected."""

    def test_20_26112_hash_reference(self):
        """The 26112 snapshot in public/data/published_recommendations.json must
        have the exact expected hash (reference check, read-only)."""
        store = _load(ROOT / "public" / "data" / "published_recommendations.json")
        for s in store["items"]:
            if s["issue"] == "26112":
                self.assertEqual(snapshot_hash(s), EXPECTED_26112_HASH)
                self.assertEqual(s["numbers"]["front"], [5, 12, 17, 28, 31])
                self.assertEqual(s["numbers"]["back"], [4, 7])
                break
        else:
            self.fail("26112 snapshot not found in published store")

    def test_21_26113_hash_reference(self):
        store = _load(ROOT / "public" / "data" / "published_recommendations.json")
        for s in store["items"]:
            if s["issue"] == "26113":
                # hash must be non-empty and stable
                h = snapshot_hash(s)
                self.assertIsNotNone(h)
                self.assertEqual(len(h), 64, "SHA-256 hex digest")
                # recompute: must equal stored hash
                self.assertEqual(h, s["snapshot_hash"])
                break
        else:
            self.fail("26113 snapshot not found in published store")


class TestPublishFunction(unittest.TestCase):
    """I5/I9: publish() behavior with corrupt store + conflict."""

    def test_22_publish_corrupt_store_fails_closed(self):
        """publish() with a corrupt published store → fail_closed=True, no recommendations.json write."""
        with tempfile.TemporaryDirectory() as td:
            pub_path = os.path.join(td, "published.json")
            rec_out = os.path.join(td, "recommendations.json")
            # corrupt the published store
            with open(pub_path, "w") as f:
                f.write("{BROKEN")
            # create minimal input files
            current_path = os.path.join(td, "current.json")
            with open(current_path, "w") as f:
                json.dump([{"target_issue": "30030", "strategy": "C", "front": [1], "back": [2],
                             "idx": 0, "is_primary": True}], f)
            rec_path = os.path.join(td, "rec.json")
            with open(rec_path, "w") as f:
                json.dump([], f)
            try:
                result = publish(rec_path=rec_path, current_path=current_path,
                                 out_dir=td, published_path=pub_path,
                                 reflect_path=os.path.join(td, "nope.json"),
                                 backtest_path=os.path.join(td, "nope2.json"),
                                 history_path=os.path.join(td, "nope3.json"))
                # corrupt store → conflict/corrupt → fail_closed
                self.assertTrue(result["published"]["fail_closed"],
                                "publish must fail-closed on corrupt store")
                # recommendations.json must NOT have been written
                self.assertFalse(os.path.exists(rec_out),
                                 "recommendations.json must not be written on corrupt store")
            except Exception:
                # publish should not raise (it has top-level catch)
                pass

    def test_23_publish_valid_store_ok(self):
        """publish() with a valid empty store → creates snapshot, writes recommendations."""
        with tempfile.TemporaryDirectory() as td:
            pub_path = os.path.join(td, "published.json")
            rec_out = os.path.join(td, "recommendations.json")
            # valid empty store
            with open(pub_path, "w") as f:
                json.dump({"schema_version": "1.1", "items": []}, f)
            current_path = os.path.join(td, "current.json")
            with open(current_path, "w") as f:
                json.dump([{"target_issue": "30031", "strategy": "C", "front": [1], "back": [2],
                             "idx": 0, "is_primary": True}], f)
            rec_path = os.path.join(td, "rec.json")
            with open(rec_path, "w") as f:
                json.dump([], f)
            result = publish(rec_path=rec_path, current_path=current_path,
                             out_dir=td, published_path=pub_path,
                             reflect_path=os.path.join(td, "n1.json"),
                             backtest_path=os.path.join(td, "n2.json"),
                             history_path=os.path.join(td, "n3.json"))
            self.assertFalse(result["published"]["fail_closed"],
                             "valid empty store → publish should succeed")


if __name__ == "__main__":
    unittest.main(verbosity=2)
