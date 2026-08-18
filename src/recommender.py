"""娱乐推荐算法：三种策略（仅娱乐，不预测中奖）。

策略 A 均衡统计型：热号 + 冷号混合抽样，并强制奇偶平衡与大小平衡。
策略 B 冷热组合型：前区约 60% 热号 + 40% 冷号。
策略 C 纯随机娱乐型：合法规则下纯随机生成。

重要：本模块仅基于历史统计做娱乐性组合，绝不声称可以预测中奖。
"""
from __future__ import annotations

import itertools
import random
from typing import Any

# 策略标识 -> 中文标签（供报告与推荐记录使用）
STRATEGY_LABELS: dict[str, str] = {
    "A": "均衡统计型",
    "B": "冷热组合型",
    "C": "纯随机娱乐型",
    "D": "综合评分型",
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


def _strategy_scored(analysis: dict[str, Any], cfg: dict[str, Any], rng: random.Random,
                     stats: dict[str, Any] | None = None) -> dict[str, Any]:
    """D 综合评分型（C-2-Step2）：C-1 四因素统计 + scorer 双层评分，遍历组合取 Top1。

    流程：单号层评分（前区 Top15 / 后区 Top8）→ itertools 组合遍历 →
          calculate_combination_score（结构分）→ 综合分 = single×单号均分 + combo×结构分 → 排序取 Top。

    仅依赖 scorer 与 stats（C-1 统计输出 + prev_issue）；A/B/C 策略零影响。
    权重全部来自 config settings.yaml（recommend.weights），inherit 硬上限 15%（scorer clamp 双保险）。
    返回：{"front", "back", "model_version", "score_total", "factors", "basis"}。
    """
    from .scorer import calculate_number_score, calculate_combination_score, normalize_score

    w_cfg = (cfg.get("recommend") or {}).get("weights") or {}
    num_w = w_cfg.get("number")
    combo_w = w_cfg.get("combo")
    svc = w_cfg.get("single_vs_combo") or {}
    w_single = float(svc.get("single", 0.7))
    w_combo = float(svc.get("combo", 0.3))
    top_front = int(w_cfg.get("top_front", 15))
    top_back = int(w_cfg.get("top_back", 8))

    stats = stats or {}
    overlap = stats.get("overlap")
    temperature = stats.get("temperature") or {}
    missing_cycle = stats.get("missing_cycle") or {}
    structure = stats.get("structure")
    prev_issue = stats.get("prev_issue") or {}
    prev_front = prev_issue.get("front")
    prev_back = prev_issue.get("back")
    prev_front_set = set(prev_front or [])
    prev_back_set = set(prev_back or [])

    def pool_scores(pmin: int, pmax: int, kind: str) -> list[dict[str, Any]]:
        scored: list[dict[str, Any]] = []
        for n in range(pmin, pmax + 1):
            s = calculate_number_score(
                n,
                (temperature.get(kind) or {}).get(n, {}),
                (missing_cycle.get(kind) or {}).get(n, {}),
                overlap,
                is_previous=(n in prev_front_set) if kind == "front" else (n in prev_back_set),
                weights=num_w,
            )
            scored.append(s)
        scored.sort(key=lambda x: x["score_total"], reverse=True)
        return scored

    front_top = pool_scores(1, 35, "front")[:top_front]
    back_top = pool_scores(1, 12, "back")[:top_back]
    if not front_top or not back_top:  # 防御：统计缺失时回退纯随机（合法规则内）
        return {"front": sorted(rng.sample(range(1, 36), 5)),
                "back": sorted(rng.sample(range(1, 13), 2))}

    fnums = [s["number"] for s in front_top]
    bnums = [s["number"] for s in back_top]
    fmap = {s["number"]: s["score_total"] for s in front_top}
    bmap = {s["number"]: s["score_total"] for s in back_top}
    ffactors = {s["number"]: s["factors"] for s in front_top}
    bfactors = {s["number"]: s["factors"] for s in back_top}

    scored_combos: list[tuple[float, dict[str, Any], dict[str, Any]]] = []
    for fc in itertools.combinations(fnums, 5):
        for bc in itertools.combinations(bnums, 2):
            combo = {"front": list(fc), "back": list(bc)}
            cs = calculate_combination_score(combo, overlap, structure,
                                             stats.get("sum_span"),
                                             prev_front, prev_back, weights=combo_w)
            avg_single = (sum(fmap[n] for n in fc) + sum(bmap[n] for n in bc)) / 7.0
            total = normalize_score(w_single * avg_single + w_combo * cs["score_total"])
            scored_combos.append((total, combo, cs))

    scored_combos.sort(key=lambda x: (-x[0], x[1]["front"], x[1]["back"]))
    total, combo, cs = scored_combos[0]

    def mean_factor(key: str) -> float:
        vals = [ffactors[n][key] for n in combo["front"]] + [bfactors[n][key] for n in combo["back"]]
        return round(sum(vals) / len(vals), 2) if vals else 0.0

    return {
        "front": combo["front"],
        "back": combo["back"],
        "model_version": "C-2-D-v1",
        "score_total": total,
        "factors": cs["factors"],
        "basis": {
            "heat": mean_factor("heat"),
            "missing": mean_factor("missing"),
            "trend": mean_factor("trend"),
            "inherit": mean_factor("inherit"),
            "structure": cs["factors"],
        },
    }


_STRATEGY_FUNCS = {
    "A": _strategy_balanced,
    "B": _strategy_hotcold,
    "C": _strategy_random,
    "D": _strategy_scored,
}


def recommend(analysis: dict[str, Any], cfg: dict[str, Any],
              stats: dict[str, Any] | None = None) -> dict[str, list[dict[str, Any]]]:
    """生成 A/B/C(/D) 策略的娱乐推荐，返回 {策略键: [组合, ...]}。

    stats（C-1 四因素统计 + prev_issue）非空时追加 D 综合评分策略；
    为 None 时行为与旧版完全一致（A/B/C），向后兼容。
    """
    per = cfg["recommend"].get("combos_per_strategy", 1)
    seed = cfg["recommend"].get("seed")
    rng = random.Random(seed)
    out: dict[str, list[dict[str, Any]]] = {}
    for key in ("A", "B", "C"):
        combos = [_STRATEGY_FUNCS[key](analysis, cfg, rng) for _ in range(per)]
        out[key] = combos
    if stats is not None:
        out["D"] = [_STRATEGY_FUNCS["D"](analysis, cfg, rng, stats) for _ in range(per)]
    return out
