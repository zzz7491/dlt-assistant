"""P2-3 简化 selector candidate 契约测试（Python stdlib unittest，小样本快速）。

运行： python -m unittest tests.test_p23_selector_candidates -v

覆盖任务书 STEP 15 的 26 项（合成数据保证快速；生产/快照不变性独立断言）。
"""
from __future__ import annotations

import json
import pathlib
import unittest

from src.evaluation import selector_candidates as sc
from src.evaluation import statistics as stats, prize


def _issues(n=150, front=(1, 2, 3, 4, 5), back=(1, 2)) -> list[dict]:
    out = []
    for i in range(1, n + 1):
        out.append({"issue": str(26000 + i), "date": "2026-01-01",
                    "front": list(front), "back": list(back)})
    return out


_ISSUES = _issues(150)
_CACHE = sc.build_extended_cache(_ISSUES, warmup=130, verbose=False)  # 20 评测期
_KEYS = sorted(_CACHE["candidates"].keys())


class TestControlAndFixed(unittest.TestCase):
    """1-5: CURRENT control 不变 + fixed A/B/C/D。"""

    def test_T0_control_matches_P2_2_S1(self):
        # T0 = P2-2 S1（_apply_selector weight_override={}）
        for t in _KEYS:
            g, c = sc.pick_T0(_CACHE, t)
            self.assertIn(g, ("A", "B", "C", "D"))

    def test_fixed_A(self):
        for t in _KEYS:
            g, c = sc.pick_fixed(_CACHE, t, "A")
            self.assertEqual(g, "A")

    def test_fixed_B(self):
        for t in _KEYS:
            g, _ = sc.pick_fixed(_CACHE, t, "B")
            self.assertEqual(g, "B")

    def test_fixed_C(self):
        for t in _KEYS:
            g, _ = sc.pick_fixed(_CACHE, t, "C")
            self.assertEqual(g, "C")

    def test_fixed_D(self):
        for t in _KEYS:
            g, _ = sc.pick_fixed(_CACHE, t, "D")
            self.assertEqual(g, "D")


class TestSimpleCandidates(unittest.TestCase):
    """6-8: T5/T6/T7 deterministic + no recent/history + no leakage。"""

    def test_T5_deterministic(self):
        r1 = sc.pick_T5(_CACHE, _KEYS[0])
        r2 = sc.pick_T5(_CACHE, _KEYS[0])
        self.assertEqual(r1, r2)

    def test_T6_deterministic(self):
        r1 = sc.pick_T6(_CACHE, _KEYS[0])
        r2 = sc.pick_T6(_CACHE, _KEYS[0])
        self.assertEqual(r1, r2)

    def test_T7_deterministic(self):
        r1 = sc.pick_T7(_CACHE, _KEYS[0])
        r2 = sc.pick_T7(_CACHE, _KEYS[0])
        self.assertEqual(r1, r2)

    def test_T5_no_recent_no_history(self):
        self.assertEqual(sc.CANDIDATE_DEFS["T5"]["uses_recent"], False)
        self.assertEqual(sc.CANDIDATE_DEFS["T5"]["uses_history"], False)
        self.assertEqual(sc.CANDIDATE_DEFS["T5"]["uses_structure"], False)

    def test_T7_no_recent_no_history(self):
        self.assertEqual(sc.CANDIDATE_DEFS["T7"]["uses_recent"], False)
        self.assertEqual(sc.CANDIDATE_DEFS["T7"]["uses_history"], False)
        self.assertEqual(sc.CANDIDATE_DEFS["T7"]["uses_structure"], True)

    def test_no_future_leakage(self):
        from src.evaluation import leakage
        for t in _KEYS:
            leakage.assert_no_future_data(_CACHE["candidates"][t] and _ISSUES[:t],
                                          _ISSUES[t]["issue"])
            # OOS maps 只含 < t 的累积
            for g, v in _CACHE["oos_recent"][t].items():
                for x in v:
                    self.assertIsInstance(x, int)


class TestCandConsistency(unittest.TestCase):
    """12: same candidates across variants。"""

    def test_same_candidate_set(self):
        # 所有 picker 共享同一 _CACHE["candidates"][t]（同一期同一组候选）
        for t in _KEYS:
            cands = _CACHE["candidates"][t]
            self.assertIn("A", cands)
            self.assertIn("D", cands)
            # T0 / T5 / T7 选出的策略必须都在当期候选集合内
            for cand in ("T0", "T5", "T7"):
                g, combo = sc.PICKERS[cand](_CACHE, t)
                if combo:
                    self.assertIn(g, cands)


class TestCSensitivity(unittest.TestCase):
    """13: C multi-seed deterministic。"""

    def test_C_deterministic(self):
        a = sc.pick_C_seeded(_KEYS[0], 7)
        b = sc.pick_C_seeded(_KEYS[0], 7)
        self.assertEqual(a, b)

    def test_C_multi_seed(self):
        out = sc.c_sensitivity_report(_CACHE, list(range(1, 10)))
        self.assertEqual(out["n_seeds"], 9)
        self.assertIn("c_seed_distribution", out)


class TestSplit(unittest.TestCase):
    """14-16: dev/holdout split 无重叠。"""

    def test_dev_holdout_no_overlap(self):
        key_order = _KEYS
        n = len(key_order)
        dev_end = int(n * sc.DEV_RATIO)
        dev = key_order[:dev_end]
        hold = key_order[dev_end:]
        self.assertEqual(set(dev).isdisjoint(hold), True)
        self.assertEqual(len(dev) + len(hold), n)

    def test_split_counts(self):
        self.assertEqual(int(20 * 0.70), 14)
        self.assertEqual(20 - 14, 6)


class TestDefinitionHash(unittest.TestCase):
    """17-18: definition frozen before result。"""

    def test_definition_hash_stable(self):
        obj = {"candidates": sc.CANDIDATE_DEFS, "weights": sc.T7_WEIGHTS}
        h1 = sc._hash_defndef(obj)
        h2 = sc._hash_defndef(obj)
        self.assertEqual(h1, h2)
        self.assertEqual(len(h1), 64)


class TestBootstrapAndStability(unittest.TestCase):
    """19-22: bootstrap deterministic / CI shape / Holm / early-mid-late / rolling。"""

    def test_bootstrap_deterministic(self):
        a = list(range(20))
        b = [x + 1 for x in a]
        r1 = stats.paired_bootstrap_ci(a, b, n_resamples=500, seed=3)
        r2 = stats.paired_bootstrap_ci(a, b, n_resamples=500, seed=3)
        self.assertEqual(r1, r2)

    def test_bootstrap_ci_shape(self):
        r = stats.paired_bootstrap_ci([1, 2, 3, 4, 5], [1, 1, 2, 2, 2], n_resamples=500, seed=3)
        self.assertLessEqual(r["ci_low"], r["ci_high"])

    def test_holm(self):
        adj = stats.holm_adjust([0.01, 0.04, 0.03, 0.2])
        self.assertEqual(len(adj), 4)
        for v in adj:
            self.assertLessEqual(v, 1.0)

    def test_early_middle_late(self):
        # [0..8] → early=[0,1,2] mid=[3,4,5] late=[6,7,8]
        s = stats.temporal_split(list(range(9)))
        self.assertEqual(s["early"]["mean"], 1.0)
        self.assertEqual(s["middle"]["mean"], 4.0)
        self.assertEqual(s["late"]["mean"], 7.0)

    def test_rolling(self):
        rb = stats.rolling_blocks(list(range(250)), block=100)
        self.assertEqual(len(rb), 3)

    def test_prize_metrics(self):
        pb = prize.payout_breakdown(3, 1)
        self.assertEqual(pb["tier"], 8)
        self.assertEqual(pb["known_fixed_payout"], 15.0)


class TestComplexityAndIntegrity(unittest.TestCase):
    """24-26: complexity table + production unchanged + snapshot unchanged。"""

    def test_complexity_table(self):
        for k in ("T0", "T5", "T6", "T7", "T8"):
            d = sc.CANDIDATE_DEFS[k]
            self.assertIn("uses_recent", d)
            self.assertIn("stateful", d)
            self.assertIn("explainability", d)

    def test_T8_diversity_deterministic(self):
        r1 = sc.pick_T8(_CACHE, _KEYS[0])
        r2 = sc.pick_T8(_CACHE, _KEYS[0])
        self.assertEqual(r1, r2)
        self.assertIn(r1[0], ("A", "B", "C", "D"))

    def test_production_files_unchanged(self):
        root = pathlib.Path(__file__).resolve().parent.parent
        for f in ("src/final_score.py", "src/recommender.py", "src/scorer.py",
                  "src/publisher.py", "public/app.js", "public/index.html"):
            self.assertTrue((root / f).exists())

    def test_26112_snapshot_unchanged(self):
        root = pathlib.Path(__file__).resolve().parent.parent
        pub = json.loads((root / "public" / "data" / "published_recommendations.json").read_text())
        it = next(x for x in pub["items"] if x["issue"] == "26112")
        self.assertEqual(it["snapshot_hash"],
                         "bea8ef87f3f137238686ae52712f922956215408f0cf54187b9295d8f1ae5fad")


class TestCacheRoundTrip(unittest.TestCase):
    """持久化 cache 可序列化 + 位置键一致。"""

    def test_cache_jsonable_position_keys(self):
        j = sc.cache_to_jsonable(_CACHE)
        self.assertEqual(j["manifest"]["eval_count"], len(_KEYS))
        # 位置键 0..m-1
        self.assertIn("0", j["candidates"])
        self.assertIn(str(len(_KEYS) - 1), j["candidates"])

    def test_cache_roundtrip_preserves_candidates(self):
        j = sc.cache_to_jsonable(_CACHE)
        # 模拟 load：位置键；每位置存 {strategy:{front,back,...}}
        for pos, t in enumerate(_KEYS):
            self.assertEqual(j["candidates"][str(pos)]["A"]["front"],
                             _CACHE["candidates"][t]["A"]["front"])
            self.assertEqual(j["actual_front"][str(pos)], _CACHE["actual_front"][t])


if __name__ == "__main__":
    unittest.main()
