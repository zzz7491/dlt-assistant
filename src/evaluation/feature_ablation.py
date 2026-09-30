"""P3-3 D 策略特征消融（research only；走真实生产 recommend()，不改生产权重默认值）。

科学目标：回答 D 综合评分型的每个历史统计特征
（heat / missing / trend / inherit / inherit_match / odd_even / big_small /
 zone / sum_span）移除后是否改变 OOS 命中，识别 SUPPORTED / HARMFUL / REDUNDANT。

权重处理规则（STEP 11，结果前冻结，记录在 p33-feature-definition.json）：
  移除特征 X = 把 X 对应的 production 权重键置 0.0，其余特征权重**保持原值不变**；
  scorer._normalize_weights 会自然把剩余权重归一化到 Σ=1（生产既有行为）。
  禁止事后为补偿 X 而重新调其它权重。

每个 target 共享一次 analysis（A/B/C/D 证据相同），只对 D 用不同 ablation 权重枚举。
"""
from __future__ import annotations

import copy
import json
from typing import Any

from ..analyzer import (analyze, analyze_previous_overlap, analyze_number_temperature,
                        analyze_missing_cycle, analyze_structure_distribution,
                        analyze_sum_span)
from ..recommender import recommend

WINDOW = "1000"   # D 消融沿用 P3-2 KEEP_1000 决策的生产等价窗口

# ---------------------------------------------------------------- 消融变体（映射到真实 scorer 权重键）
# name, (section, weight_key)
ABLATION_VARIANTS: list[tuple[str, str, str]] = [
    ("NO_HEAT",          "number", "heat"),              # frequency
    ("NO_MISSING",       "number", "missing"),           # omission
    ("NO_TREND",         "number", "trend"),             # temperature
    ("NO_INHERIT",       "number", "inherit"),           # single overlap
    ("NO_INHERIT_MATCH", "combo",  "inherit_match"),     # combo overlap
    ("NO_ODD_EVEN",      "combo",  "odd_even_match"),    # structure
    ("NO_BIG_SMALL",     "combo",  "big_small_match"),   # structure
    ("NO_ZONE",          "combo",  "zone_match"),        # structure
    ("NO_SUM_SPAN",      "combo",  "sum_span_match"),    # sum/span
]
VARIANT_NAMES = [v[0] for v in ABLATION_VARIANTS]


def make_ablation_cfg(base_cfg: dict, section: str, weight_key: str) -> dict:
    """深拷贝 base_cfg，把 (section, weight_key) 权重置 0，其余保持不变。

    冻结规则 = zero + 生产内建归一化（Σ=1）。不修改 base_cfg。
    """
    cfg = copy.deepcopy(base_cfg)
    w = cfg["recommend"]["weights"]
    w[section][weight_key] = 0.0
    return cfg


def _stats(evidence: list[dict], prev: dict) -> dict:
    return {
        "overlap": analyze_previous_overlap(evidence),
        "temperature": analyze_number_temperature(evidence),
        "missing_cycle": analyze_missing_cycle(evidence),
        "structure": analyze_structure_distribution(evidence),
        "sum_span": analyze_sum_span(evidence),
        "prev_issue": prev,
    }


def evidence_for(issues: list[dict], t_idx: int, window: str = WINDOW) -> list[dict]:
    ev = issues[:t_idx]
    if window != "FULL":
        ev = ev[-int(window):]
    return ev


def d_candidate(t_idx: int, issues: list[dict], cfg: dict,
                section: str | None = None, weight_key: str | None = None) -> dict[str, list[int]]:
    """真实生产 recommend() 取 D。可选把 (section, weight_key) 权重置 0 后枚举。"""
    ev = evidence_for(issues, t_idx)
    analysis = analyze(ev, cfg)
    use_cfg = make_ablation_cfg(cfg, section, weight_key) if section else cfg
    d = recommend(analysis, use_cfg, stats=_stats(ev, issues[t_idx - 1]))
    c = d["D"][0]
    return {"front": list(c["front"]), "back": list(c["back"])}


def ablation_candidates(t_idx: int, issues: list[dict], cfg: dict) -> dict[str, dict[str, list[int]]]:
    """单 target 共享 analysis；FULL control + 9 个 ablation。

    返回 {variant_name: {front, back}}，variant 名含 "FULL"。
    注：为控制成本，analysis 只算一次（各 ablation 的 evidence 相同）；
    D 枚举按各 ablation 权重独立跑（top-pool 会随权重变化，必须重算）。
    """
    ev = evidence_for(issues, t_idx)
    analysis = analyze(ev, cfg)
    st = _stats(ev, issues[t_idx - 1])
    out: dict[str, dict] = {}

    def _run(use_cfg):
        d = recommend(analysis, use_cfg, stats=st)
        c = d["D"][0]
        return {"front": list(c["front"]), "back": list(c["back"])}

    out["FULL"] = _run(cfg)
    for name, section, weight_key in ABLATION_VARIANTS:
        out[name] = _run(make_ablation_cfg(cfg, section, weight_key))
    return out


# ---------------------------------------------------------------- worker（shell-level 并行）

def main_worker(chunk: int, chunks: int, warmup: int, dataset: str, out_dir: str) -> None:
    import pathlib
    import sys
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
    from . import window_study as ws
    from .feature_ablation import ablation_candidates

    issues = ws.load_issues(dataset)
    cfg = ws.production_cfg()
    n = len(issues)
    t_idxs = [t for t in range(warmup, n) if t % chunks == chunk]

    out = pathlib.Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    chunk_file = out / f"ablation_chunk_{chunk}.json"
    data: dict[str, dict] = {}
    for i, t in enumerate(t_idxs):
        data[str(t)] = ablation_candidates(t, issues, cfg)
        if (i + 1) % 200 == 0:
            print(f"  ablation chunk {chunk}: {i + 1}/{len(t_idxs)}")
    chunk_file.write_text(json.dumps(data), encoding="utf-8")
    print(f"[ablation worker {chunk}/{chunks}] {len(t_idxs)} targets × "
          f"({1 + len(VARIANT_NAMES)} variants) → {chunk_file.name} DONE")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--chunk", type=int, required=True)
    ap.add_argument("--chunks", type=int, default=10)
    ap.add_argument("--warmup", type=int, default=1000)
    ap.add_argument("--dataset", default="data/research/dlt-full-history.json")
    ap.add_argument("--out", default=".agnes/work/p33")
    args = ap.parse_args()
    main_worker(args.chunk, args.chunks, args.warmup, args.dataset, args.out)
