"""P2-3 简化 selector candidate 评测。

设计原则（P2-3 任务书）：
  - T0 = CURRENT_SELECTOR（生产 final_score 完整逻辑，= P2-2 S1）作为 CONTROL。
  - T1-T4 = 固定单一策略 A/B/C/D。
  - T5 = SIMPLE_BASE（只 base + risk，去掉 recent/history/structure feedback）。
  - T6 = SIMPLE_STRUCTURE（只可严格 pre-target 的结构质量分）。
  - T7 = SIMPLE_BASE_STRUCTURE（base + structure 50/50 预固定权重，仅 pre-target 信息）。
  - T8 = DIVERSITY_SELECTOR（候选间结构差异最大的 deterministic 选择，不看结果）。
  - C-SENS = C（随机基线）50-seed 敏感性分析（random sensitivity，非 deterministic candidate）。

所有 deterministic candidate 共享同一 candidate cache（A/B/C/D + OOS maps + structure_ctx），
同一 900 期 target，同一 pre-target evidence → 公平对照。

禁止：修改生产 final_score / recommender / 权重 / 26112 / frontend。
"""
from __future__ import annotations

import json
import random
from typing import Any

from ..analyzer import (
    analyze, analyze_previous_overlap, analyze_number_temperature,
    analyze_missing_cycle, analyze_structure_distribution, analyze_sum_span,
)
from ..recommender import recommend
from ..scorer import calculate_combination_score, normalize_score
from ..final_score import compute_final_scores
from . import baselines, leakage, prize, statistics as stats
from . import ablation as _abl

EVAL_VERSION = "p23-v1"
COST = prize.TICKET_COST

# 生产 selector 权重（= P2-2 _PROD_WEIGHTS，保持不变，作为 T0 基准）
_PROD_WEIGHTS = {"base": 0.40, "history": 0.20, "recent": 0.15, "structure": 0.20, "risk": 0.05}

# 预固定权重（STEP 3 / STEP 10：运行结果前冻结，不允许按结果调优）
T7_WEIGHTS = {"base": 0.5, "structure": 0.5}
BASE_SCORE_FLOOR = 56.0   # base 分 60 + rank_adjust(-4) = 56
BASE_SCORE_CEIL = 68.0    # base 分 60 + rank_adjust(+8) = 68
BASE_SPAN = BASE_SCORE_CEIL - BASE_SCORE_FLOOR  # 12.0


def _hits(f: list, a: list) -> int:
    return len(set(f) & set(a))


def _cfg_full() -> dict:
    return {
        "analysis": {"front_min": 1, "front_max": 35, "back_min": 1, "back_max": 12,
                     "front_zones": 5, "back_zones": 2, "recent_window": 50},
        "recommend": {"combos_per_strategy": 1, "seed": None,
                      "weights": {
                          "number": {"heat": 0.30, "missing": 0.30, "trend": 0.25, "inherit": 0.15},
                          "combo": {"inherit_match": 0.20, "odd_even_match": 0.20,
                                     "big_small_match": 0.20, "zone_match": 0.20, "sum_span_match": 0.20},
                          "single_vs_combo": {"single": 0.7, "combo": 0.3},
                          "top_front": 15, "top_back": 8}},
    }


# ---------------------------------------------------------------- extended cache

def build_extended_cache(issues: list, warmup: int = 100,
                         verbose: bool = True) -> dict[str, Any]:
    """P2-3 扩展 cache = P2-2 candidate cache + 每期 structure_ctx。

    structure_ctx 供 T6/T7 严格 pre-target 结构评分（复用 D 的 4 分析器 + prev_draw）。
    """
    issues.sort(key=lambda x: str(x["issue"]))
    n = len(issues)
    if n <= warmup + 1:
        raise ValueError(f"need at least warmup+1 periods, got {n}")
    eval_indices = list(range(warmup, n))
    cfg = _cfg_full()

    cand: dict[int, dict] = {}
    oos_hist: dict[int, dict] = {}
    oos_recent: dict[int, dict] = {}
    oos_rank: dict[int, dict] = {}
    struct_ctx: dict[int, dict] = {}
    target_issue: dict[int, str] = {}
    actual_f: dict[int, list] = {}
    actual_b: dict[int, list] = {}
    prev_f: dict[int, list] = {}
    prev_b: dict[int, list] = {}
    oos_acc: dict[str, list] = {"A": [], "B": [], "C": [], "D": []}

    for i, t in enumerate(eval_indices):
        target = issues[t]
        train_last = issues[t - 1]
        target_issue[t] = str(target["issue"])
        actual_f[t] = list(target["front"])
        actual_b[t] = list(target["back"])
        prev_f[t] = list(train_last["front"])
        prev_b[t] = list(train_last["back"])

        evidence = issues[:t]
        evidence_win = evidence[-1000:]
        leakage.assert_no_future_data(evidence_win, target["issue"], label=f"evidence@t={t}")

        analysis = analyze(evidence_win, cfg)
        abc = recommend(analysis, cfg, stats=None)

        cands_t: dict[str, dict] = {}
        for key in ("A", "B", "C"):
            if key in abc:
                c = abc[key][0]
                cands_t[key] = {"front": list(c["front"]), "back": list(c["back"]),
                                "fh": _hits(c["front"], actual_f[t]),
                                "bh": _hits(c["back"], actual_b[t]),
                                "th": _hits(c["front"], actual_f[t]) + _hits(c["back"], actual_b[t])}
        # D
        stats_d = {
            "overlap": analyze_previous_overlap(evidence_win),
            "temperature": analyze_number_temperature(evidence_win),
            "missing_cycle": analyze_missing_cycle(evidence_win),
            "structure": analyze_structure_distribution(evidence_win),
            "sum_span": analyze_sum_span(evidence_win),
            "prev_issue": train_last,
        }
        full = recommend(analysis, cfg, stats=stats_d)
        if "D" in full:
            c = full["D"][0]
            cands_t["D"] = {"front": list(c["front"]), "back": list(c["back"]),
                            "fh": _hits(c["front"], actual_f[t]),
                            "bh": _hits(c["back"], actual_b[t]),
                            "th": _hits(c["front"], actual_f[t]) + _hits(c["back"], actual_b[t])}
        cand[t] = cands_t

        # 结构 ctx（供 T6/T7）
        struct_ctx[t] = {
            "overlap_dist": stats_d["overlap"],
            "structure_stats": stats_d["structure"],
            "sum_span_stats": stats_d["sum_span"],
            "prev_front": list(train_last["front"]),
            "prev_back": list(train_last["back"]),
        }

        oos_hist[t] = {g: (sum(oos_acc[g]) / len(oos_acc[g]) if oos_acc[g] else 0.0)
                       for g in oos_acc}
        oos_recent[t] = {g: list(oos_acc[g][-5:]) for g in oos_acc}
        ranked = sorted(oos_acc, key=lambda g: -(sum(oos_acc[g]) / len(oos_acc[g])
                                                 if oos_acc[g] else -1))
        oos_rank[t] = {g: (i + 1) for i, g in enumerate(ranked)}

        for g in ("A", "B", "C", "D"):
            if g in cands_t:
                oos_acc[g].append(cands_t[g]["th"])

        if verbose and (i + 1) % 100 == 0:
            print(f"  extended cache: {i+1}/{len(eval_indices)} done")

    return {
        "issues": issues, "eval_indices": eval_indices, "candidates": cand,
        "oos_history": oos_hist, "oos_recent": oos_recent, "oos_rank": oos_rank,
        "structure_ctx": struct_ctx,
        "target_issue": target_issue, "actual_front": actual_f, "actual_back": actual_b,
        "prev_front": prev_f, "prev_back": prev_b,
        "warmup": warmup,
    }


def cache_to_jsonable(cache: dict) -> dict:
    """把 cache 转为可 JSON 序列化（位置作键 0..n-1；_from_jsonable 按位置还原）。

    去掉 issues 全量，保留 manifest（eval 期序）+ 各 per-draw 字段（位置键）。
    """
    issues = cache["issues"]
    eval_issues = [str(issues[i]["issue"]) for i in cache["eval_indices"]]
    m = len(cache["eval_indices"])

    def posmap(key: str) -> dict:
        return {str(p): cache[key][cache["eval_indices"][p]] for p in range(m)}

    return {
        "manifest": {
            "total_issues": len(issues),
            "earliest_issue": str(issues[0]["issue"]),
            "latest_issue": str(issues[-1]["issue"]),
            "warmup": cache["warmup"],
            "eval_count": m,
            "eval_issues": eval_issues,
        },
        "candidates": posmap("candidates"),
        "oos_history": posmap("oos_history"),
        "oos_recent": posmap("oos_recent"),
        "oos_rank": posmap("oos_rank"),
        "structure_ctx": posmap("structure_ctx"),
        "target_issue": posmap("target_issue"),
        "actual_front": posmap("actual_front"),
        "actual_back": posmap("actual_back"),
        "prev_front": posmap("prev_front"),
        "prev_back": posmap("prev_back"),
    }


# ---------------------------------------------------------------- candidate defs

CANDIDATE_DEFS: dict[str, dict] = {
    "T0": {"name": "CURRENT_SELECTOR", "oracle": False,
            "signals": ["base", "history", "recent", "structure", "risk"],
            "uses_recent": True, "uses_history": True, "uses_structure": True,
            "learned_weight": False, "stateful": True,
            "explainability": "medium (5-factor weighted sum + OOS rank/history)"},
    "T1": {"name": "FIXED_A", "oracle": False,
            "signals": ["none"], "uses_recent": False, "uses_history": False,
            "uses_structure": False, "learned_weight": False, "stateful": False,
            "explainability": "trivial (always strategy A)"},
    "T2": {"name": "FIXED_B", "oracle": False,
            "signals": ["none"], "uses_recent": False, "uses_history": False,
            "uses_structure": False, "learned_weight": False, "stateful": False,
            "explainability": "trivial (always strategy B)"},
    "T3": {"name": "FIXED_C", "oracle": False,
            "signals": ["none"], "uses_recent": False, "uses_history": False,
            "uses_structure": False, "learned_weight": False, "stateful": False,
            "explainability": "trivial (always strategy C = random)"},
    "T4": {"name": "FIXED_D", "oracle": False,
            "signals": ["none"], "uses_recent": False, "uses_history": False,
            "uses_structure": False, "learned_weight": False, "stateful": False,
            "explainability": "trivial (always strategy D = scored)"},
    "T5": {"name": "SIMPLE_BASE", "oracle": False,
            "signals": ["base", "risk"], "uses_recent": False, "uses_history": False,
            "uses_structure": False, "learned_weight": False, "stateful": True,
            "explainability": "high (rank-based base + structural risk penalty only)"},
    "T6": {"name": "SIMPLE_STRUCTURE", "oracle": False,
            "signals": ["structure"], "uses_recent": False, "uses_history": False,
            "uses_structure": True, "learned_weight": False, "stateful": False,
            "explainability": "high (single pre-target structure quality score)"},
    "T7": {"name": "SIMPLE_BASE_STRUCTURE", "oracle": False,
            "signals": ["base", "structure"], "uses_recent": False, "uses_history": False,
            "uses_structure": True, "learned_weight": False, "stateful": False,
            "explainability": "high (pre-fixed 50/50 base+structure, no tuning)"},
    "T8": {"name": "DIVERSITY_SELECTOR", "oracle": False,
            "signals": ["candidate_diversity"], "uses_recent": False, "uses_history": False,
            "uses_structure": False, "learned_weight": False, "stateful": False,
            "explainability": "high (max symmetric-diff distance from other 3 candidates)"},
}

C_SEEDS = list(range(1, 51))  # 50-seed C sensitivity (STEP 4)
C_FIXED_PROXY_SEED = 0        # deterministic proxy for "a fixed production C seed"
BOOTSTRAP_N = 10000
BOOTSTRAP_SEED = 12345
DEV_RATIO = 0.70


# ---------------------------------------------------------------- candidate pickers

def pick_T0(cache: dict, t: int) -> tuple[str, dict]:
    """CURRENT selector（= P2-2 S1）。"""
    return _abl._apply_selector(cache, t, {})


def pick_fixed(cache: dict, t: int, g: str) -> tuple[str, dict]:
    c = cache["candidates"][t].get(g)
    return (g, c) if c else ("NONE", {})


def pick_T5(cache: dict, t: int) -> tuple[str, dict]:
    """base-only（去掉 recent/history/structure；保留 base + risk）。"""
    return _abl._apply_selector(cache, t, {"recent": 0.0, "history": 0.0, "structure": 0.0})


def _structure_score(combo: dict, ctx: dict) -> float:
    try:
        res = calculate_combination_score(
            {"front": list(combo["front"]), "back": list(combo["back"])},
            overlap_dist=ctx.get("overlap_dist"),
            structure_stats=ctx.get("structure_stats"),
            sum_span_stats=ctx.get("sum_span_stats"),
            prev_front=ctx.get("prev_front"),
            prev_back=ctx.get("prev_back"),
        )
        return float(res.get("score_total", 50.0))
    except Exception:
        return 50.0


def pick_T6(cache: dict, t: int) -> tuple[str, dict]:
    """structure-only：选结构分最高（tie 按 A<B<C<D）。"""
    ctx = cache["structure_ctx"][t]
    best_g, best_s, best_c = None, -1.0, {}
    for g in ("A", "B", "C", "D"):
        c = cache["candidates"][t].get(g)
        if not c:
            continue
        s = _structure_score(c, ctx)
        if s > best_s or (s == best_s and best_g and g < best_g):
            best_g, best_s, best_c = g, s, c
    return (best_g, best_c) if best_c else ("NONE", {})


def _base_norm(base_score: float) -> float:
    return (base_score - BASE_SCORE_FLOOR) / BASE_SPAN * 100.0


def pick_T7(cache: dict, t: int) -> tuple[str, dict]:
    """base + structure 50/50（base 归一 0-100，structure 0-100；预固定权重）。"""
    ctx = cache["structure_ctx"][t]
    ranked = cache["oos_rank"][t]
    best_g, best_s, best_c = None, -1.0, {}
    for g in ("A", "B", "C", "D"):
        c = cache["candidates"][t].get(g)
        if not c:
            continue
        from ..final_score import BASE_SCORE, RANK_ADJUST
        rank = ranked.get(g)
        base = BASE_SCORE + RANK_ADJUST.get(rank, 0.0) if rank else BASE_SCORE
        base_n = _base_norm(base)
        struct = _structure_score(c, ctx)
        s = T7_WEIGHTS["base"] * base_n + T7_WEIGHTS["structure"] * struct
        if s > best_s or (s == best_s and best_g and g < best_g):
            best_g, best_s, best_c = g, s, c
    return (best_g, best_c) if best_c else ("NONE", {})


def _sym_distance(a: dict, b: dict) -> float:
    """两 candidate 结构距离：前区 symmetric diff / 5 + 后区 symmetric diff / 2，归一 [0,1]。"""
    fd = len(set(a["front"]) ^ set(b["front"])) / 5.0
    bd = len(set(a["back"]) ^ set(b["back"])) / 2.0
    return (fd + bd) / 2.0


def pick_T8(cache: dict, t: int) -> tuple[str, dict]:
    """diversity：选与其他 3 candidate 平均对称距离最大者（不看结果，deterministic）。"""
    cands = cache["candidates"][t]
    present = [g for g in ("A", "B", "C", "D") if g in cands]
    if not present:
        return ("NONE", {})
    best_g, best_d = None, -1.0
    for g in present:
        others = [x for x in present if x != g]
        if not others:
            d = 0.0
        else:
            d = sum(_sym_distance(cands[g], cands[o]) for o in others) / len(others)
        if d > best_d or (d == best_d and best_g and g < best_g):
            best_g, best_d = g, d
    return (best_g, cands[best_g]) if best_g else ("NONE", {})


def pick_C_seeded(t: int, seed: int) -> tuple[str, dict]:
    """C = 随机 5+2（独立于 A/B/D 候选）。deterministic per (seed, t)。"""
    combo = baselines.random_combo(seed * 1000000 + t)
    return ("C-random", combo)


PICKERS: dict[str, Any] = {
    "T0": lambda cache, t: pick_T0(cache, t),
    "T1": lambda cache, t: pick_fixed(cache, t, "A"),
    "T2": lambda cache, t: pick_fixed(cache, t, "B"),
    "T3": lambda cache, t: pick_fixed(cache, t, "C"),
    "T4": lambda cache, t: pick_fixed(cache, t, "D"),
    "T5": lambda cache, t: pick_T5(cache, t),
    "T6": lambda cache, t: pick_T6(cache, t),
    "T7": lambda cache, t: pick_T7(cache, t),
    "T8": lambda cache, t: pick_T8(cache, t),
}


def run_candidate(cache: dict, cand: str, index_slice: slice | None = None) -> list[dict]:
    """对 candidate 在 index_slice（eval_indices 的切片）生成 records。"""
    picker = PICKERS[cand]
    idxs = cache["eval_indices"] if index_slice is None else cache["eval_indices"][index_slice]
    out = []
    sel_seq = []
    for t in idxs:
        g, combo = picker(cache, t)
        if not combo:
            sel_seq.append("NONE")
            continue
        fh, bh = combo["fh"], combo["bh"]
        pb = prize.payout_breakdown(fh, bh)
        out.append({
            "target_issue": cache["target_issue"][t],
            "selected_strategy": g, "selected_by": cand,
            "front": combo["front"], "back": combo["back"],
            "actual_front": cache["actual_front"][t], "actual_back": cache["actual_back"][t],
            "front_hits": fh, "back_hits": bh, "total_hits": fh + bh,
            "cost": COST, "payout": pb["known_fixed_payout"],
            "roi": pb["roi_lower_bound"], "prize_tier": pb["tier"],
            "evaluation_version": EVAL_VERSION,
        })
        sel_seq.append(g)
    out["_sel_seq"] = sel_seq  # 临时挂，外层 pop
    return out


def run_random_choice(cache: dict, seeds: list[int], index_slice: slice | None = None
                      ) -> tuple[list[dict], dict[int, list[float]]]:
    """S7-style random-choice ABCD（每期从候选均匀随机选一），多 seed。"""
    idxs = cache["eval_indices"] if index_slice is None else cache["eval_indices"][index_slice]
    recs = []
    per_seed: dict[int, list[float]] = {}
    for seed in seeds:
        hits = []
        for t in idxs:
            g, combo = _abl._pick_random_choice(cache, t, seed)
            if not combo:
                continue
            fh, bh = combo["fh"], combo["bh"]
            pb = prize.payout_breakdown(fh, bh)
            recs.append({
                "target_issue": cache["target_issue"][t],
                "selected_strategy": g, "selected_by": "S7", "seed": seed,
                "front": combo["front"], "back": combo["back"],
                "actual_front": cache["actual_front"][t], "actual_back": cache["actual_back"][t],
                "front_hits": fh, "back_hits": bh, "total_hits": fh + bh,
                "cost": COST, "payout": pb["known_fixed_payout"],
                "roi": pb["roi_lower_bound"], "prize_tier": pb["tier"],
                "evaluation_version": EVAL_VERSION,
            })
            hits.append(fh + bh)
        per_seed[seed] = hits
    return recs, per_seed


def run_C_sensitivity(cache: dict, index_slice: slice | None = None
                      ) -> dict[str, Any]:
    """STEP 4: C multi-seed sensitivity（判断固定 C seed 是否 lucky）。"""
    idxs = cache["eval_indices"] if index_slice is None else cache["eval_indices"][index_slice]
    per_seed: dict[int, list[float]] = {}
    for seed in C_SEEDS:
        hits = []
        for t in idxs:
            _, combo = pick_C_seeded(t, seed)
            fh = _hits(combo["front"], cache["actual_front"][t])
            bh = _hits(combo["back"], cache["actual_back"][t])
            hits.append(fh + bh)
        per_seed[seed] = hits
    # 每期 seed 均值 → 50-seed 分布
    seed_period_means = []
    for seed in C_SEEDS:
        hs = per_seed[seed]
        seed_period_means.append(sum(hs) / len(hs) if hs else 0.0)
    dist = stats.summary_stats(seed_period_means)
    # fixed proxy (seed 0) 在 50-seed 分布的分位
    fixed_hs = []
    for t in idxs:
        _, combo = pick_C_seeded(t, C_FIXED_PROXY_SEED)
        fixed_hs.append(_hits(combo["front"], cache["actual_front"][t]) +
                       _hits(combo["back"], cache["actual_back"][t]))
    fixed_mean = sum(fixed_hs) / len(fixed_hs) if fixed_hs else 0.0
    below = sum(1 for m in seed_period_means if m < fixed_mean)
    percentile = 100.0 * below / len(seed_period_means)
    return {
        "n_seeds": len(C_SEEDS),
        "c_seed_distribution": dist,
        "fixed_proxy_seed": C_FIXED_PROXY_SEED,
        "fixed_proxy_mean": round(fixed_mean, 4),
        "fixed_proxy_percentile_in_50seed": round(percentile, 2),
        "note": "production C uses seed=null (non-reproducible); seed 0 is a deterministic proxy",
    }


# ---------------------------------------------------------------- split

def _key_order(cache: dict) -> list:
    """cache 的时间顺序 keys（native=t 下标，loaded=0..n-1）。"""
    return sorted(cache["candidates"].keys())


def _hash_defndef(obj: dict) -> str:
    """候选定义 + 预固定权重的 SHA256（STEP 10 防过拟合：结果前冻结）。"""
    import hashlib
    s = json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def c_sensitivity_report(cache: dict, seeds: list[int]) -> dict[str, Any]:
    """C multi-seed 敏感性（space-agnostic）：判断固定 C seed 是否 lucky。

    用 cache key order 上每期真实开奖做命中；per-seed 每期均值 → seed 分布。
    """
    keys = _key_order(cache)
    per_seed: dict[int, list[float]] = {}
    for seed in seeds:
        hits = []
        for t in keys:
            combo = baselines.random_combo(seed * 1000000 + t)
            hits.append(_hits(combo["front"], cache["actual_front"][t]) +
                        _hits(combo["back"], cache["actual_back"][t]))
        per_seed[seed] = hits
    seed_period_means = [sum(v) / len(v) for v in per_seed.values() if v]
    dist = stats.summary_stats(seed_period_means)
    fixed_hits = []
    for t in keys:
        combo = baselines.random_combo(C_FIXED_PROXY_SEED * 1000000 + t)
        fixed_hits.append(_hits(combo["front"], cache["actual_front"][t]) +
                          _hits(combo["back"], cache["actual_back"][t]))
    fixed_mean = sum(fixed_hits) / len(fixed_hits) if fixed_hits else 0.0
    below = sum(1 for m in seed_period_means if m < fixed_mean)
    percentile = 100.0 * below / len(seed_period_means)
    return {
        "n_seeds": len(seeds),
        "c_seed_distribution": dist,
        "fixed_proxy_seed": C_FIXED_PROXY_SEED,
        "fixed_proxy_mean": round(fixed_mean, 4),
        "fixed_proxy_percentile_in_50seed": round(percentile, 2),
        "note": "production C uses seed=null (non-reproducible); seed 0 is a deterministic proxy",
    }
    """前 ratio 为 development，后 1-ratio 为 holdout（时间顺序，不重叠）。"""
    n = len(eval_indices)
    dev_end = int(n * ratio)
    dev = slice(0, dev_end)
    holdout = slice(dev_end, n)
    return dev, holdout, eval_indices[:dev_end], eval_indices[dev_end:]
