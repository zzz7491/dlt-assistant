"""P3-5 RESEARCH CLOSURE & PRODUCTION SIMPLIFICATION DECISION（research only；不改生产）。

本模块是 P3 研究阶段收口：
  - 组装 P2-1 → P3-4 冻结证据 → evidence ledger
  - 组件 inventory + 证据分类
  - 低成本 baseline B0-B7（复用 P3-2 candidate cache + P3-4 重建 CURRENT）
  - 复杂度成本（客观指标）+ 简化反事实（delta + CI）
  - RNG 可复现性决策 + 1000 cap 决策
  - 三生产方案 + P35_RECOMMENDED_PRODUCTION_DIRECTION

NO PRODUCTION CHANGE。不做新实验（读取已冻结 reports + P3-2 cache）。
"""
from __future__ import annotations

import math
import pathlib
import random
from typing import Any

from ..final_score import compute_final_scores
from . import baselines

STRATS = ("A", "B", "C", "D")
DEV_RATIO = 0.80
BOOTSTRAP_N = 10000
BOOTSTRAP_SEED = 20260930


def _mean(v: list[float]) -> float:
    return sum(v) / len(v) if v else 0.0


def _bootstrap_delta_ci(a: list[float], b: list[float], n: int = BOOTSTRAP_N,
                        seed: int = BOOTSTRAP_SEED) -> dict:
    """配对 bootstrap：mean(a) - mean(b) 的 95% CI（固定 seed，可复现）。"""
    npair = min(len(a), len(b))
    deltas = [a[i] - b[i] for i in range(npair)]
    rng = random.Random(seed)
    obs = sum(deltas) / npair
    boots = []
    for _ in range(n):
        s = [deltas[rng.randrange(npair)] for _ in range(npair)]
        boots.append(sum(s) / npair)
    boots.sort()
    lo = boots[int(0.025 * len(boots))]
    hi = boots[int(0.975 * len(boots))]
    return {"delta": round(obs, 4), "ci": [round(lo, 4), round(hi, 4)],
            "contains_zero": (lo <= 0.0 <= hi), "n_pairs": npair, "n_resamples": n}


def _hit_vec(cache: dict[int, dict], issues: list[dict], t_idxs: list[int],
             fixed: str | None) -> list[int]:
    """fixed A/B/C/D（来自 P3-2 cache window=1000）。"""
    out = []
    for t in t_idxs:
        c = cache[t][fixed]
        out.append(len(set(c["front"]) & set(issues[t]["front"])) +
                   len(set(c["back"]) & set(issues[t]["back"])))
    return out


def _uniform_random_ticket(issues: list[dict], t_idxs: list[int], seed: int = 13) -> list[int]:
    """B0：合法 5+2 纯随机票（固定 seed，确定性）。"""
    out = []
    for i, t in enumerate(t_idxs):
        comb = baselines.random_combo(seed * 1000003 + i)
        out.append(len(set(comb["front"]) & set(issues[t]["front"])) +
                   len(set(comb["back"]) & set(issues[t]["back"])))
    return out


def _random_choice_abcd(cache: dict[int, dict], issues: list[dict], t_idxs: list[int],
                        seed: int = 20260931) -> list[float]:
    """B5：每期从 A/B/C/D 均匀随机选一个（可复现；等价于候选期望）。"""
    out = []
    for i, t in enumerate(t_idxs):
        rng = random.Random(seed * 1000003 + i)
        keys = [g for g in STRATS if g in cache[t]]
        g = rng.choice(keys)
        out.append(_mean([len(set(cache[t][k]["front"]) & set(issues[t]["front"])) +
                          len(set(cache[t][k]["back"]) & set(issues[t]["back"]))
                          for k in keys]))  # 期望值（对 4 候选求均值）
        _ = g  # 期望与具体选中相同（均匀）
    return out


def build_baselines(cache: dict[int, dict], issues: list[dict], t_idxs: list[int],
                   current_vec: list[int] | None = None) -> dict[str, dict]:
    """B0-B7 全量/ dev / holdout 指标（复用 P3-2 cache + P3-4 重建 CURRENT）。"""
    n = len(t_idxs)
    dev = int(n * DEV_RATIO)
    hold = n - dev

    b0 = _uniform_random_ticket(issues, t_idxs)
    bA, bB, bC, bD = (_hit_vec(cache, issues, t_idxs, g) for g in ("A", "B", "C", "D"))
    b5 = _random_choice_abcd(cache, issues, t_idxs)
    b7 = current_vec if current_vec is not None else _mean(
        [sum([_hit_vec(cache, issues, t_idxs, g)[i] for g in STRATS]) / 4 for i in range(n)])
    b6 = [sum(_hit_vec(cache, issues, t_idxs, g)[i] for g in STRATS) / 4 for i in range(n)]

    def _block(v: list[float]) -> dict:
        if isinstance(v[0], float) and not isinstance(v[0], int):
            vv = [float(x) for x in v]
        else:
            vv = [float(x) for x in v]
        return {"full": round(_mean(vv), 4), "dev": round(_mean(vv[:dev]), 4),
                "holdout": round(_mean(vv[dev:]), 4),
                "variance": round(sum((x - _mean(vv)) ** 2 for x in vv) / len(vv), 4),
                "n": n}

    out = {
        "B0_uniform_random_valid_ticket": _block(b0),
        "B1_fixed_A": _block(bA), "B2_fixed_B": _block(bB),
        "B3_fixed_C": _block(bC), "B4_fixed_D": _block(bD),
        "B5_random_choice_ABCD": _block(b5),
        "B6_frequency_matched_random_selector": _block(b6),
        "B7_CURRENT": _block([float(x) for x in b7]),
    }
    return out


def complexity_costs() -> dict[str, dict]:
    """客观工程复杂度指标（不主观打分）：required historical state / scoring components /
    RNG dependency / walk-forward dependency / candidate generators。"""
    return {
        "B0_uniform_random_valid_ticket": {
            "required_historical_state": "none", "scoring_components": 0,
            "rng_dependency": "yes (ticket)", "walk_forward": "no",
            "candidate_generators": 0, "explanation_complexity": "none"},
        "B1_fixed_A": {
            "required_historical_state": "last 1000 issues", "scoring_components": "freq+recent+hot/cold+balance",
            "rng_dependency": "yes (strategy A sample)", "walk_forward": "no",
            "candidate_generators": 1, "explanation_complexity": "low"},
        "B2_fixed_B": {
            "required_historical_state": "last 1000 issues", "scoring_components": "freq+recent+hot/cold",
            "rng_dependency": "yes (strategy B sample)", "walk_forward": "no",
            "candidate_generators": 1, "explanation_complexity": "low"},
        "B3_fixed_C": {
            "required_historical_state": "none", "scoring_components": 0,
            "rng_dependency": "yes (random 5+2)", "walk_forward": "no",
            "candidate_generators": 1, "explanation_complexity": "none"},
        "B4_fixed_D": {
            "required_historical_state": "last 1000 issues",
            "scoring_components": "heat+missing+trend+inherit + combo 5 factors",
            "rng_dependency": "no (deterministic top-1)", "walk_forward": "no",
            "candidate_generators": 1, "explanation_complexity": "high (scored factors)"},
        "B5_random_choice_ABCD": {
            "required_historical_state": "last 1000 issues",
            "scoring_components": "4 candidate generators", "rng_dependency": "yes (choice)",
            "walk_forward": "no", "candidate_generators": 4,
            "explanation_complexity": "medium"},
        "B6_frequency_matched_random_selector": {
            "required_historical_state": "last 1000 issues + OOS selection history",
            "scoring_components": "4 candidate generators", "rng_dependency": "yes (choice)",
            "walk_forward": "yes (selection frequency)", "candidate_generators": 4,
            "explanation_complexity": "medium"},
        "B7_CURRENT": {
            "required_historical_state": "last 1000 issues + walk-forward OOS history/recent/rank",
            "scoring_components": "base+history+recent+structure+risk + 4 candidate generators",
            "rng_dependency": "yes (A/B/C sample) + C seed=null risk",
            "walk_forward": "yes (OOS maps, stateful)", "candidate_generators": 4,
            "explanation_complexity": "highest (5-factor + OOS + selector)"},
    }


def simplification_counterfactual(cache: dict[int, dict], issues: list[dict],
                                  t_idxs: list[int], current_vec: list[int]) -> dict:
    """STEP 8：若不用 CURRENT selector（改用最简单 / 随机 baseline），历史 OOS/holdout 损失。

    报告 delta + bootstrap CI；CI 含 0 → 不得声称复杂 selector 有实际收益。"""
    n = len(t_idxs)
    dev = int(n * DEV_RATIO)
    # 最简单且最接近 CURRENT 期望的替代：B5 random-choice-ABCD（无 walk-forward、无 RNG state）
    alt = _random_choice_abcd(cache, issues, t_idxs)
    alt_full = [float(x) for x in alt]
    cur_full = [float(x) for x in current_vec]
    ci_full = _bootstrap_delta_ci(cur_full, alt_full, seed=BOOTSTRAP_SEED)
    ci_hold = _bootstrap_delta_ci(cur_full[dev:], alt_full[dev:], seed=BOOTSTRAP_SEED + 1)
    # 固定 D（deterministic，无 RNG）作为可复现替代
    altD = [float(x) for x in _hit_vec(cache, issues, t_idxs, "D")]
    ciD_hold = _bootstrap_delta_ci(cur_full[dev:], altD[dev:], seed=BOOTSTRAP_SEED + 2)
    return {
        "current_vs_random_choice_ABCD": {
            "full": ci_full, "holdout": ci_hold,
            "claim_allowed": not ci_hold["contains_zero"] and ci_hold["delta"] > 0},
        "current_vs_fixed_D_deterministic": {
            "holdout": ciD_hold,
            "claim_allowed": not ciD_hold["contains_zero"] and ciD_hold["delta"] > 0},
        "note": "CI contains 0 → complex selector NOT demonstrated to beat the simpler alternative",
    }


def rng_reproducibility_decision() -> dict:
    """STEP 9：C seed 可复现性。生产 recommender seed=null（每次不同）→ 不可复现风险。"""
    return {
        "c_rng_reproducibility_risk": True,
        "reason": "production recommend() uses recommend.seed=null → C strategy RNG state "
                  "differs every run; P2-3 seed-0 proxy sits at 4th percentile of 50-seed C "
                  "distribution; P3-4 C seed x era rank unstable (mean|rho|=0.10).",
        "impact": "published C numbers are NOT reproducible across runs; snapshot hash pins "
                  "one realization only.",
        "future_fix_options": [
            "deterministic seed (config recommend.seed fixed)",
            "snapshot-bound seed (seed derived from issue/dataset sha)",
            "remove RNG dependency for C (deterministic pseudo-random or fixed strategy)",
        ],
        "this_gate_change": "NO (no production modification in P3-5)",
    }


def window_cap_decision() -> dict:
    """STEP 10：1000 cap。结合 P3-2（FULL 未证明更优）。区分 DATA RETENTION 与 ANALYSIS WINDOW。"""
    return {
        "data_retention": "KEEP (1000 draws retained; not the question here)",
        "analysis_window_decision": "KEEP_1000_TEMPORARILY",
        "evidence": "P3-2 FULL vs 1000: A delta -0.067 (Holm p=0.159), D -0.025 (Holm p=0.614); "
                    "no window confirmed better; B NO_WINDOW_EDGE",
        "conclusion": "no confirmatory evidence supports changing the 1000 analysis window; "
                     "retain temporarily, revisit only with a pre-registered hypothesis",
        "note": "data retention (storage) and analysis window are separate architectural concerns",
    }


def component_inventory() -> dict[str, dict]:
    """STEP 3/4：production recommendation pipeline 组件 + 角色 + 证据分类。

    role: PRODUCTION_USED / RESEARCH_ONLY / DISPLAY_ONLY / PUBLICATION_CRITICAL
    classification: PREDICTIVE_SUPPORTED / PREDICTIVE_UNSUPPORTED / PREDICTIVE_INCONCLUSIVE /
                    REDUNDANT / ENTERTAINMENT_ANALYTIC / OPERATIONALLY_REQUIRED /
                    PUBLICATION_REQUIRED / LEGACY_COMPATIBILITY
    约束：不得把 ENTERTAINMENT_ANALYTIC 标为 PREDICTIVE_SUPPORTED。"""
    INV = {
        "A": {"role": "PRODUCTION_USED",
              "classification": ["OPERATIONALLY_REQUIRED", "ENTERTAINMENT_ANALYTIC"],
              "evidence": "P2-2/P3-4: candidate quality near fair-random; not a predictor",
              "note": "candidate generator (balanced stat sample); retention for compatibility"},
        "B": {"role": "PRODUCTION_USED",
              "classification": ["OPERATIONALLY_REQUIRED", "ENTERTAINMENT_ANALYTIC"],
              "evidence": "P3-2 B NO_WINDOW_EDGE; candidate mean ~1.065",
              "note": "candidate generator (hot/cold mix)"},
        "C": {"role": "PRODUCTION_USED",
              "classification": ["ENTERTAINMENT_ANALYTIC", "LEGACY_COMPATIBILITY"],
              "evidence": "P2-3/P3-4: C seed unstable, non-reproducible (seed=None); "
                          "C is a random baseline not a model",
              "note": "random entertainment ticket; REPRODUCIBILITY_RISK"},
        "D": {"role": "PRODUCTION_USED",
              "classification": ["OPERATIONALLY_REQUIRED", "PREDICTIVE_INCONCLUSIVE"],
              "evidence": "P3-3 all D-feature ablations Holm p=1.0 (no feature has value)",
              "note": "scored combinatorial generator; no confirmed predictive edge"},
        "frequency": {"role": "PRODUCTION_USED",
                     "classification": ["PREDICTIVE_UNSUPPORTED", "ENTERTAINMENT_ANALYTIC", "REDUNDANT"],
                     "evidence": "P3-3 front/back freq AUC~0.5, redundant with avg_omit",
                     "note": "used only as construction factor, not a signal"},
        "omission": {"role": "PRODUCTION_USED",
                    "classification": ["PREDICTIVE_UNSUPPORTED", "ENTERTAINMENT_ANALYTIC"],
                    "evidence": "P3-3 omission family AUC~0.5, not supported",
                    "note": ""},
        "hot_cold": {"role": "PRODUCTION_USED",
                    "classification": ["PREDICTIVE_UNSUPPORTED", "ENTERTAINMENT_ANALYTIC", "REDUNDANT"],
                    "evidence": "P3-3 hot indicator redundant with freq",
                    "note": ""},
        "trend": {"role": "PRODUCTION_USED",
                  "classification": ["PREDICTIVE_UNSUPPORTED", "ENTERTAINMENT_ANALYTIC"],
                  "evidence": "P3-3 temperature/trend AUC~0.5",
                  "note": ""},
        "inherit": {"role": "PRODUCTION_USED",
                   "classification": ["PREDICTIVE_INCONCLUSIVE", "ENTERTAINMENT_ANALYTIC"],
                   "evidence": "P3-3 overlap/inherit no confirmed value (capped 15%)",
                   "note": ""},
        "odd_even_big_small_zone_sum_span": {"role": "PRODUCTION_USED",
                    "classification": ["PREDICTIVE_UNSUPPORTED", "ENTERTAINMENT_ANALYTIC"],
                    "evidence": "P3-3 candidate structure features |spearman|<=0.03",
                    "note": "structural construction only"},
        "base": {"role": "PRODUCTION_USED",
                 "classification": ["OPERATIONALLY_REQUIRED"],
                 "evidence": "static 60 + rank adjust; no history",
                 "note": "final_score component"},
        "risk": {"role": "PRODUCTION_USED",
                 "classification": ["OPERATIONALLY_REQUIRED", "ENTERTAINMENT_ANALYTIC"],
                 "evidence": "static structural penalty",
                 "note": ""},
        "history": {"role": "PRODUCTION_USED",
                    "classification": ["PREDICTIVE_INCONCLUSIVE", "OPERATIONALLY_REQUIRED"],
                    "evidence": "P2-2/P2-3: OOS history feedback no marginal selector effect; "
                                "P3-3 outcome-feedback not re-wrapped as feature",
                    "note": "selector input; no confirmed predictive value"},
        "recent": {"role": "PRODUCTION_USED",
                   "classification": ["PREDICTIVE_INCONCLUSIVE", "OPERATIONALLY_REQUIRED"],
                   "evidence": "P2-2 S1 vs S2(drop recent) delta 0; recent-5 feedback not confirmed",
                   "note": "selector input; no confirmed predictive value"},
        "structure": {"role": "PRODUCTION_USED",
                      "classification": ["PREDICTIVE_UNSUPPORTED", "ENTERTAINMENT_ANALYTIC"],
                      "evidence": "P3-4 structure component std=0 (structure_ctx=None neutral)",
                      "note": "selector input"},
        "final_score": {"role": "PRODUCTION_USED",
                        "classification": ["OPERATIONALLY_REQUIRED", "PREDICTIVE_INCONCLUSIVE"],
                        "evidence": "P3-4 margin not calibrated; final_score not a predictor",
                        "note": "cross-strategy ranking layer"},
        "selector": {"role": "PRODUCTION_USED",
                     "classification": ["PREDICTIVE_UNSUPPORTED", "OPERATIONALLY_REQUIRED"],
                     "evidence": "P3-4 H1-H4 all Holm p=1.0; NO robust edge; noise-compatible",
                     "note": "no confirmed predictive benefit"},
        "c_rng_seed": {"role": "PRODUCTION_USED",
                       "classification": ["LEGACY_COMPATIBILITY"],
                       "evidence": "P2-3/P3-4: seed=None non-reproducible; seed performance unstable",
                       "note": "REPRODUCIBILITY_RISK"},
        "recent_issues_1000": {"role": "OPERATIONALLY_REQUIRED",
                        "classification": ["OPERATIONALLY_REQUIRED", "LEGACY_COMPATIBILITY"],
                       "evidence": "P3-2: 1000 not confirmed superior; data retention separate",
                       "note": "KEEP_1000_TEMPORARILY"},
        "publication_snapshot": {"role": "PUBLICATION_CRITICAL",
                        "classification": ["PUBLICATION_REQUIRED", "OPERATIONALLY_REQUIRED"],
                       "evidence": "P0 immutable snapshot; 26112 hash bea8ef87 frozen",
                       "note": "must stay immutable"},
        "explanation_generation": {"role": "DISPLAY_ONLY",
                        "classification": ["ENTERTAINMENT_ANALYTIC"],
                       "evidence": "deterministic explanation engine; no predictive claim allowed",
                       "note": "wording audit required (STEP 12)"},
        "frontend_trend": {"role": "DISPLAY_ONLY",
                        "classification": ["ENTERTAINMENT_ANALYTIC"],
                       "evidence": "descriptive trend/trajectory views; no prediction wording",
                       "note": ""},
    }
    return INV


def production_options() -> dict[str, dict]:
    """STEP 13：三个未来方案（不主观选赢家；仅报告 6 维度）。"""
    return {
        "OPTION_A_KEEP_CURRENT": {
            "implementation_impact": "none",
            "reproducibility": "LOW (C seed=None, stateful walk-forward selector)",
            "research_evidence": "no confirmed edge; keeps complexity without demonstrated benefit",
            "backward_compatibility": "full",
            "snapshot_compatibility": "full (26112 unchanged)",
            "migration_risk": "none",
        },
        "OPTION_B_SIMPLIFY_SELECTOR": {
            "implementation_impact": "replace 5-factor + OOS walk-forward selector with fixed or "
                                     "random-choice among A/B/C/D; remove stateful OOS maps",
            "reproducibility": "MEDIUM-HIGH (deterministic or fixed seed)",
            "research_evidence": "P3-4: simplification loses nothing confirmed "
                                 "(all nulls not beaten; candidate means ~= random)",
            "backward_compatibility": "candidate generation unchanged; only selection policy changes",
            "snapshot_compatibility": "requires new snapshot (numbers may shift) - re-publish",
            "migration_risk": "LOW (selection layer isolated; requires a production-change Gate)",
        },
        "OPTION_C_BASELINE_FIRST_DETERMINISTIC": {
            "implementation_impact": "publish a single deterministic entertainment ticket "
                                     "(e.g. fixed C with deterministic seed) - remove A/B/D + selector",
            "reproducibility": "HIGH (deterministic, seed-bound)",
            "research_evidence": "P3-3/P3-4: no predictive feature/edge; simplest honest baseline",
            "backward_compatibility": "BREAKING (removes multi-candidate display)",
            "snapshot_compatibility": "new snapshot required; 26112 immutable until then",
            "migration_risk": "MEDIUM (largest change; separate production-change Gate)",
        },
    }


def p35_direction() -> dict:
    """STEP 14：P35_RECOMMENDED_PRODUCTION_DIRECTION（非部署授权）。"""
    return {
        "direction": "KEEP_CURRENT_TEMPORARILY",
        "rationale": "no confirmatory evidence supports either keeping the complex selector for a "
                     "predicted benefit OR changing it now. Selector edge is noise-compatible "
                     "(P3-4); no predictive feature confirmed (P3-3). A production change "
                     "(OPTION B/C) would be engineering-simplification-driven, not evidence-confirmed; "
                     "it requires a separate, explicitly authorized production-change Gate.",
        "production_change_authorized": False,
        "simplification_warranted_for_engineering": True,
        "note": "KEEP_CURRENT_TEMPORARILY = no algorithm change now; simplification is an "
                "engineering option flagged for a future authorized production-change Gate.",
    }


def research_stop_rule() -> dict:
    """STEP 15：研究停止规则。"""
    return {
        "stop_feature_mining": True,
        "stop_selector_tuning": True,
        "stop_ml_escalation": True,
        "reason": "P3-3 confirmed no identifiable predictive feature; P3-4 confirmed no robust "
                   "selector edge (noise-compatible, seed/era/unstable). Continuing to mine "
                   "within the same historical-statistics family or escalate to ML would only "
                   "expand overfitting space.",
        "future_research_requires": [
            "a NEW testable hypothesis INDEPENDENT of the current historical-statistics system",
            "pre-registered hypothesis + mechanism + metric + holdout protocol BEFORE running",
            "immutable dataset version + walk-forward + baseline + effect size + CI + "
            "multiple-comparison correction + seed policy + negative-result retention",
            "no post-hoc production change",
        ],
    }


def product_semantics_audit(root: pathlib.Path) -> dict:
    """STEP 11/12：扫描用户可见文案中的预测性措辞（仅报告，不改 UI）。

    违禁词（无免责上下文时）：预测 / 提高中奖 / 中奖概率 / 稳赢 / 高概率 / 命中模型 /
    likely / more likely / will hit。允许：非预测 / 不构成预测 / 娱乐 / 不代表 / 历史统计。
    explanation 引擎（src/explanation.py）须把 unsupported feature 表述为
    "组合构造因素"而非"更可能出现"。"""
    banned = ["提高中奖", "中奖概率", "稳赢", "高概率", "命中模型", "AI预测",
              "更可能出现", "更容易出", "will hit", "more likely to hit"]
    findings: list[dict] = []
    pub_dir = root / "public"
    if pub_dir.exists():
        for html in sorted(pub_dir.glob("*.html")):
            text = html.read_text()
            hits = [b for b in banned if b in text]
            if hits:
                findings.append({"file": f"public/{html.name}", "banned_terms": hits,
                                 "action": "future revision required (this Gate: NO UI change)"})
    # explanation engine check (allowed wording)
    exp_path = root / "src/explanation.py"
    exp_ok = False
    exp_hits = []
    if exp_path.exists():
        etext = exp_path.read_text()
        exp_ok = "不构成预测" in etext or "不代表任何号码会中奖" in etext
        exp_hits = [b for b in banned if b in etext]
    return {
        "banned_terms_scanned": banned,
        "frontend_findings": findings,
        "explanation_engine": {
            "file": "src/explanation.py",
            "has_disclaimer": exp_ok,
            "banned_terms_found": exp_hits,
            "verdict": "PASS (no unsupported→predictive packaging)" if exp_ok and not exp_hits
                       else "REVIEW NEEDED",
        },
        "this_gate_changes_ui": False,
    }


def evidence_ledger() -> list[dict]:
    """STEP 2：P2-1 → P3-4 冻结证据台账（claim/source/population/metric/effect/CI/p/holdout/
    interpretation/limitations）。"""
    return [
        {"claim": "selector mean historically higher than a random single ticket (P2-1)",
         "source_gate": "P2-1", "population": "1000 draws, warmup 100, 900 OOS",
         "metric": "S1 total-hit mean", "effect": 1.0878, "CI": None,
         "raw_p": None, "adjusted_p": None, "holdout_status": "exploratory (pre-holdout design)",
         "interpretation": "apparent edge over a single random ticket (S0)",
         "limitations": "single-ticket null is weak; not the fair null; population 900 not 1930"},
        {"claim": "selector has fair-null edge over random-choice(A/B/C/D)",
         "source_gate": "P2-2", "population": "1000 draws, 900 OOS",
         "metric": "S1 vs S7 delta", "effect": 0.05098, "CI": [0.00015, 0.10133],
         "raw_p": 0.04593, "adjusted_p": 0.10196, "holdout_status": "NOT CONFIRMED (Holm)",
         "interpretation": "raw p<0.05 but Holm-adjusted p=0.102 -> not a confirmed edge",
         "limitations": "multiple-variant comparison; C seed=None non-reproducible; C 78.89% share"},
        {"claim": "a simpler candidate beats CURRENT on final holdout",
         "source_gate": "P2-3", "population": "900, dev 630 / holdout 270",
         "metric": "T0 vs S7 holdout", "effect": -0.0134, "CI": [-0.1023, 0.07585],
         "raw_p": 1.0, "adjusted_p": 1.0, "holdout_status": "NOT CONFIRMED",
         "interpretation": "best simple candidate not better than CURRENT vs fair-null; "
                           "DECISION=KEEP_CURRENT_TEMPORARILY",
         "limitations": "C seed-0 proxy at 4th percentile; T5/T7 identical to T0"},
        {"claim": "full history (2930) integrity + production 1000 overlap",
         "source_gate": "P3-1", "population": "07001->26112, 2930 draws",
         "metric": "1000/1000 exact overlap", "effect": 1.0, "CI": None,
         "raw_p": None, "adjusted_p": None, "holdout_status": "n/a (data gate)",
         "interpretation": "frozen dataset SHA ba4bfb09; dataset reliable",
         "limitations": "single source (500.com); no cross-source"},
        {"claim": "a rolling window beats the 1000 window for A/B/D",
         "source_gate": "P3-2", "population": "1930 OOS, dev 1544 / holdout 386",
         "metric": "FULL vs 1000 delta (A/D)", "effect": -0.067, "CI": [-0.113, -0.022],
         "raw_p": 0.053, "adjusted_p": 0.15891, "holdout_status": "NOT CONFIRMED",
         "interpretation": "FULL point estimate worse but not significant after Holm; "
                           "A KEEP_1000 / B NO_WINDOW_EDGE / D KEEP_1000; cap=INSUFFICIENT",
         "limitations": "no window confirmed better; desciptive only"},
        {"claim": "a historical statistic feature has strict OOS predictive value",
         "source_gate": "P3-3", "population": "1930 OOS, dev 1544 / holdout 386",
         "metric": "single-number AUC + D-ablation", "effect": "AUC~0.5",
         "CI": None, "raw_p": None, "adjusted_p": "ablation all Holm p=1.0",
         "holdout_status": "NOT CONFIRMED",
         "interpretation": "SUPPORTED features = NONE; no identifiable predictive feature; "
                           "ML not justified",
         "limitations": "highly imbalanced labels; redundancy (freq~avg_omit, cur_omit~omit_ratio)"},
        {"claim": "CURRENT selector edge is robust and informative",
         "source_gate": "P3-4", "population": "1930 OOS, dev 1544 / holdout 386",
         "metric": "H1-H4 confirmatory + freq-matched/conditional nulls", "effect": -0.025,
         "CI": [-0.094, 0.056], "raw_p": 0.747, "adjusted_p": 1.0,
         "holdout_status": "NOT CONFIRMED",
         "interpretation": "CURRENT (1.0544) below fair-random (1.0563) and freq-matched null; "
                           "mechanism = SEED_DEPENDENT+UNCALIBRATED+ERA_DEPENDENT+NOISE_COMPATIBLE; "
                           "ML reconsideration NOT warranted",
         "limitations": "P3-4 reconstruction uses reproducible P3-2 candidates; P2-2 seed=None "
                        "not directly comparable; walk-forward OOS differs from P2 warmup=100"},
    ]


def reconcile_p2_p3() -> dict:
    """STEP 5：统一解释 P2/P3 全链路（不 cherry-pick）。"""
    return {
        "unified_explanation": (
            "Across P2-1..P3-4, the production recommendation chain shows NO confirmed predictive "
            "edge. P2-1's 'selector beats a random ticket' was a weak single-ticket null. "
            "P2-2's fair-null delta (0.051, raw p 0.046) failed Holm correction (0.102) and used "
            "non-reproducible C (seed=None) with a 78.9% C share. P2-3 final holdout could not beat "
            "the fair null (p=1.0). P3-3 confirmed no historical-statistics feature has OOS value "
            "and no D ablation improves OOS hits. P3-4 decomposed the apparent edge and found the "
            "CURRENT selector sits BELOW the fair-random and frequency-matched nulls on the "
            "final holdout; the effect is seed-dependent, uncalibrated in margin, era-dependent, "
            "and compatible with noise. The single coherent story: the pipeline is a "
            "well-implemented ENTERTAINMENT/analytics system, not a predictor; every apparent "
            "edge disappears under a proper multiple-comparison-corrected, reproducible, "
            "holdout-confirmed test."
        ),
        "no_cherry_picking": "each gate's HOLDOUT/adjusted evidence (not the best exploratory "
                             "slice) is used; exploratory P2-1 single-ticket advantage is "
                             "explicitly superseded by P2-2/P3-4 fair-null nulls.",
        "common_thread": "high candidate interchangeability + seed/era instability + high "
                         "lottery noise -> small deltas are noise, not signal.",
    }
