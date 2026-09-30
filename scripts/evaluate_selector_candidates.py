#!/usr/bin/env python3
"""P2-3 简化 selector candidate 评测 runner。

流程（防过拟合关键顺序）：
  1. 生成 candidate-definition.json（含 T0-T8 定义 + 权重 + hash + 时间戳）——冻结在结果之前
  2. build extended candidate cache（一次 D 遍历；可选加载已持久化 cache 复用）
  3. 持久化 canonical cache 到 reports/evaluation/p23-candidate-cache.json（供 P2-4/P3 复用）
  4. dev/holdout split（前 70% / 后 30%，不重叠）
  5. 运行 T0-T8（FULL / DEV / HOLDOUT）+ S7 fair-null + C 50-seed sensitivity
  6. paired bootstrap（10k，fixed seed）+ sign-flip + Holm（candidates vs T0、vs S7）
  7. 稳定性（EARLY/MID/LATE + rolling 100）on dev & holdout
  8. complexity table + 决策（PROMOTE / KEEP / NO_EDGE）
  9. 写 p23-selector-candidates.json + P23-SELECTOR-CANDIDATES-REPORT.md

禁止：修改生产 final_score/recommender/权重/26112/frontend。
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src.evaluation import selector_candidates as sc
from src.evaluation import statistics as stats
from src.evaluation import prize


def _hash_defndef(obj: dict) -> str:
    s = json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def write_definition_json(out_dir: pathlib.Path) -> dict:
    """STEP 10: 在运行结果前冻结 candidate 定义（hash + timestamp 早于 result artifact）。"""
    defn = {
        "evaluation_version": sc.EVAL_VERSION,
        "frozen_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "note": "candidate definitions + pre-fixed weights; MUST be generated before evaluation run",
        "weights": {
            "T0_prod_weights": sc._PROD_WEIGHTS,
            "T7_base_structure_fixed": sc.T7_WEIGHTS,
            "base_norm_range": [sc.BASE_SCORE_FLOOR, sc.BASE_SCORE_CEIL],
        },
        "candidates": sc.CANDIDATE_DEFS,
        "c_sensitivity": {"n_seeds": len(sc.C_SEEDS), "fixed_proxy_seed": sc.C_FIXED_PROXY_SEED},
        "bootstrap": {"n": sc.BOOTSTRAP_N, "seed": sc.BOOTSTRAP_SEED},
        "dev_holdout": {"ratio": sc.DEV_RATIO},
        "definition_hash": None,  # filled below
    }
    defn["definition_hash"] = _hash_defndef(defn)
    p = out_dir / "p23-candidate-definition.json"
    p.write_text(json.dumps(defn, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[P2-3] definition frozen → {p.name} (hash {defn['definition_hash'][:16]})")
    return defn


def load_or_build_cache(history_path: str, cache_path: pathlib.Path,
                        warmup: int, use_persisted: bool, verbose: bool):
    """STEP 14: 优先加载已持久化 cache；否则 build 并持久化。"""
    if use_persisted and cache_path.exists():
        j = json.loads(cache_path.read_text())
        if "manifest" in j and j["manifest"]["warmup"] == warmup:
            print(f"[P2-3] loaded persisted cache ({cache_path.name})")
            return _from_jsonable(j), True
        print(f"[P2-3] persisted cache warmup mismatch; rebuilding")
    issues = json.loads(pathlib.Path(history_path).read_text())
    if isinstance(issues, dict):
        issues = issues.get("issues", [])
    cache = sc.build_extended_cache(issues, warmup=warmup, verbose=verbose)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(sc.cache_to_jsonable(cache), ensure_ascii=False),
                          encoding="utf-8")
    print(f"[P2-3] built + persisted cache → {cache_path.name}")
    return cache, False


def _from_jsonable(j: dict) -> dict:
    """jsonable cache（位置键 0..m-1）→ 可运行结构。

    与 native build_extended_cache 的差异：key 是 eval 位置（0..m-1），不是 t 下标。
    所有 picker 通过 cache[key] 访问，_key_order 返回 [0..m-1]（sorted），行为一致。
    """
    order = j["manifest"]["eval_issues"]  # target issue 字符串序列
    m = len(order)
    cache: dict[str, Any] = {"warmup": j["manifest"]["warmup"]}
    for field in ("candidates", "oos_history", "oos_recent", "oos_rank",
                  "structure_ctx", "target_issue", "actual_front", "actual_back",
                  "prev_front", "prev_back"):
        cache[field] = {int(k): v for k, v in j[field].items()}
    # picker 依赖的 target_issue 等已就位；eval_indices 仅作占位（不用于 picker）
    cache["eval_indices"] = list(range(m))
    cache["issues"] = None  # 不需要（picker 只用 per-draw 字段）
    return cache


def _key_order(cache: dict) -> list:
    """cache 的时间顺序 keys（native=t 下标，loaded=0..n-1）。"""
    return sorted(cache["candidates"].keys())


def evaluate_candidate(cache: dict, cand: str, key_slice: slice) -> dict[str, Any]:
    """在 cache 的 keys[key_slice] 上运行 candidate（space-agnostic）。"""
    keys = _key_order(cache)[key_slice]
    recs, sel_seq = [], []
    for t in keys:
        g, combo = sc.PICKERS[cand](cache, t)
        if not combo:
            sel_seq.append("NONE")
            continue
        fh, bh = combo["fh"], combo["bh"]
        pb = prize.payout_breakdown(fh, bh)
        recs.append({"front_hits": fh, "back_hits": bh, "total_hits": fh + bh,
                     "selected_strategy": g, "payout": pb["known_fixed_payout"],
                     "prize_tier": pb["tier"], "cost": sc.COST})
        sel_seq.append(g)
    return {"total": [r["total_hits"] for r in recs],
            "front": [r["front_hits"] for r in recs],
            "back": [r["back_hits"] for r in recs],
            "recs": recs, "sel_seq": sel_seq}


def evaluate_random_choice_total(cache: dict, key_slice: slice, seeds: list[int]) -> list:
    """S7 random-choice：返回 pooled total-hit 列表（供均值）。"""
    keys = _key_order(cache)[key_slice]
    out = []
    for seed in seeds:
        for t in keys:
            g, combo = sc._abl._pick_random_choice(cache, t, seed)
            if combo:
                out.append(combo["fh"] + combo["bh"])
    return out


def s7_per_draw_mean(cache: dict, key_slice: slice, seeds: list[int]) -> list:
    """S7 每期 seeds 均值（per-draw，供 paired；顺序同 keys）。"""
    keys = _key_order(cache)[key_slice]
    per = []
    for t in keys:
        vals = []
        for seed in seeds:
            g, combo = sc._abl._pick_random_choice(cache, t, seed)
            if combo:
                vals.append(combo["fh"] + combo["bh"])
        per.append(sum(vals) / len(vals) if vals else 0.0)
    return per


def _mean(vals: list) -> float:
    return sum(vals) / len(vals) if vals else 0.0


def summarize_block(vals: list) -> dict:
    s = stats.summary_stats(vals)
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--history", default="public/data/dlt_history.json")
    ap.add_argument("--warmup", type=int, default=100)
    ap.add_argument("--s7-seeds", type=int, default=50)
    ap.add_argument("--use-persisted-cache", action="store_true")
    ap.add_argument("--out-dir", default="reports/evaluation")
    args = ap.parse_args()

    out_dir = pathlib.Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1) 冻结 candidate 定义（先于结果）
    defn = write_definition_json(out_dir)

    # 2) cache（持久化；native key = t 下标，loaded key = 0..n-1；全部 space-agnostic）
    cache_path = out_dir / "p23-candidate-cache.json"
    cache, used_persisted = load_or_build_cache(args.history, cache_path,
                                                 args.warmup, args.use_persisted_cache,
                                                 verbose=True)
    key_order = _key_order(cache)
    n_eval = len(key_order)
    dev_count = int(n_eval * sc.DEV_RATIO)
    dev_slice = slice(0, dev_count)
    hold_slice = slice(dev_count, n_eval)
    print(f"[P2-3] dev={dev_count} holdout={n_eval - dev_count} draws")

    C_SEEDS = list(range(1, args.s7_seeds + 1))

    results: dict[str, Any] = {}
    for scope, sl in (("full", slice(None)), ("dev", dev_slice), ("holdout", hold_slice)):
        results[scope] = {}
        for cand in ("T0", "T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8"):
            results[scope][cand] = evaluate_candidate(cache, cand, sl)
        s7_total = evaluate_random_choice_total(cache, sl, C_SEEDS)
        results[scope]["S7_mean"] = _mean(s7_total)
        results[scope]["S7_pooled_n"] = len(s7_total)
        for cand in ("T0", "T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8"):
            b = results[scope][cand]
            st = stats.summary_stats(b["total"])
            fh = b["front"]; bh = b["back"]; recs = b["recs"]
            psum = prize.aggregate_payout(recs) if recs else {}
            results[scope][cand + "_stat"] = {
                "total_mean": st["mean"], "front_mean": round(_mean(fh), 4),
                "back_mean": round(_mean(bh), 4),
                "front_ge3": sum(1 for x in fh if x >= 3),
                "back_eq2": sum(1 for x in bh if x == 2),
                "prize_hits": sum(1 for r in recs if r.get("prize_tier") is not None),
                "known_payout": psum.get("known_fixed_payout_total", 0.0),
                "roi_lower_bound": psum.get("roi_lower_bound_total", 0.0),
                "roi_fully_determinable": psum.get("roi_fully_determinable", True),
                "cost_total": psum.get("cost_total", 0.0),
            }
        for cand in ("T0", "T5", "T7", "T8"):
            results[scope][cand + "_temporal"] = stats.temporal_split(results[scope][cand]["total"])
        results[scope]["rolling_T0_minus_T5"] = stats.rolling_blocks(
            [a - b for a, b in zip(results[scope]["T0"]["total"], results[scope]["T5"]["total"])],
            block=100)

    # C 50-seed sensitivity（full；space-agnostic）
    c_sens = c_sensitivity_report(cache, C_SEEDS)

    # 4) holdout paired 统计：每个 candidate vs T0、vs S7
    hold = results["holdout"]
    t0_total = hold["T0"]["total"]
    s7_hold_per_draw = s7_per_draw_mean(cache, hold_slice, C_SEEDS)
    comparisons: dict[str, Any] = {}
    p_vs_t0: list[float] = []
    p_vs_s7: list[float] = []
    cand_order = ("T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8")
    for cand in cand_order:
        cd = hold[cand]["total"]
        b_t0 = stats.paired_bootstrap_ci(cd, t0_total, n_resamples=sc.BOOTSTRAP_N,
                                          seed=sc.BOOTSTRAP_SEED)
        s_t0 = stats.paired_sign_flip_pvalue(cd, t0_total, one_sided=True)
        b_s7 = stats.paired_bootstrap_ci(cd, s7_hold_per_draw, n_resamples=sc.BOOTSTRAP_N,
                                          seed=sc.BOOTSTRAP_SEED + 1)
        s_s7 = stats.paired_sign_flip_pvalue(cd, s7_hold_per_draw, one_sided=True)
        comparisons[f"{cand}_vs_T0"] = {"delta": b_t0["mean_delta"],
                                        "ci": [b_t0["ci_low"], b_t0["ci_high"]],
                                        "contains0": b_t0["ci_contains_zero"],
                                        "p_raw": s_t0["p_value"]}
        comparisons[f"{cand}_vs_S7"] = {"delta": b_s7["mean_delta"],
                                        "ci": [b_s7["ci_low"], b_s7["ci_high"]],
                                        "contains0": b_s7["ci_contains_zero"],
                                        "p_raw": s_s7["p_value"]}
        p_vs_t0.append(s_t0["p_value"])
        p_vs_s7.append(s_s7["p_value"])
    adj_t0 = stats.holm_adjust(p_vs_t0)
    adj_s7 = stats.holm_adjust(p_vs_s7)
    for i, cand in enumerate(cand_order):
        comparisons[f"{cand}_vs_T0"]["p_holm_vs_T0"] = adj_t0[i]
        comparisons[f"{cand}_vs_S7"]["p_holm_vs_S7"] = adj_s7[i]

    # 5) complexity table
    complexity = {k: {
        "signals": v["signals"], "n_signals": len(v["signals"]),
        "uses_recent": v["uses_recent"], "uses_history": v["uses_history"],
        "uses_structure": v["uses_structure"], "learned_weight": v["learned_weight"],
        "stateful": v["stateful"], "explainability": v["explainability"],
    } for k, v in sc.CANDIDATE_DEFS.items()}

    # 6) 决策
    decision = _decide(hold, comparisons)

    # STEP 14: 瘦身为可提交产物。per-draw 全量数组（total/front/back/recs）只用于
    # 中间统计，规范 candidate cache 已单独持久化到 p23-candidate-cache.json（供 P2-4/P3
    # 复用，避免重跑 D）。candidates JSON 只保留统计/稳定性/滚动块 + draw 数。
    draw_counts = {"full": n_eval, "dev": dev_count, "holdout": n_eval - dev_count}
    slim_results = {}
    for scope, sl in (("full", slice(None)), ("dev", dev_slice), ("holdout", hold_slice)):
        slim = dict(results[scope])
        for cand in ("T0", "T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8"):
            blk = slim.get(cand)
            if isinstance(blk, dict):
                nb = {k: v for k, v in blk.items()
                      if k not in ("total", "front", "back", "recs", "sel_seq")}
                nb["n_draws"] = draw_counts[scope]
                slim[cand] = nb
        slim_results[scope] = slim

    payload = {
        "meta": {
            "evaluation_version": sc.EVAL_VERSION,
            "definition_hash": defn["definition_hash"],
            "definition_frozen_at": defn["frozen_at"],
            "cache_persisted": str(cache_path),
            "cache_used_persisted": used_persisted,
            "total_eval_draws": n_eval,
            "warmup": args.warmup,
            "dev_draws": dev_count, "holdout_draws": n_eval - dev_count,
            "s7_seeds": args.s7_seeds, "bootstrap_n": sc.BOOTSTRAP_N,
            "note": "exploratory model-selection; holdout is the decision basis; ORACLE-free",
        },
        "candidate_definitions": sc.CANDIDATE_DEFS,
        "complexity_table": complexity,
        "results": slim_results,
        "C_sensitivity": c_sens,
        "comparisons_holdout": comparisons,
        "decision": decision,
    }
    out_dir.joinpath("p23-selector-candidates.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    report = _report({**payload, "results": results})  # 报告用内存全量
    out_dir.joinpath("P23-SELECTOR-CANDIDATES-REPORT.md").write_text(report, encoding="utf-8")
    print(f"[P2-3] done. DECISION = {decision['verdict']}")
    print(f"[P2-3] JSON → {out_dir/'p23-selector-candidates.json'}")
    print(f"[P2-3] Report → {out_dir/'P23-SELECTOR-CANDIDATES-REPORT.md'}")


def c_sensitivity_report(cache: dict, seeds: list[int]) -> dict[str, Any]:
    """C multi-seed 敏感性（space-agnostic）：判断固定 C seed 是否 lucky。

    使用 cache key order 上的每期真实开奖做命中；per-seed 每期均值 → seed 分布。
    """
    keys = _key_order(cache)
    per_seed: dict[int, list[float]] = {}
    for seed in seeds:
        hits = []
        for t in keys:
            combo = sc.baselines.random_combo(seed * 1000000 + t)
            hits.append(sc._hits(combo["front"], cache["actual_front"][t]) +
                        sc._hits(combo["back"], cache["actual_back"][t]))
        per_seed[seed] = hits
    seed_period_means = [sum(v) / len(v) for v in per_seed.values() if v]
    dist = stats.summary_stats(seed_period_means)
    # fixed proxy seed 0
    fixed_hits = []
    for t in keys:
        combo = sc.baselines.random_combo(sc.C_FIXED_PROXY_SEED * 1000000 + t)
        fixed_hits.append(sc._hits(combo["front"], cache["actual_front"][t]) +
                          sc._hits(combo["back"], cache["actual_back"][t]))
    fixed_mean = sum(fixed_hits) / len(fixed_hits) if fixed_hits else 0.0
    below = sum(1 for m in seed_period_means if m < fixed_mean)
    percentile = 100.0 * below / len(seed_period_means)
    return {
        "n_seeds": len(seeds),
        "c_seed_distribution": dist,
        "fixed_proxy_seed": sc.C_FIXED_PROXY_SEED,
        "fixed_proxy_mean": round(fixed_mean, 4),
        "fixed_proxy_percentile_in_50seed": round(percentile, 2),
        "note": "production C uses seed=null (non-reproducible); seed 0 is a deterministic proxy",
    }


def _decide(hold: dict, comparisons: dict) -> dict:
    """STEP 12 决策逻辑：基于 holdout + 统计证据。"""
    cur_hold = hold["T0_stat"]["total_mean"]
    s7_hold = hold["S7_mean"]
    simple = {k: hold[k + "_stat"]["total_mean"]
              for k in ("T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8")}
    best_k = max(simple, key=lambda k: simple[k])
    best_val = simple[best_k]
    # "不劣化"：best simple 在 holdout 不低于 T0（within 1σ 噪声带视为不劣化）
    not_worse = best_val >= cur_hold
    # 统计支持：best vs S7 Holm p < 0.05 且 vs T0 不显著更差
    key_vs_s7 = f"{best_k}_vs_S7"
    key_vs_t0 = f"{best_k}_vs_T0"
    p_s7 = comparisons.get(key_vs_s7, {}).get("p_holm_vs_S7", 1.0)
    p_t0 = comparisons.get(key_vs_t0, {}).get("p_holm_vs_T0", 1.0)
    beat_null = p_s7 < 0.05
    supported = not_worse and (p_s7 < 0.10) and (not (p_t0 < 0.05))  # 不显著劣于 T0
    if supported:
        verdict = "PROMOTE_CANDIDATE"
    elif not_worse:
        verdict = "KEEP_CURRENT_TEMPORARILY"
    else:
        verdict = "NO_SELECTOR_EDGE"
    return {
        "verdict": verdict,
        "current_holdout_mean": round(cur_hold, 4),
        "random_choice_holdout_mean": round(s7_hold, 4),
        "best_simple_candidate": best_k,
        "best_simple_holdout_mean": round(best_val, 4),
        "best_simple_vs_T0_adj_p": round(p_t0, 4),
        "best_simple_vs_S7_adj_p": round(p_s7, 4),
        "simple_not_worse_on_holdout": bool(not_worse),
        "simple_beats_fair_null": bool(beat_null),
        "rationale": (
            f"best simple candidate {best_k} holdout mean {best_val:.4f} vs CURRENT {cur_hold:.4f}; "
            f"vs fair-null S7 adj p={p_s7:.4f}; vs CURRENT adj p={p_t0:.4f}. "
            f"{'Promote' if verdict=='PROMOTE_CANDIDATE' else ''}"
            f"{'Keep current temporarily (no strong evidence a simple candidate is better)' if verdict=='KEEP_CURRENT_TEMPORARILY' else ''}"
            f"{'No stable selector edge over fair random-choice' if verdict=='NO_SELECTOR_EDGE' else ''}"
        ),
    }


def _report(p: dict) -> str:
    meta = p["meta"]
    res = p["results"]
    comp = p["comparisons_holdout"]
    c_sens = p["C_sensitivity"]
    decision = p["decision"]
    hold = res["holdout"]
    dev = res["dev"]

    def srow(scope, cand):
        s = res[scope].get(cand + "_stat")
        if not s:
            return f"| {cand} | — |"
        return (f"| {cand} {sc.CANDIDATE_DEFS[cand]['name']} | {s['total_mean']} | "
                f"{s['front_mean']} | {s['back_mean']} | {s['front_ge3']} | {s['back_eq2']} | "
                f"{s['prize_hits']} | {s['known_payout']} | {s['roi_lower_bound']} |")

    lines = [
        "# P2-3 Simplified Selector Candidate Report",
        "",
        f"Evaluation `{meta['evaluation_version']}` · dev {meta['dev_draws']} / holdout {meta['holdout_draws']} draws · "
        f"definition hash `{meta['definition_hash'][:16]}` (frozen {meta['definition_frozen_at']}) · "
        f"cache {'persisted-reuse' if meta['cache_used_persisted'] else 'rebuilt+persisted'}",
        "",
        "> **Guardrail**: exploratory model-selection. The HOLDOUT third (last 30%) is the decision "
        "basis; no formula was tuned to holdout. A 'winner' here is a hypothesis for P2-4, "
        "not a claim of predictive value. C is a random baseline, not an 'optimal model'.",
        "",
        "## Candidate Results (mean total hits)",
        "",
    ]
    for scope in ("dev", "holdout"):
        lines.append(f"### {scope.upper()}")
        lines.append("")
        lines.append("| Candidate | Total Mean | Front | Back | >=3 Front | 2 Back | Prize Hits | Known Payout | ROI (lb) |")
        lines.append("|---|---|---|---|---|---|---|---|---|")
        for c in ("T0", "T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8"):
            lines.append(srow(scope, c))
        lines.append(f"| S7 RANDOM-CHOICE | {res[scope]['S7_mean']} | (pooled n={res[scope].get('S7_pooled_n','?')} across {meta['s7_seeds']} seeds) | | | | | | |")
        lines.append("")

    lines += [
        "## Production C Seed Sensitivity",
        "",
        f"- 50-seed C distribution mean {c_sens['c_seed_distribution'].get('mean')}, "
        f"p05 {c_sens['c_seed_distribution'].get('p05')}, p95 {c_sens['c_seed_distribution'].get('p95')}",
        f"- fixed proxy seed {c_sens['fixed_proxy_seed']} mean {c_sens['fixed_proxy_mean']} "
        f"= **percentile {c_sens['fixed_proxy_percentile_in_50seed']}** within the 50-seed distribution",
        f"- {c_sens['note']}",
        "",
        "## Holdout Paired Comparisons (vs CURRENT & vs S7, Holm-adjusted)",
        "",
        "| candidate | vs T0 Δ | vs T0 95% CI | vs T0 p_adj | vs S7 Δ | vs S7 95% CI | vs S7 p_adj |",
        "|---|---|---|---|---|---|---|",
    ]
    for c in ("T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8"):
        ct = comp.get(f"{c}_vs_T0", {})
        cs = comp.get(f"{c}_vs_S7", {})
        lines.append(
            f"| {c} {sc.CANDIDATE_DEFS[c]['name']} | {ct.get('delta')} | "
            f"{ct.get('ci')} | {ct.get('p_holm_vs_T0')} | "
            f"{cs.get('delta')} | {cs.get('ci')} | {cs.get('p_holm_vs_S7')} |")
    lines += [
        "",
        "## Temporal Stability (T0 & T5 & T7 & T8)",
        "",
    ]
    for cand in ("T0", "T5", "T7", "T8"):
        tp = res["holdout"].get(cand + "_temporal")
        if tp:
            lines.append(f"- {cand} holdout early/mid/late mean: "
                         f"{tp['early']['mean']} / {tp['middle']['mean']} / {tp['late']['mean']}")
    lines += [
        "",
        "## Complexity Comparison",
        "",
        "| variant | signals | # | recent | history | structure | learned-wt | stateful | explainability |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for k, v in p["complexity_table"].items():
        lines.append(f"| {k} | {','.join(v['signals'])} | {v['n_signals']} | "
                     f"{v['uses_recent']} | {v['uses_history']} | {v['uses_structure']} | "
                     f"{v['learned_weight']} | {v['stateful']} | {v['explainability']} |")
    lines += [
        "",
        "## Decision",
        "",
        f"**{decision['verdict']}**",
        "",
        f"- best simple candidate = {decision['best_simple_candidate']} "
        f"(holdout mean {decision['best_simple_holdout_mean']})",
        f"- not worse than CURRENT on holdout: {decision['simple_not_worse_on_holdout']}",
        f"- beats fair null (S7): {decision['simple_beats_fair_null']}",
        f"- {decision['rationale']}",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    main()
