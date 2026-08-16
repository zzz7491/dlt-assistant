"""图表分析（扩展，默认关闭）。生成前区频率柱状图、区间分布图等 PNG 到 reports/assets。"""
from __future__ import annotations

import os
from typing import Any


def generate_charts(analysis: dict[str, Any], recent: list[dict[str, Any]], cfg: dict[str, Any]) -> str:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out_dir = cfg.get("charts", {}).get("dir", "reports/assets")
    os.makedirs(out_dir, exist_ok=True)

    # 前区号码频率柱状图
    f = analysis["front_freq"]
    keys = list(f.keys())
    vals = list(f.values())
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.bar([str(k) for k in keys], vals, color="#c0392b")
    ax.set_title("前区号码出现频率")
    ax.set_xlabel("号码")
    ax.set_ylabel("出现次数")
    fig.tight_layout()
    fig.savefig(f"{out_dir}/front_freq.png", dpi=100)
    plt.close(fig)

    # 前区区间分布图
    labels = analysis["front_zone_labels"]
    cnt = analysis["front_zone_counter"]
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(labels, cnt, color="#2980b9")
    ax.set_title("前区区间分布")
    ax.set_ylabel("出现次数")
    fig.tight_layout()
    fig.savefig(f"{out_dir}/front_zones.png", dpi=100)
    plt.close(fig)

    return out_dir
