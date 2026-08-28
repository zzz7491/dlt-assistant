#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成实验展示层所需的 public/data/*.json（Phase 15 + Phase 16）。

数据来源：reports/*.json（由 experiment 实验层产出，非生产推荐链路）。
输出：public/data/*.json（前端只读静态 fallback，不修改生产 recommendations.json）。

设计原则：
- 只做「复制 + 裁剪冗余字段（如 900 长度 cumulative_profit_series）」，不编造任何数字。
- 所有展示数据必须能从 reports 追溯；不引入新结论。
- 不修改 scorer/recommender/scheduler/publisher；不修改生产 recommendations.json。
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORTS = os.path.join(ROOT, "reports")
OUT = os.path.join(ROOT, "public", "data")


def load(name):
    p = os.path.join(REPORTS, name)
    if not os.path.exists(p):
        raise FileNotFoundError(p)
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def dump(name, obj):
    os.makedirs(OUT, exist_ok=True)
    p = os.path.join(OUT, name)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    print(f"  wrote {p}  ({os.path.getsize(p)} bytes)")


def build_model_ranking():
    """模型排行榜（历史回放，全量 900 期）。覆盖 public/data/model_ranking.json 旧的 6 期单测产物。"""
    src = load("model_ranking.json")
    dump("model_ranking.json", src)


def build_diagnostics():
    src = load("model_diagnostic_report.json")
    out = {
        "generated_at": src.get("generated_at"),
        "data_source": src.get("data_source"),
        "n_bets": src.get("n_bets"),
        "models": src.get("models"),
        "conclusion": src.get("conclusion"),
        "note": src.get("note"),
    }
    dump("phase15_model_diagnostics.json", out)


def build_feature_gain():
    src = load("feature_gain_report.json")
    out = {
        "generated_at": src.get("generated_at"),
        "data_source": src.get("data_source"),
        "baseline_model": src.get("baseline_model"),
        "n_bets": src.get("n_bets"),
        "history_quantiles": src.get("history_quantiles"),
        "models": src.get("models"),
        "feature_importance": src.get("feature_importance"),
        "sanity": src.get("sanity"),
        "note": src.get("note"),
    }
    dump("phase15_feature_gain.json", out)


def build_reward_stability():
    src = load("reward_stability_report.json")
    models = {}
    for mv, m in (src.get("models") or {}).items():
        models[mv] = {
            "n_periods": m.get("n_periods"),
            "total_cost": m.get("total_cost"),
            "total_prize": m.get("total_prize"),
            "roi_total": m.get("roi_total"),
            "max_drawdown": m.get("max_drawdown"),
            "longest_consecutive_miss": m.get("longest_consecutive_miss"),
            "avg_win_gap": m.get("avg_win_gap"),
            "rolling_roi_std": m.get("rolling_roi_std"),
            "rolling_winrate_std": m.get("rolling_winrate_std"),
        }
    out = {
        "generated_at": src.get("generated_at"),
        "data_source": src.get("data_source"),
        "window": src.get("window"),
        "models": models,
        "note": "已剔除每期累计收益序列（cumulative_profit_series）以减小体积；完整序列见 reports/reward_stability_report.json。娱乐分析，非预测。",
    }
    dump("phase15_reward_stability.json", out)


def build_counterfactual():
    src = load("counterfactual_analysis.json")
    out = {
        "generated_at": src.get("generated_at"),
        "feature_ablation": _trim_cf(src.get("feature_ablation")),
        "strategy_removal": _trim_cf(src.get("strategy_removal")),
        "ensemble_comparison": _trim_cf(src.get("ensemble_comparison")),
        "overall_conclusion": src.get("overall_conclusion"),
        "note": "反事实实验 = 探索性分析，非预测能力提升证据。娱乐分析，非预测。",
    }
    dump("phase15_counterfactual.json", out)


def _trim_cf(block):
    if not block:
        return block
    return {
        "experiment": block.get("experiment"),
        "generated_at": block.get("generated_at"),
        "config": block.get("config"),
        "baseline": block.get("baseline"),
        "variants": block.get("variants"),
        "comparison": block.get("comparison"),
        "interpretation": block.get("interpretation"),
    }


def build_entertainment():
    src = load("entertainment_evaluation.json")
    out = {
        "generated_at": src.get("generated_at"),
        "data_source": src.get("data_source"),
        "weights": src.get("weights"),
        "note": src.get("note"),
        "models": src.get("models"),
        "ranking": src.get("ranking"),
        "vs_random": src.get("vs_random"),
    }
    dump("phase16_entertainment.json", out)


def build_step3_validation():
    """稳定性验证：保留 config / validity / aggregate / stability_verdict，并生成紧凑 combos 表。"""
    src = load("phase16_step3_validation.json")
    grid = src.get("grid") or {}
    combos = []
    for w in sorted(grid.keys(), key=lambda x: int(x)):
        for s in sorted(grid[w].keys(), key=lambda x: int(x)):
            cell = grid[w][s]
            vs = cell.get("vs_baseline") or {}
            rec = {"window": int(w), "seed": int(s)}
            for v in ("coverage_boost", "diversity_boost", "miss_streak_breaker"):
                vd = vs.get(v, {})
                rec[v] = {
                    "ux_delta_vs_baseline": vd.get("ux_delta_vs_baseline"),
                    "small_win_not_down": vd.get("small_win_not_down"),
                    "passes": vd.get("passes"),
                    "improves_diversity_or_coverage": vd.get("improves_diversity_or_coverage"),
                }
            combos.append(rec)
    out = {
        "generated_at": src.get("generated_at"),
        "data_source": src.get("data_source"),
        "validity": src.get("validity"),
        "config": src.get("config"),
        "note": src.get("note"),
        "aggregate": src.get("aggregate"),
        "stability_verdict": src.get("stability_verdict"),
        "combos": combos,
    }
    dump("phase16_step3_validation.json", out)


def main():
    print("生成实验展示层 public/data/*.json ...")
    build_model_ranking()
    build_diagnostics()
    build_feature_gain()
    build_reward_stability()
    build_counterfactual()
    build_entertainment()
    build_step3_validation()
    print("完成。所有文件均从 reports/*.json 派生，未修改生产推荐链路。")


if __name__ == "__main__":
    sys.exit(main())
