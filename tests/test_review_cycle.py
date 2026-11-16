"""P4（2026-11-17 审计提案）：四彩种复盘闭环——程序核算错因 +
improvement/verdict 生成 + 下期 synthesize 喂回 guidance + prompt 存证。"""
import json
import random
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from src.common import ai_pick, review_cycle
from src.fc3d import stats as fc3d_stats

IMPROVEMENT = "把和值向中部收敛，补足高遗漏位的覆盖权重。"


def _fc3d_history(n=120):
    rng = random.Random(42)
    rows = []
    for i in range(n):
        rows.append({
            "issue": f"{2026001 + i:07d}",
            "date": "2026-01-01",
            "digits": [rng.randrange(10) for _ in range(3)],
        })
    return rows


def _fake_request_improvement(game_id, facts, prior):
    return {"improvement": IMPROVEMENT,
            "verdict": "上期改进在本期推荐中已落实，和值已向中部收敛。",
            "model": "TEST-fixture"}


class CausesTests(unittest.TestCase):
    def test_digit_causes(self):
        hits, causes = review_cycle.compute_causes(
            "fc3d", {"digits": [0, 0, 0]}, {"digits": [9, 9, 8]}, [])
        codes = {c["code"] for c in causes}
        self.assertEqual(hits["position_hits"], 0)
        self.assertIn("sum_bias", codes)
        self.assertIn("no_position_hit", codes)

    def test_ssq_causes(self):
        hits, causes = review_cycle.compute_causes(
            "ssq", {"red": [1, 2, 3, 4, 5, 6], "blue": 1},
            {"red": [28, 29, 30, 31, 32, 33], "blue": 2}, [])
        codes = {c["code"] for c in causes}
        self.assertEqual(hits["red_hits"], 0)
        self.assertFalse(hits["blue_hit"])
        self.assertIn("far_miss", codes)
        self.assertIn("blue_miss", codes)

    def test_validate_improvement(self):
        allowed = {Decimal(3), Decimal(5)}
        ok = {"improvement": "下一批推荐把和值向中部收敛，补足覆盖避免整体失衡。", "verdict": ""}
        self.assertEqual(review_cycle.validate_improvement(ok, allowed)["improvement"],
                         ok["improvement"])
        with self.assertRaises(ValueError):
            review_cycle.validate_improvement(
                {"improvement": "下期保证中奖，把和值向中部收敛补足覆盖。", "verdict": ""}, allowed)
        with self.assertRaises(ValueError):
            review_cycle.validate_improvement(
                {"improvement": "下一批推荐前区至少命中9个号，和值向中部收敛。", "verdict": ""}, allowed)


class EnsureReviewsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patch_root = patch.object(review_cycle, "ROOT", Path(self.tmp.name))
        self.patch_root.start()
        self.history = _fc3d_history()

    def tearDown(self):
        self.patch_root.stop()
        self.tmp.cleanup()

    def _fetch(self, issue):
        return [
            {"strategy": "A-均衡统计型", "digits": [1, 2, 3]},
            {"strategy": "F-综合AI型", "digits": [4, 5, 6]},
        ]

    def test_three_periods_chain_and_guidance_evidence(self):
        with patch.object(review_cycle, "request_improvement",
                          _fake_request_improvement):
            changed = review_cycle.ensure_reviews("fc3d", self.history, self._fetch)
        self.assertEqual(len(changed), 3)
        issues = [r["issue"] for r in changed]
        self.assertEqual(issues, [self.history[-3]["issue"],
                                  self.history[-2]["issue"],
                                  self.history[-1]["issue"]])
        for record in changed:
            self.assertEqual(record["strategy"], "F-综合AI型")  # 结算唯一推荐 F
            self.assertTrue(record["causes"])
            self.assertEqual(record["improvement"]["text"], IMPROVEMENT)
        # 第二期起 verdict 验收上期改进
        self.assertIsNone(changed[0]["verdict"])
        self.assertEqual(changed[1]["verdict"]["on_issue"], issues[0])
        self.assertEqual(changed[2]["verdict"]["on_issue"], issues[1])
        # 归档落盘 + 喂回查询
        archive = review_cycle.load_archive("fc3d")
        self.assertEqual(len(archive["reviews"]), 3)
        target = "2026121"
        self.assertEqual(review_cycle.latest_improvement("fc3d", target), IMPROVEMENT)
        # 下期 F 合成 prompt 存证中能查到 improvement 原文
        seen = {}

        def fake_call(game_id, target_issue, prompt, tag, local=False):
            seen["prompt"] = prompt
            return {"digits": [1, 2, 3]}

        picks = [{"strategy": "A-均衡统计型", "digits": [1, 2, 3]},
                 {"strategy": "B-冷热组合型", "digits": [4, 5, 6]}]
        with patch.object(ai_pick, "_call", fake_call):
            out = fc3d_stats.generate_synth_ai(target, picks)
        self.assertIsNotNone(out)
        self.assertIn(IMPROVEMENT, seen["prompt"])
        evidence = review_cycle.load_archive("fc3d")["synth_evidence"]
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0]["target_issue"], target)
        self.assertIn(IMPROVEMENT, evidence[0]["prompt"])
        self.assertEqual(evidence[0]["guidance"], IMPROVEMENT)

    def test_llm_failure_keeps_causes_and_retries_next_run(self):
        def boom(game_id, facts, prior):
            raise RuntimeError("invalid_response")

        with patch.object(review_cycle, "request_improvement", boom):
            changed = review_cycle.ensure_reviews("fc3d", self.history, self._fetch)
        self.assertEqual(len(changed), 3)
        for record in changed:
            self.assertTrue(record["causes"])          # 程序错因照常落盘
            self.assertIsNone(record["improvement"])    # improvement 留空待补
        self.assertIsNone(review_cycle.latest_improvement("fc3d", "2026121"))
        # 下一轮 LLM 恢复 → 补齐 improvement（不重复建记录）
        with patch.object(review_cycle, "request_improvement",
                          _fake_request_improvement):
            changed2 = review_cycle.ensure_reviews("fc3d", self.history, self._fetch)
        self.assertEqual(len(changed2), 3)
        self.assertEqual(len(review_cycle.load_archive("fc3d")["reviews"]), 3)
        self.assertEqual(review_cycle.latest_improvement("fc3d", "2026121"), IMPROVEMENT)

    def test_review_sql_shape(self):
        record = {"issue": "2026120", "improvement": {"text": IMPROVEMENT}}
        lines = review_cycle.review_sql("fc3d", [record])
        self.assertIn("fc3d_reviews", lines[0])
        self.assertTrue(any("INSERT OR REPLACE INTO fc3d_reviews" in x for x in lines))


if __name__ == "__main__":
    unittest.main()
