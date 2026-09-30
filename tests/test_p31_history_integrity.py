"""P3-1 完整历史数据完整性契约测试（Python stdlib unittest，无外部依赖）。

运行： /opt/homebrew/bin/python3 -m unittest tests.test_p31_history_integrity -v

覆盖任务书 STEP 14 的 24 项（合成数据保证快速；重叠/哈希/快照不变性独立断言）。
"""
from __future__ import annotations

import json
import pathlib
import unittest

from src.evaluation import history_integrity as hi


def _rec(issue, date="2026-01-01", front=(1, 2, 3, 4, 5), back=(1, 2)):
    return {"issue": str(issue), "date": date, "front": list(front), "back": list(back)}


class TestNormalization(unittest.TestCase):
    """1-9: schema / exactly 5 front / 2 back / range / unique / issue / date。"""

    def test_valid_normalization(self):
        r = hi.normalize_record(_rec(26111))
        self.assertEqual(r["front"], [1, 2, 3, 4, 5])
        self.assertEqual(r["back"], [1, 2])
        self.assertEqual(r["issue"], "26111")

    def test_front_exactly_5(self):
        with self.assertRaises(ValueError):
            hi.normalize_record(_rec(26111, front=[1, 2, 3, 4]))

    def test_back_exactly_2(self):
        with self.assertRaises(ValueError):
            hi.normalize_record(_rec(26111, back=[1]))

    def test_front_range(self):
        with self.assertRaises(ValueError):
            hi.normalize_record(_rec(26111, front=[1, 2, 3, 4, 36]))

    def test_back_range(self):
        with self.assertRaises(ValueError):
            hi.normalize_record(_rec(26111, back=[1, 13]))

    def test_front_unique(self):
        with self.assertRaises(ValueError):
            hi.normalize_record(_rec(26111, front=[1, 1, 2, 3, 4]))

    def test_back_unique(self):
        with self.assertRaises(ValueError):
            hi.normalize_record(_rec(26111, back=[1, 1]))

    def test_issue_unique_format(self):
        with self.assertRaises(ValueError):
            hi.normalize_record(_rec("2611"))  # 4-digit invalid

    def test_date_parse(self):
        with self.assertRaises(ValueError):
            hi.normalize_record(_rec(26111, date="not-a-date"))
        r = hi.normalize_record(_rec(26111, date="2026-09-28"))
        self.assertEqual(r["date"], "2026-09-28")


class TestSortingAndDuplicates(unittest.TestCase):
    """10-12: sorting / duplicate detection / conflict detection。"""

    def test_temporal_sorting(self):
        recs = [_rec(26001), _rec(26002), _rec(26003)]
        ok, _ = hi.sort_temporal(sorted(recs, key=lambda r: r["issue"]))
        self.assertTrue(ok)

    def test_duplicate_detection(self):
        recs = [_rec(26001), _rec(26001), _rec(26002)]
        d = hi.classify_duplicates(recs)
        # 只记录出现 >1 次的 issue；26002 仅 1 次不计入
        self.assertEqual(d["duplicate_issues"], {"26001": 2})
        self.assertIn("26001", d["benign"])

    def test_conflicting_duplicate(self):
        recs = [_rec(26001, front=[1, 2, 3, 4, 5]),
                _rec(26001, front=[1, 2, 3, 4, 9])]
        d = hi.classify_duplicates(recs)
        self.assertEqual(len(d["conflict"]), 1)
        self.assertEqual(d["conflict"][0]["issue"], "26001")

    def test_dedupe_keeps_one(self):
        recs = [_rec(26001), _rec(26001), _rec(26002)]
        self.assertEqual(len(hi.dedupe(recs)), 2)


class TestContinuity(unittest.TestCase):
    """13-14: year transition + missing issue detection (real YYNNN, not int+1)。"""

    def test_year_transition_detected(self):
        recs = [hi.normalize_record(_rec(26365)), hi.normalize_record(_rec(27001))]
        c = hi.check_continuity(recs)
        self.assertTrue(any(t["from_year"] == 2026 and t["to_year"] == 2027
                            for t in c["year_transitions"]))

    def test_missing_issue_detection(self):
        # 26 年内 001,002,005 → 003,004 为候选缺失
        recs = [hi.normalize_record(_rec(26001)),
                hi.normalize_record(_rec(26002)),
                hi.normalize_record(_rec(26005))]
        c = hi.check_continuity(recs)
        self.assertTrue(any(c2["year"] == 2026 for c2 in c["missing_issue_candidates"]))

    def test_no_false_gap_on_int_plus_1_assumption(self):
        # 跨年假期/休市：不同年内不产生 missing（只按年内检测）
        recs = [hi.normalize_record(_rec(26360)), hi.normalize_record(_rec(27001))]
        c = hi.check_continuity(recs)
        # 2026 内 360 后无 361..；2027 内 001 前无
        years_with_missing = {m["year"] for m in c["missing_issue_candidates"]}
        self.assertNotIn(2027, years_with_missing)  # 2027 只有 001，无从判断缺口


class TestOverlap(unittest.TestCase):
    """16-18: current-1000 overlap exact numbers / dates。"""

    def test_overlap_exact_match(self):
        prod = [_rec(26100), _rec(26101)]
        full = [_rec(26099), _rec(26100), _rec(26101)]
        o = hi.overlap_with_production(full, prod)
        self.assertEqual(o["overlap_count"], 2)
        self.assertEqual(o["overlap_match_count"], 2)
        self.assertEqual(o["mismatches"], [])

    def test_overlap_mismatch_detected(self):
        prod = [_rec(26100, front=[1, 2, 3, 4, 5])]
        full = [_rec(26100, front=[1, 2, 3, 4, 9])]
        o = hi.overlap_with_production(full, prod)
        self.assertEqual(o["overlap_match_count"], 0)
        self.assertEqual(len(o["mismatches"]), 1)


class TestHashAndManifest(unittest.TestCase):
    """19-21: manifest count / deterministic hash / hash matches file。"""

    def _recs(self):
        return [hi.normalize_record(_rec(26001, front=[1, 2, 3, 4, 5])),
                hi.normalize_record(_rec(26002, front=[1, 2, 3, 4, 6]))]

    def test_hash_deterministic(self):
        h1 = hi.dataset_sha256(self._recs())
        h2 = hi.dataset_sha256(self._recs())
        self.assertEqual(h1, h2)
        self.assertEqual(len(h1), 64)

    def test_hash_order_independent(self):
        a = self._recs()
        b = list(reversed(a))
        self.assertEqual(hi.dataset_sha256(a), hi.dataset_sha256(b))

    def test_manifest_count(self):
        m = hi.build_manifest(source="500", secondary_source="none",
                              records=self._recs(), acquired_at="2026-09-30",
                              overlap={"overlap_count": 2, "overlap_match_count": 2},
                              duplicates={"duplicate_issues": {}, "conflict": []},
                              continuity={"missing_issue_candidates": []},
                              validation_status="PASS")
        self.assertEqual(m["draw_count"], 2)
        self.assertEqual(m["earliest_issue"], "26001")
        self.assertEqual(m["latest_issue"], "26002")

    def test_manifest_hash_matches(self):
        m = hi.build_manifest(source="500", secondary_source="none",
                              records=self._recs(), acquired_at="2026-09-30",
                              overlap={}, duplicates={}, continuity={},
                              validation_status="PASS")
        self.assertEqual(m["dataset_sha256"], hi.dataset_sha256(self._recs()))


class TestIntegrityInvariants(unittest.TestCase):
    """22-24: no production dataset mutation / cap unchanged / 26112 snapshot。"""

    def test_production_dataset_unchanged(self):
        root = pathlib.Path(__file__).resolve().parent.parent
        prod = json.loads((root / "data" / "dlt_history.json").read_text())
        self.assertIn("issues", prod)
        self.assertEqual(len(prod["issues"]), 1000)  # production 1000 cap 仍在

    def test_production_cap_unchanged(self):
        root = pathlib.Path(__file__).resolve().parent.parent
        txt = (root / "config" / "settings.yaml").read_text()
        # recent_issues 仍在 scrape 段且为 1000（文本级校验，避免 yaml 依赖）
        import re
        m = re.search(r"recent_issues:\s*(\d+)", txt)
        self.assertIsNotNone(m)
        self.assertEqual(int(m.group(1)), 1000)

    def test_26112_snapshot_unchanged(self):
        root = pathlib.Path(__file__).resolve().parent.parent
        pub = json.loads((root / "public" / "data" / "published_recommendations.json").read_text())
        it = next(x for x in pub["items"] if x["issue"] == "26112")
        self.assertEqual(it["snapshot_hash"],
                         "bea8ef87f3f137238686ae52712f922956215408f0cf54187b9295d8f1ae5fad")


if __name__ == "__main__":
    unittest.main()
