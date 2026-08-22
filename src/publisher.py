"""推荐系统输出层（Phase 11-D1）：将 reports 闭环数据安全发布到 public/data 供前端消费。

职责（纯输出层，不含任何推荐算法 / 策略 / 模型逻辑）：
  1. 扩展 public/data/recommendations.json：保留一期固定号码（D1 锁定值），追加
     score / reason / is_primary / source 加法字段（前端 selectPrimary 已兼容）。
  2. 生成 public/data/review.json：最近一期复盘（来源 reports/reflection_report.json）。
  3. 生成 public/data/strategy_score.json：策略表现统计（来源 reports/backtest_summary.json）。

原则：
  - 失败安全：任一报告缺失/损坏 → 对应输出为空结构，绝不让整个流程失败。
  - 纯加法：不删除现有字段；recommendations.json 保持数组格式（前端 A/B/C/D 折叠依赖）。
  - 零第三方依赖：仅标准库（json/os/datetime/argparse）。

用法：
  python -m src.publisher                 # 默认路径（仓库根目录运行）
  python src/publisher.py                 # 直接运行亦可
  python -m src.publisher --safe          # 任何异常仅打印并 exit 0（CI 接入用）
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from typing import Any

# 策略前缀 → 中文标签（与 src/recommender.py STRATEGY_LABELS 保持一致，避免循环导入）
LABELS: dict[str, str] = {
    "A": "均衡统计型",
    "B": "冷热组合型",
    "C": "纯随机娱乐型",
    "D": "综合评分型",
}

# 命中等级（total_hit = 前区命中 + 后区命中，0-7）——与 src/backtest.py HIT_LEVEL 保持一致
HIT_LEVEL: dict[int, int] = {0: 0, 1: 1, 2: 1, 3: 2, 4: 2, 5: 3, 6: 3, 7: 4}  # 0=无,1=低,2=中,3=高,4=极高


def _load_json(path: str) -> Any:
    """安全读取 JSON：文件不存在/解析失败 → 返回 None（不抛异常）。"""
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _strategy_group(strategy: Any) -> str:
    """'D-综合评分型' → 'D'；无前缀 → 'other'。"""
    if not strategy:
        return "other"
    head = str(strategy).split("-")[0].strip().upper()
    return head if head in ("A", "B", "C", "D") else "other"


def _build_reason(rec: dict[str, Any]) -> str | None:
    """基于 basis 规则生成简短推荐理由（纯规则文案，非 AI、非预测）。无 basis 时返回 None。"""
    basis = rec.get("basis")
    if not isinstance(basis, dict):
        return None
    parts: list[str] = []
    miss = basis.get("missing")
    if isinstance(miss, (int, float)) and miss >= 70:
        parts.append("含超平均遗漏回补信号")
    st = basis.get("structure")
    if isinstance(st, dict):
        ssm = st.get("sum_span_match")
        if isinstance(ssm, (int, float)) and ssm >= 80:
            parts.append("和值/跨度贴合历史高频区间")
        if isinstance(st.get("zone_match"), (int, float)) and st["zone_match"] >= 60:
            parts.append("区间分布贴合历史常态")
    if not parts:
        return None
    return "；".join(parts)


# ---------------------------------------------------------------- ① 推荐扩展

def build_recommendations(current: Any, source_recs: Any) -> list[dict[str, Any]]:
    """扩展当前推荐（一期固定号码源）→ 追加 score/reason/is_primary/source。

    current     public/data/recommendations.json（D1 锁定值，号码权威来源；可为 None/非列表）
    source_recs reports/recommendations.json（完整记录，含 D 的 score_total/basis；可为 None/非列表）
    """
    if not isinstance(current, list):
        return []
    src = source_recs if isinstance(source_recs, list) else []
    # 源记录按键索引：(target_issue, strategy, idx)
    src_map: dict[tuple, dict[str, Any]] = {}
    for r in src:
        if isinstance(r, dict) and r.get("target_issue") is not None:
            src_map[(str(r.get("target_issue")), str(r.get("strategy")), r.get("idx", 0))] = r

    out: list[dict[str, Any]] = []
    for item in current:
        if not isinstance(item, dict):
            continue
        rec = dict(item)  # 拷贝，纯加法不污染输入
        group = _strategy_group(rec.get("strategy"))
        src_rec = src_map.get((str(rec.get("target_issue")), str(rec.get("strategy")), rec.get("idx", 0)))
        if src_rec is None:
            # D1 与 reports 键不完全一致时回退：同 target_issue + 同策略前缀
            for sr in src:
                if (str(sr.get("target_issue")) == str(rec.get("target_issue"))
                        and _strategy_group(sr.get("strategy")) == group
                        and sr.get("idx") == rec.get("idx", 0)):
                    src_rec = sr
                    break
        # score：优先 D 原始 score_total；缺失时为 None（前端 selectPrimary 按 final>score>D 容错）
        st = None
        if src_rec is not None:
            v = src_rec.get("score_total")
            st = round(float(v), 2) if isinstance(v, (int, float)) else None
        rec["score"] = st
        rec["reason"] = _build_reason(src_rec) if src_rec else None
        # is_primary：当前唯一推荐约定 = D 综合评分型（D3 引入 final_score 后再改由评分决定）
        rec["is_primary"] = (group == "D")
        rec["source"] = "reports/recommendations.json"
        out.append(rec)
    return out


# ---------------------------------------------------------------- ② 复盘

# 因子三态 → 调整方向规则（纯规则映射，不修改任何算法/评分）
_FACTOR_ADJUST_RULES: dict[str, tuple[str, str]] = {
    "heat": ("热号关注", "热号因子指向"),
    "missing": ("遗漏补偿关注", "遗漏回补"),
    "trend": ("趋势因子", "趋势判断"),
    "structure": ("结构贴合", "组合结构判断"),
}


def _build_next_adjustment(analysis: dict[str, Any]) -> list[dict[str, Any]]:
    """基于 factor_review 三态 + 和值偏差生成规则化调整建议。

    仅读取复盘数据做规则映射，不调用模型、不修改评分、不影响推荐结果。
    任一数据缺失 → 不产生对应建议；整体无建议 → 返回 []（失败安全）。
    """
    suggestions: list[dict[str, Any]] = []
    fr = (analysis or {}).get("factor_review") or {}
    for key, (text_head, reason_head) in _FACTOR_ADJUST_RULES.items():
        status = (fr.get(key) or {}).get("status")
        if status == "negative":
            suggestions.append({
                "type": "reduce",
                "text": "降低" + text_head + "权重",
                "reason": reason_head + "偏差（相对历史中位数偏低）",
            })
        elif status == "positive":
            suggestions.append({
                "type": "keep",
                "text": "维持" + text_head,
                "reason": reason_head + "正常（方向判断合理）",
            })
        # neutral：方向合理但本期未命中，不产生建议，避免噪音
    sum_diff = (analysis or {}).get("sum_diff")
    if isinstance(sum_diff, (int, float)) and sum_diff > 25:
        suggestions.append({
            "type": "reduce",
            "text": "收缩和值区间",
            "reason": "上期和值偏差较大（差 " + str(sum_diff) + "）",
        })
    elif isinstance(sum_diff, (int, float)) and sum_diff <= 10:
        suggestions.append({
            "type": "keep",
            "text": "维持和值区间",
            "reason": "上期和值贴合历史高频区间",
        })
    return suggestions

def build_review(reflection: Any) -> dict[str, Any]:
    """从 reflection_report.json 提取最近一期复盘 → review.json 结构。

    reflection 含 periods（每期 {issue,strategy,recommend,actual,result,factor_review}）。
    无数据 → 返回空结构（含 updated_at + 空标记）。
    """
    if not isinstance(reflection, dict):
        return {"updated_at": _now(), "empty": True, "issue": None}
    periods = reflection.get("periods")
    if not isinstance(periods, list) or not periods:
        return {"updated_at": _now(), "empty": True, "issue": None}
    # 取 issue 最大（最新）一期；同 issue 取 D 优先（唯一推荐复盘语义）
    p = max(periods, key=lambda x: (str(x.get("issue", "")), _strategy_group(x.get("strategy", "")) == "D"))
    rec = p.get("recommend") or {}
    act = p.get("actual") or {}
    res = p.get("result") or {}
    front = rec.get("front") or []
    actual_front = act.get("front") or []
    sum_diff = abs(sum(front) - sum(actual_front)) if front and actual_front else None
    analysis: dict[str, Any] = {
        "distance_score": res.get("distance_score"),
        "sum_diff": sum_diff,
        "factor_review": p.get("factor_review") or {},
    }
    return {
        "updated_at": _now(),
        "empty": False,
        "issue": p.get("issue"),
        "recommendation": {
            "strategy": p.get("strategy"),
            "front": front,
            "back": rec.get("back") or [],
            "score_total": rec.get("score_total"),
        },
        "actual_result": {
            "front": actual_front,
            "back": act.get("back") or [],
        },
        "hit_count": {
            "front": res.get("front_hit"),
            "back": res.get("back_hit"),
            "total": res.get("total_hit"),
            "level": HIT_LEVEL.get(int(res.get("total_hit") or 0), 0),
        },
        "analysis": analysis,
        "next_adjustment": _build_next_adjustment(analysis),
        "disclaimer": "复盘仅为娱乐回顾，不代表预测中奖",
    }


# ---------------------------------------------------------------- ③ 策略表现

def build_strategy_score(backtest: Any) -> dict[str, Any]:
    """从 backtest_summary.json 生成策略表现榜 → strategy_score.json 结构。

    strategies = {A,B,C,D: {count, avg_total_hit, avg_front_hit, avg_back_hit, ...}}
    无数据 → 空列表（含 updated_at）。
    """
    if not isinstance(backtest, dict):
        return {"updated_at": _now(), "empty": True, "strategies": []}
    strategies = backtest.get("strategies")
    if not isinstance(strategies, dict):
        return {"updated_at": _now(), "empty": True, "strategies": []}

    rows: list[dict[str, Any]] = []
    for key in ("A", "B", "C", "D"):
        s = strategies.get(key)
        if not isinstance(s, dict):
            continue
        count = s.get("count", 0)
        avg_hit = s.get("avg_total_hit", 0.0)
        rows.append({
            "strategy": key,
            "label": LABELS.get(key, key),
            "total_count": count,
            # 命中率 = 平均命中数 / 满分 7（前 5 + 后 2），归一化 0-1（娱乐参考）
            "hit_rate": round(float(avg_hit) / 7.0, 3) if count else 0.0,
            # 样本量不足时 recent_score 等同整体（防小样本误导，D3 起才引入近 10 期窗口）
            "recent_score": round(float(avg_hit), 3) if count else 0.0,
            "rank": 0,  # 下方按 avg_total_hit 降序重排
            "_avg_total_hit": round(float(avg_hit), 3) if count else 0.0,
        })
    rows.sort(key=lambda r: (-r["_avg_total_hit"], r["strategy"]))
    for i, r in enumerate(rows, 1):
        r["rank"] = i
        r.pop("_avg_total_hit", None)
    return {
        "updated_at": _now(),
        "empty": not rows,
        "strategies": rows,
        "disclaimer": "策略权重与排行仅用于展示与娱乐回顾，非预测依据",
    }


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _write_json(path: str, data: Any) -> None:
    d = os.path.dirname(os.path.abspath(path))
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _strip_updated_at(x: Any) -> Any:
    """递归剥离 dict 中的 updated_at 键（幂等比较用）。"""
    if isinstance(x, dict):
        return {k: _strip_updated_at(v) for k, v in x.items() if k != "updated_at"}
    if isinstance(x, list):
        return [_strip_updated_at(i) for i in x]
    return x


def _write_json_if_changed(path: str, data: Any) -> bool:
    """幂等写入：内容（忽略 updated_at）未变时跳过写盘，避免时间戳噪声。

    返回 True=实际写入，False=跳过。现有文件损坏/不可解析 → 视为需写入。
    """
    existing = _load_json(path)
    if existing is not None and _strip_updated_at(existing) == _strip_updated_at(data):
        return False
    _write_json(path, data)
    return True


# ---------------------------------------------------------------- 融合评分接入（D3.2）

def _load_final_score_config(config_path: str = "config/settings.yaml") -> dict[str, float] | None:
    """读取 settings.yaml 的 final_score.weights 配置（方案 B：可选导入+回退）。

    yaml 缺失 / 解析失败 / 段缺失 → 返回 None（调用方使用 final_score.DEFAULT_WEIGHTS）。
    """
    try:
        import yaml  # 第三方可选依赖；CI 环境可用（scheduler 已依赖）
    except Exception:
        return None
    if not config_path or not os.path.exists(config_path):
        return None
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
    except Exception:
        return None
    section = (cfg or {}).get("final_score") or {}
    weights = section.get("weights")
    if not isinstance(weights, dict) or not weights:
        return None
    return {k: float(v) for k, v in weights.items()
            if isinstance(v, (int, float))}


def _recent_map_from_reflection(reflection: Any, window: int = 5) -> dict[str, list[float]]:
    """从 reflection_report.periods 推导各策略最近 N 次 total_hit 列表。

    periods 条目：{issue, strategy, result:{total_hit,...}}（按时间升序）。
    缺失/损坏 → 空 map（融合层自动中性化）。
    """
    out: dict[str, list[float]] = {}
    if not isinstance(reflection, dict):
        return out
    for p in reflection.get("periods") or []:
        if not isinstance(p, dict):
            continue
        g = _strategy_group(p.get("strategy"))
        res = p.get("result") or {}
        hit = res.get("total_hit") if isinstance(res, dict) else None
        if isinstance(hit, (int, float)):
            out.setdefault(g, []).append(float(hit))
    return {g: hits[-window:] for g, hits in out.items() if hits}


def _apply_final_scores(recs: list[dict[str, Any]],
                        backtest: Any,
                        strategy_score: Any,
                        reflection: Any,
                        review: Any,
                        weights: dict[str, float] | None = None) -> list[dict[str, Any]]:
    """将 final_score 融合结果回写到 recs（失败安全：任何异常 → 原样返回 recs）。

    - effective_sample ← backtest.total_periods；
    - history_map ← backtest.strategies[g].avg_total_hit（count>0）；
    - recent_map ← reflection.periods 最近 5 次 total_hit；
    - prev_draw ← review.actual_result（风险惩罚用）；
    - structure_ctx 不传入（结构分中性 50，D3.2.0 已注明为后续增强）。
    """
    if not isinstance(recs, list) or not recs:
        return recs
    try:
        from .final_score import compute_final_scores  # 惰性导入，不改 final_score.py

        effective_sample = 0
        history_map: dict[str, float] = {}
        strategies = (backtest or {}).get("strategies")
        if isinstance(strategies, dict):
            for g, s in strategies.items():
                if isinstance(s, dict) and s.get("count"):
                    history_map[str(g)] = float(s.get("avg_total_hit") or 0.0)
                    effective_sample = max(effective_sample, int(s.get("count") or 0))
        tp = (backtest or {}).get("total_periods")
        if isinstance(tp, int):
            effective_sample = tp

        rank_map: dict[str, int] = {}
        rows = (strategy_score or {}).get("strategies")
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict) and row.get("strategy") and isinstance(row.get("rank"), int):
                    rank_map[str(row["strategy"])] = row["rank"]

        actual = (review or {}).get("actual_result") or {}
        prev_draw = {"front": actual.get("front"), "back": actual.get("back")} \
            if isinstance(actual, dict) and actual.get("front") else None

        scored = compute_final_scores(
            recs,
            effective_sample=effective_sample,
            strategy_rank=rank_map,
            history_map=history_map,
            recent_map=_recent_map_from_reflection(reflection),
            structure_ctx=None,
            prev_draw=prev_draw,
            weights=weights,
        )
        # compute_final_scores 失败安全会原样返回入参对象 → 用身份判断是否成功
        if scored is not recs and isinstance(scored, list):
            return scored
        return recs
    except Exception:
        return recs


# ---------------------------------------------------------------- 入口

def publish(*, rec_path: str = "reports/recommendations.json",
            reflect_path: str = "reports/reflection_report.json",
            backtest_path: str = "reports/backtest_summary.json",
            current_path: str = "public/data/recommendations.json",
            out_dir: str = "public/data") -> dict[str, Any]:
    """执行输出层发布，返回各文件生成结果摘要（永不抛异常）。"""
    current = _load_json(current_path)
    source_recs = _load_json(rec_path)
    reflection = _load_json(reflect_path)
    backtest = _load_json(backtest_path)

    recs = build_recommendations(current, source_recs)
    review = build_review(reflection)
    strategy_score = build_strategy_score(backtest)

    # recommendations.json 的号码源存在性检查：D1 导出缺失时回退 reports 最新一期（仍失败安全）
    if not recs and isinstance(source_recs, list) and source_recs:
        latest_issue = max(str(r.get("target_issue", "")) for r in source_recs)
        latest = [r for r in source_recs if str(r.get("target_issue")) == latest_issue]
        recs = build_recommendations(latest, source_recs)

    # D3.2 融合评分接入（回退路径之后、写盘之前）：final_score/final_breakdown/final_rank
    # + is_primary 由融合结果重算；任何异常 → 原样返回（保留 D 硬编码兜底，行为与 D3.1 前一致）
    recs = _apply_final_scores(recs, backtest, strategy_score, reflection, review,
                               weights=_load_final_score_config())

    rec_out = os.path.join(out_dir, "recommendations.json")
    review_out = os.path.join(out_dir, "review.json")
    strategy_out = os.path.join(out_dir, "strategy_score.json")
    changed = {
        "recommendations": _write_json_if_changed(rec_out, recs),
        "review": _write_json_if_changed(review_out, review),
        "strategy_score": _write_json_if_changed(strategy_out, strategy_score),
    }

    return {
        "updated_at": _now(),
        "recommendations": {"file": rec_out, "count": len(recs), "changed": changed["recommendations"]},
        "review": {"file": review_out, "empty": bool(review.get("empty")), "changed": changed["review"]},
        "strategy_score": {"file": strategy_out, "count": len(strategy_score.get("strategies", [])),
                           "changed": changed["strategy_score"]},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="推荐系统输出层：发布闭环数据到 public/data")
    parser.add_argument("--rec-path", default="reports/recommendations.json")
    parser.add_argument("--reflect-path", default="reports/reflection_report.json")
    parser.add_argument("--backtest-path", default="reports/backtest_summary.json")
    parser.add_argument("--current-path", default="public/data/recommendations.json")
    parser.add_argument("--out-dir", default="public/data")
    parser.add_argument("--safe", action="store_true", help="CI 模式：任何异常仅打印并 exit 0")
    args = parser.parse_args()
    try:
        result = publish(rec_path=args.rec_path, reflect_path=args.reflect_path,
                         backtest_path=args.backtest_path, current_path=args.current_path,
                         out_dir=args.out_dir)
        print(f"[publisher] 输出层发布完成：推荐 {result['recommendations']['count']} 条，"
              f"复盘 empty={result['review']['empty']}，策略 {result['strategy_score']['count']} 组")
    except Exception as e:  # 顶层兜底（--safe 时 exit 0）
        print(f"[publisher] 发布失败：{type(e).__name__}: {e}")
        sys.exit(0 if args.safe else 1)


if __name__ == "__main__":
    main()
