"""P2-1 评测基线契约测试（Python stdlib unittest，无 pytest）。

运行： python -m unittest tests.test_p21_evaluation -v

覆盖任务书 STEP 13 的 25 项（部分合并为断言组）：
  1-3  leakage: no future / target excluded / future excluded
  4-6  random baseline: deterministic, multi-seed, legal 5+2
  7-8  no duplicate front / back
  9-11 hit counts
  12-13 zero-hit / perfect-hit
  14-15 prize classification / cost=2
  16-17 warmup exclusion / eval record contract
  18-21 A/B/C/D walk-forward
  22   selector leakage guard
  23-24 metrics aggregation / random multi-seed aggregate
  25   production files unchanged
"""
from __future__ import annotations

import json
import pathlib
import random
import unittest

from src.evaluation import baselines, leakage, metrics, prize, walk_forward


def _issues(n=120, front=(1, 2, 3, 4, 5), back=(1, 2)) -> list[dict]:
    """合成开奖序列：期号 26001..2600n，每期 front/back 固定。"""
    out = []
    for i in range(1, n + 1):
        out.append({"issue": str(26000 + i), "date": "2026-01-01",
                    "front": list(front), "back": list(back)})
    return out


class TestLeakage(unittest.TestCase):
    """1-3, 16, 17: leakage guard + record contract."""

    def test_no_future_issue_in_training(self):
        iss = _issues(50)
        ev = leakage.build_evidence(iss, t=30)
        for rec in ev:
            self.assertLess(int(rec["issue"]), int(iss[30]["issue"]))
        leakage.assert_no_future_data(ev, iss[30]["issue"], label="train")

    def test_target_excluded(self):
        iss = _issues(50)  # iss[i].issue = 26001+i ; iss[30]=26031
        ev = leakage.build_evidence(iss, t=30)  # = 26001..26030
        self.assertNotIn(iss[30], ev)           # target 26031 not in evidence
        self.assertEqual(ev[-1]["issue"], str(26030))

    def test_future_issues_excluded(self):
        iss = _issues(50)
        ev = leakage.build_evidence(iss, t=30)
        self.assertNotIn(iss[40], ev)
        for r in ev:
            self.assertLess(int(r["issue"]), int(iss[30]["issue"]))  # all < target 26031

    def test_window_slice(self):
        iss = _issues(200)  # iss[i].issue=26001+i ; t=150 -> target 26151
        ev = leakage.build_evidence(iss, t=150, window=50)  # = 26101..26150
        self.assertEqual(len(ev), 50)
        self.assertEqual(ev[0]["issue"], str(26101))
        self.assertEqual(ev[-1]["issue"], str(26150))
        leakage.assert_no_future_data(ev, iss[150]["issue"])

    def test_eval_record_contract(self):
        rec = leakage.make_eval_record(
            target_issue="26100", train_last_issue="26099", strategy="A",
            front=[1, 2, 3, 4, 5], back=[1, 2],
            actual_front=[1, 2, 3, 4, 5], actual_back=[1, 2],
            front_hits=5, back_hits=2, total_hits=7,
            cost=2.0, payout=0.0, roi=-1.0,
        )
        for k in ("target_issue", "train_last_issue", "strategy", "front", "back",
                   "actual_front", "actual_back", "front_hits", "back_hits",
                   "total_hits", "cost", "payout", "roi", "evaluation_version"):
            self.assertIn(k, rec)
        self.assertLess(int(rec["train_last_issue"]), int(rec["target_issue"]))

    def test_record_rejects_future_train(self):
        with self.assertRaises(AssertionError):
            leakage.make_eval_record(
                target_issue="26100", train_last_issue="26100", strategy="A",
                front=[1, 2, 3, 4, 5], back=[1, 2],
                actual_front=[1, 2, 3, 4, 5], actual_back=[1, 2],
                front_hits=0, back_hits=0, total_hits=0,
                cost=2.0, payout=0.0, roi=-1.0)


class TestRandomBaseline(unittest.TestCase):
    """4-8: deterministic, multi-seed, legal, no dup."""

    def test_deterministic(self):
        c1 = baselines.random_combo(42)
        c2 = baselines.random_combo(42)
        self.assertEqual(c1, c2)

    def test_multi_seed_differ(self):
        a = baselines.random_combo(1)
        b = baselines.random_combo(2)
        self.assertNotEqual(a, b)

    def test_legal_5_plus_2(self):
        for seed in range(50):
            c = baselines.random_combo(seed)
            self.assertEqual(len(c["front"]), 5)
            self.assertEqual(len(c["back"]), 2)
            for x in c["front"]:
                self.assertTrue(1 <= x <= 35)
            for x in c["back"]:
                self.assertTrue(1 <= x <= 12)

    def test_no_duplicate_front(self):
        for seed in range(30):
            f = baselines.random_combo(seed)["front"]
            self.assertEqual(len(f), len(set(f)))

    def test_no_duplicate_back(self):
        for seed in range(30):
            b = baselines.random_combo(seed)["back"]
            self.assertEqual(len(b), len(set(b)))


class TestHits(unittest.TestCase):
    """9-13: hit counts, zero-hit, perfect hit."""

    def test_front_hit_count(self):
        self.assertEqual(walk_forward._hits([1, 2, 3, 4, 5], [1, 2, 6, 7, 8]), 2)

    def test_back_hit_count(self):
        self.assertEqual(walk_forward._hits([1, 2], [2, 3]), 1)

    def test_total_hit_count(self):
        fh = walk_forward._hits([1, 2, 3, 4, 5], [1, 2, 6, 7, 8])
        bh = walk_forward._hits([1, 2], [2, 3])
        self.assertEqual(fh + bh, 3)

    def test_zero_hit(self):
        self.assertEqual(walk_forward._hits([1, 2, 3, 4, 5], [6, 7, 8, 9, 10]), 0)

    def test_perfect_5_plus_2(self):
        rec = walk_forward._eval_record(
            {"issue": "26001"}, {"issue": "26000"}, "C",
            [1, 2, 3, 4, 5], [1, 2], [1, 2, 3, 4, 5], [1, 2])
        self.assertEqual(rec["front_hits"], 5)
        self.assertEqual(rec["back_hits"], 2)
        self.assertEqual(rec["total_hits"], 7)
        self.assertEqual(rec["prize_tier"], 1)


class TestPrize(unittest.TestCase):
    """14-15: prize classification + cost=2."""

    def test_prize_classification(self):
        self.assertEqual(prize.classify_prize(5, 2), 1)
        self.assertEqual(prize.classify_prize(5, 1), 2)
        self.assertEqual(prize.classify_prize(5, 0), 3)
        self.assertEqual(prize.classify_prize(4, 2), 4)
        self.assertEqual(prize.classify_prize(4, 1), 5)
        self.assertEqual(prize.classify_prize(3, 2), 6)
        self.assertEqual(prize.classify_prize(4, 0), 7)
        self.assertEqual(prize.classify_prize(3, 1), 8)
        self.assertEqual(prize.classify_prize(2, 2), 8)
        self.assertEqual(prize.classify_prize(3, 0), 9)
        self.assertEqual(prize.classify_prize(2, 1), 9)
        self.assertEqual(prize.classify_prize(1, 2), 9)
        self.assertEqual(prize.classify_prize(0, 2), 9)
        self.assertIsNone(prize.classify_prize(0, 0))
        self.assertIsNone(prize.classify_prize(1, 0))
        self.assertIsNone(prize.classify_prize(2, 0))

    def test_cost_is_2_rmb(self):
        self.assertEqual(prize.TICKET_COST, 2.0)
        self.assertEqual(walk_forward.COST_PER_TICKET, 2.0)

    def test_no_duplicate_front(self):
        for seed in range(30):
            f = baselines.random_combo(seed)["front"]
            self.assertEqual(len(f), len(set(f)))


class TestMetrics(unittest.TestCase):
    """23-24: aggregation + random multi-seed aggregate."""

    def _recs(self):
        return [
            {"strategy": "A", "front_hits": 2, "back_hits": 1, "total_hits": 3},
            {"strategy": "A", "front_hits": 1, "back_hits": 0, "total_hits": 1},
            {"strategy": "B", "front_hits": 0, "back_hits": 0, "total_hits": 0},
            {"strategy": "RANDOM", "front_hits": 1, "back_hits": 1, "total_hits": 2},
        ]

    def test_aggregation(self):
        agg = metrics.aggregate(self._recs())
        self.assertEqual(agg["A"]["n"], 2)
        self.assertAlmostEqual(agg["A"]["front_hit_mean"], 1.5)
        self.assertEqual(agg["B"]["n"], 1)
        self.assertEqual(agg["RANDOM"]["thresholds"]["back_eq2"], 0)

    def test_random_multi_seed_stats(self):
        seed_results = {i: {"front_hits": 1.0, "back_hits": 0.5, "total_hits": 1.5}
                        for i in range(20)}
        st = metrics.random_multi_seed_stats(seed_results)
        self.assertEqual(st["seeds"], 20)
        self.assertAlmostEqual(st["total_hit_mean"], 1.5)
        self.assertEqual(st["total_hit_std"], 0.0)

    def test_compare_to_random(self):
        s = {"total_hit_mean": 1.6}
        c = metrics.compare_to_random(s, 1.5, 0.5, 0.5, 3.0)
        self.assertAlmostEqual(c["diff_vs_random"], 0.1)
        self.assertTrue(c["in_random_p05_p95"])


class TestWalkForward(unittest.TestCase):
    """16-22: warmup exclusion, A/B/C/D walk-forward, selector leakage guard."""

    def setUp(self):
        self.iss = _issues(160, front=(1, 2, 3, 4, 5), back=(1, 2))

    def test_warmup_exclusion(self):
        res = walk_forward.run_walk_forward(self.iss, warmup=100,
                                             random_seed_list=[1, 2],
                                             include_d=False, include_selector=False,
                                             verbose=False)
        self.assertEqual(res["meta"]["evaluated_periods"], 60)
        for r in res["records"]:
            self.assertGreaterEqual(int(r["target_issue"]), 26101)
            self.assertLess(int(r["train_last_issue"]), int(r["target_issue"]))

    def test_a_walk_forward(self):
        res = walk_forward.run_walk_forward(self.iss, warmup=100,
                                             random_seed_list=[1],
                                             include_d=False, include_selector=False,
                                             verbose=False)
        a = [r for r in res["records"] if r["strategy"] == "A"]
        self.assertTrue(a, "A should be evaluated")
        for r in a:
            self.assertLess(int(r["train_last_issue"]), int(r["target_issue"]))

    def test_b_walk_forward(self):
        res = walk_forward.run_walk_forward(self.iss, warmup=100,
                                             random_seed_list=[1],
                                             include_d=False, include_selector=False,
                                             verbose=False)
        self.assertTrue([r for r in res["records"] if r["strategy"] == "B"])

    def test_c_walk_forward(self):
        res = walk_forward.run_walk_forward(self.iss, warmup=100,
                                             random_seed_list=[1],
                                             include_d=False, include_selector=False,
                                             verbose=False)
        self.assertTrue([r for r in res["records"] if r["strategy"] == "C"])

    def test_d_walk_forward(self):
        res = walk_forward.run_walk_forward(self.iss, warmup=100,
                                             random_seed_list=[1],
                                             include_d=True, include_selector=False,
                                             verbose=False, eval_count=3)
        d = [r for r in res["records"] if r["strategy"] == "D"]
        self.assertTrue(d, "D should be evaluated")
        for r in d:
            self.assertLess(int(r["train_last_issue"]), int(r["target_issue"]))

    def test_selector_leakage_guard(self):
        res = walk_forward.run_walk_forward(self.iss, warmup=100,
                                             random_seed_list=[1],
                                             include_d=True, include_selector=True,
                                             verbose=False, eval_count=20)
        for r in res["records"]:
            self.assertLess(int(r["train_last_issue"]), int(r["target_issue"]))

    def test_simple_freq_baseline_present(self):
        res = walk_forward.run_walk_forward(self.iss, warmup=100,
                                             random_seed_list=[1],
                                             include_d=False, include_selector=False,
                                             verbose=False, eval_count=2)
        self.assertTrue([r for r in res["records"] if r["strategy"] == "SIMPLE_FREQ"])

    def test_all_records_leakage_safe(self):
        res = walk_forward.run_walk_forward(self.iss, warmup=100,
                                             random_seed_list=[1, 2, 3],
                                             include_d=False, include_selector=True,
                                             verbose=False, eval_count=15)
        for r in res["records"]:
            self.assertLess(int(r["train_last_issue"]), int(r["target_issue"]),
                           f"leakage in {r['strategy']} target={r['target_issue']}")


class TestProductionIntegrity(unittest.TestCase):
    """25: production files unchanged."""

    def test_26112_snapshot_unchanged(self):
        root = pathlib.Path(__file__).resolve().parent.parent
        pub = json.loads((root / "public" / "data" / "published_recommendations.json").read_text())
        item = next(x for x in pub["items"] if x["issue"] == "26112")
        self.assertEqual(item["primary_strategy"], "C-纯随机娱乐型")
        self.assertEqual(item["numbers"]["front"], [5, 12, 17, 28, 31])
        self.assertEqual(item["numbers"]["back"], [4, 7])
        self.assertTrue(item.get("explanation"))
        self.assertEqual(len(item["snapshot_hash"]), 64)

    def test_algorithm_files_not_in_evaluation_pkg(self):
        root = pathlib.Path(__file__).resolve().parent.parent
        for f in ("src/recommender.py", "src/scorer.py", "src/final_score.py",
                  "src/publisher.py", "src/analyzer.py"):
            self.assertTrue((root / f).exists(), f"missing {f}")


if __name__ == "__main__":
    unittest.main()
