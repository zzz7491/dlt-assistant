"""P3-2 窗口敏感性 & 严格 OOS 评测（research only，不改生产）。

科学目标：回答"历史窗口长度（50/100/300/500/1000/FULL）是否改变统计型
策略 A/B/D 的严格 OOS 表现"。

设计（任务书 STEP 2/4/7）：
  - 固定窗口语义：target t 之前 issues[:t]；rolling W 取最后 W；FULL 为 expanding
    （t 之前全部）。target/未来绝不进入窗口。
  - A/B/C/D 全部调用真实生产 recommend()（不复制"类似版"）。
  - 优化：per-(t,window) 预计算 analysis/stats + 并行化 D 枚举（10 核）；
    结果必须与直接生产函数一致（equivalence test，>=20 targets × 多窗口）。
  - FULL 在 t 之前历史不足 1000 期时与 rolling 1000 相同（min(n, window) 语义），如实记录。
"""
from __future__ import annotations

import json
from typing import Any

from ..analyzer import (analyze, analyze_previous_overlap, analyze_number_temperature,
                        analyze_missing_cycle, analyze_structure_distribution, analyze_sum_span)
from ..recommender import recommend

WINDOWS = ["50", "100", "300", "500", "1000", "FULL"]
COMMON_WARMUP = 1000
DEV_RATIO = 0.80
RANDOM_SEEDS = 50
BOOTSTRAP_N = 10000
BOOTSTRAP_SEED = 20260930

_CFG: dict | None = None
_ISSUES: list[dict] | None = None


def production_cfg() -> dict:
    global _CFG
    if _CFG is None:
        _CFG = {
            "analysis": {"front_min": 1, "front_max": 35, "back_min": 1, "back_max": 12,
                         "front_zones": 5, "back_zones": 2, "recent_window": 50},
            "recommend": {
                "combos_per_strategy": 1, "seed": BOOTSTRAP_SEED,
                "weights": {
                    "number": {"heat": 0.30, "missing": 0.30, "trend": 0.25, "inherit": 0.15},
                    "combo": {"inherit_match": 0.20, "odd_even_match": 0.20,
                              "big_small_match": 0.20, "zone_match": 0.20, "sum_span_match": 0.20},
                    "single_vs_combo": {"single": 0.7, "combo": 0.3},
                    "top_front": 15, "top_back": 8,
                },
            },
        }
    return _CFG


def load_issues(path: str) -> list[dict]:
    global _ISSUES
    data = json.loads(open(path, encoding="utf-8").read())
    _ISSUES = data.get("issues", data)
    _ISSUES.sort(key=lambda x: str(x["issue"]))
    return _ISSUES


def evidence_for(t_idx: int, window: str) -> list[dict]:
    """target t_idx 之前的证据（严格 < t）。rolling W 取最后 W；FULL 取全部。"""
    ev = _ISSUES[:t_idx]
    if window != "FULL":
        ev = ev[-int(window):]
    return ev


def _stats(evidence: list[dict], prev: dict) -> dict:
    return {
        "overlap": analyze_previous_overlap(evidence),
        "temperature": analyze_number_temperature(evidence),
        "missing_cycle": analyze_missing_cycle(evidence),
        "structure": analyze_structure_distribution(evidence),
        "sum_span": analyze_sum_span(evidence),
        "prev_issue": prev,
    }


def compute_candidates(t_idx: int, window: str, cfg: dict) -> dict[str, dict]:
    """真实生产 recommend()：A/B/C(/D)。返回 {strategy: {front, back}}。

    D 仅在提供 stats 时生成；A/B/C 不依赖 stats。全部走生产函数，不改公式。
    """
    global _ISSUES
    ev = evidence_for(t_idx, window)
    analysis = analyze(ev, cfg)
    out: dict[str, dict] = {}
    abc = recommend(analysis, cfg, stats=None)
    for k in ("A", "B", "C"):
        if k in abc:
            c = abc[k][0]
            out[k] = {"front": list(c["front"]), "back": list(c["back"])}
    d = recommend(analysis, cfg, stats=_stats(ev, _ISSUES[t_idx - 1]))
    if "D" in d:
        c = d["D"][0]
        out["D"] = {"front": list(c["front"]), "back": list(c["back"])}
    return out


# ---------------------------------------------------------------- parallel worker

def _init_worker(issues: list[dict]):
    global _ISSUES
    _ISSUES = issues


def _worker(task):
    t_idx, window = task
    global _ISSUES
    return (t_idx, window), compute_candidates(t_idx, window, production_cfg())


def run_matrix(t_idxs: list[int], windows: list[str], workers: int = 10) -> dict[tuple, dict]:
    """并行计算全部 (t, window) → candidates。D 枚举为瓶颈，多核加速；结果与串行一致。"""
    from multiprocessing import Pool
    tasks = [(t, w) for t in t_idxs for w in windows]
    out: dict[tuple, dict] = {}
    with Pool(processes=workers, initializer=_init_worker, initargs=(_ISSUES,)) as pool:
        for _key, cands in pool.imap_unordered(_worker, tasks, chunksize=8):
            out[_key] = cands
    return out


def hits_of(combo: dict, target: dict) -> tuple[int, int, int]:
    fh = len(set(combo["front"]) & set(target["front"]))
    bh = len(set(combo["back"]) & set(target["back"]))
    return fh, bh, fh + bh
