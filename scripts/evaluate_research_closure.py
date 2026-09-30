#!/usr/bin/env python3
"""P3-5 RESEARCH CLOSURE & PRODUCTION SIMPLIFICATION DECISION runner（research only；NO PRODUCTION CHANGE）。

产出（STEP 19）：
  reports/p35-evidence-ledger.json
  reports/p35-component-inventory.json
  reports/p35-baseline-comparison.json
  reports/p35-production-options.json
  reports/P35-SIMPLIFICATION-DECISION.md
  reports/P3-RESEARCH-CLOSURE.md
  docs/research/EXPERIMENT-CONTRACT.md
  tests/test_p35_research_closure.py
更新：CHANGELOG.md / TASK_STATUS.md

禁止：修改生产；push；deploy；ML；调权重；挑 seed。
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src.evaluation import window_study as ws
from src.evaluation import selector_decomposition as sd
from src.evaluation import research_closure as rc

DATASET_SHA = "ba4bfb09d46aa66ab72c2ba3f72057e37ffca293ac76e1e3a21dde77f1e4dbbf"
SNAP_HASH = "bea8ef87f3f137238686ae52712f922956215408f0cf54187b9295d8f1ae5fad"


def verify_integrity(root: pathlib.Path) -> bool:
    from src.evaluation import history_integrity as hi
    data = json.loads((root / "data/research/dlt-full-history.json").read_text())
    if hi.dataset_sha256(data["issues"]) != DATASET_SHA:
        print("[P3-5] ⚠ DATASET SHA MISMATCH — STOP"); return False
    recs = json.loads((root / "public/data/published_recommendations.json").read_text())
    last = recs["items"][-1]
    if not (last["issue"] == "26112" and last["snapshot_hash"] == SNAP_HASH
            and last["numbers"] == {"front": [5, 12, 17, 28, 31], "back": [4, 7]}):
        print("[P3-5] ⚠ 26112 snapshot CHANGED — STOP"); return False
    if "recent_issues: 1000" not in (root / "config/settings.yaml").read_text():
        print("[P3-5] ⚠ recent_issues changed — STOP"); return False
    base = json.loads((root / ".agnes/work/p33/p33-precheck-baseline.json").read_text())
    for f, h in base["production_baseline_sha256"].items():
        if hashlib.sha256((root / f).read_bytes()).hexdigest() != h:
            print(f"[P3-5] ⚠ production file CHANGED: {f} — STOP"); return False
    print("[P3-5] dataset + 26112 + recent_issues=1000 + production files UNCHANGED")
    return True


def load_p32_cache(root: pathlib.Path) -> dict[int, dict]:
    cache: dict[int, dict] = {}
    for c in range(10):
        cf = root / (".agnes/work/p32/matrix_chunk_%d.json" % c)
        for t_str, rec in json.loads(cf.read_text()).items():
            cache[int(t_str)] = rec["1000"]
    return cache


def main():
    root = pathlib.Path(__file__).resolve().parent.parent
    out = root / "reports"
    out.mkdir(parents=True, exist_ok=True)

    if not verify_integrity(root):
        return

    issues = ws.load_issues(str(root / "data/research/dlt-full-history.json"))
    t_idxs = list(range(ws.COMMON_WARMUP, len(issues)))
    n = len(t_idxs)
    dev = int(n * 0.80)
    print(f"[P3-5] {n} OOS (dev {dev} / holdout {n - dev})")

    # ---- evidence ledger (STEP 2/5) ----
    ledger = rc.evidence_ledger()
    (out / "p35-evidence-ledger.json").write_text(
        json.dumps(ledger, indent=2, ensure_ascii=False), encoding="utf-8")

    # ---- component inventory (STEP 3/4) ----
    comp = rc.component_inventory()
    (out / "p35-component-inventory.json").write_text(
        json.dumps(comp, indent=2, ensure_ascii=False), encoding="utf-8")

    # ---- baselines B0-B7 (STEP 6/7/8) ----
    cache = load_p32_cache(root)
    cur_recs = sd.reconstruct_selector(issues, cache, t_idxs)
    cur_vec = [r["sel_hits"] for r in cur_recs]
    baselines = rc.build_baselines(cache, issues, t_idxs, current_vec=cur_vec)
    complexity = rc.complexity_costs()
    cf = rc.simplification_counterfactual(cache, issues, t_idxs, cur_vec)
    baseline_payload = {
        "meta": {"dataset_sha256": DATASET_SHA, "n_oos": n, "dev": dev, "holdout": n - dev,
                 "source": "P3-2 candidate cache (window=1000, frozen) + P3-4 CURRENT reconstruction",
                 "no_retraining": True},
        "baselines": baselines,
        "complexity_costs": complexity,
        "simplification_counterfactual": cf,
        "ranking_by_full_mean": sorted(baselines.items(),
                                       key=lambda kv: -kv[1]["full"]),
    }
    (out / "p35-baseline-comparison.json").write_text(
        json.dumps(baseline_payload, indent=2, ensure_ascii=False), encoding="utf-8")

    # ---- production options + direction (STEP 13/14/9/10) ----
    options = rc.production_options()
    direction = rc.p35_direction()
    rng = rc.rng_reproducibility_decision()
    cap = rc.window_cap_decision()
    options_payload = {
        "options": options,
        "p35_recommended_direction": direction,
        "rng_reproducibility": rng,
        "window_cap_decision": cap,
        "research_stop_rule": rc.research_stop_rule(),
        "reconcile": rc.reconcile_p2_p3(),
        "production_change_authorized": False,
    }
    (out / "p35-production-options.json").write_text(
        json.dumps(options_payload, indent=2, ensure_ascii=False), encoding="utf-8")

    # ---- product semantics / explanation audit (STEP 11/12) ----
    semantics = rc.product_semantics_audit(root)
    options_payload["product_semantics_audit"] = semantics
    (out / "p35-production-options.json").write_text(
        json.dumps(options_payload, indent=2, ensure_ascii=False), encoding="utf-8")

    # ---- P35-SIMPLIFICATION-DECISION.md (STEP 19) ----
    (out / "P35-SIMPLIFICATION-DECISION.md").write_text(_decision_md(baseline_payload,
                                                                      options_payload,
                                                                      ledger, comp),
                                                         encoding="utf-8")
    # ---- P3-RESEARCH-CLOSURE.md (STEP 17) ----
    (out / "P3-RESEARCH-CLOSURE.md").write_text(_closure_md(), encoding="utf-8")
    # ---- EXPERIMENT-CONTRACT.md (STEP 16) ----
    (root / "docs/research").mkdir(parents=True, exist_ok=True)
    (root / "docs/research/EXPERIMENT-CONTRACT.md").write_text(_experiment_contract(),
                                                                encoding="utf-8")
    print("[P3-5] all artifacts written")
    print("  direction:", direction["direction"], "| simplification_warranted_for_engineering:",
          direction["simplification_warranted_for_engineering"])
    print("  RNG risk:", rng["c_rng_reproducibility_risk"],
          "| 1000 cap:", cap["analysis_window_decision"])
    rk = baseline_payload["ranking_by_full_mean"]
    print("  baseline ranking (full mean):",
          " ".join(f"{k}={v['full']}" for k, v in rk))


def _decision_md(bp: dict, op: dict, ledger: list, comp: dict) -> str:
    b = bp["baselines"]
    cf = bp["simplification_counterfactual"]
    direction = op["p35_recommended_direction"]
    L = [
        "# P3-5 Production Simplification Decision (Research Closure)",
        "",
        f"dataset `{DATASET_SHA[:16]}` · {bp['meta']['n_oos']} OOS (dev {bp['meta']['dev']} / "
        f"holdout {bp['meta']['holdout']}) · NO PRODUCTION CHANGE · source: P3-2 cache + P3-4 reconstruction",
        "",
        "> 唯一目标：基于 P2+P3 全部 OOS/holdout 证据，判断当前生产推荐链的复杂度哪些有证据支持、"
        "哪些仅娱乐/解释、哪些可简化、哪些当前绝不应改。本 Gate 只形成决策建议与冻结基线。",
        "",
        "## Baseline B0-B7 (mean total hits, full OOS / holdout)",
        "",
        "| baseline | full | holdout | variance |",
        "|---|---|---|---|",
    ]
    for k, v in b.items():
        L.append(f"| {k} | {v['full']} | {v['holdout']} | {v['variance']} |")
    L += ["", "## Complexity Cost (objective metrics)", "",
          "| baseline | historical state | scoring comps | RNG | walk-forward | cand gens |",
          "|---|---|---|---|---|---|"]
    for k, v in bp["complexity_costs"].items():
        L.append(f"| {k} | {v['required_historical_state']} | {v['scoring_components']} | "
                 f"{v['rng_dependency']} | {v['walk_forward']} | {v['candidate_generators']} |")
    cur_vs = cf["current_vs_random_choice_ABCD"]
    L += ["", "## Simplification Counterfactual (STEP 8)", "",
          f"- CURRENT vs random-choice(ABCD): full Δ={cur_vs['full']['delta']} "
          f"CI[{cur_vs['full']['ci'][0]},{cur_vs['full']['ci'][1]}] "
          f"{'(excludes 0)' if not cur_vs['full']['contains_zero'] else '(contains 0)'}; "
          f"holdout Δ={cur_vs['holdout']['delta']} CI[{cur_vs['holdout']['ci'][0]},"
          f"{cur_vs['holdout']['ci'][1]}] "
          f"{'(excludes 0)' if not cur_vs['holdout']['contains_zero'] else '(contains 0)'}",
          f"- CURRENT vs fixed-D (deterministic): holdout Δ={cf['current_vs_fixed_D_deterministic']['holdout']['delta']} "
          f"CI[{cf['current_vs_fixed_D_deterministic']['holdout']['ci'][0]},"
          f"{cf['current_vs_fixed_D_deterministic']['holdout']['ci'][1]}]",
          f"- claim_allowed (complex selector actually better): "
          f"{cf['current_vs_random_choice_ABCD']['claim_allowed']} → "
          "**" + ('yes' if cf['current_vs_random_choice_ABCD']['claim_allowed']
                  else 'NO — simpler alternative not beaten') + "****",
          ""]
    L += ["## RNG / Reproducibility (STEP 9)", "",
          f"- C RNG reproducibility risk: **{op['rng_reproducibility']['c_rng_reproducibility_risk']}** "
          f"({op['rng_reproducibility']['reason']})",
          f"- future fix options: " + "; ".join(op['rng_reproducibility']['future_fix_options'])
          + " · this Gate: " + op['rng_reproducibility']['this_gate_change']]
    L += ["", "## 1000-draw Cap (STEP 10)", "",
          f"- data retention: {op['window_cap_decision']['data_retention']}",
          f"- analysis window decision: **{op['window_cap_decision']['analysis_window_decision']}**",
          f"- evidence: {op['window_cap_decision']['evidence']}"]
    L += ["", "## Production Options (STEP 13)", ""]
    for k, v in op["options"].items():
        L.append(f"### {k}")
        for dim, val in v.items():
            L.append(f"  - {dim}: {val}")
        L.append("")
    L += ["## P35 Recommended Production Direction (STEP 14)", "",
          f"**{direction['direction']}** (simplification warranted for engineering: "
          f"{direction['simplification_warranted_for_engineering']}) — NOT a deployment "
          f"authorization.", "", direction["rationale"]]
    L += ["", "## Component Evidence Classification (STEP 4)", "",
          "| component | role | classification |", "|---|---|---|"]
    for k, v in comp.items():
        L.append(f"| {k} | {v['role']} | {' / '.join(v['classification'])} |")

    sem = op.get("product_semantics_audit", {})
    L += ["", "## Product Semantics & Explanation Audit (STEP 11/12)", "",
          "- FROZEN wording: DLT results are random; historical statistics are for "
          "entertainment analysis / trend display / explaining recommendation generation ONLY.",
          "- BANNED wording (never claim): 提高中奖概率 / 预测下一期 / AI预测 / 高概率号码 / 稳赢 / 命中模型.",
          "- Frontend findings: " +
          ("NONE" if not sem.get("frontend_findings") else
           "; ".join(f"{f['file']}: {f['banned_terms']}" for f in sem["frontend_findings"]))
          + "  → flagged for FUTURE revision (this Gate: NO UI change)",
          f"- Explanation engine (src/explanation.py): **{sem.get('explanation_engine', {}).get('verdict')}** "
          f"(disclaimer present = {sem.get('explanation_engine', {}).get('has_disclaimer')})"]

    stop = op["research_stop_rule"]
    L += ["", "## Research Stop Rule (STEP 15)", "",
          f"- STOP feature mining: **{stop['stop_feature_mining']}**",
          f"- STOP selector tuning: **{stop['stop_selector_tuning']}**",
          f"- STOP ML escalation: **{stop['stop_ml_escalation']}**",
          "", "Future research requires: " + "; ".join(stop["future_research_requires"])]

    L += ["", "## FINAL ANSWERS (STEP 20)", "",
          "P2/P3 PREDICTIVE EVIDENCE: NOT CONFIRMED",
          "IDENTIFIABLE PREDICTIVE FEATURE: NO",
          "ROBUST SELECTOR EDGE: NO",
          "ML JUSTIFIED: NO",
          "CURRENT COMPLEXITY PREDICTIVELY JUSTIFIED: NO",
          "CURRENT PIPELINE OPERATIONALLY VALID: YES (entertainment/explanation, not prediction)",
          f"C RNG REPRODUCIBILITY RISK: {'YES' if op['rng_reproducibility']['c_rng_reproducibility_risk'] else 'NO'}",
          "FULL HISTORY SUPERIOR TO 1000: NO",
          f"1000 WINDOW DECISION: {op['window_cap_decision']['analysis_window_decision']}",
          "FEATURE MINING SHOULD CONTINUE: NO",
          "SELECTOR TUNING SHOULD CONTINUE: NO",
          f"PRODUCTION DIRECTION: {direction['direction']}",
          "PRODUCTION CHANGE AUTHORIZED: NO",
          "PRODUCTION ALGORITHM CHANGED: NO",
          "PRODUCTION CAP CHANGED: NO",
          "26112 SNAPSHOT CHANGED: NO",
          "PUSH: NO",
          "DEPLOY: NO",
          ""]
    return "\n".join(L)


def _closure_md() -> str:
    return "\n".join([
        "# P3 Research Phase Closure",
        "",
        "## Per-Gate Summary",
        "",
        "| Gate | Population | Key evidence | Status |",
        "|---|---|---|---|",
        "| P3-1 | 2930 draws | 1000/1000 exact overlap; SHA ba4bfb09 frozen | PASS |",
        "| P3-2 | 1930 OOS | no window confirmed better; A/D KEEP_1000; B NO_WINDOW_EDGE; cap INSUFFICIENT | PASS |",
        "| P3-3 | 1930 OOS | no identifiable predictive feature; D-ablation all Holm p=1.0; ML not justified | PASS |",
        "| P3-4 | 1930 OOS | no robust selector edge; noise-compatible; seed/era/unstable; ML not warranted | PASS |",
        "| P3-5 | 1930 OOS | closure: direction KEEP_CURRENT_TEMPORARILY; NO production change | PASS |",
        "",
        "## WHAT WE LEARNED",
        "- The production chain is a well-implemented **entertainment/analytics** system, not a predictor.",
        "- The strongest fair null (frequency-matched / random-choice among A/B/C/D) is NOT beaten by the CURRENT selector.",
        "- Candidate sets are near-interchangeable (pairwise diff ≈ 0); selection effects are small and unstable.",
        "- C is non-reproducible (seed=None) and its seed×era performance is unstable.",
        "",
        "## WHAT FAILED TO SHOW EVIDENCE",
        "- No historical-statistics feature (freq/omission/temperature/overlap/sum/span/odd-even/size/structure/risk) has OOS value (P3-3).",
        "- No selector mechanism has a holdout-confirmed, seed/era-robust edge (P3-4).",
        "- No ML justification (P3-3, P3-4).",
        "",
        "## WHAT REMAINS UNKNOWN",
        "- Whether an INDEPENDENT new hypothesis (outside the historical-statistics family) could have signal.",
        "- The exact source of the early P2-2 apparent edge (seed=None non-reproducibility is the leading candidate).",
        "",
        "## WHAT PRODUCTION MUST NOT CLAIM",
        "- Improving win probability / predicting next draw / 'AI prediction' / high-probability numbers / 'stable win' / hit model.",
        "- Historical statistics are ENTERTAINMENT/ANALYTIC/TREND and EXPLANATION material only.",
        "",
        "## WHAT FUTURE RESEARCH REQUIRES",
        "- A NEW, independent testable hypothesis + pre-registered protocol (docs/research/EXPERIMENT-CONTRACT.md).",
        "- No feature mining / selector tuning / ML escalation until then.",
        "",
    ])


def _experiment_contract() -> str:
    return "\n".join([
        "# Research Experiment Contract (P3 onward)",
        "",
        "Every future research experiment MUST satisfy all of the following:",
        "",
        "1. **Hypothesis before result** — a falsifiable hypothesis + mechanism, written before running.",
        "2. **Immutable dataset version** — pinned dataset SHA256 (current: ba4bfb09...).",
        "3. **Walk-forward** — target t uses only issues < t (no future leakage).",
        "4. **Dev/holdout split** — fixed ratio, frozen; holdout used ONCE for confirmation.",
        "5. **Baseline** — at least a fair null (frequency-matched / random-choice) plus a simple baseline.",
        "6. **Effect size + CI** — report effect size and bootstrap CI, not p-value alone.",
        "7. **Multiple-comparison correction** — Holm (primary) and/or BH-FDR; pre-declared family.",
        "8. **Seed policy** — deterministic seeds; no post-hoc seed selection; document proxy percentiles.",
        "9. **Negative-result retention** — keep and commit null results; do not discard.",
        "10. **No post-hoc production change** — research must not modify the production algorithm; "
        "any change goes through a separately authorized production-change Gate.",
        "",
        "STOP rules (inherited from P3-5): no feature mining within the current historical-statistics "
        "family, no selector tuning, no ML escalation, until a NEW independent hypothesis is "
        "pre-registered under this contract.",
        "",
    ])


if __name__ == "__main__":
    main()
