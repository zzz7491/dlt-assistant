"""Phase 11-D3.1 单元测试：src/final_score.py 融合层。

覆盖：
- 五因子融合（stable 全权重，手算期望值）
- 样本量三阶段降级（cold / transition / stable 权重与 primary 行为）
- 冷启动 primary 锁定 D（即使 D 评分最低）
- 失败安全回退（异常输入 → 原样返回）
- 风险惩罚规则与封顶
- 边界：空列表 / 缺号码字段 / 缺失输入中性化 / 入参不被修改

运行：python -m unittest discover -s tests -v
"""
import copy
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.final_score import (  # noqa: E402
    DEFAULT_WEIGHTS, MIN_SAMPLE, FULL_SAMPLE, NEUTRAL, RISK_CAP,
    _normalize_weights, _risk_penalty, _stage, compute_final_scores,
)


def _recs():
    return [
        {"strategy": "A-均衡统计型", "front": [2, 7, 20, 24, 31], "back": [4, 10]},
        {"strategy": "B-冷热组合型", "front": [4, 11, 19, 20, 24], "back": [5, 8]},
        {"strategy": "C-纯随机娱乐型", "front": [4, 5, 7, 14, 26], "back": [6, 12]},
        {"strategy": "D-综合评分型", "front": [13, 18, 21, 23, 28], "back": [6, 12]},
    ]


class TestStageAndWeights(unittest.TestCase):
    def test_stage_boundaries(self):
        self.assertEqual(_stage(0), "cold")
        self.assertEqual(_stage(MIN_SAMPLE - 1), "cold")
        self.assertEqual(_stage(MIN_SAMPLE), "transition")
        self.assertEqual(_stage(FULL_SAMPLE - 1), "transition")
        self.assertEqual(_stage(FULL_SAMPLE), "stable")

    def test_cold_weights_zero_history_recent(self):
        w = _normalize_weights(None, "cold")
        self.assertEqual(w["history"], 0.0)
        self.assertEqual(w["recent"], 0.0)
        # 四加权键之和 = 1 - risk 归一份额（risk 直接叠加、不参与加权）
        self.assertAlmostEqual(sum(w.values()) + 0.05 / 0.65, 1.0, places=9)
        # 重分配比例：归一化分母含 risk（0.40+0.20+0.05=0.65）
        self.assertAlmostEqual(w["base"], 0.40 / 0.65, places=9)
        self.assertAlmostEqual(w["structure"], 0.20 / 0.65, places=9)

    def test_transition_decay(self):
        w = _normalize_weights(None, "transition")
        # 衰减后五键 = 0.40 + 0.10 + 0.075 + 0.20 + 0.05 = 0.825，全量归一化
        self.assertAlmostEqual(w["history"], 0.10 / 0.825, places=9)
        self.assertAlmostEqual(w["recent"], 0.075 / 0.825, places=9)
        self.assertAlmostEqual(sum(w.values()) + 0.05 / 0.825, 1.0, places=9)

    def test_stable_weights_match_defaults(self):
        w = _normalize_weights(None, "stable")
        for k in ("base", "history", "recent", "structure"):
            self.assertAlmostEqual(w[k], DEFAULT_WEIGHTS[k], places=9)

    def test_custom_weights_clamped_to_known_keys(self):
        w = _normalize_weights({"base": 0.8, "hack": 99.0}, "stable")
        # 归一化分母 = 0.8+0.2+0.15+0.2+0.05 = 1.4；四加权键之和 = 1 - 0.05/1.4
        self.assertAlmostEqual(sum(w.values()) + 0.05 / 1.4, 1.0, places=9)
        self.assertNotIn("hack", w)


class TestStableFusion(unittest.TestCase):
    def test_manual_expected_value(self):
        """stable 阶段手算：A 组 base=68, history=50, recent=100, structure=50, risk=0
        final = 0.40*68 + 0.20*50 + 0.15*100 + 0.20*50 = 62.2"""
        recs = [{"strategy": "A-均衡统计型", "front": [2, 7, 20, 24, 31], "back": [4, 10]}]
        out = compute_final_scores(
            recs, effective_sample=12,
            strategy_rank={"A": 1},
            history_map={"A": 3.5},          # 3.5/7 → 50
            recent_map={"A": [7]},           # 7/7 → 100
        )
        self.assertAlmostEqual(out[0]["final_score"], 62.2, places=2)
        self.assertFalse(out[0]["final_breakdown"]["degraded"])
        self.assertEqual(out[0]["final_rank"], 1)
        self.assertTrue(out[0]["is_primary"])

    def test_cross_strategy_ranking_and_single_primary(self):
        out = compute_final_scores(
            _recs(), effective_sample=12,
            strategy_rank={"A": 1, "B": 2, "C": 3, "D": 4},
            history_map={"A": 4.0, "B": 1.0, "C": 2.0, "D": 3.0},
            recent_map={"A": [3, 4], "B": [0], "C": [1], "D": [2]},
        )
        ranks = [it.get("final_rank") for it in out]
        self.assertEqual(sorted(r for r in ranks if r), [1, 2, 3, 4])
        self.assertEqual(sum(1 for it in out if it["is_primary"]), 1)
        # A 各分量最高 → 应排第一
        a = next(it for it in out if it["strategy"].startswith("A"))
        self.assertEqual(a["final_rank"], 1)
        self.assertTrue(a["is_primary"])


class TestColdStart(unittest.TestCase):
    def test_cold_locks_primary_to_d_even_if_lowest(self):
        """冷启动：D 评分分量最低，is_primary 仍锁定 D，并标记 locked_cold_start。"""
        out = compute_final_scores(
            _recs(), effective_sample=2,
            strategy_rank={"A": 1, "B": 2, "C": 3, "D": 4},
            history_map={"A": 5.0, "B": 4.0, "C": 3.0, "D": 0.5},
        )
        d = next(it for it in out if it["strategy"].startswith("D"))
        self.assertTrue(d["is_primary"])
        self.assertTrue(d["final_breakdown"].get("locked_cold_start"))
        self.assertTrue(all(it["final_breakdown"]["degraded"] for it in out))
        self.assertTrue(all(it["final_breakdown"]["stage"] == "cold" for it in out))
        # 冷启动下 history/recent 权重为 0：D 分量低不应影响 base+structure 主导的排名
        a = next(it for it in out if it["strategy"].startswith("A"))
        self.assertGreater(a["final_score"], d["final_score"])

    def test_cold_without_d_falls_back_to_rank1(self):
        recs = [r for r in _recs() if not r["strategy"].startswith("D")]
        out = compute_final_scores(recs, effective_sample=1)
        primaries = [it for it in out if it["is_primary"]]
        self.assertEqual(len(primaries), 1)
        self.assertEqual(primaries[0]["final_rank"], 1)
        self.assertFalse(primaries[0]["final_breakdown"].get("locked_cold_start", False))


class TestRiskPenalty(unittest.TestCase):
    def test_repeat_front_penalty(self):
        prev = {"front": [2, 7, 20, 24, 31], "back": [1, 2]}
        combo = {"front": [2, 7, 20, 24, 9], "back": [3, 4]}  # 重复 4 个
        self.assertEqual(_risk_penalty(combo, prev, None), -30.0)

    def test_extreme_shapes(self):
        all_odd_mixed_size = {"front": [1, 3, 19, 21, 23], "back": [1, 2]}  # 奇偶 5:0（-15），大小 3:2 正常
        self.assertEqual(_risk_penalty(all_odd_mixed_size, None, None), -15.0)
        all_big = {"front": [19, 21, 23, 25, 27], "back": [1, 2]}  # 奇偶 5:0（-15）+ 大小 5:0（-15）
        self.assertEqual(_risk_penalty(all_big, None, None), -30.0)

    def test_sum_outlier(self):
        stats = {"front_sum": {"p5": 60, "p95": 120}}
        low = {"front": [1, 2, 3, 4, 5], "back": [1, 2]}      # 和值 15 < 60
        self.assertLessEqual(_risk_penalty(low, None, stats), -10.0)
        mid = {"front": [10, 20, 25, 28, 30], "back": [1, 2]}  # 和值 113 在区间内
        self.assertEqual(_risk_penalty(mid, None, stats), 0.0)

    def test_penalty_cap(self):
        # 与上期重复 4 个（-30）+ 全奇（-15）→ 叠加 -45 → 封顶 -40
        prev = {"front": [1, 3, 5, 7, 9], "back": [1, 2]}
        combo = {"front": [1, 3, 5, 7, 11], "back": [1, 2]}
        self.assertEqual(_risk_penalty(combo, prev, None), RISK_CAP)

    def test_repeat_only_below_cap(self):
        prev = {"front": [2, 7, 20, 24, 31], "back": [1, 2]}
        combo = {"front": [2, 7, 20, 24, 9], "back": [3, 4]}  # 仅重复 4（-30），形态正常
        self.assertEqual(_risk_penalty(combo, prev, None), -30.0)

    def test_final_floor_zero(self):
        combo = {"front": [2, 7, 20, 24, 1], "back": [1, 2]}
        out = compute_final_scores(
            [{"strategy": "A-x", "front": combo["front"], "back": combo["back"]}],
            effective_sample=12, prev_draw={"front": [2, 7, 20, 24, 31]},
        )
        self.assertGreaterEqual(out[0]["final_score"], 0.0)


class TestStructureAndNeutral(unittest.TestCase):
    def test_no_ctx_structure_neutral(self):
        out = compute_final_scores(_recs(), effective_sample=12)
        for it in out:
            self.assertEqual(it["final_breakdown"]["structure"], NEUTRAL)

    def test_structure_ctx_uses_scorer(self):
        """提供最小 ctx：scorer 可用时应产出非中性结构分（不修改 scorer）。"""
        ctx = {
            "structure_stats": {
                "odd_even": {"奇3:偶2": 0.30},
                "big_small": {"大3:小2": 0.28},
                "zone_distribution": {"front": {"pct": [0.2] * 5, "labels": ["1-7", "8-14", "15-21", "22-28", "29-35"]}},
            },
            "sum_span_stats": {"front_sum": {"p25": 70, "p75": 110}},
        }
        combo = {"front": [3, 9, 16, 22, 30], "back": [5, 9]}  # 奇3偶2、大2小3、和值90
        out = compute_final_scores(
            [{"strategy": "A-x", "front": combo["front"], "back": combo["back"]}],
            effective_sample=12, structure_ctx=ctx,
        )
        self.assertNotEqual(out[0]["final_breakdown"]["structure"], NEUTRAL)


class TestFailSafe(unittest.TestCase):
    def test_non_list_returns_unchanged(self):
        for bad in (None, "x", 123, {"a": 1}):
            self.assertEqual(compute_final_scores(bad), bad)

    def test_empty_list(self):
        self.assertEqual(compute_final_scores([]), [])

    def test_missing_combo_fields_kept_unscored(self):
        recs = _recs() + [{"strategy": "E-坏数据"}]
        out = compute_final_scores(recs, effective_sample=12)
        bad = next(it for it in out if it["strategy"].startswith("E"))
        self.assertIsNone(bad["final_score"])
        self.assertIsNone(bad.get("final_rank"))
        self.assertFalse(bad["is_primary"])

    def test_missing_maps_use_neutral(self):
        out = compute_final_scores(_recs(), effective_sample=12)
        for it in out:
            self.assertEqual(it["final_breakdown"]["history"], NEUTRAL)
            self.assertEqual(it["final_breakdown"]["recent"], NEUTRAL)

    def test_input_records_not_mutated(self):
        recs = _recs()
        snapshot = copy.deepcopy(recs)
        compute_final_scores(recs, effective_sample=12, history_map={"A": 3.0})
        self.assertEqual(recs, snapshot)
        self.assertNotIn("final_score", recs[0])

    def test_exception_fallback_via_bad_weights_type(self):
        """内部异常路径：weights 非法类型不应让主入口抛错（失败安全回退）。"""
        recs = _recs()
        out = compute_final_scores(recs, effective_sample=12, weights="not-a-dict")
        self.assertEqual(len(out), 4)  # 非法键被过滤，正常打分而非崩溃


if __name__ == "__main__":
    unittest.main()
