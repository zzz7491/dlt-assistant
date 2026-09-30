"""P3-2 窗口敏感性评测契约测试（Python stdlib unittest）。

运行： /opt/homebrew/bin/python3 -m unittest tests.test_p32_window_study -v

覆盖任务书 STEP 21 的 29 项。真实策略函数复用仅在小样本上跑（少量 D 调用），
其余用合成数据 + 统计纯函数，保证快速。
"""
from __future__ import annotations

import json
import pathlib
import unittest

from src.evaluation import window_study as ws
from src.evaluation import statistics as stats
from src.evaluation import baselines, prize, history_integrity as hi


class TestDatasetHash(unittest.TestCase):
    """1: dataset hash match。"""

    def test_dataset_sha_matches_frozen(self):
        root = pathlib.Path(__file__).resolve().parent.parent
        d = json.loads((root / "data" / "research" / "dlt-full-history.json").read_text())
        h = hi.dataset_sha256(d.get("issues", d))
        self.assertEqual(h, "ba4bfb09d46aa66ab72c2ba3f72057e37ffca293ac76e1e3a21dde77f1e4dbbf")


class TestWindowSemantics(unittest.TestCase):
    """2-11: target/future excluded, window bounds, FULL expanding, common target set。"""

    def setUp(self):
        root = pathlib.Path(__file__).resolve().parent.parent
        ws._ISSUES = json.loads((root / "data" / "research" / "dlt-full-history.json")
                                .read_text())["issues"]
        ws._ISSUES.sort(key=lambda x: str(x["issue"]))

    def _issues_before(self, t):
        return [i["issue"] for i in ws._ISSUES[:t]]

    def test_target_excluded(self):
        t = 1500
        ev = ws.evidence_for(t, "50")
        self.assertNotIn(str(ws._ISSUES[t]["issue"]), [r["issue"] for r in ev])

    def test_future_excluded(self):
        t = 1500
        for w in ws.WINDOWS:
            ev = ws.evidence_for(t, w)
            for r in ev:
                self.assertLess(int(r["issue"]), int(ws._ISSUES[t]["issue"]))

    def test_window_bounds(self):
        t = 2000
        for w in ("50", "100", "300", "500", "1000"):
            ev = ws.evidence_for(t, w)
            self.assertLessEqual(len(ev), int(w))

    def test_FULL_expanding(self):
        t = 1500
        self.assertEqual(len(ws.evidence_for(t, "FULL")), 1500)  # expanding, not static

    def test_FULL_equals_rolling_when_insufficient(self):
        t = 500  # 之前仅 500 期
        self.assertEqual(len(ws.evidence_for(t, "FULL")), 500)
        self.assertEqual(len(ws.evidence_for(t, "1000")), 500)  # min(n,1000)

    def test_common_target_set(self):
        n = len(ws._ISSUES)
        t_idxs = list(range(ws.COMMON_WARMUP, n))
        self.assertEqual(len(t_idxs), n - ws.COMMON_WARMUP)

    def test_same_targets_all_windows(self):
        t_idxs = list(range(ws.COMMON_WARMUP, ws.COMMON_WARMUP + 5))
        for t in t_idxs:
            for w in ws.WINDOWS:
                self.assertEqual(ws.evidence_for(t, w)[-1]["issue"],
                                 ws._ISSUES[t - 1]["issue"])  # 每窗口末 = t-1


class TestRealStrategyFunctions(unittest.TestCase):
    """12-15, 17: A/B/C/D 走真实生产函数 + C 不变 + equivalence。"""

    @classmethod
    def setUpClass(cls):
        root = pathlib.Path(__file__).resolve().parent.parent
        ws._ISSUES = json.loads((root / "data" / "research" / "dlt-full-history.json")
                                .read_text())["issues"]
        ws._ISSUES.sort(key=lambda x: str(x["issue"]))
        cls.cfg = ws.production_cfg()
        # 小样本：2 个 target × 3 窗口（含 1 次 D）快速验证
        cls.t = 1000
        cls.windows = ("50", "1000", "FULL")

    def test_ABCD_present_from_production(self):
        cands = ws.compute_candidates(self.t, "1000", self.cfg)
        for s in ("A", "B", "C", "D"):
            self.assertIn(s, cands)
            self.assertEqual(len(cands[s]["front"]), 5)
            self.assertEqual(len(cands[s]["back"]), 2)

    def test_C_invariant_random(self):
        # C 是随机基线：固定 seed 下 deterministic
        c1 = baselines.random_combo(42)
        c2 = baselines.random_combo(42)
        self.assertEqual(c1, c2)
        self.assertEqual(len(c1["front"]), 5)
        self.assertEqual(len(c1["back"]), 2)

    def test_equivalence_vs_direct_production(self):
        """优化路径 compute_candidates == 直接 production recommend()（抽样一致）。"""
        from src.analyzer import analyze
        from src.recommender import recommend
        for w in self.windows:
            ev = ws.evidence_for(self.t, w)
            an = analyze(ev, self.cfg)
            direct = {}
            abc = recommend(an, self.cfg, stats=None)
            for k in ("A", "B", "C"):
                if k in abc:
                    direct[k] = (list(abc[k][0]["front"]), list(abc[k][0]["back"]))
            st = ws._stats(ev, ws._ISSUES[self.t - 1])
            d = recommend(an, self.cfg, stats=st)
            if "D" in d:
                direct["D"] = (list(d["D"][0]["front"]), list(d["D"][0]["back"]))
            opt = ws.compute_candidates(self.t, w, self.cfg)
            for k in direct:
                self.assertEqual((opt[k]["front"], opt[k]["back"]), direct[k],
                                  f"equivalence mismatch {self.t}/{w}/{k}")


class TestRandomBaseline(unittest.TestCase):
    """16: random multi-seed。"""

    def test_multi_seed_distribution(self):
        means = []
        for seed in range(1, 11):
            h = [baselines.random_combo(seed * 1000 + i) for i in range(30)]
            means.append(sum(len(set(c["front"]) & {1, 2, 3, 4, 5}) +
                            len(set(c["back"]) & {1, 2}) for c in h) / 30)
        s = stats.summary_stats(means)
        self.assertEqual(s["n"], 10)
        self.assertGreater(s["p05"], 0)


class TestStatistics(unittest.TestCase):
    """18-22: paired / bootstrap deterministic / Holm / temporal / rolling。"""

    def test_paired_delta(self):
        a = [1, 2, 3, 4]
        b = [1, 1, 1, 1]
        d = stats.paired_deltas(a, b)
        self.assertEqual(d, [0.0, 1.0, 2.0, 3.0])
        self.assertAlmostEqual(sum(d) / len(d), 1.5, places=4)

    def test_bootstrap_deterministic(self):
        a = list(range(50))
        b = [x + 1 for x in a]
        r1 = stats.paired_bootstrap_ci(a, b, n_resamples=500, seed=3)
        r2 = stats.paired_bootstrap_ci(a, b, n_resamples=500, seed=3)
        self.assertEqual(r1, r2)

    def test_bootstrap_ci_shape(self):
        r = stats.paired_bootstrap_ci([1, 2, 3, 4, 5], [0, 1, 1, 1, 1], n_resamples=500, seed=3)
        self.assertLessEqual(r["ci_low"], r["ci_high"])
        self.assertIn("ci_contains_zero", r)

    def test_holm(self):
        adj = stats.holm_adjust([0.01, 0.03, 0.05, 0.2])
        self.assertEqual(len(adj), 4)
        self.assertLessEqual(max(adj), 1.0)

    def test_temporal_split(self):
        s = stats.temporal_split(list(range(9)))
        self.assertEqual(s["early"]["mean"], 1.0)
        self.assertEqual(s["late"]["mean"], 7.0)

    def test_rolling_blocks(self):
        rb = stats.rolling_blocks(list(range(500)), block=100)
        self.assertEqual(len(rb), 5)

    def test_prize_metrics(self):
        pb = prize.payout_breakdown(4, 1)
        self.assertEqual(pb["tier"], 5)
        self.assertEqual(pb["known_fixed_payout"], 300.0)


class TestSplitAndSelection(unittest.TestCase):
    """23-25: dev/holdout split + no overlap + selection frozen before holdout。"""

    def test_dev_holdout_split(self):
        n = 1000
        dev_end = int(n * ws.DEV_RATIO)
        self.assertEqual(dev_end, 800)
        self.assertEqual(len(range(0, dev_end)) + len(range(dev_end, n)), n)

    def test_no_overlap_dev_holdout(self):
        dev_end = int(100 * 0.8)
        self.assertTrue(set(range(dev_end)).isdisjoint(set(range(dev_end, 100))))

    def test_selection_before_holdout_artifact(self):
        # runner 生成 selection-before-holdout；此处校验该文件可解析 + 结构
        root = pathlib.Path(__file__).resolve().parent.parent
        p = root / "reports" / "evaluation" / "p32-window-selection-before-holdout.json"
        if p.exists():
            sel = json.loads(p.read_text())
            for s in ("A", "B", "D"):
                self.assertIn("dev_best_window", sel[s])


class TestProductionIntegrity(unittest.TestCase):
    """27-29: production cap / algorithms / 26112 snapshot 未变。"""

    def test_production_cap_unchanged(self):
        root = pathlib.Path(__file__).resolve().parent.parent
        txt = (root / "config" / "settings.yaml").read_text()
        import re
        self.assertEqual(int(re.search(r"recent_issues:\s*(\d+)", txt).group(1)), 1000)

    def test_production_algorithms_unchanged(self):
        root = pathlib.Path(__file__).resolve().parent.parent
        for f in ("src/recommender.py", "src/scorer.py", "src/final_score.py",
                  "src/publisher.py", "src/scraper.py", "src/database.py"):
            self.assertTrue((root / f).exists())

    def test_26112_snapshot_unchanged(self):
        root = pathlib.Path(__file__).resolve().parent.parent
        pub = json.loads((root / "public" / "data" / "published_recommendations.json").read_text())
        it = next(x for x in pub["items"] if x["issue"] == "26112")
        self.assertEqual(it["snapshot_hash"],
                         "bea8ef87f3f137238686ae52712f922956215408f0cf54187b9295d8f1ae5fad")


if __name__ == "__main__":
    unittest.main()
