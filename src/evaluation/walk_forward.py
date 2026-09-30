"""P2-1 严格 walk-forward 评测主引擎。

设计原则：
  - 对于目标期 issues[t]，训练/证据 = 仅 issues[:t]（严格排除目标期与未来）。
  - 生产 A/B/C/D 通过调用 recommender.recommend() 原函数复用（不复制算法）。
  - Selector 通过 final_score.compute_final_scores() 原函数复用（不复制公式）。
  - 随机基线使用 ≥ 20 个固定 seed，每期每个 seed 独立生成 5+2。
  - 所有评测记录附带 leakage 断言（train_last_issue < target_issue）。

性能：D 策略每期 ~1s（top15×top8 组合遍历），900 期 ≈ 10 min。
"""
from __future__ import annotations

import json
import time
from typing import Any

from ..analyzer import (
    analyze, analyze_previous_overlap, analyze_number_temperature,
    analyze_missing_cycle, analyze_structure_distribution, analyze_sum_span,
)
from ..final_score import compute_final_scores
from ..recommender import recommend
from . import baselines, leakage, metrics, prize

EVALUATION_VERSION = "p21-v1"
DEFAULT_WARMUP = 100
DEFAULT_SEEDS = 25
COST_PER_TICKET = prize.TICKET_COST  # 2.0 RMB


# ---------------------------------------------------------------- 工具

def _hits(recommended: list[int], actual: list[int]) -> int:
    return len(set(recommended) & set(actual))


def _build_evidence(issues: list[dict], t: int, window: int = 1000) -> list[dict]:
    """严格证据切片：issues[:t] 末 window 期。"""
    ev = issues[:t]
    if window and window > 0:
        ev = ev[-window:]
    return ev


def _build_stats(evidence: list[dict], prev_issue_rec: dict) -> dict:
    """构建 D 策略所需的 5 项分析器 + prev_issue。"""
    return {
        "overlap": analyze_previous_overlap(evidence),
        "temperature": analyze_number_temperature(evidence),
        "missing_cycle": analyze_missing_cycle(evidence),
        "structure": analyze_structure_distribution(evidence),
        "sum_span": analyze_sum_span(evidence),
        "prev_issue": prev_issue_rec,
    }


def _make_cfg(seed: int | None) -> dict:
    """构造生产配置最小集（A/B/C/D 所需）。"""
    return {
        "analysis": {
            "front_min": 1, "front_max": 35,
            "back_min": 1, "back_max": 12,
            "front_zones": 5, "back_zones": 2,
            "recent_window": 50,
        },
        "recommend": {
            "combos_per_strategy": 1,
            "seed": seed,
            "weights": {
                "number": {"heat": 0.30, "missing": 0.30, "trend": 0.25, "inherit": 0.15},
                "combo": {"inherit_match": 0.20, "odd_even_match": 0.20,
                          "big_small_match": 0.20, "zone_match": 0.20, "sum_span_match": 0.20},
                "single_vs_combo": {"single": 0.7, "combo": 0.3},
                "top_front": 15, "top_back": 8,
            },
        },
    }


def _eval_record(target: dict, train_last: dict, strategy: str,
                 front: list[int], back: list[int],
                 actual_front: list[int], actual_back: list[int],
                 **extra) -> dict:
    fh = _hits(front, actual_front)
    bh = _hits(back, actual_back)
    th = fh + bh
    pb = prize.payout_breakdown(fh, bh)
    rec = leakage.make_eval_record(
        target_issue=target["issue"],
        train_last_issue=train_last["issue"],
        strategy=strategy,
        front=front, back=back,
        actual_front=actual_front, actual_back=actual_back,
        front_hits=fh, back_hits=bh, total_hits=th,
        cost=COST_PER_TICKET,
        payout=pb["known_fixed_payout"],
        roi=pb["roi_lower_bound"],
        evaluation_version=EVALUATION_VERSION,
        **extra,
    )
    rec["prize_tier"] = pb["tier"]
    rec["roi_fully_determinable"] = pb["roi_fully_determinable"]
    return rec


# ---------------------------------------------------------------- 主引擎

def run_walk_forward(
    issues: list[dict[str, Any]],
    warmup: int = DEFAULT_WARMUP,
    random_seed_list: list[int] | None = None,
    eval_count: int | None = None,
    include_d: bool = True,
    include_selector: bool = True,
    verbose: bool = True,
) -> dict[str, Any]:
    """执行严格 walk-forward 评测。

    参数：
      issues           按期号升序排列的完整开奖记录（含 issue, date, front, back）
      warmup           前置热分期数（不计入成绩，仅用于 D 的 stats 初始化）
      random_seed_list 随机基线 seed 列表（默认 1..25）
      eval_count       最多评测期数（None=全部可用期）
      include_d        是否评测 D 策略（耗时最长）
      include_selector 是否评测 selector

    返回：
      {
        meta: {...},
        records: [eval_record, ...],
        metrics: {strategy: {...}},
        random_stats: {...},
        selector_results: {...},
        payout_summary: {...},
        elapsed_sec: float,
      }
    """
    t0 = time.time()
    issues.sort(key=lambda x: str(x["issue"]))
    n = len(issues)
    if n <= warmup + 1:
        raise ValueError(f"need at least warmup+1 = {warmup+1} periods, got {n}")

    if random_seed_list is None:
        random_seed_list = list(range(1, DEFAULT_SEEDS + 1))

    # 评测期下标：warmup .. n-1（最多 eval_count 期）
    eval_indices = list(range(warmup, n))
    if eval_count:
        eval_indices = eval_indices[:eval_count]

    all_records: list[dict] = []
    selector_oos: list[dict] = []  # OOS 累积（供 selector 重建 maps）
    oos_per_strategy: dict[str, list[int]] = {"A": [], "B": [], "C": [], "D": []}
    oos_recent: dict[str, list[int]] = {"A": [], "B": [], "C": [], "D": []}
    strategy_status: dict[str, str] = {}

    # 预构建 A/B/C 固定 cfg（seed=None → 每期独立）
    cfg_base = _make_cfg(None)

    for i, t in enumerate(eval_indices):
        target = issues[t]
        train_last = issues[t - 1]
        actual_front = target["front"]
        actual_back = target["back"]

        evidence = _build_evidence(issues, t)
        leakage.assert_no_future_data(evidence, target["issue"], label=f"evidence@t={t}")

        # --- A/B/C ---
        analysis = analyze(evidence, cfg_base)
        combos_abc = recommend(analysis, cfg_base, stats=None)
        for key in ("A", "B", "C"):
            if key in combos_abc:
                c = combos_abc[key][0]
                rec = _eval_record(target, train_last, key,
                                   c["front"], c["back"], actual_front, actual_back)
                all_records.append(rec)
                oos_per_strategy[key].append(rec["total_hits"])
                oos_recent[key].append(rec["total_hits"])
                if len(oos_recent[key]) > 50:
                    oos_recent[key] = oos_recent[key][-50:]

        # --- D (if enabled) ---
        if include_d:
            stats = _build_stats(evidence, issues[t - 1])
            combos_d = recommend(analysis, cfg_base, stats=stats)
            if "D" in combos_d:
                c = combos_d["D"][0]
                rec = _eval_record(target, train_last, "D",
                                   c["front"], c["back"], actual_front, actual_back,
                                   model_version=c.get("model_version"))
                all_records.append(rec)
                oos_per_strategy["D"].append(rec["total_hits"])
                oos_recent["D"].append(rec["total_hits"])
                if len(oos_recent["D"]) > 50:
                    oos_recent["D"] = oos_recent["D"][-50:]

        # --- RANDOM multi-seed ---
        for seed in random_seed_list:
            combo = baselines.random_combo(seed * 100000 + t)
            rec = _eval_record(target, train_last, "RANDOM",
                               combo["front"], combo["back"], actual_front, actual_back,
                               seed=seed)
            all_records.append(rec)

        # --- SIMPLE FREQUENCY ---
        sf = baselines.simple_frequency_combo(evidence, window=100)
        rec = _eval_record(target, train_last, "SIMPLE_FREQ",
                           sf["front"], sf["back"], actual_front, actual_back)
        all_records.append(rec)

        # --- SELECTOR (OOS walk-forward) ---
        if include_selector and i >= 10:  # 至少 10 期 OOS 数据
            try:
                # 重建 selector inputs
                history_map = {}
                for g in ("A", "B", "C", "D"):
                    if oos_per_strategy[g]:
                        history_map[g] = sum(oos_per_strategy[g]) / len(oos_per_strategy[g])
                recent_map = {g: oos_recent[g][-5:] for g in ("A", "B", "C", "D") if oos_recent[g]}

                # strategy_rank：按 OOS avg total_hit 降序
                ranks: dict[str, int] = {}
                for rank_i, g in enumerate(sorted(("A", "B", "C", "D"),
                        key=lambda x: -(sum(oos_per_strategy[x]) / len(oos_per_strategy[x])) if oos_per_strategy[x] else 0)):
                    ranks[g] = rank_i + 1

                # recs: 用本期 A/B/C/D 的 front/back
                sel_recs = []
                for key in ("A", "B", "C", "D"):
                    if key == "D" and not include_d:
                        continue
                    r = next((x for x in all_records if x["strategy"] == key
                              and x["target_issue"] == str(target["issue"])), None)
                    if r:
                        sel_recs.append({
                            "strategy": key,
                            "front": r["front"], "back": r["back"],
                        })

                if len(sel_recs) >= 2:
                    prev_draw = {"front": issues[t - 1]["front"], "back": issues[t - 1]["back"]}
                    scored = compute_final_scores(
                        sel_recs,
                        effective_sample=len(eval_indices) - i - 1 if len(eval_indices) > i + 1 else 0,
                        strategy_rank=ranks,
                        history_map=history_map,
                        recent_map=recent_map,
                        structure_ctx=None,
                        prev_draw=prev_draw,
                        weights=cfg_base["recommend"].get("weights"),
                    )
                    primary = next((s for s in scored if s.get("is_primary")), None)
                    if primary:
                        sr = _eval_record(target, train_last, "SELECTOR",
                                          primary["front"], primary["back"],
                                          actual_front, actual_back,
                                          selector_strategy=primary["strategy"])
                        all_records.append(sr)
            except Exception:
                strategy_status["SELECTOR"] = "PARTIALLY_RECONSTRUCTABLE"

        if verbose and (i + 1) % 100 == 0:
            print(f"  walk-forward: {i+1}/{len(eval_indices)} periods done "
                  f"({time.time()-t0:.0f}s elapsed)")

    # ----------------------------------------------------------------
    # 聚合
    strat_metrics = metrics.aggregate(all_records)

    # 随机基线多 seed 统计（用 RANDOM 记录按 seed 分组取 total_hit）
    random_by_seed: dict[int, dict] = {}
    for r in all_records:
        if r["strategy"] == "RANDOM":
            s = r.get("seed", 0)
            if s not in random_by_seed:
                random_by_seed[s] = {"front_hits": 0, "back_hits": 0, "total_hits": 0, "n": 0}
            random_by_seed[s]["front_hits"] += r["front_hits"]
            random_by_seed[s]["back_hits"] += r["back_hits"]
            random_by_seed[s]["total_hits"] += r["total_hits"]
            random_by_seed[s]["n"] += 1
    # 取均值
    for s, v in random_by_seed.items():
        v["front_hits"] = round(v["front_hits"] / max(v["n"], 1), 4)
        v["back_hits"] = round(v["back_hits"] / max(v["n"], 1), 4)
        v["total_hits"] = round(v["total_hits"] / max(v["n"], 1), 4)
    random_stats = metrics.random_multi_seed_stats(random_by_seed)

    # 与随机比较
    rand_mean = random_stats["total_hit_mean"]
    rand_std = random_stats["total_hit_std"]
    rand_p05 = random_stats["total_hit_p05"]
    rand_p95 = random_stats["total_hit_p95"]
    comparisons = {}
    for s in ("A", "B", "C", "D", "SIMPLE_FREQ", "SELECTOR"):
        if s in strat_metrics:
            comparisons[s] = metrics.compare_to_random(
                strat_metrics[s], rand_mean, rand_std, rand_p05, rand_p95)

    # 成本/回报汇总（排除 RANDOM 和 SELECTOR 避免重复计数；按策略汇总）
    payout_summary = {}
    for s in ("A", "B", "C", "D", "SIMPLE_FREQ", "SELECTOR", "RANDOM"):
        srecs = [r for r in all_records if r["strategy"] == s]
        if srecs:
            payout_summary[s] = prize.aggregate_payout(srecs)

    result = {
        "meta": {
            "evaluation_version": EVALUATION_VERSION,
            "total_issues": n,
            "earliest_issue": str(issues[0]["issue"]),
            "latest_issue": str(issues[-1]["issue"]),
            "warmup": warmup,
            "evaluated_periods": len(eval_indices),
            "random_seeds": len(random_seed_list),
            "include_d": include_d,
            "include_selector": include_selector,
            "cost_per_ticket": COST_PER_TICKET,
            "strategy_status": strategy_status,
        },
        "metrics": strat_metrics,
        "random_stats": random_stats,
        "comparisons": comparisons,
        "payout_summary": payout_summary,
        "records": all_records,
        "elapsed_sec": round(time.time() - t0, 1),
    }
    return result


# ---------------------------------------------------------------- runner

def run_and_report(history_path: str = "public/data/dlt_history.json",
                   out_dir: str = "reports/evaluation",
                   warmup: int = DEFAULT_WARMUP,
                   random_seeds: int = DEFAULT_SEEDS,
                   eval_count: int | None = None,
                   include_d: bool = True,
                   include_selector: bool = True) -> dict[str, Any]:
    """一站式：读数据 → run → 写 JSON + 报告。"""
    import pathlib
    issues = json.loads(pathlib.Path(history_path).read_text())
    if isinstance(issues, dict):
        issues = issues.get("issues", [])
    seed_list = list(range(1, random_seeds + 1))

    print(f"[P2-1] Running walk-forward: {len(issues)} periods, warmup={warmup}, "
          f"seeds={len(seed_list)}, D={'on' if include_d else 'off'}, "
          f"selector={'on' if include_selector else 'off'}")
    result = run_walk_forward(issues, warmup=warmup,
                              random_seed_list=seed_list,
                              eval_count=eval_count,
                              include_d=include_d,
                              include_selector=include_selector)

    out_dir_p = pathlib.Path(out_dir)
    out_dir_p.mkdir(parents=True, exist_ok=True)
    # 去掉 records 写 JSON（太大时只写摘要）
    json_out = dict(result)
    json_out["records_sample"] = result["records"][:10]
    json_out.pop("records", None)
    (out_dir_p / "p21-baseline.json").write_text(
        json.dumps(json_out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[P2-1] JSON → {out_dir_p / 'p21-baseline.json'} "
          f"({result['elapsed_sec']}s)")
    return result
