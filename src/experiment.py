"""历史回测权重实验框架（Task 16.5-C-3-Implement-Step1）。

walk-forward 滚动回测：对每期 t 仅使用 issues[:t]（历史已知）计算 C-1 统计与 D 推荐，
与下一期真实开奖（issues[t]）比对命中/距离，累计各组权重表现。

定位：
- **离线实验模块，不接入生产链路**（scheduler 不引用本模块）；
- 权重经 cfg 注入（不改 settings / scorer / recommender）；
- 结果仅作娱乐分析框架内的权重参考，不构成中奖预测。

模块组成：
  BASE_CFG           G0 基准配置（权重与 settings.yaml 当前默认一致）
  _fast_d_combo()    特征缓存版 D 组合（与生产 _strategy_scored 输出保真，见测试）
  walk_forward()     滚动回测主流程（返回汇总统计）
"""
from __future__ import annotations

import copy
import itertools
import json
import os
from datetime import datetime
from typing import Any

from .analyzer import (
    analyze,
    analyze_previous_overlap,
    analyze_number_temperature,
    analyze_missing_cycle,
    analyze_structure_distribution,
)
from .recommender import recommend
from .scorer import calculate_number_score, calculate_combination_score, normalize_score

# G0 基准权重（与 config/settings.yaml recommend.weights 当前默认一致）
G0_WEIGHTS: dict[str, Any] = {
    "number": {"heat": 0.30, "missing": 0.30, "trend": 0.25, "inherit": 0.15},
    "combo": {"inherit_match": 0.20, "odd_even_match": 0.20, "big_small_match": 0.20,
              "zone_match": 0.20, "sum_span_match": 0.20},
    "single_vs_combo": {"single": 0.7, "combo": 0.3},
    "top_front": 15,
    "top_back": 8,
}

BASE_CFG: dict[str, Any] = {
    "recommend": {
        "combos_per_strategy": 1, "perturb": 0.35, "hot_weight": 0.6,
        "seed": 42, "log_path": "reports/recommendations.json",
        "weights": G0_WEIGHTS,
    },
    "analysis": {"front_min": 1, "front_max": 35, "back_min": 1, "back_max": 12,
                 "front_zones": 5, "back_zones": 2, "recent_window": 50},
}

FRONT_MIN, FRONT_MAX, BACK_MIN, BACK_MAX = 1, 35, 1, 12
FRONT_BOUNDARY = 18


def build_stats(hist: list[dict[str, Any]]) -> dict[str, Any]:
    """C-1 四因素统计 + 上一期（仅使用 hist 历史，防未来信息泄漏）。"""
    return {
        "overlap": analyze_previous_overlap(hist),
        "temperature": analyze_number_temperature(hist),
        "missing_cycle": analyze_missing_cycle(hist),
        "structure": analyze_structure_distribution(hist),
        "prev_issue": hist[-1] if hist else None,
    }


def _combo_feature_key(combo: dict[str, list[int]], prev_front_set: set[int],
                       prev_back_set: set[int], zones: int = 5) -> tuple:
    """组合特征键（结构分唯一决定因素）：继承数×2、奇偶、大小、分区分布、和值。

    与 scorer.calculate_combination_score 的因子计算口径一致，保证同键同分。
    """
    front, back = combo["front"], combo["back"]
    kf = len(set(front) & prev_front_set)
    kb = len(set(back) & prev_back_set)
    odd = sum(1 for x in front if x % 2 == 1)
    big = sum(1 for x in front if x >= FRONT_BOUNDARY)
    size = (FRONT_MAX - FRONT_MIN + 1) // zones
    zl = sorted((x - FRONT_MIN) // size for x in front)
    return (kf, kb, odd, big, tuple(zl), sum(front))


def _fast_d_combo(stats: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
    """特征缓存版 D 综合评分组合（单组，Top1）。

    与生产 recommender._strategy_scored 逻辑一致，仅对组合结构分做特征级缓存
    （84k 组合按特征去重后仅数千个唯一特征 → 大幅加速离线实验）。
    保真性由测试断言（与 recommend(stats)["D"][0] 输出一致）。
    """
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
        scored = []
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

    front_top = pool_scores(FRONT_MIN, FRONT_MAX, "front")[:top_front]
    back_top = pool_scores(BACK_MIN, BACK_MAX, "back")[:top_back]
    if not front_top or not back_top:
        return {"front": [], "back": [], "model_version": "C-2-D-v1", "score_total": 0.0,
                "factors": {}, "basis": {}}

    fnums = [s["number"] for s in front_top]
    bnums = [s["number"] for s in back_top]
    fmap = {s["number"]: s["score_total"] for s in front_top}
    bmap = {s["number"]: s["score_total"] for s in back_top}
    ffactors = {s["number"]: s["factors"] for s in front_top}
    bfactors = {s["number"]: s["factors"] for s in back_top}

    cache: dict[tuple, tuple] = {}  # 特征键 -> (score_total, factors)

    def structure_score(combo: dict[str, list[int]]) -> tuple[float, dict[str, Any]]:
        key = _combo_feature_key(combo, prev_front_set, prev_back_set)
        if key not in cache:
            r = calculate_combination_score(
                combo, overlap, structure, None, prev_front, prev_back, weights=combo_w)
            cache[key] = (r["score_total"], r["factors"])
        return cache[key]

    scored_combos: list[tuple[float, dict[str, Any], dict[str, Any]]] = []
    for fc in itertools.combinations(fnums, 5):
        for bc in itertools.combinations(bnums, 2):
            combo = {"front": list(fc), "back": list(bc)}
            cs_struct, cs_factors = structure_score(combo)
            avg_single = (sum(fmap[n] for n in fc) + sum(bmap[n] for n in bc)) / 7.0
            total = normalize_score(w_single * avg_single + w_combo * cs_struct)
            scored_combos.append((total, combo, cs_factors))

    scored_combos.sort(key=lambda x: (-x[0], x[1]["front"], x[1]["back"]))
    total, combo, cs_factors = scored_combos[0]

    def mean_factor(key: str) -> float:
        vals = [ffactors[n][key] for n in combo["front"]] + [bfactors[n][key] for n in combo["back"]]
        return round(sum(vals) / len(vals), 2) if vals else 0.0

    return {
        "front": combo["front"],
        "back": combo["back"],
        "model_version": "C-2-D-v1",
        "score_total": total,
        "factors": cs_factors,
        "basis": {
            "heat": mean_factor("heat"),
            "missing": mean_factor("missing"),
            "trend": mean_factor("trend"),
            "inherit": mean_factor("inherit"),
            "structure": cs_factors,
        },
    }


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """滚动回测结果汇总。"""
    n = len(rows)
    if not n:
        return {"n": 0, "avg_front_hit": 0.0, "avg_back_hit": 0.0, "avg_total_hit": 0.0,
                "avg_distance": 0.0, "hit_total_dist": {},
                "vs_random": {"front": round(5 / 35, 4), "back": round(2 / 12, 4),
                              "total": round(5 / 35 + 2 / 12, 4)}}
    dist: dict[str, int] = {}
    for r in rows:
        key = str(r["total_hit"])
        dist[key] = dist.get(key, 0) + 1
    return {
        "n": n,
        "avg_front_hit": round(sum(r["front_hit"] for r in rows) / n, 4),
        "avg_back_hit": round(sum(r["back_hit"] for r in rows) / n, 4),
        "avg_total_hit": round(sum(r["total_hit"] for r in rows) / n, 4),
        "avg_distance": round(sum(r["distance"] for r in rows) / n, 2),
        "hit_total_dist": dist,
        "vs_random": {
            "front": round(5 / 35, 4),
            "back": round(2 / 12, 4),
            "total": round(5 / 35 + 2 / 12, 4),
        },
    }


def walk_forward(issues: list[dict[str, Any]], cfg: dict[str, Any] | None = None,
                 preheat: int = 200, start: int | None = None, end: int | None = None,
                 use_fast: bool = True, verbose: bool = False) -> dict[str, Any]:
    """walk-forward 滚动回测（G0 基准及后续权重组通用）。

    issues  按期号升序的全量历史开奖；
    cfg     实验配置（权重注入点）；preheat 预热期数（统计窗口下限）；
    start/end 实验期下标范围（默认 [preheat, len-1]）；
    use_fast=True 用特征缓存版（快）；False 用生产 recommend（保真对照，慢）。
    """
    cfg = cfg or BASE_CFG
    issues = sorted(issues, key=lambda x: x["issue"])
    n_issues = len(issues)
    start = preheat if start is None else max(preheat, start)
    end = n_issues - 1 if end is None else min(end, n_issues - 1)
    if start > end:
        return summarize([])

    rows: list[dict[str, Any]] = []
    for t in range(start, end + 1):
        hist = issues[:t]
        stats = build_stats(hist)
        if use_fast:
            combo = _fast_d_combo(stats, cfg)
        else:
            combo = recommend(analyze(hist[-200:], cfg), cfg, stats)["D"][0]
        real = issues[t]
        rf, rb = set(real.get("front") or []), set(real.get("back") or [])
        fh = len(set(combo["front"]) & rf)
        bh = len(set(combo["back"]) & rb)
        rows.append({"issue": real.get("issue"), "front_hit": fh, "back_hit": bh,
                     "total_hit": fh + bh, "distance": (5 - fh) + (2 - bh),
                     "score_total": combo.get("score_total")})
        if verbose and (t - start) % 50 == 0:
            print(f"[experiment] t={t}（{real.get('issue')}）命中 {fh}+{bh}")

    return summarize(rows)


# =========================================================
# C-3-Implement-Step2：G0-G7 权重实验矩阵 + 批量运行
# 仅实验模块，不接入生产链路；权重经 cfg 注入，不写回 settings。
# =========================================================

# 各组对 G0 的覆盖（未列字段继承 G0 默认；inherit 超 15% 由 scorer clamp 兜底）
GRID_OVERRIDES: dict[str, dict[str, Any]] = {
    "G0": {},                                              # 基准（= settings 默认）
    "G1": {"number": {"heat": 0.35, "missing": 0.35, "trend": 0.25, "inherit": 0.05}},  # 继承弱化
    "G2": {"number": {"heat": 0.28, "missing": 0.28, "trend": 0.24, "inherit": 0.20}},  # 继承强化（clamp→0.15）
    "G3": {"number": {"heat": 0.45, "missing": 0.25, "trend": 0.20, "inherit": 0.10}},  # heat 侧重
    "G4": {"number": {"heat": 0.25, "missing": 0.45, "trend": 0.20, "inherit": 0.10}},  # missing 侧重
    "G5": {"number": {"heat": 0.25, "missing": 0.25, "trend": 0.40, "inherit": 0.10}},  # trend 侧重
    "G6": {"single_vs_combo": {"single": 0.5, "combo": 0.5}},                            # combo 侧重
    "G7": {"top_front": 12, "top_back": 6},                                              # 候选池变化
}

_WORKER_ISSUES: list[list[dict[str, Any]] | None] = [None]


def grid_weights(group_id: str) -> dict[str, Any]:
    """按组生成完整 weights（G0 基础上套用覆盖）。"""
    w = copy.deepcopy(G0_WEIGHTS)
    for k, v in GRID_OVERRIDES.get(group_id, {}).items():
        if isinstance(v, dict):
            w[k] = {**(w.get(k) or {}), **v}
        else:
            w[k] = v
    return w


def _worker_init(issues: list[dict[str, Any]]) -> None:
    _WORKER_ISSUES[0] = issues


def _run_grid_one(task: tuple) -> dict[str, Any]:
    """单组任务执行（顶层函数，供 multiprocessing）。"""
    gid, weights, cfg, start, end, preheat, use_fast, verbose = task
    c = copy.deepcopy(cfg)
    c["recommend"]["weights"] = weights
    issues = _WORKER_ISSUES[0]
    if issues is None:
        return {"group_id": gid, "error": "issues 未初始化"}
    s = walk_forward(issues, c, preheat=preheat, start=start, end=end,
                     use_fast=use_fast, verbose=verbose)
    return {
        "group_id": gid,
        "weights": weights,
        "sample_count": s["n"],
        "avg_front_hit": s["avg_front_hit"],
        "avg_back_hit": s["avg_back_hit"],
        "avg_total_hit": s["avg_total_hit"],
        "avg_distance": s["avg_distance"],
        "hit_distribution": s["hit_total_dist"],
        "vs_random": s["vs_random"],
    }


def run_grid(issues: list[dict[str, Any]], cfg: dict[str, Any] | None = None,
             grid_ids: list[str] | None = None, start: int | None = None,
             end: int | None = None, preheat: int = 200, workers: int = 1,
             use_fast: bool = True, verbose: bool = False) -> list[dict[str, Any]]:
    """批量运行 G0-G7 权重网格（walk_forward 复用）。

    workers=1 顺序执行；>1 用 multiprocessing 并行（每 worker 通过 initializer 注入 issues）。
    返回 [{group_id, weights, sample_count, avg_*, hit_distribution, vs_random}]。
    """
    cfg = cfg or BASE_CFG
    ids = grid_ids or list(GRID_OVERRIDES.keys())
    tasks = [(gid, grid_weights(gid), cfg, start, end, preheat, use_fast, verbose) for gid in ids]

    if workers and workers > 1 and len(tasks) > 1:
        from multiprocessing import Pool
        with Pool(workers, initializer=_worker_init, initargs=(issues,)) as pool:
            return pool.map(_run_grid_one, tasks)
    _WORKER_ISSUES[0] = issues
    return [_run_grid_one(t) for t in tasks]


def save_results(rows: list[dict[str, Any]], path: str,
                 preheat: int | None = None, start: int | None = None,
                 end: int | None = None) -> dict[str, Any]:
    """落盘 reports/weight_experiment_results.json（schema 见 run_grid 返回）。"""
    payload = {
        "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "preheat": preheat,
        "start": start,
        "end": end,
        "groups": rows,
    }
    d = os.path.dirname(os.path.abspath(path))
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return payload


# =========================================================
# C-3-Implement-Step3：验证期评估（训练/验证两段对比）
# 严格 walk-forward：训练 t∈[train_start,train_end]，验证 t∈[valid_start,valid_end]，
# 每期仅用 issues[:t]（无未来信息泄漏）。
# =========================================================

DEFAULT_TRAIN = (200, 799)
DEFAULT_VALID = (800, 999)


def _compact(summary: dict[str, Any]) -> dict[str, Any]:
    """汇总精简（去 vs_random，供训练/验证对比）。"""
    return {k: summary[k] for k in ("n", "avg_front_hit", "avg_back_hit", "avg_total_hit",
                                    "avg_distance", "hit_total_dist")}


def _validation_one(task: tuple) -> dict[str, Any]:
    """单组训练-验证任务（顶层函数，供 multiprocessing）。"""
    gid, weights, c, pre, (ts, te), (vs, ve), uf, vb = task
    cc = copy.deepcopy(c)
    cc["recommend"]["weights"] = weights
    issues = _WORKER_ISSUES[0]
    tr = walk_forward(issues, cc, preheat=pre, start=ts, end=te, use_fast=uf, verbose=vb)
    va = walk_forward(issues, cc, preheat=pre, start=vs, end=ve, use_fast=uf, verbose=vb)
    se = (va["avg_total_hit"] / va["n"]) ** 0.5 if va["n"] else 0.0
    return {
        "group_id": gid,
        "weights": weights,
        "train": _compact(tr),
        "validation": _compact(va),
        "delta": {
            "avg_total_hit": round(va["avg_total_hit"] - tr["avg_total_hit"], 4),
            "avg_front_hit": round(va["avg_front_hit"] - tr["avg_front_hit"], 4),
            "avg_back_hit": round(va["avg_back_hit"] - tr["avg_back_hit"], 4),
            "avg_distance": round(va["avg_distance"] - tr["avg_distance"], 2),
        },
        "vs_random": va["vs_random"],
        "poisson_se": round(se, 4),
    }


def run_validation(issues: list[dict[str, Any]], cfg: dict[str, Any] | None = None,
                   groups: list[str] | None = None, preheat: int = 200,
                   train: tuple[int, int] = DEFAULT_TRAIN,
                   valid: tuple[int, int] = DEFAULT_VALID,
                   workers: int = 1, use_fast: bool = True,
                   verbose: bool = False) -> list[dict[str, Any]]:
    """G0/G5 训练-验证两段评估（walk-forward）。

    返回 [{group_id, weights, train{...}, validation{...}, delta{...}, vs_random, poisson_se}]。
    """
    cfg = cfg or BASE_CFG
    groups = groups or ["G0", "G5"]
    tasks = [(gid, grid_weights(gid), cfg, preheat, train, valid, use_fast, verbose) for gid in groups]

    if workers and workers > 1 and len(tasks) > 1:
        from multiprocessing import Pool
        with Pool(workers, initializer=_worker_init, initargs=(issues,)) as pool:
            return pool.map(_validation_one, tasks)
    _WORKER_ISSUES[0] = issues
    return [_validation_one(t) for t in tasks]


def save_validation_results(rows: list[dict[str, Any]], path: str,
                            preheat: int = 200,
                            train: tuple[int, int] = DEFAULT_TRAIN,
                            valid: tuple[int, int] = DEFAULT_VALID) -> dict[str, Any]:
    """落盘 reports/weight_validation_results.json。"""
    payload = {
        "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "preheat": preheat,
        "train": {"start": train[0], "end": train[1]},
        "validation": {"start": valid[0], "end": valid[1]},
        "groups": rows,
    }
    d = os.path.dirname(os.path.abspath(path))
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return payload
