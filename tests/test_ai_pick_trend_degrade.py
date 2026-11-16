"""P5（2026-11-17 审计提案）：走势分段链单段失败降级续跑 + diag 计数。

旧行为：任一段研判失败 → 整策略跳过（E 在生产近乎缺席的直接原因）。
新行为：单段整段重试一次 → 仍失败则缺段标注降级出号；全段失败降级
最近段原文直研判；失败/降级计数落盘 ai_pick_diag.json。
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.common import ai_pick, trend_data


def _trend(n=180):
    draws = [([1 + (i % 30), 2 + (i % 28), 3 + (i % 25), 4 + (i % 20), 5 + (i % 15)],
              [1 + (i % 11), 2 + (i % 10)]) for i in range(n)]
    return trend_data.ball_trend(draws, range(1, 36), range(1, 13))


class TrendDegradeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.diag = Path(self.tmp.name) / "ai_pick_diag.json"
        self.patches = [
            patch.object(ai_pick, "_DIAG_PATH", self.diag),
            patch.object(ai_pick, "_env_chain",
                         return_value=("KEY", "https://openrouter.ai/api/v1", ["m1"])),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def _diag_counts(self):
        return json.loads(self.diag.read_text(encoding="utf-8"))["counts"]["dlt"]

    def test_one_segment_missing_degrades_not_skips(self):
        seen = {}

        def chat(key, base, models, prompt, max_tokens=500):
            if "第 2/3 段" in prompt:
                return None
            return "本段研判要点示例文本。"

        def call(game_id, target_issue, prompt, tag, local=False):
            seen["prompt"] = prompt
            return {"front": [1, 2, 3, 4, 5], "back": [1, 2]}

        with patch.object(ai_pick, "_chat_text", chat), patch.object(ai_pick, "_call", call):
            out = ai_pick._pick_trend_segmented("dlt", "26132", _trend())
        self.assertIsNotNone(out)
        self.assertIn("第2段研判缺失", seen["prompt"])
        counts = self._diag_counts()
        self.assertEqual(counts["trend_segment_failed"], 1)
        self.assertEqual(counts["trend_degraded_missing_segments"], 1)

    def test_segment_retry_recovers(self):
        attempts = {"n": 0}

        def chat(key, base, models, prompt, max_tokens=500):
            if "第 1/3 段" in prompt:
                attempts["n"] += 1
                if attempts["n"] == 1:
                    return None
            return "本段研判要点示例文本。"

        def call(game_id, target_issue, prompt, tag, local=False):
            return {"front": [1, 2, 3, 4, 5], "back": [1, 2]}

        with patch.object(ai_pick, "_chat_text", chat), patch.object(ai_pick, "_call", call):
            out = ai_pick._pick_trend_segmented("dlt", "26132", _trend())
        self.assertIsNotNone(out)
        self.assertFalse(self.diag.exists())  # 无失败事件 → 无 diag 写入

    def test_all_segments_fail_falls_back_to_last_segment(self):
        seen = {}

        def call(game_id, target_issue, prompt, tag, local=False):
            seen["prompt"] = prompt
            return {"front": [1, 2, 3, 4, 5], "back": [1, 2]}

        with patch.object(ai_pick, "_chat_text", return_value=None), \
                patch.object(ai_pick, "_call", call):
            out = ai_pick._pick_trend_segmented("dlt", "26132", _trend())
        self.assertIsNotNone(out)
        self.assertIn("最近 60 期", seen["prompt"])  # 最近段原文直研判
        counts = self._diag_counts()
        self.assertEqual(counts["trend_segment_failed"], 3)
        self.assertEqual(counts["trend_degraded_last_segment_only"], 1)


if __name__ == "__main__":
    unittest.main()
