#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成实验展示层所需的 public/data/*.json（Phase 15 + Phase 16 Step 5）。

数据来源：reports/*.json（由 experiment 实验层产出，非生产推荐链路）。
输出：public/data/*.json（前端只读静态 fallback，不修改生产 recommendations.json）。

设计原则（Phase 16 Step 5 改造）：
- 只做「复制 + 裁剪冗余字段（如 900 长度 cumulative_profit_series）」，不编造任何数字。
- 所有展示数据必须能从 reports 追溯；不引入新结论。
- 不修改 scorer/recommender/scheduler/publisher；不修改生产 recommendations.json。
- 【容错】若某个 source 报告不存在：不报致命错误、不中断其它文件生成，
  而是为该输出文件写入 {"status": "unavailable", ...}，前端据此显示「暂无数据」。
  单个文件缺失不影响其它文件的正常生成（失败隔离）。
"""
import json
import os
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORTS = os.path.join(ROOT, "reports")
OUT = os.path.join(ROOT, "public", "data")


def load(name):
    """读取 reports/*.json；缺失时返回 None（不抛异常）。"""
    p = os.path.join(REPORTS, name)
    if not os.path.exists(p):
        return None
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def dump(name, obj):
    os.makedirs(OUT, exist_ok=True)
    p = os.path.join(OUT, name)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    print(f"  wrote {p}  ({os.path.getsize(p)} bytes)")


def dump_unavailable(name, missing_source):
    """当 source 报告缺失时，生成 status=unavailable 占位文件（失败隔离）。"""
    os.makedirs(OUT, exist_ok=True)
    p = os.path.join(OUT, name)
    obj = {
        "status": "unavailable",
        "reason": "source report missing",
        "missing": missing_source,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "note": "该展示数据当前不可用（源报告缺失）。娱乐分析，非预测。",
    }
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    print(f"  (unavailable) wrote {p}  [缺失源: {missing_source}]")


def build_if_present(src_name, out_name, transform=None):
    """容错构建单个展示文件：源缺失→写 unavailable；存在→transform 后 dump。

    参数：
        src_name   : reports/ 下的源文件名。
        out_name   : public/data/ 下的输出文件名。
        transform  : 可选，接收 src dict 返回输出 dict；缺省为原样透传。
    """
    src = load(src_name)
    if src is None:
        dump_unavailable(out_name, src_name)
        return
    try:
        out = transform(src) if transform else src
        dump(out_name, out)
    except Exception as e:  # 单文件转换异常隔离
        print(f"  ⚠️ 转换 {src_name} 失败（已隔离）: {type(e).__name__}: {e}")
        dump_unavailable(out_name, src_name)


# ============================================================
# transform 函数（仅裁剪/重组，不编造数字）
# ============================================================

def _trim_diagnostics(src):
    return {
        "generated_at": src.get("generated_at"),
        "data_source": src.get("data_source"),
        "n_bets": src.get("n_bets"),
        "models": src.get("models"),
        "conclusion": src.get("conclusion"),
        "note": src.get("note"),
    }


def _trim_feature_gain(src):
    return {
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


def _trim_reward_stability(src):
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
    return {
        "generated_at": src.get("generated_at"),
        "data_source": src.get("data_source"),
        "window": src.get("window"),
        "models": models,
        "note": "已剔除每期累计收益序列（cumulative_profit_series）以减小体积；"
                "完整序列见 reports/reward_stability_report.json。娱乐分析，非预测。",
    }


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


def _trim_counterfactual(src):
    return {
        "generated_at": src.get("generated_at"),
        "feature_ablation": _trim_cf(src.get("feature_ablation")),
        "strategy_removal": _trim_cf(src.get("strategy_removal")),
        "ensemble_comparison": _trim_cf(src.get("ensemble_comparison")),
        "overall_conclusion": src.get("overall_conclusion"),
        "note": "反事实实验 = 探索性分析，非预测能力提升证据。娱乐分析，非预测。",
    }


def _trim_entertainment(src):
    return {
        "generated_at": src.get("generated_at"),
        "data_source": src.get("data_source"),
        "weights": src.get("weights"),
        "note": src.get("note"),
        "models": src.get("models"),
        "ranking": src.get("ranking"),
        "vs_random": src.get("vs_random"),
    }


def _build_step3_validation(src):
    """稳定性验证：保留 config / validity / aggregate / stability_verdict，并生成紧凑 combos 表。"""
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
    return {
        "generated_at": src.get("generated_at"),
        "data_source": src.get("data_source"),
        "validity": src.get("validity"),
        "config": src.get("config"),
        "note": src.get("note"),
        "aggregate": src.get("aggregate"),
        "stability_verdict": src.get("stability_verdict"),
        "combos": combos,
    }


def main():
    print("生成实验展示层 public/data/*.json（容错模式）...")
    # 每个文件独立构建；源缺失或转换异常均被隔离，不影响其它文件。
    build_if_present("model_ranking.json", "model_ranking.json")
    build_if_present("model_diagnostic_report.json", "phase15_model_diagnostics.json",
                     transform=_trim_diagnostics)
    build_if_present("feature_gain_report.json", "phase15_feature_gain.json",
                     transform=_trim_feature_gain)
    build_if_present("reward_stability_report.json", "phase15_reward_stability.json",
                     transform=_trim_reward_stability)
    build_if_present("counterfactual_analysis.json", "phase15_counterfactual.json",
                     transform=_trim_counterfactual)
    build_if_present("entertainment_evaluation.json", "phase16_entertainment.json",
                     transform=_trim_entertainment)
    build_if_present("phase16_step3_validation.json", "phase16_step3_validation.json",
                     transform=_build_step3_validation)
    # Phase 16 Step 6：运行状态监控 + 数据质量护栏（新增，失败隔离）
    build_if_present("experiment_run_status.json", "experiment_run_status.json")
    build_if_present("experiment_data_quality.json", "experiment_data_quality.json")
    print("完成。所有文件均从 reports/*.json 派生，缺失源将标记为 unavailable，"
          "未修改生产推荐链路。")


if __name__ == "__main__":
    sys.exit(main())
