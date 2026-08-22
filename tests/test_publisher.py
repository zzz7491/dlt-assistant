"""Phase 11-D3.2.1 单元测试：publisher 融合接入 + 幂等写入。

覆盖：
- _apply_final_scores：cold 锁 D / 字段落盘 / 失败安全回退
- _load_final_score_config：yaml 缺失回退 None / 正常读取
- _write_json_if_changed：内容相同跳写（updated_at 不触发重写）/ 内容变化写入
- publish() 端到端（临时目录）：融合字段落盘 + 二次运行幂等

运行：python -m unittest discover -s tests -v
"""
import copy
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.publisher import (  # noqa: E402
    _apply_final_scores, _load_final_score_config, _recent_map_from_reflection,
    _strip_updated_at, _write_json_if_changed, build_recommendations, publish,
)


def _recs():
    return [
        {"strategy": "A-均衡统计型", "front": [2, 7, 20, 24, 31], "back": [4, 10]},
        {"strategy": "D-综合评分型", "front": [13, 18, 21, 23, 28], "back": [6, 12]},
    ]


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


def _review():
    return {"actual_result": {"front": [8, 10, 22, 26, 29], "back": [3, 10]}}


class TestApplyFinalScores(unittest.TestCase):
    def test_cold_locks_primary_to_d_and_adds_fields(self):
        recs = _recs()
        out = _apply_final_scores(recs, _backtest(), {"strategies": []}, _reflection(), _review())
        self.assertIsNot(out, recs)                      # 返回拷贝列表
        d = next(it for it in out if it["strategy"].startswith("D"))
        a = next(it for it in out if it["strategy"].startswith("A"))
        self.assertTrue(d["is_primary"])                 # cold 锁 D
        self.assertTrue(d["final_breakdown"]["locked_cold_start"])
        for it in out:
            for key in ("final_score", "final_breakdown", "final_rank", "is_primary"):
                self.assertIn(key, it)
            self.assertEqual(it["final_breakdown"]["stage"], "cold")
            self.assertEqual(it["final_breakdown"]["effective_sample"], 3)
        self.assertIsInstance(a["final_score"], float)

    def test_inputs_not_mutated(self):
        recs = _recs()
        snapshot = copy.deepcopy(recs)
        _apply_final_scores(recs, _backtest(), {}, _reflection(), _review())
        self.assertEqual(recs, snapshot)

    def test_fail_safe_on_bad_backtest(self):
        """backtest 损坏 → 各分量中性化但仍产出字段；完全异常 → 原样返回。"""
        out = _apply_final_scores(_recs(), None, None, None, None)
        self.assertEqual(len(out), 2)
        for it in out:
            self.assertIn("final_score", it)

    def test_empty_recs_passthrough(self):
        self.assertEqual(_apply_final_scores([], _backtest(), {}, {}, {}), [])


class TestRecentMap(unittest.TestCase):
    def test_grouped_and_windowed(self):
        rm = _recent_map_from_reflection(_reflection())
        self.assertEqual(rm["A"], [1.0, 2.0, 2.0])       # 按出现顺序保留
        self.assertEqual(rm["D"], [0.0, 2.0])

    def test_window_limits_to_last_n(self):
        refl = {"periods": [{"strategy": f"A-x", "result": {"total_hit": i}} for i in range(8)]}
        rm = _recent_map_from_reflection(refl, window=5)
        self.assertEqual(rm["A"], [3.0, 4.0, 5.0, 6.0, 7.0])

    def test_bad_input(self):
        self.assertEqual(_recent_map_from_reflection(None), {})
        self.assertEqual(_recent_map_from_reflection({"periods": "x"}), {})


class TestConfig(unittest.TestCase):
    def test_missing_file_returns_none(self):
        self.assertIsNone(_load_final_score_config("nonexistent/path.yaml"))

    def test_repo_config_loads(self):
        cfg = _load_final_score_config("config/settings.yaml")
        if cfg is None:
            self.skipTest("PyYAML 不可用（回退默认权重，符合设计）")
        self.assertAlmostEqual(cfg["base"], 0.40)
        self.assertIn("risk", cfg)


class TestIdempotentWrite(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "x.json")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_same_content_skips_write(self):
        data = {"updated_at": "2026-01-01 00:00:00", "k": 1}
        self.assertTrue(_write_json_if_changed(self.path, data))
        first_mtime = os.path.getmtime(self.path)
        with open(self.path, encoding="utf-8") as f:
            saved_ts = json.load(f)["updated_at"]
        # 仅 updated_at 变化 → 跳过写盘，文件保持原时间戳字符串与 mtime
        self.assertFalse(_write_json_if_changed(self.path, {"updated_at": "2026-02-02 00:00:00", "k": 1}))
        self.assertEqual(os.path.getmtime(self.path), first_mtime)
        with open(self.path, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["updated_at"], saved_ts)

    def test_content_change_writes(self):
        _write_json_if_changed(self.path, {"updated_at": "t1", "k": 1})
        self.assertTrue(_write_json_if_changed(self.path, {"updated_at": "t1", "k": 2}))

    def test_list_payload(self):
        self.assertTrue(_write_json_if_changed(self.path, [{"a": 1}]))
        self.assertFalse(_write_json_if_changed(self.path, [{"a": 1}]))

    def test_corrupted_existing_writes(self):
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("{broken json")
        self.assertTrue(_write_json_if_changed(self.path, {"k": 1}))

    def test_strip_updated_at_recursive(self):
        self.assertEqual(_strip_updated_at({"updated_at": "x", "a": [{"updated_at": "y", "b": 1}]}),
                         {"a": [{"b": 1}]})


class TestPublishEndToEnd(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.out_dir = os.path.join(self.tmp, "out")
        os.makedirs(self.out_dir)
        self.paths = {
            "current_path": os.path.join(self.out_dir, "recommendations.json"),
            "rec_path": os.path.join(self.tmp, "reports_rec.json"),
            "reflect_path": os.path.join(self.tmp, "reflection.json"),
            "backtest_path": os.path.join(self.tmp, "backtest.json"),
        }
        current = [{**r, "date": "2026-08-22", "target_issue": "26096", "idx": 0}
                   for r in _recs()]
        with open(self.paths["current_path"], "w", encoding="utf-8") as f:
            json.dump(current, f, ensure_ascii=False)
        with open(self.paths["rec_path"], "w", encoding="utf-8") as f:
            json.dump(current, f, ensure_ascii=False)
        with open(self.paths["reflect_path"], "w", encoding="utf-8") as f:
            json.dump(_reflection(), f, ensure_ascii=False)
        with open(self.paths["backtest_path"], "w", encoding="utf-8") as f:
            json.dump(_backtest(), f, ensure_ascii=False)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_publish_fusion_fields_then_idempotent(self):
        result = publish(out_dir=self.out_dir, **self.paths)
        self.assertTrue(result["recommendations"]["changed"])
        with open(self.paths["current_path"], encoding="utf-8") as f:
            recs = json.load(f)
        self.assertIn("final_score", recs[0])
        d = next(r for r in recs if r["strategy"].startswith("D"))
        self.assertTrue(d["is_primary"])                 # sample=3 → cold 锁 D
        self.assertTrue(d["final_breakdown"]["locked_cold_start"])

        # 二次运行：三文件全部跳过写入（幂等）
        result2 = publish(out_dir=self.out_dir, **self.paths)
        self.assertFalse(result2["recommendations"]["changed"])
        self.assertFalse(result2["review"]["changed"])
        self.assertFalse(result2["strategy_score"]["changed"])


class TestBuildRecommendationsUnchanged(unittest.TestCase):
    def test_is_primary_fallback_still_d_before_fusion(self):
        """融合前的兜底行为不变：build_recommendations 单独调用时 is_primary=D。"""
        current = [{"strategy": "A-x", "front": [1], "back": [1], "target_issue": "1"}]
        out = build_recommendations(current, [])
        self.assertTrue(out[0]["is_primary"] is False or out[0]["is_primary"] == False)  # noqa: E712
        d_current = [{"strategy": "D-y", "front": [1], "back": [1], "target_issue": "1"}]
        out_d = build_recommendations(d_current, [])
        self.assertTrue(out_d[0]["is_primary"])


if __name__ == "__main__":
    unittest.main()
