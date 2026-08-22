"""跨策略动态评分融合层（Phase 11-D3.1，纯函数，不接入推荐算法）。

定位：
- 对 A/B/C/D 四策略候选组合统一打 0-100 final_score，消除「只有 D 有分」的量纲偏置；
- **不修改 scorer.py / recommender.py**：结构因子按需复用 scorer.calculate_combination_score
  （惰性导入），任何输入缺失 → 对应分量中性化（50）；
- 失败安全：compute_final_scores 顶层 try/except，任何异常 → 原样返回输入记录；
- 娱乐定位：final_score 仅用于「唯一推荐展示选择的透明化」，不构成中奖概率。

五因子公式（权重配置化，Σ=1 归一化后生效）：
  final_score = w1·base + w2·history + w3·recent + w4·structure + risk_penalty(直接叠加)
  - base      ：策略基础分 60 + 排名微调（rank1 +8 / rank2 +4 / rank3 0 / rank4 -4）
  - history   ：策略历史平均命中 avg_total_hit ∈ [0,7] → /7×100（缺失→中性 50）
  - recent    ：近期窗口命中列表均值 → /7×100（缺失→中性 50）
  - structure ：复用 scorer 组合 5 因子（无 ctx → 中性 50）
  - risk      ：结构性惩罚直接叠加（非加权），单规则见 RISK_*，叠加封顶 -40，总分下限裁剪 0

样本量三阶段降级：
  cold       : effective_sample < MIN_SAMPLE            → w2=w3=0（重分配至其余因子），
                                                          is_primary 锁定 D 策略（locked_cold_start）
  transition : MIN_SAMPLE ≤ effective_sample < FULL_SAMPLE
                                                        → w2/w3 ×TRANSITION_DECAY 后全量归一化
  stable     : effective_sample ≥ FULL_SAMPLE           → 全权重

主推荐选择（is_primary 重算，纯加法字段）：
  stable/transition → final_rank=1 者；cold → D 策略记录（无 D 时回退 final_rank=1）。
"""
from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------- 常量

NEUTRAL = 50.0          # 缺失信息中性分（与 scorer 一致）
BASE_SCORE = 60.0       # 策略基础分基准
RANK_ADJUST = {1: 8.0, 2: 4.0, 3: 0.0, 4: -4.0}  # 排名微调（未知排名 → 0）

DEFAULT_WEIGHTS: dict[str, float] = {
    "base": 0.40,
    "history": 0.20,
    "recent": 0.15,
    "structure": 0.20,
    "risk": 0.05,       # 保留键位以兼容配置；risk 实际为直接叠加惩罚，不参与加权
}

MIN_SAMPLE = 5           # 历史/近期权重启用门槛
FULL_SAMPLE = 10         # 全权重门槛
TRANSITION_DECAY = 0.5   # 过渡期衰减系数

RISK_REPEAT_FRONT = -30.0   # 与上期前区重复 ≥4
RISK_EXTREME_ODD = -15.0    # 奇偶 5:0 / 0:5
RISK_EXTREME_SIZE = -15.0   # 大小 5:0 / 0:5（前区以 18 为界，与 scorer 一致）
RISK_SUM_OUTLIER = -10.0    # 和值超出 [p5, p95]
RISK_CAP = -40.0            # 惩罚叠加封顶

STRATEGY_GROUPS = ("A", "B", "C", "D")


# ---------------------------------------------------------------- 工具纯函数

def _strategy_group(strategy: str) -> str:
    head = str(strategy or "").split("-")[0].strip().upper()
    return head if head in STRATEGY_GROUPS else "other"


def _clip100(v: float) -> float:
    return round(min(100.0, max(0.0, float(v))), 2)


def _stage(effective_sample: int) -> str:
    if effective_sample < MIN_SAMPLE:
        return "cold"
    if effective_sample < FULL_SAMPLE:
        return "transition"
    return "stable"


def _normalize_weights(weights: dict[str, float] | None, stage: str) -> dict[str, float]:
    """合并默认权重 → 按阶段调整 → Σ=1 归一化。

    cold       : history/recent 权重归零，剩余按比例重分配；
    transition : history/recent ×TRANSITION_DECAY 后全量归一化；
    stable     : 直接归一化。
    """
    w = dict(DEFAULT_WEIGHTS)
    w.update({k: float(v) for k, v in (weights or {}).items() if k in DEFAULT_WEIGHTS})
    if stage == "cold":
        w["history"] = 0.0
        w["recent"] = 0.0
    elif stage == "transition":
        w["history"] *= TRANSITION_DECAY
        w["recent"] *= TRANSITION_DECAY
    # 归一化分母含全部五键：stable 阶段默认权重保持原值（risk 键不参与加权，仅占位）
    total = sum(w.values()) or 1.0
    return {k: w[k] / total for k in ("base", "history", "recent", "structure")}


def _base_score(group: str, strategy_rank: dict[str, Any] | None) -> float:
    rank = None
    if isinstance(strategy_rank, dict):
        raw = strategy_rank.get(group)
        if isinstance(raw, dict) and isinstance(raw.get("rank"), int):
            rank = raw["rank"]
        elif isinstance(raw, int):
            rank = raw
    return BASE_SCORE + RANK_ADJUST.get(rank, 0.0)


def _history_score(history_map: dict[str, Any] | None, group: str) -> float:
    if not isinstance(history_map, dict):
        return NEUTRAL
    v = history_map.get(group)
    if not isinstance(v, (int, float)):
        return NEUTRAL
    return _clip100(float(v) / 7.0 * 100.0)


def _recent_score(recent_map: dict[str, Any] | None, group: str) -> float:
    if not isinstance(recent_map, dict):
        return NEUTRAL
    hits = recent_map.get(group)
    if not isinstance(hits, (list, tuple)) or not hits:
        return NEUTRAL
    vals = [float(h) for h in hits if isinstance(h, (int, float))]
    if not vals:
        return NEUTRAL
    return _clip100(sum(vals) / len(vals) / 7.0 * 100.0)


def _structure_score(combo: dict[str, Any],
                     structure_ctx: dict[str, Any] | None,
                     prev_draw: dict[str, Any] | None) -> float:
    """复用 scorer.calculate_combination_score（惰性导入，不改其实现）。

    ctx 缺失或 scorer 抛错 → 中性 50。ctx 期望字段：
      overlap_dist / structure_stats / sum_span_stats（analyzer 输出，透传给 scorer）
    """
    if not isinstance(structure_ctx, dict):
        return NEUTRAL
    try:
        from .scorer import calculate_combination_score  # 惰性导入，不修改 scorer.py
        result = calculate_combination_score(
            {"front": list(combo.get("front") or []),
             "back": list(combo.get("back") or [])},
            overlap_dist=structure_ctx.get("overlap_dist"),
            structure_stats=structure_ctx.get("structure_stats"),
            sum_span_stats=structure_ctx.get("sum_span_stats"),
            prev_front=(prev_draw or {}).get("front"),
            prev_back=(prev_draw or {}).get("back"),
        )
        v = result.get("score_total")
        return float(v) if isinstance(v, (int, float)) else NEUTRAL
    except Exception:
        return NEUTRAL


def _risk_penalty(combo: dict[str, Any],
                  prev_draw: dict[str, Any] | None,
                  sum_span_stats: dict[str, Any] | None) -> float:
    """结构性风险惩罚（直接叠加，非加权）。叠加封顶 RISK_CAP，无下限偏置。"""
    front = [x for x in (combo.get("front") or []) if isinstance(x, int)]
    back = [x for x in (combo.get("back") or []) if isinstance(x, int)]
    penalty = 0.0
    pf = (prev_draw or {}).get("front") or []
    if pf and len(set(front) & set(pf)) >= 4:
        penalty += RISK_REPEAT_FRONT
    odd = sum(1 for x in front if x % 2 == 1)
    if front and odd in (0, len(front)):
        penalty += RISK_EXTREME_ODD
    big = sum(1 for x in front if x >= 18)
    if front and big in (0, len(front)):
        penalty += RISK_EXTREME_SIZE
    fs = (sum_span_stats or {}).get("front_sum") or {}
    p5, p95 = fs.get("p5"), fs.get("p95")
    if isinstance(p5, (int, float)) and isinstance(p95, (int, float)) and front:
        s = sum(front)
        if s < p5 or s > p95:
            penalty += RISK_SUM_OUTLIER
    return max(RISK_CAP, penalty)


# ---------------------------------------------------------------- 主入口

def compute_final_scores(recs: list[dict[str, Any]],
                         effective_sample: int = 0,
                         strategy_rank: dict[str, Any] | None = None,
                         history_map: dict[str, Any] | None = None,
                         recent_map: dict[str, Any] | None = None,
                         structure_ctx: dict[str, Any] | None = None,
                         prev_draw: dict[str, Any] | None = None,
                         weights: dict[str, float] | None = None) -> list[dict[str, Any]]:
    """跨策略统一评分主入口（失败安全：任何异常 → 原样返回 recs）。

    参数：
      recs             候选推荐列表（每条含 strategy/front/back；缺 front/back 跳过该条打分但保留原样）
      effective_sample 已开奖验证期数（决定冷启动/过渡/稳定三阶段）
      strategy_rank    {group: rank|int 或 {rank:int}}（如 publisher 的 strategy_score 行）
      history_map      {group: avg_total_hit}
      recent_map       {group: [total_hit, ...]}
      structure_ctx    scorer 组合评分输入 {overlap_dist, structure_stats, sum_span_stats}（可省略）
      prev_draw        上期开奖 {front:[...], back:[...]}（风险惩罚用，可省略）
      weights          自定义权重（仅 base/history/recent/structure/risk 五键生效）

    返回：深拷贝记录列表，逐条追加：
      final_score / final_breakdown / final_rank / is_primary
    冷启动时 primary 记录 breakdown 附 locked_cold_start=True。
    """
    try:
        return _compute(recs, effective_sample, strategy_rank, history_map,
                        recent_map, structure_ctx, prev_draw, weights)
    except Exception:
        return recs


def _compute(recs, effective_sample, strategy_rank, history_map,
             recent_map, structure_ctx, prev_draw, weights) -> list[dict[str, Any]]:
    if not isinstance(recs, list) or not recs:
        return recs  # 失败安全语义：非法/空输入原样返回

    stage = _stage(int(effective_sample or 0))
    w = _normalize_weights(weights, stage)

    scored: list[dict[str, Any]] = []
    for r in recs:
        item = dict(r)  # 不修改入参
        combo = {"front": r.get("front"), "back": r.get("back")}
        group = _strategy_group(r.get("strategy"))
        has_combo = isinstance(r.get("front"), list) and isinstance(r.get("back"), list)

        if has_combo:
            base = round(_base_score(group, strategy_rank), 2)
            hist = _history_score(history_map, group)
            rec = _recent_score(recent_map, group)
            struct = round(_structure_score(combo, structure_ctx, prev_draw), 2)
            risk = _risk_penalty(combo, prev_draw,
                                 (structure_ctx or {}).get("sum_span_stats"))
            final = _clip100(
                w["base"] * base + w["history"] * hist +
                w["recent"] * rec + w["structure"] * struct + risk
            )
        else:
            # 缺号码字段：不打分、不参与排名，保留原样
            base = hist = rec = struct = None
            risk = 0.0
            final = None

        breakdown = {
            "base": base, "history": hist, "recent": rec,
            "structure": struct, "risk": round(risk, 2),
            "weights": {k: round(w[k], 4) for k in ("base", "history", "recent", "structure")},
            "degraded": stage != "stable",
            "stage": stage,
            "effective_sample": int(effective_sample or 0),
        }
        item["final_score"] = final
        item["final_breakdown"] = breakdown
        scored.append(item)

    # 排名（仅对有分的记录）；平分时保持输入顺序稳定
    ranked = [it for it in scored if isinstance(it.get("final_score"), (int, float))]
    ranked.sort(key=lambda it: -it["final_score"])
    for i, it in enumerate(ranked, 1):
        it["final_rank"] = i

    # 主推荐选择：冷启动锁定 D；否则 final_rank=1
    if stage == "cold":
        primary = next((it for it in scored if _strategy_group(it.get("strategy")) == "D"), None)
        if primary is None and ranked:
            primary = ranked[0]
    else:
        primary = ranked[0] if ranked else None

    for it in scored:
        it["is_primary"] = it is primary
    if primary is not None and stage == "cold" and _strategy_group(primary.get("strategy")) == "D":
        primary["final_breakdown"]["locked_cold_start"] = True

    return scored
