#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
实验输入数据质量护栏（Phase 16 Step 6 · 纯实验层模块）。

职责：
- 只读取 data/dlt_history.json（实验输入数据，由生产开奖采集生成）。
- 检查实验输入数据的完整性，输出 reports/experiment_data_quality.json。
- 不修改 data/dlt_history.json，不调用任何生产模块，不写任何生产文件。

检查项（9 项，全部以实际数据格式为准，不猜测字段）：
  1. JSON 是否可解析
  2. 顶层结构是否符合实际格式（dict 且含 issues 列表）
  3. issue 是否存在（每期均有 issue）
  4. issue 是否重复
  5. issue 是否按正确顺序排列（数值单调非降）
  6. 是否存在明显期号缺口（相邻 issue 整数差 > 1）
  7. 开奖数据字段是否缺失或异常（front/back/date 存在且合法）
  8. 数据是否为空
  9. 最新期号是否能够正确识别

状态语义：
  ok        : 全部检查通过
  degraded  : 发现重复 / 缺口 / 非单调 / 字段缺失或异常 / 空数据（需要关注，但不致命）
  error     : JSON 不可解析或顶层结构不符合预期（检查本身无法完成）

注意（期号缺口）：
  大乐透存在春节加开期（如特殊编号期），整数序列并不严格连续。
  因此「相邻期号差 > 1」仅作为完整性提醒（flag 在 gaps 中），
  并标记为需人工确认，不臆断为「数据缺失」。详见 notes。
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 允许测试注入临时历史路径
HISTORY_PATH = os.environ.get(
    "EXPERIMENT_HISTORY_PATH", os.path.join(ROOT, "data", "dlt_history.json")
)
OUT_PATH = os.environ.get(
    "EXPERIMENT_DATA_QUALITY_OUT",
    os.path.join(ROOT, "reports", "experiment_data_quality.json"),
)

STATUS_OK = "ok"
STATUS_DEGRADED = "degraded"
STATUS_ERROR = "error"

# 大乐透合法号码范围（仅用于字段异常检测，不假设期号连续性）
FRONT_MIN, FRONT_MAX, FRONT_LEN = 1, 35, 5
BACK_MIN, BACK_MAX, BACK_LEN = 1, 12, 2


def _check_int_issue(v) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _field_valid(issue: dict) -> tuple[list[str], list[str]]:
    """返回 (missing_fields, anomalies)。"""
    missing: list[str] = []
    anomalies: list[str] = []
    for fld in ("issue", "front", "back", "date"):
        if fld not in issue or issue.get(fld) in (None, ""):
            missing.append(fld)
    # front / back 合法性（仅当存在时校验）
    front = issue.get("front")
    back = issue.get("back")
    if isinstance(front, list):
        if len(front) != FRONT_LEN:
            anomalies.append(f"front 长度={len(front)} 期望 {FRONT_LEN}")
        for n in front:
            if not isinstance(n, int) or not (FRONT_MIN <= n <= FRONT_MAX):
                anomalies.append(f"front 号码非法: {n}")
                break
    elif front is not None:
        anomalies.append("front 非列表")
    if isinstance(back, list):
        if len(back) != BACK_LEN:
            anomalies.append(f"back 长度={len(back)} 期望 {BACK_LEN}")
        for n in back:
            if not isinstance(n, int) or not (BACK_MIN <= n <= BACK_MAX):
                anomalies.append(f"back 号码非法: {n}")
                break
    elif back is not None:
        anomalies.append("back 非列表")
    return missing, anomalies


def build_quality(path: str = HISTORY_PATH) -> dict:
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    notes: list[str] = []

    def result(status, **extra):
        base = {
            "status": status,
            "generated_at": generated_at,
            "source": path,
            "fatal_error": None,
            "notes": notes,
        }
        base.update(extra)
        return base

    # 1) JSON 可解析
    if not os.path.exists(path):
        notes.append("数据文件不存在：实验输入数据缺失，请检查开奖采集流程。")
        return result(
            STATUS_DEGRADED, issues_count=0, latest_issue=None, empty=True,
            monotonic=True, duplicates=[], gaps=[], missing_fields=[],
            field_anomalies=[], checks=_checks(
                json_parse="fail:file_missing",
                structure="unknown",
            ),
        )
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except (json.JSONDecodeError, ValueError) as e:
        notes.append("JSON 解析失败：文件可能损坏或被截断，请重新采集。")
        return result(
            STATUS_ERROR, issues_count=None, latest_issue=None, empty=None,
            monotonic=None, duplicates=[], gaps=[], missing_fields=[], field_anomalies=[],
            fatal_error=f"{type(e).__name__}: {e}",
            checks=_checks(json_parse=f"fail:{type(e).__name__}", structure="unknown"),
        )
    except Exception as e:
        return result(
            STATUS_ERROR, issues_count=None, latest_issue=None, empty=None,
            monotonic=None, duplicates=[], gaps=[], missing_fields=[], field_anomalies=[],
            fatal_error=f"{type(e).__name__}: {e}",
            checks=_checks(json_parse=f"fail:{type(e).__name__}", structure="unknown"),
        )

    # 2) 顶层结构
    if not isinstance(raw, dict) or not isinstance(raw.get("issues"), list):
        notes.append("顶层结构不符合预期：期望 {issues:[...]}。")
        return result(
            STATUS_ERROR, issues_count=None, latest_issue=None, empty=None,
            monotonic=None, duplicates=[], gaps=[], missing_fields=[], field_anomalies=[],
            fatal_error="structure:not_dict_or_no_issues",
            checks=_checks(json_parse="ok", structure="fail"),
        )

    issues = raw["issues"]
    issues_count = len(issues)

    # 8) 数据是否为空
    if issues_count == 0:
        notes.append("issues 为空：无开奖数据。")
        return result(
            STATUS_DEGRADED, issues_count=0, latest_issue=None, empty=True,
            monotonic=True, duplicates=[], gaps=[], missing_fields=[], field_anomalies=[],
            checks=_checks(json_parse="ok", structure="ok", empty="fail"),
        )

    # 3/4/5/6/7 逐项校验
    int_issues: list[int] = []
    duplicates: list[int] = []
    seen = set()
    missing_fields: list[str] = []
    field_anomalies: list[str] = []
    gaps: list[dict] = []
    monotonic = True
    issues_missing_issue = 0

    for idx, it in enumerate(issues):
        if not isinstance(it, dict):
            missing_fields.append(f"[{idx}] 非对象")
            issues_missing_issue += 1
            continue
        iv = _check_int_issue(it.get("issue"))
        if iv is None:
            issues_missing_issue += 1
            missing_fields.append(f"[{idx}] issue 缺失/非法")
            continue
        # 重复
        if iv in seen:
            if iv not in duplicates:
                duplicates.append(iv)
        else:
            seen.add(iv)
        int_issues.append(iv)
        # 字段缺失/异常
        mf, fa = _field_valid(it)
        if mf:
            missing_fields.append(f"issue={iv}:缺{mf}")
        if fa:
            field_anomalies.append(f"issue={iv}:{'|'.join(fa)}")

    # 5) 单调（非降）& 6) 缺口（基于去重前的顺序，但用整数序列判断）
    if int_issues:
        for i in range(1, len(int_issues)):
            if int_issues[i] < int_issues[i - 1]:
                monotonic = False
            diff = int_issues[i] - int_issues[i - 1]
            if diff > 1:
                gaps.append({
                    "prev": int_issues[i - 1],
                    "next": int_issues[i],
                    "diff": diff,
                })

    latest_issue = int_issues[-1] if int_issues else None

    # 汇总状态
    degraded = bool(
        duplicates or gaps or (not monotonic)
        or missing_fields or field_anomalies or issues_missing_issue
    )
    status = STATUS_DEGRADED if degraded else STATUS_OK

    if gaps:
        notes.append(
            "期号缺口需人工确认：大乐透存在春节加开期（特殊编号期），相邻期号差 > 1 "
            "不必然表示数据缺失，此处仅作完整性提醒，不代表采集失败。"
        )
    if duplicates:
        notes.append("存在重复期号：实验回放若出现重复期会导致幂等插入冲突，需核实采集去重逻辑。")
    if not monotonic:
        notes.append("期号非单调：实验增量位点（last_processed_issue）依赖单调顺序，非单调将导致处理异常。")
    if missing_fields or field_anomalies or issues_missing_issue:
        notes.append("存在字段缺失或号码范围异常：实验评估/预测可能读取到非法数据，需核实采集质量。")

    return result(
        status,
        issues_count=issues_count,
        latest_issue=latest_issue,
        empty=False,
        monotonic=monotonic,
        duplicates=duplicates,
        gaps=gaps,
        missing_fields=missing_fields,
        field_anomalies=field_anomalies,
        checks=_checks(
            json_parse="ok",
            structure="ok",
            issue_present="fail" if issues_missing_issue else "ok",
            duplicate="fail" if duplicates else "ok",
            monotonic="ok" if monotonic else "fail",
            gap="fail" if gaps else "ok",
            field="fail" if (missing_fields or field_anomalies) else "ok",
            empty="ok",
            latest_issue="ok" if latest_issue is not None else "fail",
        ),
    )


def _checks(**kw) -> list[dict]:
    return [{"name": k, "status": "ok" if v == "ok" else "fail", "detail": v}
            for k, v in kw.items()]


def main() -> int:
    """写入 reports/experiment_data_quality.json；任何异常均被捕获，绝不崩溃。"""
    try:
        out = build_quality(HISTORY_PATH)
        os.makedirs(os.path.dirname(OUT_PATH) or ".", exist_ok=True)
        with open(OUT_PATH, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        print(f"[experiment_data_quality] 已生成数据质量: {OUT_PATH} (status={out['status']})")
        return 0
    except Exception as e:
        try:
            os.makedirs(os.path.dirname(OUT_PATH) or ".", exist_ok=True)
            with open(OUT_PATH, "w", encoding="utf-8") as f:
                json.dump({
                    "status": STATUS_ERROR,
                    "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "source": HISTORY_PATH,
                    "fatal_error": f"{type(e).__name__}: {e}",
                    "notes": ["数据质量检查自身异常（已隔离）。"],
                }, f, ensure_ascii=False, indent=2)
            print(f"[experiment_data_quality] ⚠️ 自身异常已隔离并写入 error 状态: {e}")
        except Exception:
            pass
        return 0  # 失败隔离


if __name__ == "__main__":
    sys.exit(main())
