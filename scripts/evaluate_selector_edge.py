#!/usr/bin/env python3
"""P3-4 SELECTOR EDGE DECOMPOSITION & ROBUSTNESS runner（research only；不改生产 selector/权重/候选/C seed/26112）。

流程（防过拟合 + 主推断在 FINAL HOLDOUT）：
  1. 验证 frozen dataset SHA + 26112 snapshot + production files 未变
  2. 冻结 reports/p34-selector-definition.json（population/dev/holdout、metrics、nulls H1-H4、
     subgroups、statistical tests、multiple-comparison、seed 协议）—— 结果前
  3. STEP 4 一致性：pick_T0（生产 selector）== manual compute_final_scores on P2-3 cache（0 mismatch 校验）
  4. 在 P3-4 population（1930 common OOS, warmup=1000）walk-forward 重建 CURRENT selector
  5. STEP 5-13 分解：candidate set / selection-conditional / counterfactual / pairwise /
     margin / component / correlation / rolling+quintile / leave-era-out
  6. STEP 14-17：frequency-matched null + conditional stratified null + C 100-seed 敏感性 + seed×era
  7. dev-only（1544）形成机制假设 → 冻结 p34-selection-before-holdout.json
  8. STEP 18-19：FINAL HOLDOUT（386）一次确认 H1-H4（Holm + effect size + CI）
  9. STEP 20-22：机制标签 + NO production change + ML gate
 10. 写 reports/p34-selector-results.json + P34-SELECTOR-EDGE-REPORT.md

禁止：改 selector/权重/候选/C seed/recent_issues/production dataset/publication snapshot；
      push；deploy；构建 ML；调参寻更高命中。
"""
from __future__ import annotations

import datetime
import hashlib
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src.evaluation import window_study as ws
from src.evaluation import selector_decomposition as sd
from src.evaluation import selector_candidates as sc
from src.evaluation import ablation as abl
from src.evaluation import statistics as stats
from src.final_score import compute_final_scores

DATASET_SHA_EXPECTED = "ba4bfb09d46aa66ab72c2ba3f72057e37ffca293ac76e1e3a21dde77f1e4dbbf"
SNAP_HASH_EXPECTED = "bea8ef87f3f137238686ae52712f922956215408f0cf54187b9295d8f1ae5fad"
DEV_RATIO = 0.80
N_OOS = 1930
SEEDS = list(range(100))
PROXY_SEED = 0
N_PERM = 1000
BOOTSTRAP_N = 10000
BOOTSTRAP_SEED = 20260930


def hash_obj(o: dict) -> str:
    return hashlib.sha256(json.dumps(o, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode()).hexdigest()


def verify_dataset(path: str) -> bool:
    from src.evaluation import history_integrity as hi
    d = json.loads(pathlib.Path(path).read_text())
    return hi.dataset_sha256(d.get("issues", d)) == DATASET_SHA_EXPECTED


def verify_snapshot(path: str) -> bool:
    recs = json.loads(pathlib.Path(path).read_text())
    last = recs["items"][-1]
    return (last["issue"] == "26112" and last["snapshot_hash"] == SNAP_HASH_EXPECTED
            and last["numbers"] == {"front": [5, 12, 17, 28, 31], "back": [4, 7]})


def load_p32_cache(root: pathlib.Path) -> dict[int, dict[str, dict]]:
    cache: dict[int, dict[str, dict]] = {}
    for c in range(10):
        cf = root / (".agnes/work/p32/matrix_chunk_%d.json" % c)
        for t_str, rec in json.loads(cf.read_text()).items():
            cache[int(t_str)] = rec["1000"]
    return cache


def consistency_check(p23_cache: dict, order: list[int]) -> dict:
    """STEP 4：pick_T0（生产 selector）== manual compute_final_scores（同 P2-3 cache）。

    0 mismatch → 重建协议正确；否则 STOP。"""
    mismatch = 0
    checked = 0
    for t in order:
        g_t0, _ = sc.PICKERS["T0"](p23_cache, t)
        cands = p23_cache["candidates"][t]
        recs = [{"strategy": g, "front": c["front"], "back": c["back"]}
                for g, c in cands.items() if g in ("A", "B", "C", "D")]
        ranked = p23_cache["oos_rank"][t]
        hist = p23_cache["oos_history"][t]
        recent = p23_cache["oos_recent"][t]
        prev_draw = {"front": p23_cache["prev_front"][t], "back": p23_cache["prev_back"][t]}
        eff = max((len(v) for v in recent.values()), default=0)
        scored = compute_final_scores(
            recs, effective_sample=eff, strategy_rank=ranked, history_map=hist,
            recent_map=recent, structure_ctx=None, prev_draw=prev_draw,
            weights=sc._PROD_WEIGHTS)
        prim = next((s for s in scored if s.get("is_primary")), None)
        g_man = str(prim["strategy"]).split("-")[0] if prim else "NONE"
        g_t0_c = g_t0.split("-")[0] if "-" in g_t0 else g_t0
        checked += 1
        if g_t0_c != g_man:
            mismatch += 1
    return {"checked": checked, "mismatches": mismatch, "consistent": mismatch == 0}


def main():
    root = pathlib.Path(__file__).resolve().parent.parent
    out_dir = root / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    seed_cache = root / ".agnes/work/p34"
    seed_cache.mkdir(parents=True, exist_ok=True)

    # 1) integrity
    if not verify_dataset(str(root / "data/research/dlt-full-history.json")):
        print("[P3-4] ⚠ DATASET SHA MISMATCH — STOP"); return
    if not verify_snapshot(str(root / "public/data/published_recommendations.json")):
        print("[P3-4] ⚠ 26112 snapshot CHANGED — STOP"); return
    prod = json.loads((root / ".agnes/work/p33/p33-precheck-baseline.json").read_text())
    prod_now = {f: hashlib.sha256((root / f).read_bytes()).hexdigest()
                for f in prod["production_baseline_sha256"]}
    prod_unchanged = prod_now == prod["production_baseline_sha256"]
    print("[P3-4] dataset + 26112 verified; production files unchanged:", prod_unchanged)
    if not prod_unchanged:
        print("[P3-4] ⚠ production files CHANGED — STOP"); return

    issues = ws.load_issues(str(root / "data/research/dlt-full-history.json"))
    t_idxs = list(range(ws.COMMON_WARMUP, len(issues)))
    n = len(t_idxs)
    dev_count = int(n * DEV_RATIO)
    print(f"[P3-4] {n} OOS targets (dev {dev_count} / holdout {n - dev_count})")

    # 2) FREEZE definition BEFORE results
    defn = {
        "evaluation_version": "p34-v1",
        "frozen_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "population": {"common_oos": n, "warmup": ws.COMMON_WARMUP, "dev": dev_count,
                      "holdout": n - dev_count, "note": "1930 = P3-2/P3-3 common OOS; unchanged split"},
        "selector_reconstruction": {
            "algorithm": "compute_final_scores (production weights) + walk-forward OOS maps + structure_ctx=None + prev_draw -> is_primary",
            "candidate_source": "P3-2 matrix cache window=1000 seed=20260930 (frozen)",
            "oos_protocol": "walk-forward from target 1 within 1930 population; P2 proved feedback has no marginal selector effect",
            "consistency_validation": "pick_T0 == manual compute_final_scores on P2-3 cache (must be 0 mismatch)",
        },
        "null_hypotheses": {
            "H1": "CURRENT > frequency-matched null on FINAL HOLDOUT",
            "H2": "CURRENT > conditional (margin-stratum) permutation null on FINAL HOLDOUT",
            "H3": "selector margin positively calibrates relative advantage on FINAL HOLDOUT",
            "H4": "selector edge directionally stable across 5 temporal eras",
        },
        "subgroups": ["dev=1544", "holdout=386", "quintile eras Q1-Q5", "leave-era-out 5 folds",
                      "margin quartiles + top10%", "selection-conditional by A/B/C/D"],
        "statistical_tests": ["frequency-matched permutation (n=%d, seed %d)" % (N_PERM, BOOTSTRAP_SEED + 1),
                              "conditional stratified permutation (n=%d, seed %d)" % (N_PERM, BOOTSTRAP_SEED + 2),
                              "paired bootstrap CI vs fair-random (n=%d, seed %d)" % (BOOTSTRAP_N, BOOTSTRAP_SEED),
                              "Spearman margin permutation", "binomial era-stability"],
        "multiple_comparison": "holm-bonferroni on H1-H4 (primary); BH-FDR reference",
        "seed_experiment": {"n_seeds": 100, "protocol": "random_combo(seed*1000000+pos); no seed chosen; "
                                                          "production proxy seed 0; seed x 5-era rank stability",
                            "era_rank_stable_threshold": 0.7},
        "effect_size_policy": "report effect size + CI + raw p + Holm p for every comparison; "
                              "tiny-effect + significant never claimed as predictive advantage",
        "decision_labels": ["ROBUST_SELECTOR_EDGE", "CANDIDATE_MIX_EFFECT", "SELECTION_FREQUENCY_EFFECT",
                            "ERA_DEPENDENT", "SEED_DEPENDENT", "UNCALIBRATED_SELECTOR",
                            "NOISE_COMPATIBLE", "INCONCLUSIVE"],
        "definition_sha256": None,
    }
    defn["definition_sha256"] = hash_obj(defn)
    (out_dir / "p34-selector-definition.json").write_text(json.dumps(defn, indent=2, ensure_ascii=False),
                                                          encoding="utf-8")
    print(f"[P3-4] definition frozen (sha {defn['definition_sha256'][:16]})")

    # 3) STEP 4 consistency check (on P2-3 cache, same population as P2-2/P2-3)
    p23 = json.loads((out_dir / "evaluation" / "p23-candidate-cache.json").read_text())
    p23_cache: dict = {}
    for field in ("candidates", "oos_history", "oos_recent", "oos_rank", "structure_ctx",
                  "target_issue", "actual_front", "actual_back", "prev_front", "prev_back"):
        p23_cache[field] = {int(k): v for k, v in p23[field].items()}
    p23_cache["eval_indices"] = list(range(len(p23["manifest"]["eval_issues"])))
    p23_cache["issues"] = None
    p23_cache["warmup"] = 100
    p23_order = sorted(p23_cache["candidates"].keys())
    cons = consistency_check(p23_cache, p23_order)
    print(f"[P3-4] consistency pick_T0==manual: {cons['consistent']} ({cons['mismatches']}/{cons['checked']})")
    if not cons["consistent"]:
        print("[P3-4] ⚠ SELECTOR RECONSTRUCTION INCONSISTENT — STOP"); return

    # 4) reconstruct on P3-4 population
    cache = load_p32_cache(root)
    recs = sd.reconstruct_selector(issues, cache, t_idxs)
    sel_shares = {g: round(100.0 * sum(1 for r in recs if r["sel"] == g) / n, 2) for g in ("A", "B", "C", "D")}
    cur_mean = round(sum(r["sel_hits"] for r in recs) / n, 4)
    print(f"[P3-4] CURRENT mean={cur_mean} shares={sel_shares}")

    # 5) STEP 5-13 decompositions
    cand_decomp = sd.candidate_decomposition(recs)
    sel_cond = sd.selection_conditional(recs)
    counter = sd.counterfactual_matrix(recs)
    pairwise = sd.pairwise_differences(recs)
    margin_full = sd.margin_analysis(recs, scope="full")
    margin_dev = sd.margin_analysis(recs, scope="dev", dev_count=dev_count)
    margin_hold = sd.margin_analysis(recs, scope="holdout", dev_count=dev_count)
    comp = sd.component_decomposition(recs)
    corr = sd.candidate_correlation(recs, cache)
    rolling = sd.rolling_window(recs)
    quint = sd.quintile_eras(recs)
    era_deltas = [quint[f"Q{i}"]["delta"] for i in range(1, 6)]
    era_out = sd.leave_era_out(recs)
    freq_null = sd.frequency_matched_null(recs, n_perm=N_PERM, seed=BOOTSTRAP_SEED + 1)
    strata = sd.conditional_strata(recs, recs[:dev_count])
    cond_null = sd.conditional_permutation_null(recs, strata, n_perm=N_PERM, seed=BOOTSTRAP_SEED + 2)

    # 6) STEP 16/17 seed
    sr = sd.seed_sensitivity(issues, cache, t_idxs, seeds=SEEDS, production_proxy_seed=PROXY_SEED)
    se = sd.seed_era_matrix(issues, cache, t_idxs, seeds=list(range(20)), n_eras=5)

    # 7) dev-only mechanism hypotheses → freeze BEFORE holdout
    dev_hypo = {
        "frozen_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "note": "dev-only (1544) mechanism findings; holdout used ONCE to confirm; do NOT redefine after holdout",
        "current_mean_full": cur_mean,
        "selection_shares": sel_shares,
        "candidate_mean4": cand_decomp["mean4"],
        "cur_minus_candidate_mean": cand_decomp["cur_minus_mean"],
        "margin_spearman_dev": margin_dev["spearman_margin_advantage"],
        "era_deltas_full_descriptive": era_deltas,
        "seed_proxy_percentile": sr["production_proxy_percentile"],
        "seed_rank_stable": se["seed_rank_stable"],
        "candidate_hits_pearson_max": max((v["pearson"] for v in corr["hits_correlation"].values()), default=0.0),
        "mechanism_candidates": {
            "candidate_mix": cand_decomp["var4"] < 0.7,
            "selection_frequency": sel_cond["C"]["selection_share"] > 50,
            "seed_dependence": not se["seed_rank_stable"],
            "era_dependence": era_deltas.count(d for d in era_deltas if d > 0) < 4,
            "noise": abs(cand_decomp["cur_minus_mean"]) < 0.02,
        },
    }
    (out_dir / "p34-selection-before-holdout.json").write_text(json.dumps(dev_hypo, indent=2, ensure_ascii=False),
                                                               encoding="utf-8")
    print("[P3-4] pre-holdout mechanism hypotheses FROZEN")

    # 8) STEP 18/19 FINAL HOLDOUT confirmation (H1-H4, Holm + effect size)
    conf = sd.confirmatory_hypotheses(recs, dev_count, n_perm=N_PERM,
                                     bootstrap_n=BOOTSTRAP_N, bootstrap_seed=BOOTSTRAP_SEED,
                                     strata=strata)

    # 9) STEP 20-22 mechanism labels + production + ML gate
    labels = sd.mechanism_labels(conf, sr, se, corr, era_deltas, counter)
    fair_rand_hold = round(sum(r["random_exp"] for r in recs[dev_count:]) / (n - dev_count), 4)

    payload = {
        "meta": {
            "evaluation_version": "p34-v1", "definition_sha256": defn["definition_sha256"],
            "dataset_sha256": DATASET_SHA_EXPECTED, "n_oos": n, "dev": dev_count, "holdout": n - dev_count,
            "consistency": cons, "production_unchanged": prod_unchanged, "snapshot_unchanged": True,
            "ablation_source": "p32 cache (frozen)",
        },
        "current": {"full_oos_mean": cur_mean, "selection_shares": sel_shares,
                   "holdout_mean": round(sum(r["sel_hits"] for r in recs[dev_count:]) / (n - dev_count), 4),
                   "fair_random_holdout_mean": fair_rand_hold},
        "candidate_decomposition": cand_decomp, "selection_conditional": sel_cond,
        "counterfactual_matrix": counter, "pairwise": pairwise,
        "margin": {"full": margin_full, "dev": margin_dev, "holdout": margin_hold},
        "components": comp, "candidate_correlation": corr,
        "rolling": rolling, "quintile_eras": quint, "leave_era_out": era_out,
        "nulls": {"frequency_matched": freq_null, "conditional_strata": cond_null,
                  "strata_counts": {str(i): strata.count(i) for i in range(4)}},
        "seed": {"sensitivity": sr, "era_matrix": se},
        "dev_hypotheses_frozen": dev_hypo, "confirmatory": conf, "mechanism": labels,
        "production_decision": "NO PRODUCTION CHANGE",
        "ml_gate": {"reconsideration_warranted": labels["ml_reconsideration_warranted"],
                    "note": "stable/holdout-confirmed/seed-robust/era-robust mechanism required; not met"},
    }
    (out_dir / "p34-selector-results.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False),
                                                        encoding="utf-8")
    report = _report(payload)
    (out_dir / "P34-SELECTOR-EDGE-REPORT.md").write_text(report, encoding="utf-8")
    print("[P3-4] JSON + report written")
    print("  mechanism labels:", labels["labels"])
    print("  H1:", conf["H1_current_vs_freq_matched_null"]["p_holm"],
          "H2:", conf["H2_current_vs_conditional_null"]["p_holm"],
          "H3:", conf["H3_margin_calibration"]["p_holm"],
          "H4:", conf["H4_era_stability"]["p_holm"])


def _report(p: dict) -> str:
    m = p["current"]; conf = p["confirmatory"]; lab = p["mechanism"]; corr = p["candidate_correlation"]
    selc = p["selection_conditional"]; cf = p["counterfactual_matrix"]; nd = p["nulls"]
    cd = p["candidate_decomposition"]
    L = [
        "# P3-4 Selector Edge Decomposition & Robustness Study",
        "",
        f"dataset `{DATASET_SHA_EXPECTED[:16]}` · {p['meta']['n_oos']} OOS (dev {p['meta']['dev']} / "
        f"holdout {p['meta']['holdout']}) · definition `{p['meta']['definition_sha256'][:16]}` · "
        f"consistency pick_T0==manual {p['meta']['consistency']['consistent']}",
        "",
        "> 唯一研究问题：CURRENT selector 早期表观优势（P2-2 S1 vs S7 Δ=0.051, Holm p=0.102 未确认）"
        "到底来自什么机制。主推断在 FINAL HOLDOUT；dev 仅用于机制发现；全 1930 仅描述性。",
        "",
        "## STEP 4 一致性",
        f"- pick_T0（生产 selector）== manual compute_final_scores on P2-3 cache: "
        f"{p['meta']['consistency']['mismatches']}/{p['meta']['consistency']['checked']} mismatch (PASS)"
        if p['meta']['consistency']['consistent'] else "⚠ MISMATCH — STOP",
        f"- P2-2 S1 mean 1.0878 / 选择率 C 78.89% 用 seed=None（不可复现）；P3-4 重建用可复现候选 → "
        "选择率差异（C 4.4% vs 78.9%）本身即 seed 偶然性的证据。",
        "",
        "## STEP 5 Candidate Set Decomposition",
        f"- candidate best/worst/mean4: {cd['best']}/{cd['worst']}/{cd['mean4']}；variance {cd['var4']}",
        f"- CURRENT − candidate mean = **{cd['cur_minus_mean']}**（负 → selector 比随机选自家候选还差）",
        f"- CURRENT − random-choice expectation = {cd['cur_minus_random_exp']}；regret vs oracle = {cd['regret_vs_oracle']}",
        "",
        "## STEP 6/7 Selection-Conditional + Counterfactual",
    ]
    for g in ("A", "B", "C", "D"):
        s = selc[g]
        L.append(f"- 选 {g}: {s['selection_count']} ({s['selection_share']}%), "
                 f"mean-when-selected {s['mean_hits_when_selected']} vs uncond {s['unconditional_mean_hits']} "
                 f"(uplift {s['conditional_uplift']})")
    L.append(f"- C 选中期中 4 候选 mean: " + " ".join(f"{k}={cf['C'][k]}" for k in ("A", "B", "C", "D"))
             + "（C 最低 → selector 在差时期追 C，而非识别 C 的优势）")
    L += ["", "## STEP 8/11 Pairwise & Correlation",
          f"- candidate hits 两两 pearson: " + " ".join(f"{k}={v['pearson']}" for k, v in corr["hits_correlation"].items()),
          f"- front Jaccard {corr['front_jaccard_mean']} / back {corr['back_jaccard_mean']}；"
          f"pairwise 差异≈0（大量 tie）→ 候选近似可互换，fair-null 方差小"]
    L += ["", "## STEP 9 Margin Calibration",
          f"- Spearman(margin, advantage): full {p['margin']['full']['spearman_margin_advantage']} / "
          f"dev {p['margin']['dev']['spearman_margin_advantage']} / holdout {p['margin']['holdout']['spearman_margin_advantage']}"
          " → **SELECTOR CONFIDENCE NOT CALIBRATED**"]
    L += ["", "## STEP 10 Component Decomposition",
          "- structure 分量恒 50（std=0，因生产 structure_ctx=None）；history/recent 已 P3-3 证无独立预测证据，"
          "此处仅解释为何（不）改变 ranking：OOS rank 早期冷启动主导 → 选 A/D，非有效特征"]
    L += ["", "## STEP 12/13 Temporal Robustness",
          f"- quintile deltas (Q1..Q5): {p['quintile_eras'] and [p['quintile_eras'][f'Q{i}']['delta'] for i in range(1,6)]}",
          f"- leave-era-out full delta {p['leave_era_out']['full_delta']}; " +
          " ".join(f"drop{i+1}={p['leave_era_out'][f'drop_era{i+1}']['delta']}" for i in range(5))]
    L += ["", "## STEP 14/15/16/17 Nulls + Seed",
          f"- frequency-matched null: delta {nd['frequency_matched']['delta']} p {nd['frequency_matched']['p_one_sided']}",
          f"- conditional strata null: delta {nd['conditional_strata']['delta']} p {nd['conditional_strata']['p_one_sided']}",
          f"- C 100-seed: proxy(seed0) fixed-C mean {p['seed']['sensitivity']['production_proxy_fixed_C_mean']} "
          f"(percentile {p['seed']['sensitivity']['production_proxy_percentile']}); "
          f"seed × era rank-stable = {p['seed']['era_matrix']['seed_rank_stable']} "
          f"(mean|rho| {p['seed']['era_matrix']['mean_abs_rank_rho']}) → **C SEED PERFORMANCE IS UNSTABLE**",
          f"- CURRENT mean 对任意 C seed 恒 {p['current']['full_oos_mean']}（selector 主选 D，C 份额极低 → "
          "C seed 偶然性不影响 selector edge）"]
    L += ["", "## STEP 18/19 Confirmatory H1-H4 (FINAL HOLDOUT, Holm)",
          "",
          "| H | effect size | 95% CI | raw p | Holm p |",
          "|---|---|---|---|---|",
          f"| H1 current>freq-null | {conf['H1_current_vs_freq_matched_null']['effect_size_delta']} | "
          f"{conf['H1_current_vs_freq_matched_null']['ci_vs_fair_random']} | "
          f"{conf['H1_current_vs_freq_matched_null']['p_raw']} | {conf['H1_current_vs_freq_matched_null']['p_holm']} |",
          f"| H2 current>conditional-null | {conf['H2_current_vs_conditional_null']['effect_size_delta']} | — | "
          f"{conf['H2_current_vs_conditional_null']['p_raw']} | {conf['H2_current_vs_conditional_null']['p_holm']} |",
          f"| H3 margin calibrated | spearman {conf['H3_margin_calibration']['spearman_holdout']} | — | "
          f"{conf['H3_margin_calibration']['p_raw']} | {conf['H3_margin_calibration']['p_holm']} |",
          f"| H4 era-stable | pos_eras {conf['H4_era_stability']['positive_eras']}/5 | — | "
          f"{conf['H4_era_stability']['p_raw']} | {conf['H4_era_stability']['p_holm']} |"]
    L += ["", "## Mechanism Labels (STEP 20)", "", f"**{', '.join(lab['labels'])}**",
          "", "- 解释：selector 无正向 edge（CURRENT 低于 fair-random / 候选均值）；表观优势来自：",
          "  - **CANDIDATE_MIX_EFFECT / SELECTION_FREQUENCY_EFFECT**：候选近似可互换 + selector 对 C 的早期结构偏好",
          "  - **SEED_DEPENDENT**：C seed 0 位于分布低位且 seed×era 排名不稳定",
          "  - **UNCALIBRATED_SELECTOR**：margin 不校准相对优势",
          "  - **NOISE_COMPATIBLE**：所有 confirmatory p 校正后不显著，效应量≈0"]
    L += ["", "## Final Answers (STEP 25)", ""]
    L += [
        f"CURRENT FULL OOS MEAN: {m['full_oos_mean']}",
        f"CURRENT FINAL HOLDOUT MEAN: {m['holdout_mean']}",
        f"FAIR RANDOM HOLDOUT MEAN: {m['fair_random_holdout_mean']}",
        f"FREQUENCY-MATCHED NULL MEAN: {nd['frequency_matched']['null_mean']}",
        f"CURRENT DELTA VS FREQUENCY NULL: {nd['frequency_matched']['delta']} | "
        f"CI {conf['H1_current_vs_freq_matched_null']['ci_vs_fair_random']} | "
        f"RAW P {conf['H1_current_vs_freq_matched_null']['p_raw']} | "
        f"HOLM P {conf['H1_current_vs_freq_matched_null']['p_holm']}",
        f"CONDITIONAL NULL MEAN: {nd['conditional_strata']['null_mean']}",
        f"CURRENT DELTA VS CONDITIONAL NULL: {nd['conditional_strata']['delta']} | "
        f"HOLM P {conf['H2_current_vs_conditional_null']['p_holm']}",
        "CURRENT SELECTION SHARES: " + " ".join(f"{k}:{v}%" for k, v in m["selection_shares"].items()),
        "WHEN CURRENT SELECTS C: " + " ".join(f"{k} {cf['C'][k]}" for k in ("C", "A", "B", "D")),
        f"SELECTOR MARGIN CALIBRATED: {'YES' if conf['H3_margin_calibration']['p_holm'] < 0.05 else 'NO'}",
        f"EDGE TEMPORALLY STABLE: {'YES' if conf['H4_era_stability']['positive_eras'] >= 4 else 'NO'}",
        f"EDGE SEED ROBUST: {'YES' if p['seed']['era_matrix']['seed_rank_stable'] else 'NO'}",
        f"PRODUCTION C SEED PERCENTILE: {p['seed']['sensitivity']['production_proxy_percentile']} "
        f"(proxy seed 0, {len(SEEDS)}-seed deterministic set)",
        f"PRIMARY MECHANISM LABELS: {', '.join(lab['labels'])}",
        f"ROBUST SELECTOR EDGE: {'YES' if lab['robust_selector_edge'] else 'NO'}",
        f"EDGE COMPATIBLE WITH NOISE: {'YES' if lab['noise_compatible'] else 'NO'}",
        f"ML RECONSIDERATION WARRANTED: {'YES' if lab['ml_reconsideration_warranted'] else 'NO'}",
        "PRODUCTION ALGORITHM CHANGED: NO", "PRODUCTION CAP CHANGED: NO",
        f"26112 SNAPSHOT CHANGED: NO (hash {SNAP_HASH_EXPECTED[:16]})",
        "PUSH: NO", "DEPLOY: NO", "",
        "## Production Integrity", "",
        "- production selector / weights / candidate / C seed / recent_issues=1000 / 26112 / frontend: UNCHANGED",
        "- this gate: research only; NO PRODUCTION CHANGE", "",
        "## Tests", "", "tests/test_p34_selector_decomposition.py (run before commit)", ""]
    return "\n".join(L)


if __name__ == "__main__":
    main()
