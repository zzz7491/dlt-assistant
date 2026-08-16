"""历史开奖数据读取接口（loader）。

Task 1.1-A：先支持「JSON 文件路径」与「传入对象（dict/list）」；
D1 读取（wrangler d1 export / API）接口留待后续 Task 扩展。

输出标准 issues 列表：[{issue, date, front[5], back[2]}]（升序），与前端同构。
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Union


def load_issues(path: Optional[str] = None,
                data: Optional[Union[Dict[str, Any], List[Dict[str, Any]]]] = None) -> List[Dict[str, Any]]:
    """读取历史开奖数据，返回标准 issues 列表。

    参数优先级：data（传入对象）> path（JSON 文件）。
    data 可为完整包裹对象（含 "issues" 键）或直接为 issues 列表。
    """
    if data is not None:
        issues = data.get("issues", []) if isinstance(data, dict) else data
    elif path:
        with open(path, encoding="utf-8") as fh:
            issues = json.load(fh).get("issues", [])
    else:
        raise ValueError("需要提供 path 或 data 之一")
    return _normalize(issues)


def _normalize(issues: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """标准化：仅保留 issue/date/front/back，front/back 转为升序整数列表。"""
    out: List[Dict[str, Any]] = []
    for it in issues:
        front = sorted(int(x) for x in it["front"])
        back = sorted(int(x) for x in it["back"])
        out.append({
            "issue": str(it["issue"]),
            "date": str(it["date"]),
            "front": front,
            "back": back,
        })
    return out


def load_from_d1(database: str = "dlt-draws") -> List[Dict[str, Any]]:
    """从 D1 读取（预留接口，Task 后续实现）。

    计划：wrangler d1 export / API /api/issues?range=all → 标准 issues。
    """
    raise NotImplementedError("D1 读取将于后续 Task 实现")
