"""多因素评分基础层（Task 16.5-C-2-Step1，纯函数，不接入推荐）。

定位：
- 仅为后续 C-2-Step2「D 策略（综合评分型）」提供评分能力；
- 只负责评分，不生成号码；
- 全部因子为历史统计描述，不构成任何预测或中奖承诺。

模块内三个纯函数：
  normalize_score(value, lo=0, hi=100) -> float        # 任意评分归一化到 0-100
  calculate_number_score(...) -> dict                  # 单号码评分（4 因子）
  calculate_combination_score(...) -> dict             # 组合评分（5 因子）

硬约束：
- 继承因素权重硬上限 15%（INHERIT_MAX_WEIGHT），任何单因素不得主导结果；
- 缺失统计信息时对应因子返回中性分（50），不偏向；
- 默认权重会在函数内归一化（Σw=1）。
"""
from __future__ import annotations

from typing import Any

# 单号码评分默认权重（总和 1.0）
DEFAULT_NUMBER_WEIGHTS: dict[str, float] = {
    "heat": 0.30,
    "missing": 0.30,
    "trend": 0.25,
    "inherit": 0.15,
}

# 组合评分默认权重（总和 1.0）
DEFAULT_COMBO_WEIGHTS: dict[str, float] = {
    "inherit_match": 0.20,
    "odd_even_match": 0.20,
    "big_small_match": 0.20,
    "zone_match": 0.20,
    "sum_span_match": 0.20,
}

# 继承因素硬上限：任何调用方都不得超过 15%
INHERIT_MAX_WEIGHT = 0.15

# 遗漏周期状态 → 基础分（历史统计语义，非预测）
MISSING_STATUS_SCORES: dict[str, float] = {
    "just_hit": 40.0,      # 刚开出：本期再现概率按历史分布一般
    "within_cycle": 55.0,  # 周期内：中性偏稳
    "over_avg": 80.0,      # 超平均遗漏：回补观察窗口
    "at_max": 88.0,        # 接近/达到历史最大遗漏：强回补信号
}

NEUTRAL = 50.0  # 缺失信息时的中性分


def normalize_score(value: float | None, lo: float = 0.0, hi: float = 100.0) -> float:
    """任意评分归一化到 [0, 100]。

    若 value 在 [lo, hi] 之外则线性映射后裁剪；保证输出恒在 [0, 100]，
    避免不同因子量纲差异影响组合总分。
    """
    if value is None:
        return NEUTRAL
    if hi <= lo:
        return 0.0
    v = (float(value) - lo) / (hi - lo) * 100.0
    return round(min(100.0, max(0.0, v)), 2)


def _normalize_weights(weights: dict[str, float], defaults: dict[str, float]) -> dict[str, float]:
    """合并默认权重并归一化（Σw=1）。继承权重硬上限 15%。"""
    w = dict(defaults)
    w.update(weights or {})
    if w.get("inherit", defaults.get("inherit", 0.0)) > INHERIT_MAX_WEIGHT:
        w["inherit"] = INHERIT_MAX_WEIGHT
    total = sum(w.values()) or 1.0
    return {k: v / total for k, v in w.items()}


def calculate_number_score(number: int,
                           temp: dict[str, Any],
                           missing: dict[str, Any],
                           overlap_dist: dict[str, Any] | None = None,
                           is_previous: bool = False,
                           weights: dict[str, float] | None = None) -> dict[str, Any]:
    """单号码评分（纯函数，不生成号码）。

    参数：
      number       号码（1-35 或 1-12）
      temp         analyze_number_temperature 的单号输出
                   {total_count, recent_30, recent_100, trend}
      missing      analyze_missing_cycle 的单号输出
                   {current_missing, avg_missing, max_missing, cycle_status}
      overlap_dist analyze_previous_overlap 输出（取前区分布给继承边际概率；可省略）
      is_previous  该号码是否为上一期开出号码（继承因素只对它有值）
      weights      自定义权重（inherit 硬上限 15%）

    输出：{"number", "score_total", "factors": {"heat", "missing", "trend", "inherit"}}
    原则：任何单因子不得主导结果；score_total = Σw·factor，均归一化到 0-100。
    """
    w = _normalize_weights(weights, DEFAULT_NUMBER_WEIGHTS)

    # heat：近 100 期窗口频率归一（0-100）
    r100 = int(temp.get("recent_100", 0) or 0)
    heat = normalize_score(r100 / 100.0 * 100.0)

    # missing：遗漏周期状态 → 0-100
    status = missing.get("cycle_status", "within_cycle")
    miss = round(MISSING_STATUS_SCORES.get(status, NEUTRAL), 2)

    # trend：近期每期频率差（裁剪 [-1, 1]）映射到 0-100（0.5 为中性）
    t = max(-1.0, min(1.0, float(temp.get("trend", 0.0) or 0.0)))
    trend = normalize_score((t + 1.0) / 2.0 * 100.0)

    # inherit：仅上期开出号码有值——按「重复 1-2 个」边际概率给分（弱权重）
    if is_previous:
        fdist = (overlap_dist or {}).get("front_overlap_distribution", {}) or {}
        p1 = float(fdist.get("1", 0.39))
        p2 = float(fdist.get("2", 0.14))
        inherit = normalize_score((p1 + p2) * 100.0)
    else:
        inherit = 0.0

    factors = {"heat": heat, "missing": miss, "trend": trend, "inherit": round(inherit, 2)}
    score_total = normalize_score(sum(w[k] * factors[k] for k in ("heat", "missing", "trend", "inherit")))
    return {"number": number, "score_total": score_total, "factors": factors}


def _zone_of(x: int, pmin: int, zones: int, size: int) -> int:
    return min((x - pmin) // size, zones - 1)


def calculate_combination_score(combo: dict[str, list[int]],
                                overlap_dist: dict[str, Any] | None = None,
                                structure_stats: dict[str, Any] | None = None,
                                sum_span_stats: dict[str, Any] | None = None,
                                prev_front: list[int] | None = None,
                                prev_back: list[int] | None = None,
                                weights: dict[str, float] | None = None) -> dict[str, Any]:
    """组合评分（纯函数，不生成号码）。

    参数：
      combo         候选组合 {front: [5], back: [2]}
      overlap_dist  analyze_previous_overlap 输出（继承数量匹配分）
      structure_stats analyze_structure_distribution 输出（奇偶/大小/区间贴合分）
      sum_span_stats 和值/跨度分布（契约见下；None 时 sum_span_match=中性 50）
                     {front_sum: {p25, p75, mean}, front_span: {p25, p75},
                      back_span: {p25, p75}}（由 C-2-Step2 提供）
      prev_front/prev_back 上一期号码（计算组合继承个数；缺省时 inherit_match=中性 50）
      weights      自定义权重

    输出：{"score_total", "factors": {"inherit_match", "odd_even_match",
           "big_small_match", "zone_match", "sum_span_match"}}
    """
    w = _normalize_weights(weights, DEFAULT_COMBO_WEIGHTS)
    front = combo.get("front") or []
    back = combo.get("back") or []

    # inherit_match：组合继承个数落在历史分布的匹配度（p(k) 直作分）
    if prev_front is not None and overlap_dist is not None:
        kf = len(set(front) & set(prev_front))
        kb = len(set(back) & set(prev_back or []))
        fd = (overlap_dist.get("front_overlap_distribution") or {})
        bd = (overlap_dist.get("back_overlap_distribution") or {})
        inherit_match = normalize_score(
            (float(fd.get(str(kf), 0.0)) + float(bd.get(str(kb), 0.0))) / 2.0 * 100.0)
    else:
        inherit_match = NEUTRAL

    # odd_even / big_small：组合形态在历史分布中的占比
    def _shape_match(key_prefix: str, odd: int, total_c: int) -> float:
        dist = {}
        if structure_stats:
            dist = structure_stats.get(key_prefix, {}) or {}
        s = sum(float(v) for v in dist.values()) or 1.0
        return normalize_score(float(dist.get(f"奇{odd}:偶{total_c - odd}", 0.0)) / s * 100.0)

    odd = sum(1 for x in front if x % 2 == 1)
    odd_even_match = _shape_match("odd_even", odd, 5)
    big = sum(1 for x in front if x >= 18)
    big_small_match = _shape_match("big_small", big, 5)

    # zone_match：组合号码所在区历史占比均值
    if structure_stats and structure_stats.get("zone_distribution"):
        zf = structure_stats["zone_distribution"].get("front") or {}
        pct = zf.get("pct") or []
        labels = zf.get("labels") or []
        if pct and labels:
            size = max(1, (35 - 1 + 1) // max(1, len(pct)))
            vals = [float(pct[_zone_of(x, 1, len(pct), size)]) for x in front if 1 <= x <= 35]
            zone_match = normalize_score((sum(vals) / len(vals) if vals else 0.0) * 100.0)
        else:
            zone_match = NEUTRAL
    else:
        zone_match = NEUTRAL

    # sum_span_match：和值/跨度落入高频区间（缺省中性）
    if sum_span_stats is not None and front:
        s = sum(front)
        fs = sum_span_stats.get("front_sum") or {}
        lo = fs.get("p25"); hi = fs.get("p75")
        if lo is not None and hi is not None:
            if lo <= s <= hi:
                sum_span_match = 100.0
            else:
                d = min(abs(s - lo), abs(s - hi))
                span = max(1.0, float(hi - lo))
                sum_span_match = normalize_score(max(0.0, 100.0 - d / span * 100.0))
        else:
            sum_span_match = NEUTRAL
    else:
        sum_span_match = NEUTRAL

    factors = {
        "inherit_match": round(inherit_match, 2),
        "odd_even_match": round(odd_even_match, 2),
        "big_small_match": round(big_small_match, 2),
        "zone_match": round(zone_match, 2),
        "sum_span_match": round(sum_span_match, 2),
    }
    score_total = normalize_score(
        sum(w[k] * factors[k] for k in ("inherit_match", "odd_even_match", "big_small_match",
                                        "zone_match", "sum_span_match")))
    return {"score_total": score_total, "factors": factors}
