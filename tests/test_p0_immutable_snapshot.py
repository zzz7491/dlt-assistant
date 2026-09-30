"""P0-1 不可变发布快照 —— 正式 stdlib unittest（不依赖 pytest / 第三方库）。

覆盖契约：
  发布端 final_score 选出唯一 primary（可为 A/B/C/D 任意）→ 写不可变快照；
  复盘端 build_review 按 issue 读取该快照，绝不重算/重选/硬编码 D。

所有快照文件读写均走 tempfile 临时目录，不触碰真实
public/data/* 与 reports/* 生产 JSON。
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
    build_snapshot,
    snapshot_hash,
    upsert_published_snapshot,
    load_published_by_issue,
    build_review,
    pick_primary,
    _hit_counts,
)


def _snap(issue, strategy, front, back, **extra):
    rec = {
        "target_issue": issue,
        "strategy": strategy,
        "front": front,
        "back": back,
        "reason": extra.get("reason"),
        "final_score": extra.get("final_score"),
        "final_breakdown": extra.get("final_breakdown"),
        "model_version": extra.get("model_version", "C-2-D-v1"),
    }
    return build_snapshot(rec, published_at="2026-08-28 00:00:00")


def _reflection(issue, actual_front, actual_back):
    """最小 reflection 结构：该 issue 含 actual 开奖（供复盘命中计算）。"""
    return {
        "periods": [
            {
                "issue": issue,
                "strategy": "D-综合评分型",
                "recommend": {"front": [1, 2, 3], "back": [1, 2]},
                "actual": {"front": actual_front, "back": actual_back},
                "result": {"total_hit": 0},
            }
        ]
    }


class TestSnapshotLifecycle(unittest.TestCase):
    def _tmp(self):
        d = tempfile.mkdtemp(prefix="p01_snap_")
        self.addCleanup(lambda: shutil.rmtree(d, ignore_errors=True))
        return os.path.join(d, "published.json")

    # 1) 首次发布创建快照
    def test_01_first_publication_creates(self):
        path = self._tmp()
        snap = _snap("26098", "A-均衡统计型", [3, 5, 9, 24, 26], [3, 9])
        st = upsert_published_snapshot(path, snap)
        self.assertEqual(st, "created")
        store = load_published_by_issue(path)
        self.assertIn("26098", store)
        self.assertEqual(store["26098"]["primary_strategy"], "A-均衡统计型")

    # 2) 同 issue + 完全相同内容 → 幂等（unchanged，不写盘）
    def test_02_same_issue_same_content_idempotent(self):
        path = self._tmp()
        snap = _snap("26098", "A-均衡统计型", [3, 5, 9, 24, 26], [3, 9])
        self.assertEqual(upsert_published_snapshot(path, snap), "created")
        # 重新发布完全相同内容（published_at 可不同，hash 不含它）
        snap2 = _snap("26098", "A-均衡统计型", [3, 5, 9, 24, 26], [3, 9])
        snap2["published_at"] = "2099-01-01 00:00:00"
        self.assertEqual(upsert_published_snapshot(path, snap2), "unchanged")

    # 3) 同 issue + 内容改变 → CONFLICT，原快照保留
    def test_03_same_issue_changed_content_conflict_preserved(self):
        path = self._tmp()
        upsert_published_snapshot(path, _snap("26098", "A-均衡统计型", [3, 5, 9], [3, 9]))
        # 新 primary 变为 D 且号码不同
        st = upsert_published_snapshot(path, _snap("26098", "D-综合评分型", [13, 23, 21], [11, 6]))
        self.assertEqual(st, "conflict")
        store = load_published_by_issue(path)
        # 原快照未被覆盖
        self.assertEqual(store["26098"]["primary_strategy"], "A-均衡统计型")

    # 8) 发布下一期不改动上一期
    def test_08_next_issue_does_not_modify_previous(self):
        path = self._tmp()
        upsert_published_snapshot(path, _snap("26097", "B-冷热组合型", [4, 8, 24, 26, 35], [5, 7]))
        upsert_published_snapshot(path, _snap("26098", "A-均衡统计型", [3, 5, 9, 24, 26], [3, 9]))
        store = load_published_by_issue(path)
        self.assertEqual(store["26097"]["primary_strategy"], "B-冷热组合型")
        self.assertEqual(store["26097"]["numbers"]["front"], [4, 8, 24, 26, 35])
        self.assertEqual(store["26098"]["primary_strategy"], "A-均衡统计型")

    # 9) 快照哈希确定性（同内容同 hash，key 顺序无关，published_at 无关）
    def test_09_snapshot_hash_deterministic(self):
        s1 = _snap("26098", "A-均衡统计型", [3, 5, 9, 24, 26], [3, 9])
        s2 = _snap("26098", "A-均衡统计型", [3, 5, 9, 24, 26], [3, 9])
        self.assertEqual(snapshot_hash(s1), snapshot_hash(s2))
        self.assertIsNotNone(snapshot_hash(s1))
        self.assertEqual(len(snapshot_hash(s1)), 64)  # sha256 hex
        # 内容变 → hash 变
        s3 = _snap("26098", "C-纯随机娱乐型", [9, 10, 11, 22, 34], [1, 9])
        self.assertNotEqual(snapshot_hash(s1), snapshot_hash(s3))


class TestReviewReadsSnapshot(unittest.TestCase):
    def _published(self, mapping):
        # mapping: {issue: snap_dict}
        return mapping

    # 4) 复盘读取与快照相同的 primary_strategy
    def test_04_review_reads_same_primary_strategy(self):
        snap = _snap("26097", "A-均衡统计型", [3, 5, 9, 24, 26], [3, 9])
        published = {"26097": snap}
        refl = _reflection("26097", actual_front=[3, 10, 12, 20, 25], actual_back=[1, 9])
        review = build_review(refl, published)
        self.assertEqual(review["snapshot_status"], "ok")
        self.assertTrue(review["authoritative"])
        self.assertEqual(review["recommendation"]["strategy"], snap["primary_strategy"])

    # 5) 复盘读取与快照相同的号码
    def test_05_review_reads_same_numbers(self):
        snap = _snap("26097", "A-均衡统计型", [3, 5, 9, 24, 26], [3, 9])
        refl = _reflection("26097", actual_front=[1, 2, 3, 4, 5], actual_back=[1, 2])
        review = build_review(refl, {"26097": snap})
        self.assertEqual(review["recommendation"]["front"], [3, 5, 9, 24, 26])
        self.assertEqual(review["recommendation"]["back"], [3, 9])

    # 6) 复盘命中计算使用冻结号码（非 reflection 的旧号码）
    def test_06_review_hit_uses_frozen_numbers(self):
        snap = _snap("26097", "C-纯随机娱乐型", [1, 2, 3, 4, 5], [6, 7])
        refl = _reflection("26097", actual_front=[1, 2, 99, 100, 101], actual_back=[6, 99])
        review = build_review(refl, {"26097": snap})
        # 冻结前区 [1,2,3,4,5] vs 实际 [1,2,99,100,101] → 命中 2；后区 [6,7] vs [6,99] → 命中 1
        self.assertEqual(review["hit_count"]["front"], 2)
        self.assertEqual(review["hit_count"]["back"], 1)
        self.assertEqual(review["hit_count"]["total"], 3)

    # 7) 无历史快照 → 明确 legacy/missing 状态，不冒充权威
    def test_07_missing_snapshot_marked_legacy(self):
        refl = _reflection("26093", actual_front=[1, 2, 3, 4, 5], actual_back=[1, 2])
        review = build_review(refl, {})  # 无该 issue 快照
        self.assertEqual(review["snapshot_status"], "missing")
        self.assertFalse(review["authoritative"])
        self.assertTrue(review.get("legacy"))
        self.assertIsNone(review["snapshot_hash"])

    # 10) 无论 primary 是 A/B/C/D，复盘都读该 primary，绝不强制 D
    def test_10_any_strategy_primary_respected(self):
        for strat, front, back in [
            ("A-均衡统计型", [3, 5, 9, 24, 26], [3, 9]),
            ("B-冷热组合型", [4, 8, 24, 26, 35], [5, 7]),
            ("C-纯随机娱乐型", [9, 10, 11, 22, 34], [1, 9]),
            ("D-综合评分型", [13, 23, 21, 18, 28], [11, 6]),
        ]:
            snap = _snap("26096", strat, front, back)
            # reflection 里故意放 D 记录，验证复盘不会被 D 带走
            refl = _reflection("26096", actual_front=[1, 2, 3, 4, 5], actual_back=[1, 2])
            review = build_review(refl, {"26096": snap})
            self.assertEqual(review["recommendation"]["strategy"], strat,
                             msg=f"primary {strat} not respected")
            self.assertEqual(review["recommendation"]["front"], front)
            self.assertTrue(review["authoritative"])

    # D-priority 不再作为权威来源：快照缺失时 legacy fallback 也必须是 non-authoritative
    def test_10b_legacy_fallback_not_authoritative(self):
        refl = _reflection("26093", actual_front=[1, 2, 3, 4, 5], actual_back=[1, 2])
        review = build_review(refl, None)  # 未提供快照索引
        self.assertFalse(review["authoritative"])
        self.assertEqual(review["snapshot_status"], "missing")


class TestPickPrimary(unittest.TestCase):
    # pick_primary 优先级：is_primary=True 优先（快照与前端 selectPrimary 对齐）
    def test_pick_primary_by_flag(self):
        recs = [
            {"strategy": "A-均衡统计型", "front": [1], "back": [1], "final_score": 49.0, "is_primary": True},
            {"strategy": "D-综合评分型", "front": [2], "back": [2], "final_score": 50.0, "is_primary": False},
        ]
        self.assertEqual(pick_primary(recs)["strategy"], "A-均衡统计型")

    # pick_primary：只读 is_primary 权威标记；无标记（0 个）→ None（不再 score 回退，P0-2 契约）
    def test_pick_primary_no_marker_fail_closed(self):
        recs = [
            {"strategy": "C-纯随机娱乐型", "front": [1], "back": [1], "score": 30.0},
            {"strategy": "A-均衡统计型", "front": [2], "back": [2], "score": 45.0},
        ]
        # 无任何 is_primary 标记 → 不猜、不 score 重排、不回退 D → None
        self.assertIsNone(pick_primary(recs))


class TestHitCounts(unittest.TestCase):
    def test_hit_counts(self):
        h = _hit_counts([1, 2, 3, 4, 5], [6, 7], [1, 2, 99, 100, 101], [6, 99])
        self.assertEqual(h["front"], 2)
        self.assertEqual(h["back"], 1)
        self.assertEqual(h["total"], 3)
        self.assertEqual(h["level"], 2)  # HIT_LEVEL: total 3 → level 2（中等级）


if __name__ == "__main__":
    unittest.main(verbosity=2)
