"""推荐开奖复盘与因素贡献分析（Task 16.5-C-2-Step4）。

开奖后分析推荐质量：单期复盘 + 因素有效性三态 + 累计统计 + 策略排行 + 结论摘要。
**仅分析，不调整权重**；不判断中奖、不预测中奖；彩票开奖为独立随机事件。

模块设计：
  reflect(recommendations, issues, backtest_summary=None) -> dict   # 纯函数
  run_reflect(rec_path, db_path, bt_path, out_path) -> dict         # 读文件 → 写 reflection_report.json

单期输出 schema：
  {issue, strategy, recommend{front,back,score_total}, actual{front,back},
   result{front_hit,back_hit,total_hit,distance_score},
   factor_review{inherit,heat,missing,trend,structure → {value,median,status}}}

因素三态判定（D 策略 basis 因子值 vs 累计中位数）：
  positive  因子值 ≥ 中位数（高指向）且本期命中
  neutral   因子值 ≥ 中位数（方向判断合理）但本期未命中
  negative  因子值 < 中位数（未重点指向 / 方向偏差）
累计 factor_performance：{times, positive, neutral, negative, score=positive/times}
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any

from .backtest import _strategy_group, HIT_LEVEL

FACTOR_KEYS = ("inherit", "heat", "missing", "trend", "structure")

# 摘要结论规则阈值（仅分析输出，不参与任何权重调整）
SCORE_OK = 0.30
SCORE_WEAK = 0.15


def _structure_value(basis: dict[str, Any]) -> float | None:
    """structure 因子值：basis.structure 为 dict 时取各值均值，数值则直接用。"""
    st = basis.get("structure") if isinstance(basis, dict) else None
    if isinstance(st, dict):
        vals = [v for v in st.values() if isinstance(v, (int, float))]
        return sum(vals) / len(vals) if vals else None
    if isinstance(st, (int, float)):
        return st
    return None


def _factor_value(basis: dict[str, Any], f: str) -> float | None:
    if f == "structure":
        return _structure_value(basis)
    v = basis.get(f) if isinstance(basis, dict) else None
    return v if isinstance(v, (int, float)) else None


def _factor_review(rec: dict[str, Any], median_map: dict[str, float]) -> dict[str, Any]:
    """单期 D 记录因素三态。median_map 缺失时以该值自身为中位（单条数据退化为 positive/neutral）。"""
    basis = rec.get("basis") or {}
    review: dict[str, Any] = {}
    for f in FACTOR_KEYS:
        v = _factor_value(basis, f)
        if v is None:
            continue  # 缺因素字段，跳过
        med = median_map.get(f, v)
        if v >= med:
            status = "positive" if rec["total_hit"] > 0 else "neutral"
        else:
            status = "negative"
        review[f] = {"value": round(v, 2), "median": round(med, 2), "status": status}
    return review


def _build_conclusions(fp: dict[str, Any]) -> tuple[list[str], list[str]]:
    """基于累计因素统计生成结论与后续观察点（规则化，不调权重）。"""
    conclusion: list[str] = []
    next_points: list[str] = []
    for f in FACTOR_KEYS:
        t = fp[f]["times"]
        s = fp[f]["score"]
        if t == 0:
            continue
        if t < 3:
            next_points.append(f"{f} 因素数据不足（{t} 期），继续观察")
        elif s >= SCORE_OK:
            conclusion.append(f"{f} 因素表现正常（命中率 {s:.0%}）")
        elif s >= SCORE_WEAK:
            conclusion.append(f"{f} 因素偏弱（命中率 {s:.0%}）")
            next_points.append(f"关注 {f} 因素指向的有效性")
        else:
            conclusion.append(f"{f} 因素有效性不足（命中率 {s:.0%}）")
            next_points.append(f"{f} 因素需重新评估（本阶段仅分析，不调权重）")
    return conclusion, next_points


def reflect(recommendations: list[dict[str, Any]], issues: list[dict[str, Any]],
            backtest_summary: dict[str, Any] | None = None) -> dict[str, Any]:
    """核心复盘（纯函数）。输入推荐记录 + 开奖 issues；backtest_summary 可选（仅用于版本备注）。"""
    real_map = {it.get("issue"): it for it in issues if it.get("issue")}

    # 单期记录（内联计算命中/距离，保留原始推荐号码）
    records: list[dict[str, Any]] = []
    for r in recommendations:
        issue = r.get("target_issue")
        front, back = r.get("front"), r.get("back")
        if not issue or not isinstance(front, list) or not isinstance(back, list):
            continue
        real = real_map.get(str(issue))
        if real is None:
            continue
        rf, rb = real.get("front") or [], real.get("back") or []
        front_hit = len(set(front) & set(rf))
        back_hit = len(set(back) & set(rb))
        total_hit = front_hit + back_hit
        records.append({
            "issue": str(issue),
            "strategy": r.get("strategy", ""),
            "front": list(front), "back": list(back),
            "actual_front": list(rf), "actual_back": list(rb),
            "front_hit": front_hit, "back_hit": back_hit,
            "total_hit": total_hit,
            "hit_level": HIT_LEVEL.get(total_hit, 0),
            "distance_score": (5 - front_hit) + (2 - back_hit),
            "score_total": r.get("score_total"),
            "basis": r.get("basis") if isinstance(r.get("basis"), dict) else None,
        })

    # 中位数（仅 D 且有 basis 的记录）
    d_basis = [rec for rec in records if _strategy_group(rec["strategy"]) == "D" and rec["basis"]]
    medians: dict[str, float] = {}
    if d_basis:
        for f in FACTOR_KEYS:
            vals = sorted(v for rec in d_basis if (v := _factor_value(rec["basis"], f)) is not None)
            if vals:
                medians[f] = vals[len(vals) // 2]

    # 单期复盘
    periods: list[dict[str, Any]] = []
    for rec in records:
        periods.append({
            "issue": rec["issue"],
            "strategy": rec["strategy"],
            "recommend": {"front": rec["front"], "back": rec["back"], "score_total": rec["score_total"]},
            "actual": {"front": rec["actual_front"], "back": rec["actual_back"]},
            "result": {"front_hit": rec["front_hit"], "back_hit": rec["back_hit"],
                       "total_hit": rec["total_hit"], "distance_score": rec["distance_score"]},
            "factor_review": _factor_review(rec, medians) if _strategy_group(rec["strategy"]) == "D" else {},
        })

    # 累计因素统计
    fp: dict[str, dict[str, Any]] = {
        f: {"times": 0, "positive": 0, "neutral": 0, "negative": 0, "score": 0.0} for f in FACTOR_KEYS
    }
    for p in periods:
        for f, st in p["factor_review"].items():
            fp[f]["times"] += 1
            fp[f][st["status"]] += 1
    for f in fp:
        fp[f]["score"] = round(fp[f]["positive"] / fp[f]["times"], 3) if fp[f]["times"] else 0.0

    # 策略排行榜
    groups: dict[str, list[dict[str, Any]]] = {g: [] for g in ("A", "B", "C", "D")}
    for p in periods:
        g = _strategy_group(p["strategy"])
        if g in groups:
            groups[g].append(p)
    rank: dict[str, dict[str, Any]] = {}
    for g, rows in groups.items():
        if not rows:
            rank[g] = {"avg_hit": 0, "best_hit": 0, "total_distance": 0, "factor_score": 0.0}
            continue
        rank[g] = {
            "avg_hit": round(sum(r["result"]["total_hit"] for r in rows) / len(rows), 3),
            "best_hit": max(r["result"]["total_hit"] for r in rows),
            "total_distance": sum(r["result"]["distance_score"] for r in rows),
            "factor_score": round(sum(fp[f]["score"] for f in FACTOR_KEYS) / len(FACTOR_KEYS), 3),
        }

    conclusion, next_points = _build_conclusions(fp)
    if not periods:
        conclusion.append("暂无已开奖的推荐记录可供复盘")

    return {
        "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "periods": periods,
        "factor_performance": fp,
        "strategy_rank": rank,
        "conclusion": conclusion,
        "next_review_points": next_points,
    }


def run_reflect(rec_path: str, db_path: str, bt_path: str, out_path: str) -> dict[str, Any]:
    """读 recommendations.json + dlt_history.json（+ backtest_summary.json 可选）→ 写 reflection_report.json。"""
    from .database import load as load_db
    from .recommendations import load as load_recs

    recs = load_recs(rec_path)
    db = load_db(db_path)
    bt_summary = None
    if bt_path and os.path.exists(bt_path):
        try:
            with open(bt_path, "r", encoding="utf-8") as f:
                bt_summary = json.load(f)
        except Exception:
            bt_summary = None
    summary = reflect(recs, db.get("issues", []), bt_summary)
    d = os.path.dirname(os.path.abspath(out_path))
    if d:
        os.makedirs(d, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    return summary
