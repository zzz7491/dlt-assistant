"""推荐回测闭环（Task 16.5-C-2-Step3）。

比对历史推荐记录（reports/recommendations.json）与真实开奖（data/dlt_history.json），
输出：命中统计 / 中奖理论距离 / 策略维度表现 / D 策略因素有效性。

仅记录「号码重合个数」与「理论接近程度」（娱乐分析用途），
**不判断中奖、不预测中奖**；彩票开奖为独立随机事件。

模块设计：
  backtest(recommendations, issues) -> dict    # 纯函数：核心回测
  run_backtest(rec_path, db_path, out_path)   # 读文件 → backtest → 写 backtest_summary.json
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any

# 命中等级（total_hit = 前区命中 + 后区命中，0-7）
HIT_LEVEL = {0: 0, 1: 1, 2: 1, 3: 2, 4: 2, 5: 3, 6: 3, 7: 4}  # 0=无, 1=低(1-2), 2=中(3-4), 3=高(5-6), 4=极高(7)


def _strategy_group(strategy: str) -> str:
    """策略归组：'A-均衡统计型' → 'A'；无前缀 → 'other'。"""
    if not strategy:
        return "other"
    head = str(strategy).split("-")[0].strip().upper()
    return head if head in ("A", "B", "C", "D") else "other"


def _per_period(r: dict[str, Any], real: dict[str, Any]) -> dict[str, Any]:
    """单条推荐 → 命中/距离记录（保留 D 策略可选字段供因素分析）。"""
    front_hit = len(set(r.get("front") or []) & set(real.get("front") or []))
    back_hit = len(set(r.get("back") or []) & set(real.get("back") or []))
    total_hit = front_hit + back_hit
    prize1 = (5 - front_hit) + (2 - back_hit)                 # 一等奖理论距离
    prize2 = (5 - front_hit) + max(0, 1 - back_hit)           # 二等奖（5+1）理论距离
    prize3 = 5 - front_hit                                    # 三等奖（5+0）理论距离
    rec: dict[str, Any] = {
        "issue": r.get("target_issue"),
        "strategy": r.get("strategy", ""),
        "front_hit": front_hit,
        "back_hit": back_hit,
        "total_hit": total_hit,
        "hit_level": HIT_LEVEL.get(total_hit, 0),
        "distance_score": prize1,
        "prize2_distance": prize2,
        "prize3_distance": prize3,
    }
    for k in ("score_total", "factors", "basis", "model_version"):  # D 策略兼容字段透传
        if k in r:
            rec[k] = r[k]
    return rec


def _stats(records: list[dict[str, Any]]) -> dict[str, Any]:
    """策略维度统计。"""
    n = len(records)
    if not n:
        return {"count": 0}
    hits = [r["total_hit"] for r in records]
    front = [r["front_hit"] for r in records]
    back = [r["back_hit"] for r in records]
    level_dist: dict[str, int] = {}
    for r in records:
        key = str(r["hit_level"])
        level_dist[key] = level_dist.get(key, 0) + 1
    front_dist: dict[str, int] = {}
    back_dist: dict[str, int] = {}
    for f in front:
        front_dist[str(f)] = front_dist.get(str(f), 0) + 1
    for b in back:
        back_dist[str(b)] = back_dist.get(str(b), 0) + 1
    return {
        "count": n,
        "avg_front_hit": round(sum(front) / n, 3),
        "avg_back_hit": round(sum(back) / n, 3),
        "avg_total_hit": round(sum(hits) / n, 3),
        "max_total_hit": max(hits),
        "avg_distance_score": round(sum(r["distance_score"] for r in records) / n, 2),
        "hit_level_dist": level_dist,
        "front_hit_dist": front_dist,
        "back_hit_dist": back_dist,
    }


def _factor_analysis_d(d_records: list[dict[str, Any]]) -> dict[str, Any]:
    """D 策略因素有效性基础分析：按 score_total 中位数分高/低组，对比平均命中。

    用于后续（C-4）判断评分是否有效、哪些因素贡献最大；本阶段仅输出分组对比基线。
    """
    if not d_records:
        return {}
    scores = [r.get("score_total") for r in d_records if isinstance(r.get("score_total"), (int, float))]
    scored = [r for r in d_records if isinstance(r.get("score_total"), (int, float))]
    if not scored:
        return {"count": len(d_records), "note": "D 记录无 score_total，无法分组"}
    scores_sorted = sorted(scores)
    median = scores_sorted[len(scores_sorted) // 2]
    high = [r for r in scored if r["score_total"] >= median]
    low = [r for r in scored if r["score_total"] < median]

    def grp(rows: list[dict[str, Any]]) -> dict[str, Any]:
        if not rows:
            return {"count": 0}
        return {
            "count": len(rows),
            "avg_front_hit": round(sum(r["front_hit"] for r in rows) / len(rows), 3),
            "avg_back_hit": round(sum(r["back_hit"] for r in rows) / len(rows), 3),
            "avg_total_hit": round(sum(r["total_hit"] for r in rows) / len(rows), 3),
        }

    return {
        "count": len(d_records),
        "median_score": median,
        "high_score": grp(high),
        "low_score": grp(low),
        "note": "高/低评分组平均命中对比（娱乐参考），用于后续评估评分有效性",
    }


def backtest(recommendations: list[dict[str, Any]], issues: list[dict[str, Any]]) -> dict[str, Any]:
    """核心回测（纯函数）：比对推荐记录与真实开奖。

    输入：recommendations.json 记录列表；dlt_history 的 issues 列表。
    输出：backtest_summary 结构（见 run_backtest 落盘 schema）。
    容错：无推荐 → 空结构；target_issue 无对应开奖 → 跳过；缺字段 → 跳过该条。
    """
    real_map = {it.get("issue"): it for it in issues if it.get("issue")}
    records: list[dict[str, Any]] = []
    for r in recommendations:
        issue = r.get("target_issue")
        if not issue or not isinstance(r.get("front"), list) or not isinstance(r.get("back"), list):
            continue  # 缺字段，跳过
        real = real_map.get(str(issue))
        if real is None:
            continue  # 该目标期号尚未开奖，跳过
        records.append(_per_period(r, real))

    strategies: dict[str, dict[str, Any]] = {}
    by_group: dict[str, list[dict[str, Any]]] = {}
    for rec in records:
        g = _strategy_group(rec["strategy"])
        by_group.setdefault(g, []).append(rec)
    for g in ("A", "B", "C", "D"):
        strategies[g] = _stats(by_group.get(g, []))

    d_records = [rec for rec in records if _strategy_group(rec["strategy"]) == "D"]

    validated_issues = sorted({rec["issue"] for rec in records})

    quality = {
        "total_groups": len(records),
        "validated_periods": len(validated_issues),
        "avg_front_hit": round(sum(r["front_hit"] for r in records) / len(records), 3) if records else 0,
        "avg_back_hit": round(sum(r["back_hit"] for r in records) / len(records), 3) if records else 0,
        "avg_total_hit": round(sum(r["total_hit"] for r in records) / len(records), 3) if records else 0,
    }
    if records:
        best = max(records, key=lambda r: (r["total_hit"], -r["distance_score"]))
        quality["best"] = {
            "issue": best["issue"], "strategy": best["strategy"],
            "front_hit": best["front_hit"], "back_hit": best["back_hit"],
            "total_hit": best["total_hit"], "distance_score": best["distance_score"],
        }

    return {
        "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_periods": len(validated_issues),
        "strategies": strategies,
        "factor_analysis": {"D": _factor_analysis_d(d_records)},
        "recommendation_quality": quality,
    }


def run_backtest(rec_path: str, db_path: str, out_path: str) -> dict[str, Any]:
    """读文件 → backtest → 写 reports/backtest_summary.json → 返回 summary。"""
    from .database import load as load_db
    from .recommendations import load as load_recs

    recs = load_recs(rec_path)
    db = load_db(db_path)
    summary = backtest(recs, db.get("issues", []))
    d = os.path.dirname(os.path.abspath(out_path))
    if d:
        os.makedirs(d, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    return summary
