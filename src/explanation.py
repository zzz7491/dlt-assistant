"""P1-2 推荐理由引擎：为「唯一正式推荐」生成真实、可追溯、确定性的解释。

设计约束：
  - 只用 Python 标准库 + 当期真实数据（dlt_history.json + 推荐记录已有字段）。
  - 确定性：同一输入（numbers + history + window + 记录字段）→ 同一 explanation。
    不使用 LLM / 外部 API / 随机 / 时间戳。
  - 描述「算法为何构造出这组候选」，绝不描述「这些号码会中奖」。
    不暗示预测确定性，不出现 建设中/开发中/待完善/TODO/coming soon。
  - 按策略真实逻辑分类：
      A balanced_statistical（热冷混合 + 奇偶/大小均衡）
      B hot_cold_mix（热冷组合）
      C random_baseline（纯随机基线——诚实标注，不伪造统计依据）
      D scored（综合评分——基于记录自带的 basis/factors）

strategy_type 由记录 strategy 前缀（A/B/C/D）决定，与 recommender.STRATEGY_LABELS 一致。
"""
from __future__ import annotations

import hashlib
from typing import Any

# 与 src/analyzer + public/app.js 口径一致的热冷/奇偶阈值（仅服务解释展示）
DEFAULT_RECENT_WINDOW = 50
HOT_TOP = {"front": 10, "back": 5}
COLD_TOP = {"front": 8, "back": 4}
FRONT_MIN, FRONT_MAX = 1, 35
BACK_MIN, BACK_MAX = 1, 12
SIZE_BOUNDARY = 18

# strategy 前缀 → 内部类型
_STRATEGY_TYPE = {
    "A": "balanced_statistical",
    "B": "hot_cold_mix",
    "C": "random_baseline",
    "D": "scored",
}

DISCLAIMER = "本解释仅描述内部算法如何构造候选组合，不代表任何号码会中奖，亦不构成预测。"


def _strategy_prefix(strategy: Any) -> str:
    head = str(strategy or "").split("-")[0].strip().upper()
    return head if head in _STRATEGY_TYPE else ""


def _pad(n: int) -> str:
    return f"{n:02d}"


# ---------------------------------------------------------------- 确定性统计（自 history）

def _observed(issues: list[dict[str, Any]], numbers: list[int], kind: str,
               window: int) -> dict[str, Any]:
    """给定一组号码，返回其可追溯的观测统计（频率/遗漏/热冷归属/奇偶大小/和值/跨度/连号）。

    全部为 history 的纯函数，无时间、无随机 → 确定性。
    """
    win = issues[-window:] if window and len(issues) > window else list(issues)
    pool = range(FRONT_MIN, FRONT_MAX + 1) if kind == "front" else range(BACK_MIN, BACK_MAX + 1)

    freq = {n: 0 for n in pool}
    for it in win:
        for x in (it.get(kind) or []):
            if x in freq:
                freq[x] += 1

    # 当前遗漏（从最新一期往回数，直到该号出现）
    omit = {}
    for n in pool:
        m = 0
        for it in reversed(issues):
            if n in (it.get(kind) or []):
                break
            m += 1
        omit[n] = m

    hot_rank = sorted(freq, key=lambda n: (-freq[n], n))
    hot_set = set(hot_rank[: HOT_TOP[kind]])
    cold_rank = sorted([n for n in pool if omit[n] > 0], key=lambda n: (-omit[n], n))
    cold_set = set(cold_rank[: COLD_TOP[kind]])

    sel = [n for n in numbers if n in freq]
    odd = sum(1 for n in sel if n % 2 == 1)
    even = len(sel) - odd
    big = sum(1 for n in sel if n >= SIZE_BOUNDARY)
    small = len(sel) - big
    total = sum(sel)
    if len(sel) >= 2:
        span = max(sel) - min(sel)
    else:
        span = 0
    consecutive = sum(1 for i in range(len(sel) - 1) if sorted(sel)[i + 1] - sorted(sel)[i] == 1)

    return {
        "window": len(win),
        "freq": {n: freq[n] for n in sel},
        "omit": {n: omit[n] for n in sel},
        "in_hot": [n for n in sel if n in hot_set],
        "in_cold": [n for n in sel if n in cold_set],
        "odd_even": [odd, even],
        "big_small": [big, small],
        "sum": total,
        "span": span,
        "consecutive_pairs": consecutive,
    }


# ---------------------------------------------------------------- 因子构造

def _factor(ftype: str, label: str, detail: str, evidence: dict[str, Any]) -> dict[str, Any]:
    return {"type": ftype, "label": label, "detail": detail, "evidence": evidence}


def _summarize_structure(obs: dict[str, Any], kind: str) -> str:
    oe = obs.get("odd_even") or [0, 0]
    bs = obs.get("big_small") or [0, 0]
    return f"奇偶比 {oe[0]}:{oe[1]}、大小比 {bs[0]}:{bs[1]}、和值 {obs.get('sum', 0)}、跨度 {obs.get('span', 0)}"


def build_explanation(*, strategy: Any, front: list[int], back: list[int],
                      history: list[dict[str, Any]] | None,
                      recent_window: int = DEFAULT_RECENT_WINDOW,
                      basis: dict[str, Any] | None = None,
                      factors: dict[str, Any] | None = None,
                      model_version: Any = None,
                      score_total: Any = None,
                      target_issue: Any = None) -> dict[str, Any]:
    """生成该推荐记录的确定性 explanation。

    history 为空 → reason_status="unavailable"（前端显示中性占位，不编造）。
    正常路径 → reason_status="ok"，summary + 2~5 个可追溯 factors。
    """
    stype = _STRATEGY_TYPE.get(_strategy_prefix(strategy), "unknown")
    front = [int(x) for x in (front or []) if isinstance(x, int)]
    back = [int(x) for x in (back or []) if isinstance(x, int)]
    issues = [i for i in (history or []) if isinstance(i, dict)]

    result: dict[str, Any] = {
        "explanation_version": "1.1",
        "strategy_type": stype,
        "strategy": strategy,
        "target_issue": target_issue,
        "summary": "",
        "factors": [],
        "generated_from": [],
        "reason_status": "unavailable",
        "disclaimer": DISCLAIMER,
    }

    if not issues or stype == "unknown":
        # 无历史数据 / 未知策略 → 中性占位，不编造
        result["summary"] = "本期推荐理由暂未生成（缺少可追溯的统计依据）。"
        result["generated_from"] = []
        return result

    obs_f = _observed(issues, front, "front", recent_window)
    obs_b = _observed(issues, back, "back", recent_window)

    if stype == "random_baseline":
        # 诚实：随机基线，不伪造热冷/遗漏/趋势依据
        result["summary"] = (
            "本期候选由随机基线策略在合法规则下随机生成，"
            "作为与统计型策略对比的对照候选，不代表任何统计倾向或走势判断。"
        )
        result["factors"] = [
            _factor("random", "随机基线",
                    "该组合为合法规则内随机抽取，非基于热冷/遗漏/趋势的统计构造。",
                    {"is_random": True}),
            _factor("structure", "结构分布（仅描述）",
                    f"前区 {_summarize_structure(obs_f, 'front')}。",
                    {"front_odd_even": obs_f["odd_even"], "front_big_small": obs_f["big_small"],
                     "front_sum": obs_f["sum"], "front_span": obs_f["span"]}),
        ]
    elif stype == "balanced_statistical":
        hf, hb = len(obs_f["in_hot"]), len(obs_b["in_hot"])
        result["summary"] = (
            f"均衡统计型：依据近 {obs_f['window']} 期频率与遗漏，前区混合热号 {hf} 个、"
            f"冷号 {len(obs_f['in_cold'])} 个并强制奇偶/大小均衡后生成；"
            f"本组前区 {_summarize_structure(obs_f, 'front')}。"
        )
        result["factors"] = [
            _factor("hot_cold", "热冷混合",
                    f"前区落在当前窗口热号集合 {hf} 个、冷号集合 {len(obs_f['in_cold'])} 个。",
                    {"front_hot": obs_f["in_hot"], "front_cold": obs_f["in_cold"], "window": obs_f["window"]}),
            _factor("frequency", "频率依据",
                    "前区号码取自近期基础频率与近期频率加权（0.5/0.5）的候选池。",
                    {"front_freq": obs_f["freq"]}),
            _factor("balance", "奇偶/大小均衡",
                    f"前区奇偶比 {obs_f['odd_even'][0]}:{obs_f['odd_even'][1]}、"
                    f"大小比 {obs_f['big_small'][0]}:{obs_f['big_small'][1]}（算法强制均衡到 2~3）。",
                    {"front_odd_even": obs_f["odd_even"], "front_big_small": obs_f["big_small"]}),
            _factor("structure", "结构分布",
                    f"前区和值 {obs_f['sum']}、跨度 {obs_f['span']}。",
                    {"front_sum": obs_f["sum"], "front_span": obs_f["span"]}),
        ]
    elif stype == "hot_cold_mix":
        result["summary"] = (
            f"冷热组合型：前区约 60% 热号 + 40% 冷号构造；"
            f"本组前区命中当前窗口热号 {len(obs_f['in_hot'])} 个、冷号 {len(obs_f['in_cold'])} 个，"
            f"{_summarize_structure(obs_f, 'front')}。"
        )
        result["factors"] = [
            _factor("hot_cold", "热冷组合",
                    f"前区约 60% 热号 / 40% 冷号（按近 {obs_f['window']} 期频率与遗漏界定）。",
                    {"front_hot": obs_f["in_hot"], "front_cold": obs_f["in_cold"], "window": obs_f["window"]}),
            _factor("frequency", "频率依据",
                    "热号/冷号判定基于近期出现次数与当前遗漏。",
                    {"front_freq": obs_f["freq"], "front_omit": obs_f["omit"]}),
            _factor("structure", "结构分布",
                    f"前区和值 {obs_f['sum']}、跨度 {obs_f['span']}、连号 {obs_f['consecutive_pairs']} 对。",
                    {"front_sum": obs_f["sum"], "front_span": obs_f["span"],
                     "front_consecutive_pairs": obs_f["consecutive_pairs"]}),
        ]
    elif stype == "scored":
        b = basis or {}
        f = factors or {}
        parts = []
        for key in ("heat", "missing", "trend", "inherit"):
            v = b.get(key)
            if isinstance(v, (int, float)):
                parts.append(f"{key}={v}")
        struct_sum = f.get("sum_span_match") if isinstance(f, dict) else None
        if isinstance(struct_sum, (int, float)):
            parts.append(f"sum_span_match={struct_sum}")
        basis_txt = ("，".join(parts) if parts else "综合评分")
        result["summary"] = (
            f"综合评分型：对单号（热/遗漏/趋势/继承）与组合（结构/和值跨度）双层评分后取 Top1；"
            f"本组关键依据：{basis_txt}。"
            + (f"（模型 {model_version}，评分 {score_total}）" if model_version else "")
        )
        result["factors"] = [
            _factor("heat", "热度", f"本组单号热度均值 {b.get('heat')}。", {"heat": b.get("heat")}) if b.get("heat") is not None
            else _factor("heat", "热度", "热度依据未提供。", {"heat": None}),
            _factor("missing", "遗漏", f"本组单号遗漏均值 {b.get('missing')}（越高=越久未出）。", {"missing": b.get("missing")}) if b.get("missing") is not None
            else _factor("missing", "遗漏", "遗漏依据未提供。", {"missing": None}),
            _factor("structure", "组合结构", f"和值/跨度贴合度 {f.get('sum_span_match')}、区间贴合 {f.get('zone_match')}。",
                    {"sum_span_match": f.get("sum_span_match"), "zone_match": f.get("zone_match")}) if isinstance(f, dict)
            else _factor("structure", "组合结构", "结构依据未提供。", {}),
            _factor("sum_span", "结构分布",
                    f"前区和值 {obs_f['sum']}、跨度 {obs_f['span']}（观测值）。",
                    {"front_sum": obs_f["sum"], "front_span": obs_f["span"]}),
        ]
        result["model_version"] = model_version
        result["score_total"] = score_total

    # generated_from：记录本条 explanation 的真实数据来源（供追溯）
    result["generated_from"] = [
        "dlt_history.json", f"window={obs_f['window']}", f"strategy_type={stype}",
    ]
    if stype == "scored":
        result["generated_from"].extend(["basis", "factors"])
    result["reason_status"] = "ok"
    # 冻结哈希（确定性）：对 explanation 稳定序列化后取短指纹，纳入快照完整性
    result["explanation_hash"] = _explain_hash(result)
    return result


def _explain_hash(expl: dict[str, Any]) -> str:
    import json as _json
    d = {k: v for k, v in expl.items() if k not in ("explanation_hash",)}
    return hashlib.sha256(_json.dumps(d, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()[:16]


def explanation_summary(expl: Any) -> str:
    """取 explanation 的 summary（供 reason 字段 / 前端默认行）。"""
    if isinstance(expl, dict) and expl.get("summary"):
        return str(expl["summary"])
    return ""
