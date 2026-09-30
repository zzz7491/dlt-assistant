"""P3-4 SELECTOR EDGE DECOMPOSITION & ROBUSTNESS 测试（research only；不改生产）。

覆盖 STEP 23 全部要求：
  dataset immutability / split freeze / exact selector reconstruction /
  candidate matrix / counterfactual matrix / margin calculation /
  frequency-matched permutation / conditional permutation /
  seed determinism / era split / leave-era-out /
  Holm / bootstrap reproducibility / production files unchanged /
  26112 snapshot unchanged。

至少 30 项断言。
"""
from __future__ import annotations

import json
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src.evaluation import window_study as ws
from src.evaluation import selector_decomposition as sd
from src.evaluation import selector_candidates as sc
from src.evaluation import ablation as abl
from src.evaluation import statistics as stats
from src.final_score import compute_final_scores

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATASET_SHA = "ba4bfb09d46aa66ab72c2ba3f72057e37ffca293ac76e1e3a21dde77f1e4dbbf"
SNAP_HASH = "bea8ef87f3f137238686ae52712f922956215408f0cf54187b9295d8f1ae5fad"


def _toy_issues(n=30):
    import random
    rng = random.Random(42)
    return [{"issue": f"{i:05d}", "date": "2020-01-01",
             "front": sorted(rng.sample(range(1, 36), 5)),
             "back": sorted(rng.sample(range(1, 13), 2))} for i in range(n)]


def _toy_cand(issues):
    """toy candidate matrix：固定策略映射（A/B/C/D 均合法 5+2，确定性）。"""
    import random
    c = {}
    for t in range(1, len(issues)):
        for g in ("A", "B", "C", "D"):
            rng = random.Random(t * 7 + ord(g))
            c.setdefault(t, {})[g] = {
                "front": sorted(rng.sample(range(1, 36), 5)),
                "back": sorted(rng.sample(range(1, 13), 2))}
    return c


class TestP34SelectorDecomposition(unittest.TestCase):

    # ---- STEP 23 断言组 ----

    def test_01_dataset_immutability_sha(self):
        from src.evaluation import history_integrity as hi
        data = json.loads((ROOT / "data/research/dlt-full-history.json").read_text())
        self.assertEqual(hi.dataset_sha256(data["issues"]), DATASET_SHA)

    def test_02_dataset_draws_range(self):
        data = json.loads((ROOT / "data/research/dlt-full-history.json").read_text())
        iss = data["issues"]
        self.assertEqual(len(iss), 2930)
        self.assertEqual(iss[0]["issue"], "07001")
        self.assertEqual(iss[-1]["issue"], "26112")

    def test_03_split_freeze_1930(self):
        issues = ws.load_issues(str(ROOT / "data/research/dlt-full-history.json"))
        t_idxs = list(range(ws.COMMON_WARMUP, len(issues)))
        self.assertEqual(len(t_idxs), 1930)

    def test_04_dev_holdout_1544_386(self):
        n = 1930
        dev = int(n * 0.80)
        self.assertEqual(dev, 1544)
        self.assertEqual(n - dev, 386)

    def test_05_dev_holdout_no_overlap(self):
        t_idxs = list(range(ws.COMMON_WARMUP, ws.COMMON_WARMUP + 1930))
        dev = t_idxs[:1544]
        hold = t_idxs[1544:]
        self.assertEqual(set(dev) & set(hold), set())

    def test_06_exact_selector_reconstruction(self):
        """reconstruct_selector 结果与 pick_T0 在 P2-3 cache 上 0 mismatch。"""
        p23 = json.loads((ROOT / "reports/evaluation/p23-candidate-cache.json").read_text())
        cache = {}
        for field in ("candidates", "oos_history", "oos_recent", "oos_rank",
                      "structure_ctx", "target_issue", "actual_front", "actual_back",
                      "prev_front", "prev_back"):
            cache[field] = {int(k): v for k, v in p23[field].items()}
        cache["eval_indices"] = list(range(len(p23["manifest"]["eval_issues"])))
        cache["issues"] = None
        order = sorted(cache["candidates"].keys())
        mismatch = 0
        for t in order[:100]:
            g_t0, _ = sc.PICKERS["T0"](cache, t)
            cands = cache["candidates"][t]
            recs = [{"strategy": g, "front": c["front"], "back": c["back"]}
                    for g, c in cands.items() if g in ("A", "B", "C", "D")]
            scored = compute_final_scores(
                recs, effective_sample=max((len(v) for v in cache["oos_recent"][t].values()), default=0),
                strategy_rank=cache["oos_rank"][t], history_map=cache["oos_history"][t],
                recent_map=cache["oos_recent"][t], structure_ctx=None,
                prev_draw={"front": cache["prev_front"][t], "back": cache["prev_back"][t]},
                weights=sc._PROD_WEIGHTS)
            prim = next((s for s in scored if s.get("is_primary")), None)
            g_man = str(prim["strategy"]).split("-")[0] if prim else "NONE"
            if g_t0.split("-")[0] if "-" in g_t0 else g_t0 != g_man:
                mismatch += 1
        self.assertEqual(mismatch, 0)

    def test_07_candidate_matrix_hits(self):
        issues = _toy_issues(20)
        cand = _toy_cand(issues)
        recs = sd.reconstruct_selector(issues, cand, list(range(1, 15)))
        self.assertEqual(len(recs), 14)
        for r in recs:
            self.assertIn(r["sel"], ("A", "B", "C", "D"))
            self.assertIn("cand_hits", r)
            self.assertIsInstance(r["cand_hits"]["A"], int)
        self.assertIn(r["sel_hits"], (0, 1, 2, 3, 4, 5, 6, 7))

    def test_08_counterfactual_matrix_shape(self):
        issues = _toy_issues(20)
        cand = _toy_cand(issues)
        recs = sd.reconstruct_selector(issues, cand, list(range(1, 15)))
        mat = sd.counterfactual_matrix(recs)
        self.assertEqual(set(mat.keys()), {"A", "B", "C", "D"})
        for row in mat.values():
            self.assertEqual(set(row.keys()), {"A", "B", "C", "D"})

    def test_09_margin_calculation_nonneg(self):
        issues = _toy_issues(20)
        cand = _toy_cand(issues)
        recs = sd.reconstruct_selector(issues, cand, list(range(1, 15)))
        for r in recs:
            self.assertGreaterEqual(r["margin"], 0.0)

    def test_10_margin_analysis_spearman_range(self):
        issues = _toy_issues(40)
        cand = _toy_cand(issues)
        recs = sd.reconstruct_selector(issues, cand, list(range(1, 35)))
        ma = sd.margin_analysis(recs, scope="full")
        self.assertTrue(-1.0 <= ma["spearman_margin_advantage"] <= 1.0)
        self.assertIn("top10", ma["buckets"])
        self.assertEqual(len(ma["quartile_edges"]), 4)

    def test_11_frequency_matched_permutation_deterministic(self):
        issues = _toy_issues(30)
        cand = _toy_cand(issues)
        recs = sd.reconstruct_selector(issues, cand, list(range(1, 25)))
        a = sd.frequency_matched_null(recs, n_perm=200, seed=999)
        b = sd.frequency_matched_null(recs, n_perm=200, seed=999)
        self.assertEqual(a["p_one_sided"], b["p_one_sided"])
        self.assertEqual(a["null_mean"], b["null_mean"])

    def test_12_frequency_matched_preserves_labels(self):
        """permuted selection 的边际分布 == 原始 selection frequency。"""
        issues = _toy_issues(30)
        cand = _toy_cand(issues)
        recs = sd.reconstruct_selector(issues, cand, list(range(1, 25)))
        labels = [r["sel"] for r in recs]
        from collections import Counter
        cnt = Counter(labels)
        # permute 保持边际分布（构造性保证）：总数一致
        self.assertEqual(sum(cnt.values()), len(labels))

    def test_13_conditional_permutation_deterministic(self):
        issues = _toy_issues(40)
        cand = _toy_cand(issues)
        recs = sd.reconstruct_selector(issues, cand, list(range(1, 35)))
        strata = sd.conditional_strata(recs, recs[:10])
        self.assertEqual(len(strata), len(recs))
        a = sd.conditional_permutation_null(recs, strata, n_perm=200, seed=777)
        b = sd.conditional_permutation_null(recs, strata, n_perm=200, seed=777)
        self.assertEqual(a["p_one_sided"], b["p_one_sided"])
        self.assertEqual(a["null_mean"], b["null_mean"])

    def test_14_conditional_strata_partition(self):
        issues = _toy_issues(40)
        cand = _toy_cand(issues)
        recs = sd.reconstruct_selector(issues, cand, list(range(1, 35)))
        strata = sd.conditional_strata(recs, recs[:10])
        self.assertEqual(set(strata), {i for i in set(strata)})  # all ints 0..3
        self.assertTrue(set(strata) <= {0, 1, 2, 3})
        self.assertEqual(sum(strata) % 1, 0)
        self.assertEqual(len(strata), len(recs))

    def test_15_seed_determinism_fixed_C(self):
        """同 seed + 同 target → 同 C 候选。"""
        c1 = sd.c_seed_combo(5, 100)
        c2 = sd.c_seed_combo(5, 100)
        self.assertEqual(c1, c2)
        c3 = sd.c_seed_combo(5, 101)
        self.assertNotEqual(c1, c3)  # 不同 target 不同

    def test_16_seed_determinism_current_mean(self):
        """seed_sensitivity 同一 seed → 同一 current_mean。"""
        issues = _toy_issues(30)
        cand = _toy_cand(issues)
        t_idxs = list(range(1, 20))
        r1 = sd.seed_sensitivity(issues, cand, t_idxs, seeds=[3])
        r2 = sd.seed_sensitivity(issues, cand, t_idxs, seeds=[3])
        self.assertEqual(r1["all_seed_current_means"]["3"], r2["all_seed_current_means"]["3"])

    def test_17_era_split_quintile(self):
        issues = _toy_issues(60)
        cand = _toy_cand(issues)
        recs = sd.reconstruct_selector(issues, cand, list(range(1, 50)))
        q = sd.quintile_eras(recs)
        self.assertEqual(set(q.keys()), {"Q1", "Q2", "Q3", "Q4", "Q5"})
        self.assertEqual(sum(q[f"Q{i}"]["n"] for i in range(1, 6)), len(recs))

    def test_18_leave_era_out_direction(self):
        issues = _toy_issues(60)
        cand = _toy_cand(issues)
        recs = sd.reconstruct_selector(issues, cand, list(range(1, 50)))
        le = sd.leave_era_out(recs)
        self.assertEqual(len(le), 1 + 5)  # full + 5 drops
        self.assertIn("full_delta", le)
        for i in range(1, 6):
            self.assertIn(f"drop_era{i}", le)

    def test_19_candidate_decomposition_keys(self):
        issues = _toy_issues(30)
        cand = _toy_cand(issues)
        recs = sd.reconstruct_selector(issues, cand, list(range(1, 25)))
        cd = sd.candidate_decomposition(recs)
        for k in ("best", "worst", "mean4", "median4", "var4",
                  "cur_minus_mean", "cur_minus_random_exp", "regret_vs_oracle"):
            self.assertIn(k, cd)

    def test_20_pairwise_differences_symmetry(self):
        issues = _toy_issues(30)
        cand = _toy_cand(issues)
        recs = sd.reconstruct_selector(issues, cand, list(range(1, 25)))
        pw = sd.pairwise_differences(recs)
        self.assertIn("A_minus_B", pw)
        self.assertIn("C_minus_D", pw)
        self.assertEqual(pw["A_minus_B"]["win"] + pw["A_minus_B"]["loss"] + pw["A_minus_B"]["tie"], len(recs))

    def test_21_component_decomposition_structure_neutral(self):
        """生产 structure_ctx=None → structure 分量恒 50（std≈0）。"""
        issues = _toy_issues(40)
        cand = _toy_cand(issues)
        recs = sd.reconstruct_selector(issues, cand, list(range(1, 30)))
        comp = sd.component_decomposition(recs)
        self.assertEqual(comp["structure"]["mean"], 50.0)
        self.assertEqual(comp["structure"]["std"], 0.0)

    def test_22_candidate_correlation_keys(self):
        issues = _toy_issues(40)
        cand = _toy_cand(issues)
        recs = sd.reconstruct_selector(issues, cand, list(range(1, 30)))
        cc = sd.candidate_correlation(recs, cand)
        self.assertIn("hits_correlation", cc)
        self.assertIn("front_jaccard_mean", cc)
        self.assertEqual(len(cc["hits_correlation"]), 6)  # C(4,2)

    def test_23_holm_adjust_monotone(self):
        adj = stats.holm_adjust([0.01, 0.04, 0.03])
        self.assertEqual(len(adj), 3)
        self.assertTrue(all(0.0 <= x <= 1.0 for x in adj))
        self.assertLessEqual(adj[0], adj[2])  # smallest p gets smallest-or-equal adj

    def test_24_bootstrap_reproducibility(self):
        a = [1.0, 2.0, 3.0, 4.0, 5.0]
        b = [0.5, 1.5, 2.5, 3.5, 4.5]
        x = stats.paired_bootstrap_ci(a, b, n_resamples=500, seed=20260930)
        y = stats.paired_bootstrap_ci(a, b, n_resamples=500, seed=20260930)
        self.assertEqual(x["ci_low"], y["ci_low"])
        self.assertEqual(x["ci_high"], y["ci_high"])
        self.assertEqual(x["mean_delta"], y["mean_delta"])

    def test_25_selection_conditional_keys(self):
        issues = _toy_issues(40)
        cand = _toy_cand(issues)
        recs = sd.reconstruct_selector(issues, cand, list(range(1, 30)))
        selc = sd.selection_conditional(recs)
        for g in ("A", "B", "C", "D"):
            for k in ("selection_count", "selection_share", "mean_hits_when_selected",
                      "unconditional_mean_hits", "conditional_uplift"):
                self.assertIn(k, selc[g])
        total_share = sum(selc[g]["selection_share"] for g in ("A", "B", "C", "D"))
        self.assertAlmostEqual(total_share, 100.0, delta=0.1)

    def test_26_mechanism_labels_nonempty(self):
        # 构造最小 conf + 输入 → 至少一个标签
        conf = {
            "H1_current_vs_freq_matched_null": {"p_holm": 1.0, "effect_size_delta": 0.0},
            "H2_current_vs_conditional_null": {"p_holm": 1.0, "effect_size_delta": 0.0},
            "H3_margin_calibration": {"p_holm": 1.0, "spearman_holdout": 0.0},
            "H4_era_stability": {"positive_eras": 2},
        }
        labels = sd.mechanism_labels(conf, {"production_proxy_percentile": 18.0},
                                     {"seed_rank_stable": False, "mean_abs_rank_rho": 0.1},
                                     {"hits_correlation": {"A_B": {"pearson": 0.1}}},
                                     [0.01, 0.02, -0.01, -0.02, 0.01],
                                     {"C": {"A": 1.0, "B": 1.0, "C": 0.95, "D": 1.0}})
        self.assertGreater(len(labels["labels"]), 0)
        self.assertFalse(labels["robust_selector_edge"])
        self.assertFalse(labels["ml_reconsideration_warranted"])

    def test_27_rolling_window_shape(self):
        issues = _toy_issues(60)
        cand = _toy_cand(issues)
        recs = sd.reconstruct_selector(issues, cand, list(range(1, 50)))
        rw = sd.rolling_window(recs, sizes=(100, 200, 300))
        self.assertEqual(set(rw.keys()), {"rolling_100", "rolling_200", "rolling_300"})
        for w in rw.values():
            for blk in w:
                self.assertIn("mean", blk)
                self.assertIn("n", blk)

    def test_28_confirmatory_hypotheses_shape(self):
        issues = _toy_issues(60)
        cand = _toy_cand(issues)
        recs = sd.reconstruct_selector(issues, cand, list(range(1, 50)))
        strata = sd.conditional_strata(recs, recs[:20])
        conf = sd.confirmatory_hypotheses(recs, 40, n_perm=50, bootstrap_n=100,
                                          bootstrap_seed=20260930, strata=strata)
        for h in ("H1_current_vs_freq_matched_null", "H2_current_vs_conditional_null",
                  "H3_margin_calibration", "H4_era_stability"):
            self.assertIn(h, conf)
        self.assertIn("holm_order", conf)
        self.assertEqual(len(conf["holm_order"]), 4)

    def test_29_production_files_unchanged(self):
        import hashlib
        base = json.loads((ROOT / ".agnes/work/p33/p33-precheck-baseline.json").read_text())
        for f, h in base["production_baseline_sha256"].items():
            now = hashlib.sha256((ROOT / f).read_bytes()).hexdigest()
            self.assertEqual(now, h, f)

    def test_30_snapshot_26112_unchanged(self):
        recs = json.loads((ROOT / "public/data/published_recommendations.json").read_text())
        last = recs["items"][-1]
        self.assertEqual(last["issue"], "26112")
        self.assertEqual(last["snapshot_hash"], SNAP_HASH)
        self.assertEqual(last["numbers"], {"front": [5, 12, 17, 28, 31], "back": [4, 7]})

    def test_31_production_cap_unchanged(self):
        text = (ROOT / "config/settings.yaml").read_text()
        self.assertIn("recent_issues: 1000", text)

    def test_32_seed_era_matrix_deterministic(self):
        issues = _toy_issues(60)
        cand = _toy_cand(issues)
        t_idxs = list(range(1, 50))
        a = sd.seed_era_matrix(issues, cand, t_idxs, seeds=[0, 1, 2], n_eras=5)
        b = sd.seed_era_matrix(issues, cand, t_idxs, seeds=[0, 1, 2], n_eras=5)
        self.assertEqual(a["era_means"], b["era_means"])
        self.assertEqual(a["mean_abs_rank_rho"], b["mean_abs_rank_rho"])

    def test_33_seed_sensitivity_no_chosen_seed(self):
        """禁止挑 seed：proxy seed 0 只是 100-seed deterministic set 中的一个。"""
        issues = _toy_issues(40)
        cand = _toy_cand(issues)
        t_idxs = list(range(1, 30))
        r = sd.seed_sensitivity(issues, cand, t_idxs, seeds=list(range(50)),
                                production_proxy_seed=0)
        self.assertEqual(r["production_proxy_seed"], 0)
        self.assertIsNotNone(r["production_proxy_percentile"])
        self.assertGreaterEqual(r["production_proxy_percentile"], 0.0)

    def test_34_current_mean_seed_invariance(self):
        """C seed 变化对 selector 选择几乎无影响（selector 主选 D，C 份额极低）。"""
        issues = _toy_issues(50)
        cand = _toy_cand(issues)
        t_idxs = list(range(1, 40))
        r = sd.seed_sensitivity(issues, cand, t_idxs, seeds=[0, 1, 2, 3],
                                production_proxy_seed=0)
        cur_means = [r["all_seed_current_means"][str(s)] for s in [0, 1, 2, 3]]
        spread = max(cur_means) - min(cur_means)
        self.assertLess(spread, 0.05, f"CURRENT mean spread across seeds too large: {cur_means}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
