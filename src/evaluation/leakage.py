"""P2-1 数据泄露守卫（leakage guard）。

严格 walk-forward 契约：
  对于目标期 t（issues 列表中下标 t，期号 issues[t].issue）：
  - 训练/证据数据 = 仅 issues[0 : t]（期号 < target_issue 的全部）
  - 目标/结果    = issues[t]（真实开奖，仅用于命中计算与评测，绝不回流到 t 的任何特征）

本模块提供：
  - build_evidence(issues, t, window)：返回仅使用 issues[:t] 的证据窗口
  - assert_no_future_data(evidence_issues, target_issue, ...)：断言无未来数据
  - make_eval_record(...)：构造评测记录（含 leakage 断言字段）

禁止把 issue >= target_issue 的数据（frequency / omission / hot/cold / feature /
weight / score / selector / recommendation）混入 t 的生成。
"""
from __future__ import annotations

from typing import Any


def _issue_no(rec: dict[str, Any]) -> int:
    return int(rec["issue"])


def build_evidence(issues: list[dict[str, Any]], t: int, window: int | None = None) -> list[dict[str, Any]]:
    """返回生成第 t 期推荐时可用的历史证据（严格 issues[:t]，可选再取最近 window 期）。

    参数：
      issues : 按期号升序排列的完整开奖记录列表
      t      : 目标期在 issues 中的下标（0-based）；issues[t] 是当期真实开奖，
               只用于事后命中计算，不可进入证据。
      window : 若给定，仅取证据末尾 window 期（生产 analysis 用近 N 期窗口）；
               None 表示使用全部 issues[:t]。

    返回：issues[:t]（或其中末 window 期）的浅拷贝列表。
    """
    if t <= 0:
        return []
    evidence = issues[:t]
    if window is not None and window > 0:
        evidence = evidence[-window:]
    return list(evidence)


def assert_no_future_data(evidence: list[dict[str, Any]], target_issue: str | int,
                          label: str = "evidence") -> None:
    """断言证据中不含目标期或未来期（数据泄露守卫）。

    任何证据期号必须严格 < target_issue。违反即抛 AssertionError。
    """
    target = int(target_issue)
    for rec in evidence:
        no = _issue_no(rec)
        if no >= target:
            raise AssertionError(
                f"[leakage] {label} 含未来/目标数据: issue {no} >= target {target}"
            )


def assert_train_last_before_target(train_last_issue: str | int, target_issue: str | int) -> None:
    """断言训练最后一期严格早于目标期（评测记录必填不变量）。"""
    if int(train_last_issue) >= int(target_issue):
        raise AssertionError(
            f"[leakage] train_last_issue {train_last_issue} 未严格 < target_issue {target_issue}"
        )


def make_eval_record(*, target_issue: str | int, train_last_issue: str | int,
                     strategy: str, front: list[int], back: list[int],
                     actual_front: list[int], actual_back: list[int],
                     front_hits: int, back_hits: int, total_hits: int,
                     cost: float, payout: float | None, roi: float | None,
                     evaluation_version: str = "p21-v1",
                     **extra: Any) -> dict[str, Any]:
    """构造单条评测记录，并强制验证 leakage 不变量。

    字段契约（P2-1 要求的最小集 + 扩展）：
      target_issue / train_last_issue / strategy / front / back /
      actual_front / actual_back / front_hits / back_hits / total_hits /
      cost / payout / roi / evaluation_version
    """
    assert_train_last_before_target(train_last_issue, target_issue)
    rec: dict[str, Any] = {
        "target_issue": str(target_issue),
        "train_last_issue": str(train_last_issue),
        "strategy": strategy,
        "front": list(front),
        "back": list(back),
        "actual_front": list(actual_front),
        "actual_back": list(actual_back),
        "front_hits": int(front_hits),
        "back_hits": int(back_hits),
        "total_hits": int(total_hits),
        "cost": float(cost),
        "payout": payout,
        "roi": roi,
        "evaluation_version": evaluation_version,
    }
    rec.update(extra)
    return rec
