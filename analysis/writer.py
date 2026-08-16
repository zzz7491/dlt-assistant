"""D1 写入模块（writer）——生成 INSERT OR REPLACE SQL（Task 1.1-C 实现）。

策略：INSERT OR REPLACE（幂等、可重复运行、支持算法版本升级），
执行统一走 `wrangler d1 execute dlt-draws --remote --file=<sql>`。

写入目标：
  - dlt_analysis（指标缓存）：period / kind / metric / version / payload(JSON) / computed_at
  - dlt_scores（评分缓存）：period / kind / num / total / parts(JSON) / tag /
                            model_type / weight_version / computed_at
不写 dlt_draws；不改 schema / migration。

period 归一化：前端 "all" → D1 整数 0（schema 注释：0=全历史）。
computed_at 使用 SQLite 的 datetime('now')（UTC），与表默认值一致；
同一批 SQL 文本完全确定 → 重复生成文件内容一致（幂等）。

本模块只生成 SQL 文本，绝不直接执行写入。
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Union


def normalize_period(period: Union[int, str, None]) -> int:
    """period 归一化：None / "all" → 0（全历史）；数字窗口 → int。"""
    if period is None or str(period).lower() == "all":
        return 0
    return int(period)


def _json_sql(obj: Any) -> str:
    """JSON 序列化为 SQL 字符串字面量：紧凑输出 + 单引号转义（SQLite 字符串）。"""
    raw = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    return raw.replace("'", "''")


def build_analysis_inserts(results: Dict[str, Any], period: Union[int, str],
                           kind: str, metric: str, version: str = "v1") -> List[str]:
    """生成 dlt_analysis 的 INSERT OR REPLACE 语句（单条）。

    唯一键：UNIQUE(period, kind, metric, version)
    results：指标计算结果 dict（frequency/hot/missing/oddEven/bigSmall/consec 的 payload）。
    """
    p = normalize_period(period)
    payload = _json_sql(results)
    return [(
        "INSERT OR REPLACE INTO dlt_analysis "
        "(period, kind, metric, version, payload, computed_at) VALUES "
        f"({p}, '{kind}', '{metric}', '{version}', '{payload}', datetime('now'));"
    )]


def build_scores_inserts(scores: List[Dict[str, Any]], period: Union[int, str],
                         kind: str, model_type: str,
                         weight_version: str = "default") -> List[str]:
    """生成 dlt_scores 的 INSERT OR REPLACE 语句（每号码一条）。

    唯一键：UNIQUE(period, kind, num, model_type, weight_version)
    scores：score_all() 输出 [{num, total, parts{7 维}, tag}]。
    """
    p = normalize_period(period)
    out: List[str] = []
    for s in scores:
        parts = _json_sql(s["parts"])
        out.append((
            "INSERT OR REPLACE INTO dlt_scores "
            "(period, kind, num, total, parts, tag, model_type, weight_version, computed_at) "
            f"VALUES ({p}, '{kind}', {int(s['num'])}, {int(s['total'])}, '{parts}', "
            f"'{s['tag']}', '{model_type}', '{weight_version}', datetime('now'));"
        ))
    return out


def write_sql_file(statements: List[str], path: str) -> None:
    """将 SQL 语句列表写入文件（供 wrangler d1 execute --file 执行）。"""
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(statements) + "\n")
