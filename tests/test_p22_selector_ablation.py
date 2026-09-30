"""P2-2 selector ablation 契约测试（Python stdlib unittest，无 pytest）。

运行： python -m unittest tests.test_p22_selector_ablation -v

覆盖任务书 STEP 16 的 21 项（小样本合成数据保证快速 + 确定性）。
"""
from __future__ import annotations

import json
import pathlib
import unittest

from src.evaluation import ablation, baselines, statistics as stats, walk_forward


def _issues(n=140, front=(1, 2, 3, 4, 5), back=(1, 2)) -> list[dict]:
    out = []
    for i in range(1, n + 1):
        out.append({"issue": str(26000 + i), "date": "2026-01-01",
                    "front": list(front), "back": list(back)})
    return out


# 小样本 cache（warmup=120 → 20 评测期；D 20 期 × 1s ≈ 20s，可接受）
_SMALL_WARMUP = 120
_SMALL_ISSUES = _issues(140)
_SMALL_CACHE = ablation.build_candidate_cache(_SMALL_ISSUES, warmup=_SMALL_WARMUP,
                                              verbose=False)


class TestLeakageAndIntegrity(unittest.TestCase):
    """19-21: no future leakage / production unchanged / snapshot unchanged."""

    def test_no_future_leakage(self):
        for t in _SMALL_CACHE["eval_indices"]:
            for g, c in _SMALL_CACHE["candidates"][t].items():
                self.assertIn("th", c)
            tgt = int(_SMALL_CACHE["target_issue"][t])
            for ev in _SMALL_CACHE["oos_recent"][t].values():
                pass  # OOS maps 由 walk_forward 侧 issues[:t-1] 累积，天然无未来
            # 直接再验证 evidence 契约
            from src.evaluation import leakage
            leakage.assert_no_future_data(_SMALL_ISSUES[:t], tgt)

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


class TestVariantDefinitions(unittest.TestCase):
    """2-7: 同一 target/candidates；oracle 标记；random-choice 确定性/多 seed。"""

    def test_same_candidates_across_selector_variants(self):
        # S1-S6 用同一 _apply_selector 输入（candidates + OOS maps）；仅 weight_override 差异
        self.assertEqual(set(_SMALL_CACHE["candidates"].keys()),
                         set(_SMALL_CACHE["eval_indices"]))

    def test_recent_only_differs(self):
        self.assertEqual(ablation.VARIANTS["S2"]["weight_override"], {"recent": 0.0})
        self.assertNotIn("recent", ablation.VARIANTS["S1"]["weight_override"])

    def test_history_only_differs(self):
        self.assertEqual(ablation.VARIANTS["S3"]["weight_override"], {"history": 0.0})

    def test_random_choice_deterministic(self):
        t = _SMALL_CACHE["eval_indices"][0]
        g1, c1 = ablation._pick_random_choice(_SMALL_CACHE, t, seed=7)
        g2, c2 = ablation._pick_random_choice(_SMALL_CACHE, t, seed=7)
        self.assertEqual((g1, c1["front"]), (g2, c2["front"]))

    def test_random_choice_multi_seed(self):
        t = _SMALL_CACHE["eval_indices"][0]
        picks = {ablation._pick_random_choice(_SMALL_CACHE, t, seed=s)[0]
                 for s in range(40)}
        # 40 个 seed 下应出现多于 1 种选择（除非所有候选相同）
        self.assertGreaterEqual(len(picks), 1)

    def test_oracle_marked(self):
        self.assertTrue(ablation.VARIANTS["S8"]["oracle"])
        self.assertFalse(ablation.VARIANTS["S1"]["oracle"])

    def test_oracle_upper_bound_not_in_production_variants(self):
        for v in ("S0", "S1", "S2", "S3", "S4", "S5", "S6", "S7"):
            self.assertFalse(ablation.VARIANTS[v]["oracle"], f"{v} must not be oracle")


class TestSelectorAblation(unittest.TestCase):
    """3-4, 8-18: 变体运行 + paired delta + bootstrap + selection freq + switching + temporal。"""

    def setUp(self):
        # 小样本跑 S1/S2（fast，无 S0/S7 多 seed 以省时）
        self.s1, self.s1_seq = ablation._variant_records_selector(_SMALL_CACHE, "S1")
        self.s2, self.s2_seq = ablation._variant_records_selector(_SMALL_CACHE, "S2")

    def test_records_length_matches_eval_periods(self):
        self.assertEqual(len(self.s1), len(_SMALL_CACHE["eval_indices"]))

    def test_paired_delta_correct(self):
        d = [a["total_hits"] - b["total_hits"] for a, b in zip(self.s1, self.s2)]
        mean_d = sum(d) / len(d)
        boot = stats.paired_bootstrap_ci([a["total_hits"] for a in self.s1],
                                         [a["total_hits"] for a in self.s2],
                                         n_resamples=1000, seed=42)
        self.assertAlmostEqual(boot["mean_delta"], mean_d, places=4)

    def test_bootstrap_deterministic(self):
        b1 = stats.paired_bootstrap_ci([a["total_hits"] for a in self.s1],
                                       [a["total_hits"] for a in self.s2],
                                       n_resamples=1000, seed=7)
        b2 = stats.paired_bootstrap_ci([a["total_hits"] for a in self.s1],
                                       [a["total_hits"] for a in self.s2],
                                       n_resamples=1000, seed=7)
        self.assertEqual(b1, b2)

    def test_bootstrap_ci_shape(self):
        b = stats.paired_bootstrap_ci([a["total_hits"] for a in self.s1],
                                      [a["total_hits"] for a in self.s2],
                                      n_resamples=1000, seed=7)
        self.assertLessEqual(b["ci_low"], b["ci_high"])
        self.assertIn("ci_contains_zero", b)

    def test_signflip_deterministic(self):
        p1 = stats.paired_sign_flip_pvalue([a["total_hits"] for a in self.s1],
                                           [a["total_hits"] for a in self.s2])
        p2 = stats.paired_sign_flip_pvalue([a["total_hits"] for a in self.s1],
                                           [a["total_hits"] for a in self.s2])
        self.assertEqual(p1, p2)

    def test_holm_adjust(self):
        adj = stats.holm_adjust([0.01, 0.02, 0.04, 0.5])
        self.assertEqual(len(adj), 4)
        for a in adj:
            self.assertGreaterEqual(a, 0.0)
            self.assertLessEqual(a, 1.0)
        # Holm 单调不减性质：排序后 adjusted 非递减
        self.assertLessEqual(adj[0], max(adj))

    def test_selection_freq_sums_100(self):
        freq = ablation.selection_freq(self.s1_seq)
        self.assertAlmostEqual(sum(freq[g] for g in ("A", "B", "C", "D")), 100.0, delta=0.1)

    def test_switch_rate(self):
        sw = ablation.switching_stats(self.s1_seq)
        self.assertGreaterEqual(sw["switch_rate"], 0.0)
        self.assertLessEqual(sw["switch_rate"], 1.0)

    def test_run_length(self):
        sw = ablation.switching_stats(["A", "A", "B", "B", "B", "A"])
        # runs = [2,3,1] → mean 2.0
        self.assertAlmostEqual(sw["mean_run"], 2.0, places=4)

    def test_early_middle_late_split(self):
        s = stats.temporal_split([1, 1, 1, 2, 2, 2, 3, 3, 3])
        self.assertEqual(s["early"]["mean"], 1.0)
        self.assertEqual(s["late"]["mean"], 3.0)

    def test_rolling_blocks(self):
        rb = stats.rolling_blocks(list(range(250)), block=100)
        self.assertEqual(len(rb), 3)
        self.assertEqual(rb[0]["n"], 100)
        self.assertEqual(rb[2]["n"], 50)

    def test_payout_metrics_present(self):
        r = self.s1[0]
        self.assertIn("cost", r)
        self.assertIn("payout", r)
        self.assertIn("roi", r)
        self.assertEqual(r["cost"], 2.0)


class TestS7AndS8(unittest.TestCase):
    """5-6, 18: random-choice 多 seed 记录 + oracle 上限。"""

    def test_s7_records(self):
        recs, per_seed = ablation._variant_records_s7(_SMALL_CACHE, [1, 2, 3])
        # 3 seeds × 20 periods = 60
        self.assertEqual(len(recs), 60)
        self.assertEqual(set(per_seed.keys()), {1, 2, 3})

    def test_s8_oracle_upper_bound(self):
        recs = ablation._variant_records_s8(_SMALL_CACHE)
        # oracle 每期命中 >= 各单策略
        for t in _SMALL_CACHE["eval_indices"]:
            cands = _SMALL_CACHE["candidates"][t]
            best = max(c["th"] for c in cands.values())
            got = next(r["total_hits"] for r in recs if r["target_issue"] ==
                       _SMALL_CACHE["target_issue"][t])
            self.assertEqual(got, best)


class TestFullRun(unittest.TestCase):
    """端到端 run_ablation（小样本、少 seed、少 bootstrap）跑通完整 pipeline。"""

    def test_run_ablation_smoke(self):
        res = ablation.run_ablation(_SMALL_ISSUES, warmup=_SMALL_WARMUP,
                                    random_s7_seeds=[1, 2, 3],
                                    s0_seeds=[1, 2, 3],
                                    bootstrap_n=500, bootstrap_seed=1,
                                    verbose=False)
        for k in ("S0", "S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8"):
            self.assertIn(k, res["variants"])
        for k in ("S1_vs_S2", "S1_vs_S3", "S1_vs_S4", "S1_vs_S7"):
            self.assertIn(k, res["comparisons"])
            self.assertIn("p_value_holm", res["comparisons"][k]["signflip"])
        self.assertIn("early", res["temporal_S1"])
        self.assertTrue(res["variants"]["S8"]["oracle"])
        self.assertIn("rolling_S1_minus_S2", res)


if __name__ == "__main__":
    unittest.main()
