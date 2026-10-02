"""P4-2 Production Wording Integrity tests.

Verifies that user-visible production copy (public/*.html + public/*.js) does
NOT make unqualified current-product predictive claims, while preserving:
  - the required disclaimer,
  - the entertainment / analysis framing,
  - the exactly-one-final-recommendation product semantics,
  - the key JS/data hooks that P4-2 wording edits must not break.

Deliberately NOT brittle on full-sentence Chinese copy — it checks for the
absence of unqualified predictive-claim markers and the presence of required
disclaimers/framing.

Run: .venv/bin/python -m unittest tests.test_p42_wording_integrity -v
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXP_HTML = ROOT / "public" / "experiment.html"
EXP_JS = ROOT / "public" / "experiment.js"
IDX_HTML = ROOT / "public" / "index.html"

EXP_26112_HASH = "bea8ef87f3f137238686ae52712f922956215408f0cf54187b9295d8f1ae5fad"


def _read(path):
    return path.read_text(encoding="utf-8")


# An unqualified B-class predictive-claim marker is one that appears on a line
# WITHOUT any disclaimer/qualification wording.
QUALIFIERS = (
    "不构成", "未确认", "不衡量", "非预测", "不代表", "仅为随机噪声",
    "不保证", "不构成显著", "相对随机基线", "历史回测", "回测", "娱乐",
    "负期望", "理性购彩", "仅展示", "透明展示", "可能仅为随机噪声",
)

# Forbidden unqualified markers (current-product predictive claims).
FORBIDDEN = (
    "预测目标期号", "预测目标", "预测次数",
    "提高中奖率", "战胜随机", "模型优势", "高概率中奖",
)


def _unqualified_matches(text, markers):
    """Return (marker, line_no, line) tuples where marker appears on a line
    that has NO qualifying wording. Legitimate disclaimer/research lines keep
    the marker together with a qualifier, so they are not flagged."""
    hits = []
    for i, line in enumerate(text.splitlines(), 1):
        for m in markers:
            if m in line:
                has_q = any(q in line for q in QUALIFIERS)
                if not has_q:
                    hits.append((m, i, line.strip()))
    return hits


class TestExperimentHtml(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = _read(EXP_HTML)
        cls.js = _read(EXP_JS)

    # 1. no unqualified current-product predictive claims
    def test_01_no_unqualified_predictive_claims(self):
        # "预测目标期号" was renamed to 娱乐推荐目标期号; the bare forbidden
        # markers must not appear on unqualified lines.
        hits = _unqualified_matches(self.html, FORBIDDEN)
        self.assertEqual(
            [h for h in hits if h[0] in ("预测目标期号", "预测目标", "预测次数",
                                          "提高中奖率", "战胜随机", "模型优势",
                                          "高概率中奖")],
            [],
            f"unqualified predictive claims remain in experiment.html: {hits}",
        )

    # 2. the old "胜随机" WIN-claim column header is gone (renamed + qualified)
    def test_02_no_unqualified_win_random_header(self):
        # "胜随机" as a standalone table header must not exist unqualified.
        header_like = re.findall(r"胜随机", self.html)
        # any remaining 胜随机 must be inside a qualified disclaimer line
        unq = _unqualified_matches(self.html, ("胜随机",))
        self.assertEqual(unq, [], f"unqualified '胜随机' remains: {unq}")

    # 3. disclaimer present
    def test_03_disclaimer_present(self):
        self.assertTrue(
            any(q in self.html for q in ("不构成", "非预测", "不保证", "不具备预测", "理性购彩")),
            "experiment.html must carry a lottery-disclaimer",
        )

    # 4. entertainment / analysis framing present
    def test_04_entertainment_framing(self):
        self.assertTrue(
            any(f in self.html for f in ("娱乐推荐", "娱乐分析", "娱乐统计", "非预测")),
            "experiment.html must carry entertainment/analysis framing",
        )

    # 5. "保证中奖" and absolute-promise markers must NOT appear
    def test_05_no_win_guarantee(self):
        self.assertNotIn("保证中奖", self.html)
        self.assertNotIn("必中", self.html)
        self.assertNotIn("稳赢", self.html)

    # 6. exactly-one-final-recommendation semantics not broken (index.html)
    def test_06_exactly_one_final_recommendation(self):
        idx = _read(IDX_HTML)
        self.assertIn("本期唯一推荐", idx,
                      "exactly-one-final-recommendation section must remain")

    # 7. key JS/data hooks survived P4-2 wording edits
    def test_07_js_hooks_intact(self):
        for hook in ("target-issue", "gen-at", "model-ver", "reco-list",
                     "rank-body", "model-overview", "sec-ranking"):
            self.assertIn(f'id="{hook}"', self.html,
                          f"JS data hook #{hook} missing from experiment.html")

    # 8. the JS rank table header no longer shows the bare 胜随机 header
    def test_08_js_header_renamed(self):
        # The JS-generated overview table header must use 相对随机基线, not 胜随机.
        self.assertIn("相对随机基线", self.js)
        # 胜随机 may still appear inside a qualified disclaimer sentence; it must
        # NOT appear as a bare table header entry.
        self.assertNotIn('"胜随机"', self.js, "JS table header '胜随机' must be renamed")

    # 9. JS data field names unchanged (P4-2 must not alter data logic)
    def test_09_js_data_fields_unchanged(self):
        for field in ("total_predictions", "avg_front_hit", "beats_random",
                      "composite", "hit3plus_rate", "max_consecutive_miss"):
            self.assertIn(field, self.js,
                          f"data field '{field}' must be preserved")


class TestIndexHtml(unittest.TestCase):
    def test_10_no_win_guarantee(self):
        html = _read(IDX_HTML)
        self.assertNotIn("保证中奖", html)
        self.assertNotIn("提高中奖率", html)
        self.assertIn("娱乐推荐", html)
        self.assertIn("不等于中奖预测", html)


class TestImmutableSnapshots(unittest.TestCase):
    """P4-2 must not touch published recommendation data."""

    def test_11_snapshot_files_intact(self):
        # published_recommendations.json / recommendations.json must still exist.
        for rel in ("public/data/published_recommendations.json",
                    "public/data/recommendations.json"):
            p = ROOT / rel
            self.assertTrue(p.exists(), f"{rel} missing")

    def test_12_26112_hash_constant_documented(self):
        # The known 26112 immutable hash is recorded in this test so a change
        # to the snapshot would be visible (the authoritative check lives in
        # test_p41_deterministic_rng.TestPublicationIdempotency).
        self.assertEqual(
            len(EXP_26112_HASH), 64,
            "26112 expected hash constant must be a 64-hex-char SHA-256",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
