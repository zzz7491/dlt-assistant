"""娱乐推荐算法：三种策略（仅娱乐，不预测中奖）。

策略 A 均衡统计型：热号 + 冷号混合抽样，并强制奇偶平衡与大小平衡。
策略 B 冷热组合型：前区约 60% 热号 + 40% 冷号。
策略 C 纯随机娱乐型：合法规则下纯随机生成。

重要：本模块仅基于历史统计做娱乐性组合，绝不声称可以预测中奖。
"""
from __future__ import annotations

import random
from typing import Any

# 策略标识 -> 中文标签（供报告与推荐记录使用）
STRATEGY_LABELS: dict[str, str] = {
    "A": "均衡统计型",
    "B": "冷热组合型",
    "C": "纯随机娱乐型",
}


def _norm(d: dict[int, float]) -> dict[int, float]:
    s = sum(d.values()) or 1.0
    return {k: v / s for k, v in d.items()}


def _weighted_unique(pool: list[int], weights: dict[int, float], n: int, rng: random.Random) -> set[int]:
    """按权重无放回抽取 n 个（权重为 0 时退回纯随机），返回集合。"""
    chosen: set[int] = set()
    guard = 0
    while len(chosen) < n and guard < 1000:
        k = rng.choices(pool, weights=[weights.get(x, 0) for x in pool], k=1)[0]
        chosen.add(k)
        guard += 1
    while len(chosen) < n:  # 极端兜底
        chosen.add(rng.choice(pool))
    return chosen


def _balance(front: set[int], fmin: int, fmax: int, rng: random.Random, boundary: int = 18) -> list[int]:
    """在不改变数量前提下，微调奇偶/大小分布，使其更均衡（奇 2~3、大 2~3）。"""
    front = set(front)
    pool = list(range(fmin, fmax + 1))
    for _ in range(30):
        odd = sum(1 for x in front if x % 2 == 1)
        big = sum(1 for x in front if x >= boundary)
        if odd in (2, 3) and big in (2, 3):
            break
        cand = list(front)
        rng.shuffle(cand)
        swapped = False
        if odd > 3 or odd < 2:
            for rm in cand:
                opp = [x for x in pool if x not in front and (x % 2) != (rm % 2)]
                if opp:
                    front.discard(rm)
                    front.add(rng.choice(opp))
                    swapped = True
                    break
        elif big > 3 or big < 2:
            for rm in cand:
                opp = [x for x in pool if x not in front and (x >= boundary) != (rm >= boundary)]
                if opp:
                    front.discard(rm)
                    front.add(rng.choice(opp))
                    swapped = True
                    break
        if not swapped:
            break
    return sorted(front)


def _weighted_back(analysis: dict[str, Any], rng: random.Random) -> list[int]:
    bmin, bmax = analysis["back_min"], analysis["back_max"]
    bbase = _norm(analysis["back_freq"])
    brec = _norm(analysis["back_recent_freq"])
    w = {k: 0.5 * bbase.get(k, 0) + 0.5 * brec.get(k, 0) for k in range(bmin, bmax + 1)}
    return sorted(_weighted_unique(list(range(bmin, bmax + 1)), w, 2, rng))


def _strategy_balanced(analysis: dict[str, Any], cfg: dict[str, Any], rng: random.Random) -> dict[str, Any]:
    """A 均衡统计型：热号+冷号混合，强制奇偶/大小平衡。"""
    fmin, fmax = analysis["front_min"], analysis["front_max"]
    hot = [k for k, _ in analysis["front_hot"]]
    cold = [k for k, _ in analysis["front_cold"]]
    fbase = _norm(analysis["front_freq"])
    frec = _norm(analysis["front_recent_freq"])
    w = {k: 0.5 * fbase.get(k, 0) + 0.5 * frec.get(k, 0) for k in range(fmin, fmax + 1)}
    front: set[int] = set()
    if hot:
        front |= set(rng.sample(hot, min(2, len(hot))))
    if cold:
        front |= set(rng.sample(cold, min(2, len(cold))))
    while len(front) < 5:
        front |= _weighted_unique(list(range(fmin, fmax + 1)), w, 1, rng)
    front = _balance(front, fmin, fmax, rng)
    return {"front": front, "back": _weighted_back(analysis, rng)}


def _strategy_hotcold(analysis: dict[str, Any], cfg: dict[str, Any], rng: random.Random) -> dict[str, Any]:
    """B 冷热组合型：前区约 60% 热号 + 40% 冷号。"""
    fmin, fmax = analysis["front_min"], analysis["front_max"]
    hot = [k for k, _ in analysis["front_hot"]]
    cold = [k for k, _ in analysis["front_cold"]]
    front: set[int] = set()
    if hot:
        front |= set(rng.sample(hot, min(3, len(hot))))
    if cold:
        front |= set(rng.sample(cold, min(2, len(cold))))
    while len(front) < 5:
        front.add(rng.choice(list(range(fmin, fmax + 1))))
    return {"front": sorted(front), "back": _weighted_back(analysis, rng)}


def _strategy_random(analysis: dict[str, Any], cfg: dict[str, Any], rng: random.Random) -> dict[str, Any]:
    """C 纯随机娱乐型：合法规则下纯随机生成。"""
    fmin, fmax = analysis["front_min"], analysis["front_max"]
    bmin, bmax = analysis["back_min"], analysis["back_max"]
    return {
        "front": sorted(rng.sample(range(fmin, fmax + 1), 5)),
        "back": sorted(rng.sample(range(bmin, bmax + 1), 2)),
    }


_STRATEGY_FUNCS = {
    "A": _strategy_balanced,
    "B": _strategy_hotcold,
    "C": _strategy_random,
}


def recommend(analysis: dict[str, Any], cfg: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """生成 A/B/C 三策略的娱乐推荐，返回 {策略键: [组合, ...]}。"""
    per = cfg["recommend"].get("combos_per_strategy", 1)
    seed = cfg["recommend"].get("seed")
    rng = random.Random(seed)
    out: dict[str, list[dict[str, Any]]] = {}
    for key in ("A", "B", "C"):
        combos = [_STRATEGY_FUNCS[key](analysis, cfg, rng) for _ in range(per)]
        out[key] = combos
    return out
