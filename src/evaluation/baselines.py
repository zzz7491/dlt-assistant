"""P2-1 基线策略（仅使用目标期之前的数据，严格 walk-forward）。

提供两类基线，回答「复杂 A/B/C/D 算法是否真的优于 随机 / 简单启发式」：

  BASELINE-RANDOM   合法大乐透 5+2 纯随机（固定 seed，可复现，多 seed 聚合）。
  BASELINE-SIMPLE   简单历史频率启发式：取证据窗口内前区频次最高 5 号 + 后区最高 2 号。

两者都只接受 evidence（issues[:t]）+ target（issues[t]），绝不接触未来。
"""
from __future__ import annotations

import random
from typing import Any


# ---------------------------------------------------------------- 合法性工具

def _legal_front(pool: list[int], n: int = 5) -> list[int]:
    return sorted(pool[:n])


def random_combo(seed: int, front_min: int = 1, front_max: int = 35,
                 back_min: int = 1, back_max: int = 12) -> dict[str, Any]:
    """固定 seed 的合法 5+2 纯随机组合。

    可复现：同一 seed → 同一组合。合法：前区 5 个去重 ∈ [front_min, front_max]，
    后区 2 个去重 ∈ [back_min, back_max]。
    """
    rng = random.Random(seed)
    front = rng.sample(range(front_min, front_max + 1), 5)
    back = rng.sample(range(back_min, back_max + 1), 2)
    return {"front": sorted(front), "back": sorted(back)}


def simple_frequency_combo(evidence: list[dict[str, Any]],
                           front_min: int = 1, front_max: int = 35,
                           back_min: int = 1, back_max: int = 12,
                           window: int = 100) -> dict[str, Any]:
    """简单历史频率启发式：证据（前 window 期）内频次最高前区 5 号 + 后区 2 号。

    只用 evidence（= issues[:t]），绝不接触目标期或未来。频次平手时按号码升序取，
    保证确定性（无 RNG）。
    """
    if not evidence:
        return random_combo(0, front_min, front_max, back_min, back_max)
    # 前置条件：evidence = issues[:t]（由调用方保证无目标期/未来数据）
    recent = evidence[-window:] if window and window > 0 else evidence

    def top_n(freq: dict[int, int], lo: int, hi: int, n: int) -> list[int]:
        # 频次降序，平手按号码升序 → 确定性
        items = [(freq.get(x, 0), x) for x in range(lo, hi + 1)]
        items.sort(key=lambda t: (-t[0], t[1]))
        return [x for _, x in items[:n]]

    ff: dict[int, int] = {}
    fb: dict[int, int] = {}
    for it in recent:
        for x in it.get("front", []):
            ff[x] = ff.get(x, 0) + 1
        for x in it.get("back", []):
            fb[x] = fb.get(x, 0) + 1
    front = top_n(ff, front_min, front_max, 5)
    back = top_n(fb, back_min, back_max, 2)
    return {"front": front, "back": back}
