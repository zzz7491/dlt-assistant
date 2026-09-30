"""P3-5 RESEARCH CLOSURE 测试（≥25 assertions）。"""
from __future__ import annotations

import json
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src.evaluation import research_closure as rc

ROOT = pathlib.Path(__file__).resolve().parent.parent


class TestP35ResearchClosure(unittest.TestCase):

    # 1-3 dataset / snapshot / cap
    def test_01_dataset_sha_unchanged(self):
        from src.evaluation import history_integrity as hi
        data = json.loads((ROOT / "data/research/dlt-full-history.json").read_text())
        self.assertEqual(hi.dataset_sha256(data["issues"]),
                         "ba4bfb09d46aa66ab72c2ba3f72057e37ffca293ac76e1e3a21dde77f1e4dbbf")

    def test_02_26112_snapshot_unchanged(self):
        recs = json.loads((ROOT / "public/data/published_recommendations.json").read_text())
        last = recs["items"][-1]
        self.assertEqual(last["issue"], "26112")
        self.assertEqual(last["snapshot_hash"],
                         "bea8ef87f3f137238686ae52712f922956215408f0cf54187b9295d8f1ae5fad")

    def test_03_recent_issues_1000_unchanged(self):
        self.assertIn("recent_issues: 1000", (ROOT / "config/settings.yaml").read_text())

    # 4-7 evidence ledger
    def test_04_evidence_ledger_all_gates(self):
        ledger = rc.evidence_ledger()
        gates = {e["source_gate"] for e in ledger}
        for g in ("P2-1", "P2-2", "P2-3", "P3-1", "P3-2", "P3-3", "P3-4"):
            self.assertIn(g, gates, f"missing gate {g}")

    def test_05_evidence_ledger_fields(self):
        for e in rc.evidence_ledger():
            for f in ("claim", "source_gate", "population", "metric", "effect",
                      "holdout_status", "interpretation", "limitations"):
                self.assertIn(f, e, f"missing field {f} in {e['source_gate']}")

    def test_06_no_unsupported_promoted_to_supported(self):
        """P3-3/P3-4 claims must not be PREDICTIVE_SUPPORTED in ledger."""
        for e in rc.evidence_ledger():
            if e["source_gate"] in ("P3-3", "P3-4"):
                self.assertIn("NOT CONFIRMED", e["holdout_status"],
                              f"{e['source_gate']} claim appears confirmed: {e}")

    def test_07_evidence_ledger_7_entries(self):
        self.assertEqual(len(rc.evidence_ledger()), 7)

    # 8-10 component inventory
    def test_08_component_inventory_completeness(self):
        comp = rc.component_inventory()
        for required in ("A", "B", "C", "D", "frequency", "omission", "hot_cold",
                         "trend", "inherit", "odd_even_big_small_zone_sum_span",
                         "base", "risk", "history", "recent", "structure",
                         "final_score", "selector", "c_rng_seed", "recent_issues_1000",
                         "publication_snapshot", "explanation_generation", "frontend_trend"):
            self.assertIn(required, comp, f"missing component {required}")

    def test_09_component_roles_valid(self):
        valid = {"PRODUCTION_USED", "RESEARCH_ONLY", "DISPLAY_ONLY", "PUBLICATION_CRITICAL",
                 "OPERATIONALLY_REQUIRED"}
        for k, v in rc.component_inventory().items():
            self.assertIn(v["role"], valid, f"{k} role={v['role']}")

    def test_10_no_entertainment_as_predictive_supported(self):
        for k, v in rc.component_inventory().items():
            if "ENTERTAINMENT_ANALYTIC" in v["classification"]:
                self.assertNotIn("PREDICTIVE_SUPPORTED", v["classification"],
                                  f"{k} marked ENTERTAINMENT but also PREDICTIVE_SUPPORTED")

    # 11-13 baselines
    def test_11_baselines_8_total(self):
        # 8 baselines: B0..B7
        import json as _json, pathlib as _pl
        from src.evaluation import window_study as ws
        issues = ws.load_issues(str(ROOT / "data/research/dlt-full-history.json"))
        cache = {}
        for c in range(10):
            cf = ROOT / (".agnes/work/p32/matrix_chunk_%d.json" % c)
            for t_str, rec in _json.loads(cf.read_text()).items():
                cache[int(t_str)] = rec["1000"]
        t_idxs = list(range(ws.COMMON_WARMUP, len(issues)))
        from src.evaluation import selector_decomposition as sd
        cur = sd.reconstruct_selector(issues, cache, t_idxs)
        b = rc.build_baselines(cache, issues, t_idxs, current_vec=[r["sel_hits"] for r in cur])
        self.assertEqual(len(b), 8)

    def test_12_baseline_fields(self):
        import json as _json
        from src.evaluation import window_study as ws
        issues = ws.load_issues(str(ROOT / "data/research/dlt-full-history.json"))
        cache = {}
        for c in range(10):
            cf = ROOT / (".agnes/work/p32/matrix_chunk_%d.json" % c)
            for t_str, rec in _json.loads(cf.read_text()).items():
                cache[int(t_str)] = rec["1000"]
        t_idxs = list(range(ws.COMMON_WARMUP, len(issues)))
        from src.evaluation import selector_decomposition as sd
        cur = sd.reconstruct_selector(issues, cache, t_idxs)
        b = rc.build_baselines(cache, issues, t_idxs, current_vec=[r["sel_hits"] for r in cur])
        for k, v in b.items():
            for f in ("full", "dev", "holdout", "variance", "n"):
                self.assertIn(f, v, f"{k} missing {f}")

    def test_13_b7_below_b5_or_b6(self):
        """CURRENT (B7) must not beat random-choice (B5/B6) on full mean."""
        import json as _json
        from src.evaluation import window_study as ws
        issues = ws.load_issues(str(ROOT / "data/research/dlt-full-history.json"))
        cache = {}
        for c in range(10):
            cf = ROOT / (".agnes/work/p32/matrix_chunk_%d.json" % c)
            for t_str, rec in _json.loads(cf.read_text()).items():
                cache[int(t_str)] = rec["1000"]
        t_idxs = list(range(ws.COMMON_WARMUP, len(issues)))
        from src.evaluation import selector_decomposition as sd
        cur = sd.reconstruct_selector(issues, cache, t_idxs)
        b = rc.build_baselines(cache, issues, t_idxs, current_vec=[r["sel_hits"] for r in cur])
        self.assertLessEqual(b["B7_CURRENT"]["full"], b["B5_random_choice_ABCD"]["full"],
                             "CURRENT should not beat random-choice")

    # 14-15 complexity
    def test_14_complexity_costs_all_baselines(self):
        cc = rc.complexity_costs()
        self.assertEqual(len(cc), 8)
        for k, v in cc.items():
            for f in ("required_historical_state", "scoring_components",
                      "rng_dependency", "walk_forward", "candidate_generators"):
                self.assertIn(f, v, f"{k} missing {f}")

    def test_15_b7_most_complex(self):
        cc = rc.complexity_costs()
        self.assertEqual(cc["B7_CURRENT"]["candidate_generators"], 4)
        self.assertEqual(cc["B7_CURRENT"]["scoring_components"],
                         "base+history+recent+structure+risk + 4 candidate generators")

    # 16-17 simplification counterfactual
    def test_16_counterfactual_ci_contains_zero(self):
        import json as _json
        from src.evaluation import window_study as ws
        issues = ws.load_issues(str(ROOT / "data/research/dlt-full-history.json"))
        cache = {}
        for c in range(10):
            cf = ROOT / (".agnes/work/p32/matrix_chunk_%d.json" % c)
            for t_str, rec in _json.loads(cf.read_text()).items():
                cache[int(t_str)] = rec["1000"]
        t_idxs = list(range(ws.COMMON_WARMUP, len(issues)))
        from src.evaluation import selector_decomposition as sd
        cur = sd.reconstruct_selector(issues, cache, t_idxs)
        cf_res = rc.simplification_counterfactual(cache, issues, t_idxs,
                                                  [r["sel_hits"] for r in cur])
        self.assertTrue(cf_res["current_vs_random_choice_ABCD"]["holdout"]["contains_zero"],
                         "CI must contain 0 → cannot claim complex selector benefit")
        self.assertFalse(cf_res["current_vs_random_choice_ABCD"]["claim_allowed"])

    def test_17_counterfactual_fixed_D_ci(self):
        import json as _json
        from src.evaluation import window_study as ws
        issues = ws.load_issues(str(ROOT / "data/research/dlt-full-history.json"))
        cache = {}
        for c in range(10):
            cf = ROOT / (".agnes/work/p32/matrix_chunk_%d.json" % c)
            for t_str, rec in _json.loads(cf.read_text()).items():
                cache[int(t_str)] = rec["1000"]
        t_idxs = list(range(ws.COMMON_WARMUP, len(issues)))
        from src.evaluation import selector_decomposition as sd
        cur = sd.reconstruct_selector(issues, cache, t_idxs)
        cf_res = rc.simplification_counterfactual(cache, issues, t_idxs,
                                                  [r["sel_hits"] for r in cur])
        self.assertTrue(cf_res["current_vs_fixed_D_deterministic"]["holdout"]["contains_zero"])

    # 18-19 RNG
    def test_18_rng_reproducibility_risk(self):
        rng = rc.rng_reproducibility_decision()
        self.assertTrue(rng["c_rng_reproducibility_risk"])
        self.assertIn("seed=null", rng["reason"].lower() or "seed")
        self.assertEqual(rng["this_gate_change"], "NO (no production modification in P3-5)")

    def test_19_rng_fix_options(self):
        rng = rc.rng_reproducibility_decision()
        self.assertGreaterEqual(len(rng["future_fix_options"]), 2)

    # 20-21 1000 cap
    def test_20_window_cap_decision(self):
        cap = rc.window_cap_decision()
        self.assertIn(cap["analysis_window_decision"], ("KEEP_1000_TEMPORARILY", "EVIDENCE_SUPPORTS_CHANGE"))
        self.assertEqual(cap["analysis_window_decision"], "KEEP_1000_TEMPORARILY")

    def test_21_data_retention_separate(self):
        cap = rc.window_cap_decision()
        self.assertNotEqual(cap["data_retention"], cap["analysis_window_decision"])

    # 22-23 production options + direction
    def test_22_three_options(self):
        opts = rc.production_options()
        self.assertIn("OPTION_A_KEEP_CURRENT", opts)
        self.assertIn("OPTION_B_SIMPLIFY_SELECTOR", opts)
        self.assertIn("OPTION_C_BASELINE_FIRST_DETERMINISTIC", opts)

    def test_23_direction(self):
        d = rc.p35_direction()
        self.assertIn(d["direction"], ("KEEP_CURRENT_TEMPORARILY",
                                       "SIMPLIFICATION_WARRANTED_FOR_ENGINEERING",
                                       "RESEARCH_REQUIRED_BEFORE_CHANGE"))
        self.assertFalse(d["production_change_authorized"])

    # 24-25 reconcile + stop rule
    def test_24_reconcile_unified(self):
        r = rc.reconcile_p2_p3()
        self.assertIn("unified_explanation", r)
        self.assertIn("no_cherry_picking", r)

    def test_25_stop_rule(self):
        s = rc.research_stop_rule()
        self.assertTrue(s["stop_feature_mining"])
        self.assertTrue(s["stop_selector_tuning"])
        self.assertTrue(s["stop_ml_escalation"])
        self.assertGreaterEqual(len(s["future_research_requires"]), 4)

    # 26-27 product semantics audit
    def test_26_product_semantics_no_ui_change(self):
        sem = rc.product_semantics_audit(ROOT)
        self.assertFalse(sem["this_gate_changes_ui"])
        self.assertIn("banned_terms_scanned", sem)
        for b in ("提高中奖", "稳赢", "命中模型", "AI预测"):
            self.assertIn(b, sem["banned_terms_scanned"])

    def test_27_explanation_engine_disclaimer(self):
        sem = rc.product_semantics_audit(ROOT)
        eng = sem["explanation_engine"]
        self.assertTrue(eng["has_disclaimer"])
        self.assertEqual(eng["verdict"], "PASS (no unsupported→predictive packaging)")
        self.assertEqual(eng["banned_terms_found"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
