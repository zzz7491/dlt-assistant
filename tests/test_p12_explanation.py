"""P1-2 推荐理由引擎 —— stdlib unittest（不依赖 pytest / 第三方库）。

覆盖契约：
  - A/B/C/D 各策略正常输入都能生成真实、可追溯 explanation（summary/factors 非空）
  - C（random_baseline）诚实披露随机性，不出现伪造的统计依据
  - D 使用真实 basis/factors
  - explanation 确定性（同输入同输出）
  - 不含 banned 占位词（建设中/开发中/待完善/TODO/coming soon）
  - 无历史数据 → reason_status=unavailable（中性占位，不编造）
  - snapshot 冻结 explanation；review 读取而非重算
"""
import sys
import json
import re
import tempfile
import shutil
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.explanation import build_explanation  # noqa: E402
from src.publisher import (  # noqa: E402
    build_snapshot,
    upsert_published_snapshot,
    load_published_by_issue,
    build_review,
)

BANNED = re.compile(r"建设中|开发中|待完善|TODO|coming soon")

ISSUES = [{"issue": i, "front": [1, 2, 3, 4, 5], "back": [6, 7]} for i in range(1, 51)]

CASES = [
    ("A-均衡统计型", [3, 5, 9, 24, 26], [3, 9], None, None, "balanced_statistical"),
    ("B-冷热组合型", [4, 8, 24, 26, 35], [5, 7], None, None, "hot_cold_mix"),
    ("C-纯随机娱乐型", [9, 10, 11, 22, 34], [1, 9], None, None, "random_baseline"),
    ("D-综合评分型", [13, 23, 21, 18, 28], [11, 6],
     {"heat": 72, "missing": 66, "trend": 58, "inherit": 30,
      "structure": {"sum_span_match": 88, "zone_match": 70}},
     {"sum_span_match": 88, "zone_match": 70}, "scored"),
]


class TestStrategyExplanations(unittest.TestCase):
    def _build(self, i):
        strat, front, back, basis, factors, stype = CASES[i]
        return build_explanation(strategy=strat, front=front, back=back, history=ISSUES,
                                 recent_window=50, basis=basis, factors=factors,
                                 model_version="C-2-D-v1" if stype == "scored" else None,
                                 score_total=54.4 if stype == "scored" else None,
                                 target_issue="26098"), stype

    def test_01_each_strategy_real(self):
        for i in range(4):
            e, _ = self._build(i)
            self.assertEqual(e["reason_status"], "ok", CASES[i][0])
            self.assertTrue(e["summary"].strip(), f"summary empty for {CASES[i][0]}")
            self.assertTrue(len(e["factors"]) >= 1, f"no factors for {CASES[i][0]}")

    def test_02_strategy_types(self):
        for i in range(4):
            e, stype = self._build(i)
            self.assertEqual(e["strategy_type"], stype, CASES[i][0])

    def test_03_deterministic(self):
        for i in range(4):
            e1, _ = self._build(i)
            e2, _ = self._build(i)
            self.assertEqual(e1["explanation_hash"], e2["explanation_hash"], CASES[i][0])

    def test_04_no_banned_placeholders(self):
        for i in range(4):
            e, _ = self._build(i)
            text = e["summary"] + json.dumps(e["factors"], ensure_ascii=False)
            self.assertIsNone(BANNED.search(text), f"banned word in {CASES[i][0]}")

    def test_05_random_C_honest(self):
        e, _ = self._build(2)  # C
        self.assertEqual(e["strategy_type"], "random_baseline")
        joined = json.dumps(e, ensure_ascii=False)
        # 不得出现伪造的统计优势措辞
        for fake in ("较大概率", "必出", "应该出", "值得关注", "高概率号码"):
            self.assertNotIn(fake, joined)
        # 随机基线应标注
        self.assertTrue(any(f.get("type") == "random" for f in e["factors"]))

    def test_06_d_uses_real_basis(self):
        e, _ = self._build(3)  # D
        joined = json.dumps(e, ensure_ascii=False)
        self.assertIn("heat", joined)  # basis 的真实字段被引用
        self.assertIn("72", joined)    # 具体数值（heat=72）被引用，非泛泛


class TestFailClosedAndUnavailable(unittest.TestCase):
    def test_07_no_history_unavailable(self):
        e = build_explanation(strategy="A-均衡统计型", front=[3, 5, 9], back=[3, 9],
                              history=[], recent_window=50)
        self.assertEqual(e["reason_status"], "unavailable")
        self.assertIsNone(BANNED.search(e["summary"]))

    def test_08_unknown_strategy_unavailable(self):
        e = build_explanation(strategy="X-未知型", front=[3, 5, 9], back=[3, 9],
                              history=ISSUES, recent_window=50)
        self.assertEqual(e["reason_status"], "unavailable")


class TestSnapshotFreezeReview(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="p12_")
        self.addCleanup(lambda: shutil.rmtree(self.d, ignore_errors=True))
        self.pub = self.d + "/published.json"

    def test_09_snapshot_freezes_explanation(self):
        strat, front, back, basis, factors, _ = CASES[3]  # D
        e = build_explanation(strategy=strat, front=front, back=back, history=ISSUES,
                              basis=basis, factors=factors, model_version="C-2-D-v1",
                              score_total=54.4, target_issue="26098")
        rec = {"target_issue": "26098", "strategy": strat, "front": front, "back": back,
               "final_score": 54.4, "basis": basis, "explanation": e, "is_primary": True}
        snap = build_snapshot(rec, published_at="2026-08-28 00:00:00")
        self.assertEqual(upsert_published_snapshot(self.pub, snap), "created")
        frozen = load_published_by_issue(self.pub)["26098"]
        self.assertEqual(frozen["explanation"]["explanation_hash"], e["explanation_hash"])
        self.assertEqual(frozen["explanation"]["summary"], e["summary"])

    def test_10_review_reads_frozen_not_regenerated(self):
        strat, front, back, basis, factors, _ = CASES[0]  # A
        e = build_explanation(strategy=strat, front=front, back=back, history=ISSUES,
                              basis=basis, factors=factors, target_issue="26097")
        snap = build_snapshot({"target_issue": "26097", "strategy": strat, "front": front,
                               "back": back, "explanation": e, "final_score": 49.0},
                              published_at="2026-08-27 00:00:00")
        upsert_published_snapshot(self.pub, snap)
        # reflection 里故意放 D 记录；复盘仍读 A 快照的冻结 explanation
        refl = {"periods": [{"issue": "26097", "strategy": "D-综合评分型",
                             "recommend": {"front": [1, 2, 3], "back": [1, 2]},
                             "actual": {"front": [3, 10, 12], "back": [1, 9]},
                             "result": {"total_hit": 0}}]}
        review = build_review(refl, load_published_by_issue(self.pub))
        self.assertEqual(review["recommendation"]["strategy"], strat)
        self.assertEqual(review["explanation"]["explanation_hash"], e["explanation_hash"])
        self.assertTrue(review["authoritative"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
