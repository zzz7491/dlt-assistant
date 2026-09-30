"""P2-1 命中指标与随机基线统计。

输入：一批评测记录（list of dict，每条含 strategy / front_hits / back_hits /
total_hits / 可选 payout 分解）。

输出：
  - 每策略：front/back/total hit mean、front 0..5 / back 0..2 / total 分布
  - 关键阈值计数：>=1 front / >=2 front / >=3 front / >=1 back / 2 back
  - 奖级匹配计数（复用 prize.classify_prize）
  - 随机多 seed 统计：mean / median / std / p05 / p95
"""
from __future__ import annotations

import statistics as _stat
from typing import Any

from .prize import classify_prize


def _group_by_strategy(records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for r in records:
        out.setdefault(r.get("strategy", "?"), []).append(r)
    return out


def _pct(sorted_vals: list[float], p: float) -> float:
    """线性插值百分位（0-100）。空表返回 0。"""
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return float(sorted_vals[0])
    k = (len(sorted_vals) - 1) * (p / 100.0)
    lo = int(k)
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = k - lo
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * frac


def _distribution(values: list[int], lo: int, hi: int) -> dict[str, int]:
    d = {str(i): 0 for i in range(lo, hi + 1)}
    for v in values:
        if lo <= v <= hi:
            d[str(v)] += 1
    return d


def _strategy_block(recs: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(recs)
    fh = [int(r["front_hits"]) for r in recs]
    bh = [int(r["back_hits"]) for r in recs]
    th = [int(r["total_hits"]) for r in recs]
    tier_counts: dict[str, int] = {}
    prize_hit_count = 0
    for r in recs:
        t = classify_prize(r["front_hits"], r["back_hits"])
        key = str(t) if t is not None else "none"
        tier_counts[key] = tier_counts.get(key, 0) + 1
        if t is not None:
            prize_hit_count += 1
    return {
        "n": n,
        "front_hit_mean": round(sum(fh) / n, 4) if n else 0.0,
        "back_hit_mean": round(sum(bh) / n, 4) if n else 0.0,
        "total_hit_mean": round(sum(th) / n, 4) if n else 0.0,
        "front_hit_distribution": _distribution(fh, 0, 5),
        "back_hit_distribution": _distribution(bh, 0, 2),
        "total_hit_distribution": _distribution(th, 0, 7),
        "thresholds": {
            "front_ge1": sum(1 for x in fh if x >= 1),
            "front_ge2": sum(1 for x in fh if x >= 2),
            "front_ge3": sum(1 for x in fh if x >= 3),
            "back_ge1": sum(1 for x in bh if x >= 1),
            "back_eq2": sum(1 for x in bh if x == 2),
        },
        "prize_hit_count": prize_hit_count,
        "prize_tier_counts": tier_counts,
    }


def aggregate(records: list[dict[str, Any]]) -> dict[str, Any]:
    """按策略聚合全部 P2-1 指标。"""
    by = _group_by_strategy(records)
    return {
        strategy: _strategy_block(recs) for strategy, recs in sorted(by.items())
    }


def random_multi_seed_stats(seed_results: dict[int, dict[str, Any]]) -> dict[str, Any]:
    """对随机基线的多 seed 结果输出统计量。

    seed_results: {seed: {"front_hits":..,"back_hits":..,"total_hits":..}}（单期或单 seed 的代表值）。
    实际多 seed 聚合在 walk_forward.py 完成；本函数对「每个 seed 的均值向量」
    输出 mean/median/std/p05/p95。
    """
    total_vals = [float(v["total_hits"]) for v in seed_results.values()]
    total_vals_sorted = sorted(total_vals)
    front_vals = sorted(float(v["front_hits"]) for v in seed_results.values())
    back_vals = sorted(float(v["back_hits"]) for v in seed_results.values())
    return {
        "seeds": len(seed_results),
        "total_hit_mean": round(_stat.fmean(total_vals), 4) if total_vals else 0.0,
        "total_hit_median": round(_stat.median(total_vals), 4) if total_vals else 0.0,
        "total_hit_std": round(_stat.pstdev(total_vals), 4) if len(total_vals) >= 2 else 0.0,
        "total_hit_p05": round(_pct(total_vals_sorted, 5), 4),
        "total_hit_p95": round(_pct(total_vals_sorted, 95), 4),
        "front_hit_mean": round(_stat.fmean(front_vals), 4) if front_vals else 0.0,
        "back_hit_mean": round(_stat.fmean(back_vals), 4) if back_vals else 0.0,
    }


def compare_to_random(strategy_stats: dict[str, Any],
                      random_total_mean: float,
                      random_total_std: float,
                      random_total_p05: float,
                      random_total_p95: float) -> dict[str, Any]:
    """比较某策略均值与随机基线波动范围（回答「是否明显超出随机波动」）。

    输出：
      strategy_total_mean, diff_vs_random, in_random_p05_p95(bool),
      within_1sd(bool)
    """
    m = float(strategy_stats.get("total_hit_mean", 0.0))
    diff = m - random_total_mean
    within_band = random_total_p05 <= m <= random_total_p95
    one_sd = abs(diff) <= random_total_std
    return {
        "strategy_total_mean": round(m, 4),
        "random_total_mean": round(random_total_mean, 4),
        "diff_vs_random": round(diff, 4),
        "in_random_p05_p95": bool(within_band),
        "within_1sd": bool(one_sd),
    }
