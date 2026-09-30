"""P2-2 selector ablation 引擎。

一次 walk 构建 candidate cache（A/B/C/D + OOS history/recent maps per t），
之后所有 variant 基于同一 cache 派生 selection → 避免重复跑 D。

Variant 定义（与任务书 STEP 3 一致）：
  S0 RANDOM_SINGLE       独立单注随机 5+2（不与 A/B/C/D 候选相关）
  S1 CURRENT_SELECTOR    生产 selector 完整（base+history+recent+structure+risk）
  S2 NO_RECENT          S1 但 recent=0
  S3 NO_HISTORY         S1 但 history=0
  S4 NO_RECENT_NO_HISTORY  recent=0 且 history=0
  S5 BASE_ONLY          history=0, recent=0, structure=0（保留 base + risk）
  S6 BASE_STRUCTURE    history=0, recent=0（保留 base + structure + risk）
  S7 RANDOM_CHOICE_ABCD  每期从 [A,B,C,D] 均匀随机挑一（固定 seed）
  S8 ORACLE_ABCD         每期挑命中最高者（POST-HOC，仅理论上限，明确 INVALID）

S7 支持多 seed 聚合；S8 明确标记 ORACLE / NOT FOR PRODUCTION。
"""
from __future__ import annotations

import random
from typing import Any

from ..final_score import compute_final_scores
from ..analyzer import (analyze, analyze_previous_overlap, analyze_number_temperature,
                        analyze_missing_cycle, analyze_structure_distribution,
                        analyze_sum_span)
from ..recommender import recommend
from . import baselines, leakage, prize, statistics as stats

EVALUATION_VERSION = "p22-v1"
COST = prize.TICKET_COST

# 默认 selector 权重（生产 final_score.DEFAULT_WEIGHTS 的加权部分）
_PROD_WEIGHTS = {"base": 0.40, "history": 0.20, "recent": 0.15, "structure": 0.20, "risk": 0.05}

VARIANTS: dict[str, dict[str, Any]] = {
    "S0": {"name": "RANDOM_SINGLE",       "desc": "独立单注随机 5+2",                  "oracle": False},
    "S1": {"name": "CURRENT_SELECTOR",    "desc": "生产 selector（base+hist+rec+str+risk）", "oracle": False,
           "weight_override": {}},
    "S2": {"name": "NO_RECENT",           "desc": "S1 但 recent=0",                    "oracle": False,
           "weight_override": {"recent": 0.0}},
    "S3": {"name": "NO_HISTORY",          "desc": "S1 但 history=0",                   "oracle": False,
           "weight_override": {"history": 0.0}},
    "S4": {"name": "NO_RECENT_NO_HISTORY","desc": "S1 但 recent=0 且 history=0",        "oracle": False,
           "weight_override": {"recent": 0.0, "history": 0.0}},
    "S5": {"name": "BASE_ONLY",          "desc": "S1 但只保留 base（+risk）",          "oracle": False,
           "weight_override": {"recent": 0.0, "history": 0.0, "structure": 0.0}},
    "S6": {"name": "BASE_STRUCTURE",     "desc": "S1 但只保留 base+structure（+risk）","oracle": False,
           "weight_override": {"recent": 0.0, "history": 0.0}},
    "S7": {"name": "RANDOM_CHOICE_ABCD", "desc": "每期从 [A,B,C,D] 均匀随机选一（fair null baseline）", "oracle": False},
    "S8": {"name": "ORACLE_ABCD",        "desc": "每期挑命中最高（POST-HOC，仅理论上限，INVALID FOR PRODUCTION）", "oracle": True},
}


# ---------------------------------------------------------------- 工具

def _hits(f: list, a: list) -> int:
    return len(set(f) & set(a))


def _build_evidence(issues: list, t: int, window: int = 1000) -> list:
    ev = issues[:t]
    if window and window > 0:
        ev = ev[-window:]
    return ev


def _make_cfg() -> dict:
    return {
        "analysis": {"front_min": 1, "front_max": 35, "back_min": 1, "back_max": 12,
                     "front_zones": 5, "back_zones": 2, "recent_window": 50},
        "recommend": {
            "combos_per_strategy": 1, "seed": None,
            "weights": {
                "number": {"heat": 0.30, "missing": 0.30, "trend": 0.25, "inherit": 0.15},
                "combo": {"inherit_match": 0.20, "odd_even_match": 0.20,
                          "big_small_match": 0.20, "zone_match": 0.20, "sum_span_match": 0.20},
                "single_vs_combo": {"single": 0.7, "combo": 0.3},
                "top_front": 15, "top_back": 8,
            },
        },
    }


# ---------------------------------------------------------------- candidate cache

def build_candidate_cache(issues: list, warmup: int = 100, verbose: bool = True) -> dict[str, Any]:
    """单次 walk 生成：
      - candidates[t] = {"A": {"front","back","fh","bh","th"}, "B":..., "C":..., "D":...}
      - oos_history[t] = {g: running_avg_total_hit up to t-1}
      - oos_recent[t]  = {g: last 5 total_hits up to t-1}
      - oos_rank[t]    = {g: rank 1..4 by OOS mean}
      - target_issues[t], actual_front[t], actual_back[t], prev_draw[t]

    t 范围：warmup .. len(issues)-1（可评测期）。
    """
    issues.sort(key=lambda x: str(x["issue"]))
    n = len(issues)
    if n <= warmup + 1:
        raise ValueError(f"need at least warmup+1 periods")
    eval_indices = list(range(warmup, n))

    cfg = _make_cfg()
    cand: dict[int, dict[str, dict]] = {}
    oos_hist: dict[int, dict[str, float]] = {}
    oos_recent: dict[int, dict[str, list]] = {}
    oos_rank: dict[int, dict[str, int]] = {}
    target_issue: dict[int, str] = {}
    actual_f: dict[int, list] = {}
    actual_b: dict[int, list] = {}
    prev_f: dict[int, list] = {}
    prev_b: dict[int, list] = {}

    oos_acc: dict[str, list[int]] = {"A": [], "B": [], "C": [], "D": []}

    for i, t in enumerate(eval_indices):
        target = issues[t]
        train_last = issues[t - 1]
        target_issue[t] = str(target["issue"])
        actual_f[t] = list(target["front"])
        actual_b[t] = list(target["back"])
        prev_f[t] = list(train_last["front"])
        prev_b[t] = list(train_last["back"])

        evidence = _build_evidence(issues, t)
        leakage.assert_no_future_data(evidence, target["issue"], label=f"evidence@t={t}")

        analysis = analyze(evidence, cfg)
        abc = recommend(analysis, cfg, stats=None)

        cands_t: dict[str, dict] = {}
        for key in ("A", "B", "C"):
            if key not in abc:
                continue
            c = abc[key][0]
            cands_t[key] = {
                "front": list(c["front"]), "back": list(c["back"]),
                "fh": _hits(c["front"], actual_f[t]),
                "bh": _hits(c["back"], actual_b[t]),
                "th": _hits(c["front"], actual_f[t]) + _hits(c["back"], actual_b[t]),
            }
        # D
        stats_d = {
            "overlap": analyze_previous_overlap(evidence),
            "temperature": analyze_number_temperature(evidence),
            "missing_cycle": analyze_missing_cycle(evidence),
            "structure": analyze_structure_distribution(evidence),
            "sum_span": analyze_sum_span(evidence),
            "prev_issue": train_last,
        }
        full = recommend(analysis, cfg, stats=stats_d)
        if "D" in full:
            c = full["D"][0]
            cands_t["D"] = {
                "front": list(c["front"]), "back": list(c["back"]),
                "fh": _hits(c["front"], actual_f[t]),
                "bh": _hits(c["back"], actual_b[t]),
                "th": _hits(c["front"], actual_f[t]) + _hits(c["back"], actual_b[t]),
            }
        cand[t] = cands_t

        # OOS maps at t（使用前 t-1 及之前累积）
        oos_hist[t] = {g: (sum(oos_acc[g]) / len(oos_acc[g]) if oos_acc[g] else 0.0)
                       for g in oos_acc}
        oos_recent[t] = {g: list(oos_acc[g][-5:]) for g in oos_acc}
        ranked = sorted(oos_acc, key=lambda g: -(sum(oos_acc[g]) / len(oos_acc[g])
                                                 if oos_acc[g] else -1))
        oos_rank[t] = {g: (i + 1) for i, g in enumerate(ranked)}

        # 更新 OOS（用当期 4 策略真实命中）
        for g in ("A", "B", "C", "D"):
            if g in cands_t:
                oos_acc[g].append(cands_t[g]["th"])

        if verbose and (i + 1) % 100 == 0:
            print(f"  candidate cache: {i+1}/{len(eval_indices)} done")

    return {
        "issues": issues, "eval_indices": eval_indices, "candidates": cand,
        "oos_history": oos_hist, "oos_recent": oos_recent, "oos_rank": oos_rank,
        "target_issue": target_issue, "actual_front": actual_f, "actual_back": actual_b,
        "prev_front": prev_f, "prev_back": prev_b,
        "warmup": warmup,
    }


# ---------------------------------------------------------------- selector pick

def _apply_selector(cache: dict, t: int, weight_override: dict) -> tuple[str, dict]:
    """在 t 用 compute_final_scores + OOS maps 选 primary，返回 (strategy_key, combo)。"""
    cands = cache["candidates"][t]
    recs = [{"strategy": g, "front": c["front"], "back": c["back"]}
            for g, c in cands.items() if g in ("A", "B", "C", "D")]
    if not recs:
        return ("NONE", {})
    ranked = cache["oos_rank"][t]
    hist = cache["oos_history"][t]
    recent = cache["oos_recent"][t]
    prev_draw = {"front": cache["prev_front"][t], "back": cache["prev_back"][t]}
    # effective_sample：用 OOS 累积期数（各组 count 的最大值；A/B/C 累积期数相同）
    oos = cache["oos_recent"][t]
    effective_sample = max((len(v) for v in oos.values()), default=0)

    weights = dict(_PROD_WEIGHTS)
    weights.update(weight_override or {})
    scored = compute_final_scores(
        recs,
        effective_sample=effective_sample,
        strategy_rank=ranked,
        history_map=hist,
        recent_map=recent,
        structure_ctx=None,
        prev_draw=prev_draw,
        weights=weights,
    )
    primary = next((s for s in scored if s.get("is_primary")), None)
    if primary is None:
        # compute_final_scores 失败安全会原样返回；此时无 is_primary → 取 final_rank=1
        with_score = [s for s in scored if isinstance(s.get("final_score"), (int, float))]
        with_score.sort(key=lambda x: -x["final_score"])
        primary = with_score[0] if with_score else scored[0]
    g = str(primary.get("strategy", "")).split("-")[0]
    combo = cands.get(g, {})
    return (g, combo)


def _pick_random_choice(cache: dict, t: int, seed: int) -> tuple[str, dict]:
    """S7：固定 seed + t → 从 A/B/C/D 均匀随机挑一（可复现）。"""
    cands = cache["candidates"][t]
    keys = [k for k in ("A", "B", "C", "D") if k in cands]
    if not keys:
        return ("NONE", {})
    rng = random.Random(seed * 1000003 + t)
    g = rng.choice(keys)
    return (g, cands[g])


def _pick_oracle(cache: dict, t: int) -> tuple[str, dict]:
    """S8 ORACLE：t 期命中最高者（POST-HOC）。"""
    cands = cache["candidates"][t]
    if not cands:
        return ("NONE", {})
    best_g, best_c = None, None
    for g, c in cands.items():
        if best_c is None or c["th"] > best_c["th"]:
            best_g, best_c = g, c
    return (best_g, best_c)


# ---------------------------------------------------------------- variant 生成

def _variant_records_s0(cache: dict, seed: int) -> list[dict]:
    """S0：独立随机 5+2 单注（按 t 与 seed 派生确定性 RNG）。"""
    out = []
    for t in cache["eval_indices"]:
        combo = baselines.random_combo(seed * 1000000 + t)
        fh = _hits(combo["front"], cache["actual_front"][t])
        bh = _hits(combo["back"], cache["actual_back"][t])
        pb = prize.payout_breakdown(fh, bh)
        out.append({
            "target_issue": cache["target_issue"][t],
            "strategy": "S0", "seed": seed,
            "front": combo["front"], "back": combo["back"],
            "actual_front": cache["actual_front"][t], "actual_back": cache["actual_back"][t],
            "front_hits": fh, "back_hits": bh, "total_hits": fh + bh,
            "cost": COST, "payout": pb["known_fixed_payout"],
            "roi": pb["roi_lower_bound"], "prize_tier": pb["tier"],
            "evaluation_version": EVALUATION_VERSION,
        })
    return out


def _variant_records_selector(cache: dict, variant: str) -> list[dict]:
    """S1-S6：用 weight_override 派生 selection → per-period record。"""
    vo = VARIANTS[variant]["weight_override"]
    out = []
    sel_seq: list[str] = []
    for t in cache["eval_indices"]:
        g, combo = _apply_selector(cache, t, vo)
        if not combo:
            sel_seq.append("NONE")
            continue
        fh, bh = combo["fh"], combo["bh"]
        pb = prize.payout_breakdown(fh, bh)
        out.append({
            "target_issue": cache["target_issue"][t],
            "strategy": g, "selected_by": variant,
            "front": combo["front"], "back": combo["back"],
            "actual_front": cache["actual_front"][t], "actual_back": cache["actual_back"][t],
            "front_hits": fh, "back_hits": bh, "total_hits": fh + bh,
            "cost": COST, "payout": pb["known_fixed_payout"],
            "roi": pb["roi_lower_bound"], "prize_tier": pb["tier"],
            "evaluation_version": EVALUATION_VERSION,
        })
        sel_seq.append(g)
    out[-1]["_sel_seq"] = sel_seq  # 挂到末尾 record（内部用；后续移除）
    for r in out:
        r.pop("_sel_seq", None)
    return out, sel_seq


def _variant_records_s7(cache: dict, seeds: list[int]) -> tuple[list[dict], dict]:
    """S7：多 seed 的 random-choice ABCD。返回 (records, per_seed_stats)。"""
    recs = []
    per_seed: dict[int, list[float]] = {}
    for seed in seeds:
        seed_hits = []
        for t in cache["eval_indices"]:
            g, combo = _pick_random_choice(cache, t, seed)
            if not combo:
                continue
            fh, bh = combo["fh"], combo["bh"]
            pb = prize.payout_breakdown(fh, bh)
            recs.append({
                "target_issue": cache["target_issue"][t],
                "strategy": g, "selected_by": "S7", "seed": seed,
                "front": combo["front"], "back": combo["back"],
                "actual_front": cache["actual_front"][t], "actual_back": cache["actual_back"][t],
                "front_hits": fh, "back_hits": bh, "total_hits": fh + bh,
                "cost": COST, "payout": pb["known_fixed_payout"],
                "roi": pb["roi_lower_bound"], "prize_tier": pb["tier"],
                "evaluation_version": EVALUATION_VERSION,
            })
            seed_hits.append(fh + bh)
        per_seed[seed] = seed_hits
    return recs, per_seed


def _variant_records_s8(cache: dict) -> list[dict]:
    out = []
    for t in cache["eval_indices"]:
        g, combo = _pick_oracle(cache, t)
        if not combo:
            continue
        fh, bh = combo["fh"], combo["bh"]
        pb = prize.payout_breakdown(fh, bh)
        out.append({
            "target_issue": cache["target_issue"][t],
            "strategy": g, "selected_by": "S8_ORACLE", "oracle": True,
            "front": combo["front"], "back": combo["back"],
            "actual_front": cache["actual_front"][t], "actual_back": cache["actual_back"][t],
            "front_hits": fh, "back_hits": bh, "total_hits": fh + bh,
            "cost": COST, "payout": pb["known_fixed_payout"],
            "roi": pb["roi_lower_bound"], "prize_tier": pb["tier"],
            "evaluation_version": EVALUATION_VERSION,
        })
    return out


# ---------------------------------------------------------------- switching

def switching_stats(seq: list[str]) -> dict[str, Any]:
    """selector selection 序列 → 切换率 / 连续 run / 后 win/loss 切换率。

    需要配合每期的 total_hits 才能算 "switch-after-win/loss"；这里 seq 是策略选择序列，
    win/loss 由外部 hits_seq 提供（同长度）。
    """
    if len(seq) < 2:
        return {"n": len(seq), "switch_rate": 0.0, "mean_run": 0.0,
                "switch_after_win_rate": 0.0, "switch_after_loss_rate": 0.0}
    switches = sum(1 for i in range(1, len(seq)) if seq[i] != seq[i - 1])
    # 连续 run：每次策略不变的区间长度
    runs, cur = [1], 1
    for i in range(1, len(seq)):
        if seq[i] == seq[i - 1]:
            cur += 1
        else:
            runs.append(cur)
            cur = 1
    mean_run = sum(runs) / len(runs) if runs else 0.0
    return {
        "n": len(seq),
        "switches": switches,
        "switch_rate": round(switches / (len(seq) - 1), 4),
        "mean_run": round(mean_run, 4),
        "runs": runs,
    }


def selection_freq(seq: list[str]) -> dict[str, float]:
    """策略选择频率（%）+ early/mid/late 分段。"""
    total = len(seq) or 1
    out: dict[str, float] = {}
    for g in ("A", "B", "C", "D"):
        out[g] = round(100.0 * seq.count(g) / total, 2)
    third = total // 3
    early, mid, late = seq[:third], seq[third:2 * third], seq[2 * third:]
    for label, chunk in (("early", early), ("middle", mid), ("late", late)):
        sub: dict[str, float] = {}
        for g in ("A", "B", "C", "D"):
            sub[g] = round(100.0 * chunk.count(g) / (len(chunk) or 1), 2)
        out[label] = sub
    return out


# ---------------------------------------------------------------- runner

def run_ablation(issues: list, warmup: int = 100,
                 random_s7_seeds: list[int] | None = None,
                 s0_seeds: list[int] | None = None,
                 bootstrap_n: int = 10000, bootstrap_seed: int = 12345,
                 verbose: bool = True) -> dict[str, Any]:
    """完整 P2-2 ablation：

    - 构建 candidate cache（一次 D 遍历）
    - S1-S6 selector variants
    - S7 多 seed random-choice（默认 50 seeds；可传 100）
    - S8 oracle
    - S0 独立随机（默认 50 seeds）
    - paired bootstrap CI（CURRENT vs NO_RECENT / NO_HISTORY / NO_RN / RANDOM_CHOICE）
    - Holm-adjusted p-values
    - selection frequency + switching
    - temporal split + rolling blocks
    """
    if random_s7_seeds is None:
        random_s7_seeds = list(range(1, 51))
    if s0_seeds is None:
        s0_seeds = list(range(1, 51))

    if verbose:
        print(f"[P2-2] building candidate cache (warmup={warmup}) ...")
    cache = build_candidate_cache(issues, warmup=warmup, verbose=verbose)

    variant_records: dict[str, Any] = {}
    sel_seq: dict[str, list[str]] = {}

    # S1-S6
    for v in ("S1", "S2", "S3", "S4", "S5", "S6"):
        if verbose:
            print(f"[P2-2] running {v} {VARIANTS[v]['name']} ...")
        recs, seq = _variant_records_selector(cache, v)
        variant_records[v] = recs
        sel_seq[v] = seq

    # S0
    if verbose:
        print(f"[P2-2] running S0 RANDOM_SINGLE ({len(s0_seeds)} seeds) ...")
    s0_rec: list[dict] = []
    for sd in s0_seeds:
        s0_rec.extend(_variant_records_s0(cache, seed=sd))
    variant_records["S0"] = s0_rec

    # S7
    if verbose:
        print(f"[P2-2] running S7 RANDOM_CHOICE_ABCD ({len(random_s7_seeds)} seeds) ...")
    s7_rec, s7_per_seed = _variant_records_s7(cache, random_s7_seeds)
    variant_records["S7"] = s7_rec

    # S8
    if verbose:
        print(f"[P2-2] running S8 ORACLE_ABCD (POST-HOC upper bound) ...")
    variant_records["S8"] = _variant_records_s8(cache)

    # ---- 汇总 & 统计
    per_variant: dict[str, dict] = {}
    for v, recs in variant_records.items():
        th = [r["total_hits"] for r in recs]
        fh = [r["front_hits"] for r in recs]
        bh = [r["back_hits"] for r in recs]
        s = stats.summary_stats(th)
        # prize 汇总
        psum = prize.aggregate_payout(recs)
        per_variant[v] = {
            "variant": VARIANTS[v]["name"],
            "description": VARIANTS[v]["desc"],
            "oracle": VARIANTS[v]["oracle"],
            "n_records": len(recs),
            "unique_periods": len({r["target_issue"] for r in recs}),
            "total_hit_stats": s,
            "front_mean": round(_statmean(fh), 4),
            "back_mean": round(_statmean(bh), 4),
            "payout_summary": psum,
        }

    # ---- 主比较：S1 vs {S2, S3, S4, S7}
    # 需同 target 集：S1/S2/S3/S4 是每 t 一条 record；S7 是 seeds×t 条 record。
    # 对 S1 vs S7：S7 用每个 seed 各自的 mean total_hit 作为代表（seeds 维度聚合）
    s1_th = [r["total_hits"] for r in variant_records["S1"]]
    s2_th = [r["total_hits"] for r in variant_records["S2"]]
    s3_th = [r["total_hits"] for r in variant_records["S3"]]
    s4_th = [r["total_hits"] for r in variant_records["S4"]]
    s7_th_by_seed = s7_per_seed  # {seed: [total_hits per period]}

    # S1 vs S7：S7 每期取 seeds 均值
    s7_mean_per_period: dict[str, float] = {}
    for seed, hits in s7_th_by_seed.items():
        for r, h in zip(variant_records["S1"], hits):
            tp = r["target_issue"]
            s7_mean_per_period.setdefault(tp, []).append(h)
    s7_aggregated = [sum(v) / len(v) for v in s7_mean_per_period.values()]
    s1_th_sorted = sorted(s1_th)
    s7_period_list = [s7_mean_per_period[cache["target_issue"][t]]
                      for t in cache["eval_indices"] if cache["target_issue"][t] in s7_mean_per_period]

    # 对齐顺序：按 eval_indices 顺序
    s1_in_order = s1_th
    s7_in_order = [sum(v) / len(v) if v else 0.0 for v in
                   (s7_mean_per_period.get(cache["target_issue"][t], [])
                    for t in cache["eval_indices"])]

    def paired(a: list, b: list) -> dict:
        return {
            "bootstrap": stats.paired_bootstrap_ci(a, b, n_resamples=bootstrap_n, seed=bootstrap_seed),
            "signflip": stats.paired_sign_flip_pvalue(a, b, one_sided=True),
            "t": stats.t_statistic_paired(a, b),
            "paired_delta_mean": round(_statmean([x - y for x, y in zip(a, b)]), 5),
        }

    comparisons = {
        "S1_vs_S2": paired(s1_in_order, s2_th),
        "S1_vs_S3": paired(s1_in_order, s3_th),
        "S1_vs_S4": paired(s1_in_order, s4_th),
        "S1_vs_S7": paired(s1_in_order, s7_in_order),
    }
    # 主比较 p 值（one-sided: S1 优于 对照）
    pvals = [comparisons[k]["signflip"]["p_value"] for k in
             ("S1_vs_S2", "S1_vs_S3", "S1_vs_S4", "S1_vs_S7")]
    pvals_adj = stats.holm_adjust(pvals)
    for i, k in enumerate(("S1_vs_S2", "S1_vs_S3", "S1_vs_S4", "S1_vs_S7")):
        comparisons[k]["signflip"]["p_value_raw"] = pvals[i]
        comparisons[k]["signflip"]["p_value_holm"] = pvals_adj[i]

    # ---- selection frequency + switching（对 S1）
    s1_seq = sel_seq["S1"]
    s1_hits = [r["total_hits"] for r in variant_records["S1"]]
    sel_freq = selection_freq(s1_seq)
    sw = switching_stats(s1_seq)
    # switch-after-win/loss：t 期相对 t-1 期 total_hits 的 win/loss
    win_idx = [i for i in range(1, len(s1_hits)) if s1_hits[i] >= s1_hits[i - 1]]
    loss_idx = [i for i in range(1, len(s1_hits)) if s1_hits[i] < s1_hits[i - 1]]
    def _sw_in(idxs):
        return (sum(1 for i in idxs if s1_seq[i] != s1_seq[i - 1]) / len(idxs)
                if idxs else 0.0)
    sw["switch_after_win_rate"] = round(_sw_in(win_idx), 4)
    sw["switch_after_loss_rate"] = round(_sw_in(loss_idx), 4)
    sw["win_events"] = len(win_idx)
    sw["loss_events"] = len(loss_idx)

    # ---- temporal split（对 S1 与 S2，按 t 顺序；与 eval_indices 对齐）
    s1_temporal = stats.temporal_split(s1_in_order)
    s2_temporal = stats.temporal_split(s2_th)
    rolling_s1_minus_s2 = stats.rolling_blocks(
        [a - b for a, b in zip(s1_in_order, s2_th)], block=100)

    # ---- S7 多 seed stats
    seed_means = [sum(v) / len(v) for v in s7_th_by_seed.values()]
    s7_seed_stats = stats.summary_stats(seed_means)
    s7_full_stats = stats.summary_stats([h for hits in s7_th_by_seed.values() for h in hits])

    # ---- S8 oracle summary
    s8_hits = [r["total_hits"] for r in variant_records["S8"]]
    s8_stats = stats.summary_stats(s8_hits)

    # ---- S0 独立随机
    s0_hits = [r["total_hits"] for r in variant_records["S0"]]
    s0_stats = stats.summary_stats(s0_hits)

    return {
        "meta": {
            "evaluation_version": EVALUATION_VERSION,
            "history_count": len(issues),
            "warmup": warmup,
            "evaluated_periods": len(cache["eval_indices"]),
            "earliest_issue": str(issues[0]["issue"]),
            "latest_issue": str(issues[-1]["issue"]),
            "s7_seeds": len(random_s7_seeds),
            "s0_seeds": len(s0_seeds),
            "bootstrap_n": bootstrap_n,
            "bootstrap_seed": bootstrap_seed,
            "note": "exploratory model-selection analysis; multiple comparisons adjusted via Holm; ORACLE is POST-HOC invalid for production",
        },
        "variants": per_variant,
        "comparisons": comparisons,
        "selection_frequency_S1": sel_freq,
        "switching_S1": sw,
        "temporal_S1": s1_temporal,
        "temporal_S2": s2_temporal,
        "rolling_S1_minus_S2": rolling_s1_minus_s2,
        "s7_seed_stats": s7_seed_stats,
        "s7_full_stats": s7_full_stats,
        "s8_oracle_stats": s8_stats,
        "s8_oracle_warning": "POST-HOC / INVALID FOR PRODUCTION — theoretical upper bound only",
        "s0_stats": s0_stats,
    }


def _statmean(vals: list[float]) -> float:
    import statistics as _s
    return _s.fmean(vals) if vals else 0.0
