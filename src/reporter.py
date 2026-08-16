"""生成 Markdown 格式的每日娱乐分析报告。"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from .recommender import STRATEGY_LABELS


def _freq_line(freq: dict[int, int]) -> str:
    return "  ".join(f"{k}:{v}" for k, v in freq.items())


def _dist_table(dist: dict[str, int], total: int) -> str:
    lines = ["| 比例 | 出现期数 | 占比 |", "| --- | ---: | ---: |"]
    for k, v in sorted(dist.items(), key=lambda kv: kv[1], reverse=True):
        pct = (v / total * 100) if total else 0.0
        lines.append(f"| {k} | {v} | {pct:.1f}% |")
    return "\n".join(lines)


def _zone_table(labels: list[str], counter: list[int]) -> str:
    total = sum(counter) or 1
    lines = ["| 区间 | 出现次数 | 占比 |", "| --- | ---: | ---: |"]
    for lab, c in zip(labels, counter):
        pct = c / total * 100
        lines.append(f"| {lab} | {c} | {pct:.1f}% |")
    return "\n".join(lines)


def build_report(meta: dict[str, Any], analysis: dict[str, Any], recommendations: list[dict[str, Any]]) -> str:
    n = analysis["count"]
    gen = meta.get("generated_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    rng = meta.get("range", "")

    parts: list[str] = []
    parts.append(f"# 大乐透AI娱乐分析报告\n")
    parts.append(f"> 生成时间：**{gen}**  ｜  数据来源：{meta.get('source','')}  ｜  分析期数：**{n}** 期（{rng}）\n")

    # 免责声明
    parts.append("## ⚠️ 免责声明\n")
    parts.append(
        "**本工具仅用于历史数据分析和娱乐，不具有预测彩票结果能力。**\n"
        "彩票开奖为独立随机事件，任何历史规律均不构成未来结果的依据。\n"
        "请理性购彩，量力而行，切勿沉迷。\n"
    )

    # 频率
    parts.append("## 一、号码出现频率\n")
    parts.append(f"**前区（1-35）总频次：** {_freq_line(analysis['front_freq'])}\n")
    parts.append(f"**后区（1-12）总频次：** {_freq_line(analysis['back_freq'])}\n")

    # 热号冷号
    parts.append("## 二、热号 / 冷号（按总体频率）\n")
    fh = "、".join(f"{k}({v})" for k, v in analysis["front_hot"])
    fc = "、".join(f"{k}({v})" for k, v in analysis["front_cold"])
    bh = "、".join(f"{k}({v})" for k, v in analysis["back_hot"])
    bc = "、".join(f"{k}({v})" for k, v in analysis["back_cold"])
    parts.append(f"- 前区热号（高频）：{fh}")
    parts.append(f"- 前区冷号（低频）：{fc}")
    parts.append(f"- 后区热号（高频）：{bh}")
    parts.append(f"- 后区冷号（低频）：{bc}\n")

    # 遗漏
    parts.append("## 三、遗漏分析（当前连续未出现期数 / 历史最大遗漏）\n")
    fcur = analysis["front_cur_omit"]
    fmaxo = analysis["front_max_omit"]
    top_omit = sorted(fcur.items(), key=lambda kv: kv[1], reverse=True)[:10]
    parts.append("**前区当前遗漏最大的号码：**")
    parts.append("、".join(f"{k}(当前{cur}/最大{fmaxo[k]})" for k, cur in top_omit) + "\n")

    # 奇偶
    parts.append("## 四、奇偶比例分布（前区）\n")
    parts.append(_dist_table(analysis["odd_even_dist"], n) + "\n")

    # 大小
    parts.append("## 五、大小比例分布（前区，分界18）\n")
    parts.append(_dist_table(analysis["big_small_dist"], n) + "\n")

    # 连号
    parts.append("## 六、连号概率（前区出现相邻差1的对）\n")
    parts.append(f"- 含连号的期数占比：**{analysis['consec_prob']*100:.1f}%**")
    parts.append(f"- 平均每期连号对数：**{analysis['consec_avg']:.2f}**\n")

    # 区间
    parts.append("## 七、区间分布\n")
    parts.append("**前区：**")
    parts.append(_zone_table(analysis["front_zone_labels"], analysis["front_zone_counter"]))
    parts.append("\n**后区：**")
    parts.append(_zone_table(analysis["back_zone_labels"], analysis["back_zone_counter"]) + "\n")

    # 推荐（A/B/C 三策略）
    parts.append("## 八、娱乐推荐号码（仅供参考，非预测）\n")
    parts.append("以下 A/B/C 三策略均基于历史统计或随机生成，**仅供娱乐讨论，不等于中奖预测**：\n")
    for key in ("A", "B", "C"):
        combos = recommendations.get(key, [])
        parts.append(f"**推荐 {key}（{STRATEGY_LABELS.get(key, key)}）：**")
        for c in combos:
            front = " ".join(f"{x:02d}" for x in c["front"])
            back = " ".join(f"{x:02d}" for x in c["back"])
            parts.append(f"- 前区：**{front}** 　后区：**{back}**")
        parts.append("")
    parts.append("> 再次提醒：以上号码为算法随机娱乐产物，不等于中奖预测。\n")

    # 历史验证统计（娱乐回顾，仅统计号码重合，不计算中獎）
    val = meta.get("validation")
    parts.append("## 九、历史验证统计（娱乐回顾）\n")
    if val and val.get("validated"):
        parts.append(
            f"- 累计生成推荐：**{val['total']}** 次\n"
            f"- 已开奖可验证：**{val['validated']}** 次\n"
            f"- 平均命中：**{val['avg_hit']:.2f}** 个（仅统计号码重合，不计算中獎）\n"
        )
    else:
        total = val["total"] if val else 0
        parts.append(f"- 累计生成推荐：**{total}** 次\n")
        parts.append("- 已开奖可验证：**0** 次（目标期号尚未开出，暂无可验证记录）\n")
        parts.append("- 平均命中：—（待开奖后自动统计）\n")
    parts.append("")

    parts.append("---\n")
    parts.append(f"*本报告由 大乐透AI娱乐分析助手 自动生成 · {gen}*\n")
    return "\n".join(parts)


def write_report(text: str, path: str) -> str:
    d = os.path.dirname(os.path.abspath(path))
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path
