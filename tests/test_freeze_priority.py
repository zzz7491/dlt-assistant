"""2026-11-01 治本回归：冻结优先 + 导出保留展开字段 + 发布完整性校验。

复现 26125 事故链：
  首轮发布冻结快照（primary=A/D 之一）→ 次日 F 迟到进候选集 → plain 导出
  覆盖展开版 → 旧逻辑按 F 重算 primary 与快照冲突 → fail-closed →
  recommendations.json 只剩 plain 版 → 前端/ai_cycle 失去唯一 primary。

治本后：
  - publisher 冻结优先：已有快照的期，primary 以快照为准，快照 unchanged，
    展开版正常写出，迟到 F 只作普通候选；
  - export 合并：plain 导出不得抹掉同号码记录的展开字段；
  - integrity check：primary 缺失时必须报错（exit 1 语义）。
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.publisher import publish  # noqa: E402
from scripts.export_recommendations_json import merge_expanded  # noqa: E402
from scripts.check_publication_integrity import check  # noqa: E402


def _backtest():
    return {"total_periods": 3,
            "strategies": {"A": {"count": 3, "avg_total_hit": 1.667},
                           "D": {"count": 2, "avg_total_hit": 1.0}}}


def _reflection():
    return {"periods": [
        {"issue": "26093", "strategy": "A-均衡统计型", "result": {"total_hit": 1}},
        {"issue": "26094", "strategy": "A-均衡统计型", "result": {"total_hit": 2}},
        {"issue": "26094", "strategy": "D-综合评分型", "result": {"total_hit": 0}},
        {"issue": "26095", "strategy": "A-均衡统计型", "result": {"total_hit": 2}},
        {"issue": "26095", "strategy": "D-综合评分型", "result": {"total_hit": 2}},
    ]}


BASE = [
    {"strategy": "A-均衡统计型", "front": [2, 7, 20, 24, 31], "back": [4, 10]},
    {"strategy": "D-综合评分型", "front": [13, 18, 21, 23, 28], "back": [6, 12]},
]
F_REC = {"strategy": "F-综合AI型", "front": [1, 9, 15, 22, 30], "back": [2, 7]}


def _plain(recs, issue="26096"):
    return [{**r, "date": "2026-08-22", "target_issue": issue, "idx": 0}
            for r in recs]


class TestFreezePriority(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.out_dir = os.path.join(self.tmp, "out")
        os.makedirs(self.out_dir)
        self.paths = {
            "current_path": os.path.join(self.out_dir, "recommendations.json"),
            "rec_path": os.path.join(self.tmp, "reports_rec.json"),
            "reflect_path": os.path.join(self.tmp, "reflection.json"),
            "backtest_path": os.path.join(self.tmp, "backtest.json"),
            "history_path": os.path.join(self.tmp, "history.json"),
        }
        for name, data in (("rec_path", _plain(BASE)),
                           ("reflect_path", _reflection()),
                           ("backtest_path", _backtest()),
                           ("history_path", {"issues": []})):
            with open(self.paths[name], "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_current(self, recs):
        with open(self.paths["current_path"], "w", encoding="utf-8") as f:
            json.dump(recs, f, ensure_ascii=False)

    def _read_current(self):
        with open(self.paths["current_path"], encoding="utf-8") as f:
            return json.load(f)

    def test_late_f_keeps_frozen_primary(self):
        # 首轮：无 F，发布并冻结（cold 锁 D 为 primary）
        self._write_current(_plain(BASE))
        r1 = publish(out_dir=self.out_dir, **self.paths)
        self.assertEqual(r1["published"]["issues"]["26096"], "created")
        frozen = [r for r in self._read_current() if r.get("is_primary") is True]
        self.assertEqual(len(frozen), 1)
        frozen_strategy = frozen[0]["strategy"]

        # 次日：F 迟到 + plain 导出覆盖（只剩 plain 字段，含 F）
        self._write_current(_plain(BASE + [F_REC]))
        r2 = publish(out_dir=self.out_dir, **self.paths)
        # 快照不得冲突、不得 fail-closed
        self.assertEqual(r2["published"]["issues"]["26096"], "unchanged")
        self.assertFalse(r2["published"]["fail_closed"])
        recs = self._read_current()
        primaries = [r for r in recs if r.get("is_primary") is True]
        self.assertEqual(len(primaries), 1)
        self.assertEqual(primaries[0]["strategy"], frozen_strategy)
        f_rec = next(r for r in recs if r["strategy"].startswith("F"))
        self.assertIs(f_rec.get("is_primary"), False)
        self.assertIn("final_score", f_rec)  # 展开版字段齐全

    def test_genuine_conflict_still_fail_closed(self):
        # 冻结后锁定策略号码被改（真冲突）→ 仍 fail-closed，不写新展开版
        self._write_current(_plain(BASE))
        publish(out_dir=self.out_dir, **self.paths)
        tampered = _plain([{**BASE[0]},
                           {**BASE[1], "front": [1, 2, 3, 4, 5]}])
        self._write_current(tampered)
        r = publish(out_dir=self.out_dir, **self.paths)
        self.assertEqual(r["published"]["issues"]["26096"], "conflict")
        self.assertTrue(r["published"]["fail_closed"])
        self.assertEqual(self._read_current(), tampered)


class TestExportMerge(unittest.TestCase):
    def test_merge_preserves_expanded_same_numbers(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))
        out = os.path.join(tmp, "recommendations.json")
        expanded = [{**_plain(BASE)[0], "is_primary": True, "final_score": 42.0,
                     "final_rank": 1, "reason": "r"}]
        with open(out, "w", encoding="utf-8") as f:
            json.dump(expanded, f, ensure_ascii=False)
        merged = merge_expanded(_plain(BASE), out)
        a = next(r for r in merged if r["strategy"].startswith("A"))
        self.assertIs(a["is_primary"], True)
        self.assertEqual(a["final_score"], 42.0)

    def test_merge_skips_when_numbers_changed(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))
        out = os.path.join(tmp, "recommendations.json")
        expanded = [{**_plain(BASE)[0], "is_primary": True, "final_score": 42.0}]
        with open(out, "w", encoding="utf-8") as f:
            json.dump(expanded, f, ensure_ascii=False)
        changed = _plain([{**BASE[0], "front": [3, 4, 5, 6, 7]}])
        merged = merge_expanded(changed, out)
        self.assertNotIn("is_primary", merged[0])


class TestIntegrityCheck(unittest.TestCase):
    def _dir_with(self, recs, snaps=None, cycle=None):
        tmp = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))
        with open(os.path.join(tmp, "recommendations.json"), "w",
                  encoding="utf-8") as f:
            json.dump(recs, f, ensure_ascii=False)
        with open(os.path.join(tmp, "published_recommendations.json"), "w",
                  encoding="utf-8") as f:
            json.dump(snaps if snaps is not None else
                      {"items": [{"issue": "26096"}]}, f, ensure_ascii=False)
        if cycle is not None:
            with open(os.path.join(tmp, "ai_cycle.json"), "w",
                      encoding="utf-8") as f:
                json.dump(cycle, f, ensure_ascii=False)
        return tmp

    def test_plain_without_primary_is_broken(self):
        d = self._dir_with(_plain(BASE))
        problems = check(d)
        self.assertTrue(any("is_primary" in p for p in problems))

    def test_expanded_ok_and_invalid_context_flagged(self):
        recs = _plain(BASE)
        recs[0]["is_primary"] = True
        recs[1]["is_primary"] = False
        d = self._dir_with(recs, cycle={"statuses": {"analysis": "completed"}})
        self.assertEqual(check(d), [])
        d2 = self._dir_with(recs, cycle={"statuses": {"analysis": "invalid_context"}})
        self.assertTrue(any("invalid_context" in p for p in check(d2)))


if __name__ == "__main__":
    unittest.main()
