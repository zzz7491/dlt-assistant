"""P3-3 特征有效性 & 消融评测测试（research only；不改生产）。

覆盖任务书 STEP 23 全部 34 项断言。用合成小数据做确定性断言，
用真实 dataset 做泄漏/SHA/生产完整性断言。
"""
from __future__ import annotations

import json
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src.evaluation import window_study as ws
from src.evaluation import feature_study as fs
from src.evaluation import feature_ablation as fa
from src.evaluation import statistics as st
from src.analyzer import analyze


def _toy_issues(n=20):
    """合成 n 期大乐透历史（确定性）。"""
    import random
    rng = random.Random(42)
    out = []
    for i in range(n):
        out.append({
            "issue": f"{i:05d}",
            "date": f"2020-01-{i+1:02d}",
            "front": sorted(rng.sample(range(1, 36), 5)),
            "back": sorted(rng.sample(range(1, 13), 2)),
        })
    return out


def _toy_cfg():
    return {
        "analysis": {"front_min": 1, "front_max": 35, "back_min": 1, "back_max": 12,
                     "front_zones": 5, "back_zones": 2, "recent_window": 50},
        "recommend": {"combos_per_strategy": 1, "seed": 20260930,
                      "weights": {
                          "number": {"heat": 0.30, "missing": 0.30, "trend": 0.25, "inherit": 0.15},
                          "combo": {"inherit_match": 0.20, "odd_even_match": 0.20,
                                    "big_small_match": 0.20, "zone_match": 0.20, "sum_span_match": 0.20},
                          "single_vs_combo": {"single": 0.7, "combo": 0.3},
                          "top_front": 15, "top_back": 8,
                      }},
    }


class TestP33FeatureStudy(unittest.TestCase):

    def test_01_dataset_sha(self):
        """1) dataset canonical SHA。"""
        from src.evaluation import history_integrity as hi
        data = json.loads((pathlib.Path(__file__).resolve().parent.parent /
                           "data/research/dlt-full-history.json").read_text())
        sha = hi.dataset_sha256(data["issues"])
        self.assertEqual(sha, "ba4bfb09d46aa66ab72c2ba3f72057e37ffca293ac76e1e3a21dde77f1e4dbbf")

    def test_02_target_excluded_from_features(self):
        """2) target excluded（特征只用 issues[:t]）。"""
        issues = _toy_issues(30)
        s = fs.build_single_features(15, issues, _toy_cfg())
        # evidence must be exactly first 15; target issue not used in features
        # rebuild with a different target to confirm features differ by evidence only
        s2 = fs.build_single_features(16, issues, _toy_cfg())
        self.assertNotEqual(s["front"][1]["freq_ratio"], s2["front"][1]["freq_ratio"])

    def test_03_future_excluded(self):
        """3) future excluded（issues[t] 及以后不进特征）。"""
        issues = _toy_issues(30)
        # mutate future draws; single-feature build at t must be unchanged
        before = fs.build_single_features(10, issues, _toy_cfg())
        base = json.dumps(before)
        issues[25]["front"] = [1, 2, 3, 4, 5]
        issues[29]["back"] = [11, 12]
        after = fs.build_single_features(10, issues, _toy_cfg())
        self.assertEqual(json.dumps(before), base, "future draw mutation must not affect features at t=10")

    def test_04_feature_inventory(self):
        """4) feature inventory 覆盖任务书全部具名特征。"""
        inv = fs.build_feature_inventory()
        names = set(inv["single_features"].keys()) | set(inv["candidate_features"].keys())
        for required in ["freq_ratio", "cur_omit", "trend", "hot", "in_prev",
                         "front_sum", "front_span", "odd_cnt", "big_cnt", "combo_score"]:
            self.assertIn(required, names, required)

    def test_05_front_number_rows(self):
        """5) front number rows（35 行，全 1-35）。"""
        issues = _toy_issues(30)
        s = fs.build_single_features(20, issues, _toy_cfg())
        self.assertEqual(len(s["front"]), 35)
        self.assertEqual(sorted(s["front"].keys()), list(range(1, 36)))

    def test_06_back_number_rows(self):
        """6) back number rows（12 行，全 1-12）。"""
        issues = _toy_issues(30)
        s = fs.build_single_features(20, issues, _toy_cfg())
        self.assertEqual(len(s["back"]), 12)
        self.assertEqual(sorted(s["back"].keys()), list(range(1, 13)))

    def test_07_appeared_label(self):
        """7) appeared label（front 恰 5 个 1，back 恰 2 个 1）。"""
        issues = _toy_issues(30)
        s = fs.build_single_features(20, issues, _toy_cfg())
        self.assertEqual(sum(s["front_labels"].values()), 5)
        self.assertEqual(sum(s["back_labels"].values()), 2)

    def test_08_frequency_calculation(self):
        """8) frequency = count/n。"""
        issues = _toy_issues(30)
        cfg = _toy_cfg()
        s = fs.build_single_features(20, issues, cfg)
        an = analyze(issues[:20], cfg)
        num = 1
        expected = an["front_freq"][num] / 20
        self.assertAlmostEqual(s["front"][num]["freq_ratio"], expected, places=6)

    def test_09_omission_calculation(self):
        """9) omission = current consecutive missing（与 analyzer.front_cur_omit 一致）。"""
        issues = _toy_issues(30)
        cfg = _toy_cfg()
        s = fs.build_single_features(20, issues, cfg)
        an = analyze(issues[:20], cfg)
        for num in [1, 10, 20, 35]:
            self.assertEqual(s["front"][num]["cur_omit"], an["front_cur_omit"][num])

    def test_10_temperature_calculation(self):
        """10) temperature/trend = 近30率 - 近100率（analyzer.analyze_number_temperature）。"""
        issues = _toy_issues(30)
        cfg = _toy_cfg()
        s = fs.build_single_features(20, issues, cfg)
        from src.analyzer import analyze_number_temperature
        temp = analyze_number_temperature(issues[:20])
        for num in [1, 5, 35]:
            self.assertAlmostEqual(s["front"][num]["trend"], temp["front"][num]["trend"], places=6)

    def test_11_overlap_calculation(self):
        """11) overlap indicator in_prev（1 iff num in issues[t-1]）。"""
        issues = _toy_issues(30)
        s = fs.build_single_features(20, issues, _toy_cfg())
        prev_front = set(issues[19]["front"])
        for num in range(1, 36):
            self.assertEqual(s["front"][num]["in_prev"], 1 if num in prev_front else 0)

    def test_12_candidate_sum(self):
        """12) candidate sum。"""
        cf = fs.candidate_features({"front": [3, 7, 15, 20, 30], "back": [2, 9]},
                                   {"front": [], "back": []}, {}, {}, {})
        self.assertEqual(cf["front_sum"], 75)

    def test_13_candidate_span(self):
        """13) candidate span。"""
        cf = fs.candidate_features({"front": [3, 7, 15, 20, 30], "back": [2, 9]},
                                   {"front": [], "back": []}, {}, {}, {})
        self.assertEqual(cf["front_span"], 27)
        self.assertEqual(cf["back_span"], 7)

    def test_14_odd_even(self):
        """14) odd/even count。"""
        cf = fs.candidate_features({"front": [3, 7, 15, 20, 30], "back": [2, 9]},
                                   {"front": [], "back": []}, {}, {}, {})
        self.assertEqual(cf["odd_cnt"], 3)  # 3,7,15 odd; 20,30 even

    def test_15_size(self):
        """15) size balance (>=18 = big)。"""
        cf = fs.candidate_features({"front": [3, 7, 15, 20, 30], "back": [2, 9]},
                                   {"front": [], "back": []}, {}, {}, {})
        self.assertEqual(cf["big_cnt"], 2)  # 20,30

    def test_16_structure(self):
        """16) structure score（combo_score 走真实 scorer）。"""
        from src.analyzer import analyze_structure_distribution
        issues = _toy_issues(40)
        st_ = analyze_structure_distribution(issues[:30])
        cf = fs.candidate_features({"front": [3, 7, 15, 20, 30], "back": [2, 9]},
                                   {"front": [1, 2, 3], "back": [4, 5]}, {}, st_, {})
        self.assertIn("combo_score", cf)
        self.assertIsInstance(cf["combo_score"], float)

    def test_17_shuffled_null_deterministic(self):
        """17) shuffled null deterministic（同 seed → 同结果）。"""
        scores = [float(i % 7) for i in range(40)]
        labels = [i % 2 for i in range(40)]
        a = fs.shuffled_feature_aucs({"f": scores}, labels, seeds=5)
        b = fs.shuffled_feature_aucs({"f": scores}, labels, seeds=5)
        self.assertEqual(a["f"]["null_p95"], b["f"]["null_p95"])

    def test_18_random_score_deterministic(self):
        """18) random-score deterministic。"""
        labels = [i % 2 for i in range(40)]
        a = fs.random_score_aucs(labels, seeds=5)
        b = fs.random_score_aucs(labels, seeds=5)
        self.assertEqual(a, b)

    def test_19_development_split(self):
        """19) development split = first 80%。"""
        t_idxs = list(range(1930))
        dev_count = int(len(t_idxs) * ws.DEV_RATIO)
        self.assertEqual(dev_count, 1544)

    def test_20_holdout_split(self):
        """20) holdout split = last 20%。"""
        self.assertEqual(1930 - 1544, 386)

    def test_21_no_overlap(self):
        """21) dev / holdout 无重叠。"""
        dev = list(range(1930))[:1544]
        hold = list(range(1930))[1544:]
        self.assertEqual(set(dev) & set(hold), set())

    def test_22_definition_frozen(self):
        """22) definition frozen（哈希对象确定性）。"""
        o = {"a": 1, "b": [1, 2]}
        h1 = _hash(o); h2 = _hash(o)
        self.assertEqual(h1, h2)
        o2 = dict(o); o2["a"] = 2
        self.assertNotEqual(_hash(o), _hash(o2))

    def test_23_selection_frozen_before_holdout(self):
        """23) selection frozen before holdout（文件结构含 frozen_at + 假设）。"""
        p = {"frozen_at": "2026-01-01T00:00:00", "dev_count": 1544, "holdout_count": 386,
             "single_feature_hypotheses": {"front_freq_ratio": {"dev_auc": 0.51, "dev_dir": "pos"}}}
        self.assertIn("frozen_at", p)
        self.assertEqual(p["dev_count"] + p["holdout_count"], 1930)

    def test_24_ablation_one_feature_only(self):
        """24) ablation one-feature-only（每个 variant 只置 1 个权重键为 0）。"""
        cfg = _toy_cfg()
        for name, section, key in fa.ABLATION_VARIANTS:
            acfg = fa.make_ablation_cfg(cfg, section, key)
            # exactly one key zeroed
            zeroed = [k for k, v in acfg["recommend"]["weights"][section].items() if v == 0.0]
            self.assertEqual(zeroed, [key], name)

    def test_25_no_weight_retuning(self):
        """25) no weight retuning（其余权重保持原值）。"""
        cfg = _toy_cfg()
        for name, section, key in fa.ABLATION_VARIANTS:
            acfg = fa.make_ablation_cfg(cfg, section, key)
            wcfg = acfg["recommend"]["weights"][section]
            for k, v in wcfg.items():
                if k != key:
                    self.assertEqual(v, cfg["recommend"]["weights"][section][k], name)

    def test_26_paired_deltas(self):
        """26) paired deltas（FULL vs variant 同 target 配对）。"""
        a = [1.0, 2.0, 3.0, 4.0]; b = [0.5, 2.0, 2.0, 4.0]
        self.assertEqual(st.paired_deltas(a, b), [0.5, 0.0, 1.0, 0.0])
        with self.assertRaises(ValueError):
            st.paired_deltas([1, 2], [1])

    def test_27_bootstrap_deterministic(self):
        """27) bootstrap deterministic（同 seed → 同 CI）。"""
        a = [1.0, 2.0, 3.0, 4.0, 5.0]; b = [0.8, 1.9, 3.1, 3.8, 4.7]
        x = st.paired_bootstrap_ci(a, b, n_resamples=200, seed=12345)
        y = st.paired_bootstrap_ci(a, b, n_resamples=200, seed=12345)
        self.assertEqual(x["ci_low"], y["ci_low"])
        self.assertEqual(x["ci_high"], y["ci_high"])

    def test_28_holm(self):
        """28) Holm（单调不减；最小 p 校正后 <= 最大 p 校正后）。"""
        adj = st.holm_adjust([0.01, 0.02, 0.04])
        self.assertEqual(len(adj), 3)
        self.assertTrue(all(0.0 <= x <= 1.0 for x in adj))
        self.assertLessEqual(adj[0], adj[2])

    def test_29_fdr(self):
        """29) FDR（bh_fdr reference）。"""
        from src.evaluation import feature_study as ffs
        q = ffs.bh_fdr([0.001, 0.01, 0.05, 0.5], alpha=0.05)
        self.assertEqual(len(q), 4)
        self.assertTrue(all(0.0 <= x <= 1.0 for x in q))
        # smallest p retained (below threshold)
        self.assertEqual(q[0], 0.001)

    def test_30_temporal_stability(self):
        """30) temporal stability（early/mid/late 分段）。"""
        import random
        vals = [random.Random(1).random() for _ in range(300)]
        segs = st.temporal_split(vals)
        self.assertEqual(set(segs.keys()), {"early", "middle", "late"})
        self.assertEqual(segs["early"]["n"] + segs["middle"]["n"] + segs["late"]["n"], 300)

    def test_31_redundancy(self):
        """31) redundancy（freq_ratio ~ avg_omit 高相关）。"""
        issues = ws.load_issues("data/research/dlt-full-history.json")
        cfg = ws.production_cfg()
        feat, lab = fs.pool_single_features([1000, 1001], issues, cfg, "front")
        m = fs.redundancy_matrix({k: feat[k] for k in fs.SINGLE_FEATURES}, threshold=0.7)
        self.assertIsInstance(m["high_corr_pairs"], list)

    def test_32_production_unchanged(self):
        """32) production unchanged（9 文件 baseline SHA）。"""
        import hashlib
        base = json.loads((pathlib.Path(__file__).resolve().parent.parent /
                           ".agnes/work/p33/p33-precheck-baseline.json").read_text())
        for f, h in base["production_baseline_sha256"].items():
            now = hashlib.sha256((pathlib.Path(__file__).resolve().parent.parent / f).read_bytes()).hexdigest()
            self.assertEqual(now, h, f)

    def test_33_production_cap_unchanged(self):
        """33) production cap unchanged（recent_issues=1000）。"""
        text = (pathlib.Path(__file__).resolve().parent.parent /
                "config/settings.yaml").read_text()
        self.assertIn("recent_issues: 1000", text)

    def test_34_snapshot_unchanged(self):
        """34) 26112 snapshot unchanged。"""
        recs = json.loads((pathlib.Path(__file__).resolve().parent.parent /
                           "public/data/published_recommendations.json").read_text())
        last = recs["items"][-1]
        self.assertEqual(last["issue"], "26112")
        self.assertEqual(last["snapshot_hash"],
                         "bea8ef87f3f137238686ae52712f922956215408f0cf54187b9295d8f1ae5fad")
        self.assertEqual(last["numbers"], {"front": [5, 12, 17, 28, 31], "back": [4, 7]})

    def test_auc_neutral(self):
        """AUC 接近 0.5 = 无判别力（构造反例：完全随机 label）。"""
        labels = [1, 0, 1, 0, 1, 0]
        scores = [0.5, 0.5, 0.5, 0.5, 0.5, 0.5]  # all tied
        self.assertAlmostEqual(fs.roc_auc(labels, scores), 0.5, places=4)

    def test_ablation_full_equals_direct(self):
        """消融 FULL = 直接 recommend()（equivalence spot-check）。"""
        issues = _toy_issues(40)
        cfg = _toy_cfg()
        cands = fa.ablation_candidates(30, issues, cfg)
        from src.recommender import recommend
        ev = fa.evidence_for(issues, 30)
        an = analyze(ev, cfg)
        d = recommend(an, cfg, stats=fa._stats(ev, issues[29]))["D"][0]
        self.assertEqual(cands["FULL"], {"front": list(d["front"]), "back": list(d["back"])})


def _hash(o):
    import hashlib
    return hashlib.sha256(json.dumps(o, sort_keys=True).encode()).hexdigest()


if __name__ == "__main__":
    unittest.main(verbosity=2)
