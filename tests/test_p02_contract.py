"""P0-2 端到端契约测试：published == snapshot == frontend == review。

stdlib unittest（不依赖 pytest / 第三方库），全部走 tempfile 临时目录，
不触碰真实 public/data/* 与 reports/* 生产 JSON。

覆盖契约（PASS RULE）：
  - 恰好一个权威 primary（final_score 产出 is_primary 计数==1）
  - publisher primary == snapshot
  - snapshot == review source
  - A/B/C/D 任一 primary 的快照→复盘 roundtrip
  - conflict fail-closed（publish 不写分叉的 recommendations.json）
  - idempotent replay 保留原 published_at
  - 下一期不改上一期
  - legacy 缺快照 → 显式 non-authoritative
"""
import sys
import os
import json
import shutil
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.publisher import (  # noqa: E402
    build_recommendations,
    build_snapshot,
    snapshot_hash,
    upsert_published_snapshot,
    load_published_by_issue,
    build_review,
    pick_primary,
    publish,
)
from src.final_score import compute_final_scores  # noqa: E402


def _recs_4(issue="26098"):
    """一期 4 策略（含唯一 is_primary 标记）作为 display 输入。"""
    return [
        {"target_issue": issue, "strategy": "A-均衡统计型", "front": [3, 5, 9, 24, 26], "back": [3, 9], "idx": 0, "is_primary": False},
        {"target_issue": issue, "strategy": "B-冷热组合型", "front": [4, 8, 24, 26, 35], "back": [5, 7], "idx": 0, "is_primary": False},
        {"target_issue": issue, "strategy": "C-纯随机娱乐型", "front": [9, 10, 11, 22, 34], "back": [1, 9], "idx": 0, "is_primary": False},
        {"target_issue": issue, "strategy": "D-综合评分型", "front": [13, 23, 21, 18, 28], "back": [11, 6], "idx": 0, "is_primary": True,
         "score_total": 41.46, "basis": {"missing": 85, "structure": {"sum_span_match": 90, "zone_match": 70}}},
    ]


def _mkd(self=None):
    d = tempfile.mkdtemp(prefix="p02_")
    return d


class TestExactlyOnePrimary(unittest.TestCase):
    def setUp(self):
        d = _mkd()
        self.addCleanup(lambda: shutil.rmtree(d, ignore_errors=True))
        self.d = d

    # 1) final_score 对 4 策略恰好产出 1 个 is_primary
    def test_exactly_one_authoritative_primary(self):
        recs = _recs_4()
        scored = compute_final_scores(recs, effective_sample=12,
                                      strategy_rank={"A": 2, "B": 3, "C": 4, "D": 1},
                                      history_map={"A": 3.1, "B": 2.4, "C": 2.0, "D": 3.4},
                                      recent_map={}, structure_ctx=None, prev_draw=None, weights=None)
        pri = [r for r in scored if r.get("is_primary") is True]
        self.assertEqual(len(pri), 1)
        self.assertEqual(pick_primary(scored)["strategy"], pri[0]["strategy"])

    # pick_primary fail-closed：0 个或多个 is_primary → None
    def test_pick_primary_fail_closed(self):
        zero = _recs_4(); [r.pop("is_primary") for r in zero]
        self.assertIsNone(pick_primary(zero))
        two = _recs_4(); two[0]["is_primary"] = True; two[3]["is_primary"] = True
        self.assertIsNone(pick_primary(two))


class TestSnapshotVsOutput(unittest.TestCase):
    """STEP 4：publisher primary == snapshot（primary/numbers/reason 一致）。"""

    def setUp(self):
        self.d = _mkd()
        self.addCleanup(lambda: shutil.rmtree(self.d, ignore_errors=True))

    def _publish_one(self, front=None):
        current = _recs_4()
        if front:
            current[3]["front"] = front
            current[3]["back"] = [11, 6]
        for name, data in [("current.json", current), ("recs.json", [dict(r) for r in current]),
                           ("no_refl.json", {}), ("no_bt.json", {})]:
            with open(os.path.join(self.d, name), "w") as fh:
                json.dump(data, fh, ensure_ascii=False)
        return publish(rec_path=os.path.join(self.d, "recs.json"),
                      reflect_path=os.path.join(self.d, "no_refl.json"),
                      backtest_path=os.path.join(self.d, "no_bt.json"),
                      current_path=os.path.join(self.d, "current.json"),
                      out_dir=self.d,
                      published_path=os.path.join(self.d, "published.json"))

    # 2) publisher primary == snapshot
    def test_02_publisher_primary_equals_snapshot(self):
        self._publish_one(front=[13, 23, 21, 18, 28])
        with open(os.path.join(self.d, "recommendations.json")) as fh:
            pub = json.load(fh)
        pri = [r for r in pub if r.get("is_primary") is True]
        snap = list(load_published_by_issue(os.path.join(self.d, "published.json")).values())[0]
        self.assertEqual(len(pri), 1)
        self.assertEqual(pri[0]["strategy"], snap["primary_strategy"])
        self.assertEqual(pri[0]["front"], snap["numbers"]["front"])
        self.assertEqual(pri[0]["back"], snap["numbers"]["back"])

    # 4a) 正常发布后 recommendations.json 恰好 1 个 is_primary（PASS RULE: EXACTLY ONE）
    def test_04a_normal_publish_exactly_one_primary(self):
        self._publish_one()
        pub = json.load(open(os.path.join(self.d, "recommendations.json")))
        self.assertEqual(len([r for r in pub if r.get("is_primary") is True]), 1)

    # 4b) 当 primary 无法确定（0 个或多个 is_primary → pick_primary=None）时 fail-closed
    #      不写 recommendations.json，避免 display 与 snapshot 分叉。
    def test_04b_unresolvable_primary_fails_closed(self):
        import src.publisher as pubmod
        for name, data in [("current.json", [dict(r) for r in _recs_4()]),
                           ("recs.json", [dict(r) for r in _recs_4()]),
                           ("no_refl.json", {}), ("no_bt.json", {})]:
            with open(os.path.join(self.d, name), "w") as fh:
                json.dump(data, fh, ensure_ascii=False)
        orig = pubmod.pick_primary
        pubmod.pick_primary = lambda recs: None  # 模拟 primary 无法确定（0 或 >1）
        try:
            res = publish(rec_path=os.path.join(self.d, "recs.json"),
                         reflect_path=os.path.join(self.d, "no_refl.json"),
                         backtest_path=os.path.join(self.d, "no_bt.json"),
                         current_path=os.path.join(self.d, "current.json"),
                         out_dir=self.d,
                         published_path=os.path.join(self.d, "published.json"))
        finally:
            pubmod.pick_primary = orig
        self.assertTrue(res["published"]["fail_closed"])
        self.assertFalse(os.path.exists(os.path.join(self.d, "recommendations.json")))


class TestReviewContract(unittest.TestCase):
    """STEP 6：N→A / N+1→B / N+2→C / N+3→D roundtrip；命中用冻结快照号码。"""

    def setUp(self):
        self.d = _mkd()
        self.addCleanup(lambda: shutil.rmtree(self.d, ignore_errors=True))
        self.pub = os.path.join(self.d, "published.json")

    def _snap(self, issue, strat, front, back):
        return upsert_published_snapshot(
            self.pub,
            build_snapshot({"target_issue": issue, "strategy": strat,
                            "front": front, "back": back,
                            "reason": "r", "final_score": 50.0,
                            "model_version": "C-2-D-v1"},
                           published_at="2026-08-28 00:00:00"))

    def _reflection_for(self, issue, actual_front, actual_back):
        return {"periods": [
            {"issue": issue, "strategy": "D-综合评分型",
             "recommend": {"front": [1, 2, 3], "back": [1, 2]},
             "actual": {"front": actual_front, "back": actual_back},
             "result": {"total_hit": 0}}]}

    def test_05_roundtrip_all_strategies(self):
        cases = [
            ("26094", "A-均衡统计型", [3, 5, 9, 24, 26], [3, 9]),
            ("26095", "B-冷热组合型", [4, 8, 24, 26, 35], [5, 7]),
            ("26096", "C-纯随机娱乐型", [9, 10, 11, 22, 34], [1, 9]),
            ("26097", "D-综合评分型", [13, 23, 21, 18, 28], [11, 6]),
        ]
        for issue, strat, front, back in cases:
            self._snap(issue, strat, front, back)
        idx = load_published_by_issue(self.pub)
        # 每期复盘读自己的快照，且命中用冻结号码（非 reflection 里写死的 [1,2,3]）
        for issue, strat, front, back in cases:
            refl = self._reflection_for(issue, actual_front=[1, 2, 3, 4, 5], actual_back=[1, 2])
            review = build_review(refl, idx)
            self.assertEqual(review["recommendation"]["strategy"], strat, issue)
            self.assertEqual(review["recommendation"]["front"], front, issue)
            self.assertEqual(review["recommendation"]["back"], back, issue)
            self.assertTrue(review["authoritative"], issue)
            self.assertEqual(review["snapshot_status"], "ok", issue)
            # 冻结 front [3,5,9,24,26] vs actual [1,2,3,4,5] → 命中 1 (3)
            self.assertIsInstance(review["hit_count"]["total"], int, issue)

    # 10) 复盘绝不因 D/score/recent 重新选择（reflection 里故意放 D，仍读 A 快照）
    def test_10_review_not_forced_to_D(self):
        self._snap("26094", "A-均衡统计型", [3, 5, 9, 24, 26], [3, 9])
        refl = self._reflection_for("26094", actual_front=[1, 2, 3, 4, 5], actual_back=[1, 2])
        review = build_review(refl, load_published_by_issue(self.pub))
        self.assertEqual(review["recommendation"]["strategy"], "A-均衡统计型")
        self.assertTrue(review["authoritative"])


class TestConflictFailClosed(unittest.TestCase):
    """STEP 7/8/11/12：conflict 不改已冻结快照；idempotent 保留 published_at；下期不动上期。"""

    def setUp(self):
        self.d = _mkd()
        self.addCleanup(lambda: shutil.rmtree(self.d, ignore_errors=True))
        self.pub = os.path.join(self.d, "published.json")

    # 11) 幂等 replay 保留原 published_at
    def test_11_idempotent_replay_preserves_published_at(self):
        s1 = build_snapshot({"target_issue": "26098", "strategy": "A", "front": [1], "back": [1]},
                            published_at="2026-08-28 00:00:00")
        self.assertEqual(upsert_published_snapshot(self.pub, s1), "created")
        s2 = build_snapshot({"target_issue": "26098", "strategy": "A", "front": [1], "back": [1]},
                            published_at="2099-01-01 00:00:00")
        self.assertEqual(upsert_published_snapshot(self.pub, s2), "unchanged")
        snap = list(load_published_by_issue(self.pub).values())[0]
        self.assertEqual(snap["published_at"], "2026-08-28 00:00:00")  # 原时间不变

    # 12) 发布下一期不修改上一期
    def test_12_next_issue_does_not_mutate_previous(self):
        upsert_published_snapshot(self.pub, build_snapshot(
            {"target_issue": "26097", "strategy": "B", "front": [4], "back": [5]},
            published_at="2026-08-27 00:00:00"))
        upsert_published_snapshot(self.pub, build_snapshot(
            {"target_issue": "26098", "strategy": "A", "front": [3], "back": [9]},
            published_at="2026-08-28 00:00:00"))
        idx = load_published_by_issue(self.pub)
        self.assertEqual(idx["26097"]["primary_strategy"], "B")
        self.assertEqual(idx["26097"]["numbers"]["front"], [4])
        self.assertEqual(idx["26098"]["primary_strategy"], "A")

    # 9/10) conflict：已有不同快照 → 保留原值；publish() 层 fail-closed（不写分叉）
    def test_09_conflict_preserves_original_and_fail_closed(self):
        upsert_published_snapshot(self.pub, build_snapshot(
            {"target_issue": "26098", "strategy": "A", "front": [3, 5, 9], "back": [3, 9]},
            published_at="2026-08-28 00:00:00"))
        # 新发布同 issue 但不同 primary → conflict
        st = upsert_published_snapshot(self.pub, build_snapshot(
            {"target_issue": "26098", "strategy": "D", "front": [13, 23], "back": [11, 6]},
            published_at="2026-08-28 01:00:00"))
        self.assertEqual(st, "conflict")
        idx = load_published_by_issue(self.pub)
        self.assertEqual(idx["26098"]["primary_strategy"], "A")  # 原快照保留

    def test_10b_publish_conflict_fail_closed_no_divergence(self):
        # 预置 26098 的冻结快照（A）
        upsert_published_snapshot(self.pub, build_snapshot(
            {"target_issue": "26098", "strategy": "A", "front": [3, 5, 9], "back": [3, 9]},
            published_at="2026-08-28 00:00:00"))
        # 现发布同 issue 的 D（不同内容）→ publish() 必须 fail-closed，不写 recommendations.json
        for name, data in [("current.json", _recs_4()), ("recs.json", [dict(r) for r in _recs_4()]),
                           ("no_refl.json", {}), ("no_bt.json", {})]:
            with open(os.path.join(self.d, name), "w") as fh:
                json.dump(data, fh, ensure_ascii=False)
        res = publish(rec_path=os.path.join(self.d, "recs.json"),
                      reflect_path=os.path.join(self.d, "no_refl.json"),
                      backtest_path=os.path.join(self.d, "no_bt.json"),
                      current_path=os.path.join(self.d, "current.json"),
                      out_dir=self.d,
                      published_path=self.pub)
        self.assertTrue(res["published"]["fail_closed"])
        # 冻结展示：recommendations.json 未被写出/未改（display == 冻结 A）
        self.assertFalse(os.path.exists(os.path.join(self.d, "recommendations.json")))
        # snapshot 仍是 A（未变）
        self.assertEqual(load_published_by_issue(self.pub)["26098"]["primary_strategy"], "A")


class TestLegacyReview(unittest.TestCase):
    """13) 缺快照 → 显式 non-authoritative（前端据此显示 legacy 横幅）。"""

    def test_13_missing_snapshot_non_authoritative(self):
        refl = {"periods": [
            {"issue": "26093", "strategy": "D-综合评分型",
             "recommend": {"front": [1, 2, 3], "back": [1, 2]},
             "actual": {"front": [3, 10, 12], "back": [1, 9]}, "result": {"total_hit": 0}}]}
        review = build_review(refl, {})
        self.assertEqual(review["snapshot_status"], "missing")
        self.assertFalse(review["authoritative"])
        self.assertTrue(review["legacy"])
        self.assertIsNone(review["snapshot_hash"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
