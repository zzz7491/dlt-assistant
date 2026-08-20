"""推荐引擎适配器：桥接 new_recommender 与前端 API。

职责：
- 调用 new_recommender.py 生成推荐
- 统一输出 JSON 格式供前端使用
- 不修改原有推荐逻辑

依赖：
- src/new_recommender.py（Phase1已实现）

版本：v1.0
日期：2026-08-20
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

try:
    from .new_recommender import recommend as new_recommend
except ImportError:
    from new_recommender import recommend as new_recommend


def get_recommendation(prev_issue: dict[str, Any] | None = None) -> dict[str, Any]:
    """获取智能推荐并转换为前端标准格式。
    
    Args:
        prev_issue: 上一期开奖数据 {"front": [...], "back": [...]}，可选
    
    Returns:
        {
            "status": "success",
            "data": {
                "main": {...},
                "backup": [...],
                "stats": {...},
                "metadata": {...}
            },
            "timestamp": "2026-08-20T10:30:00"
        }
    """
    # 调用新引擎生成推荐
    result = new_recommend(prev_issue=prev_issue, seed=None)
    
    # 提取规则应用列表
    rules_applied = [
        "five_consecutive",      # Rule 1: 五连号过滤
        "all_odd",              # Rule 2: 全奇数过滤
        "all_even",             # Rule 3: 全偶数过滤
        "all_big",              # Rule 4: 全大号过滤
        "all_small",            # Rule 5: 全小号过滤
        "extreme_sum",          # Rule 6: 和值极端过滤
        "extreme_span",         # Rule 7: 跨度极端过滤
        "duplicate_previous",   # Rule 8: 与上期重复过滤
    ]
    
    # 构建响应格式
    response = {
        "status": "success",
        "data": {
            "main": result.get("main", [{}])[0] if result.get("main") else {},
            "backup": result.get("backup", []),
            "stats": {
                "filtered_count": result.get("stats", {}).get("total_candidates", 0),
                "quality_score": result.get("stats", {}).get("avg_quality_score", 0),
                "rules_applied": rules_applied,
            },
            "metadata": {
                "mode": "assistant",
                "version": "v2",
                "engine_version": result.get("metadata", {}).get("engine_version", "1.0"),
                "disclaimer": "娱乐性选号辅助，不构成任何中奖承诺",
            }
        },
        "timestamp": datetime.now().isoformat()
    }
    
    return response


def get_recommendation_json(prev_issue: dict[str, Any] | None = None) -> str:
    """获取推荐并序列化为 JSON 字符串。
    
    Args:
        prev_issue: 上一期开奖数据，可选
    
    Returns:
        JSON 字符串
    """
    result = get_recommendation(prev_issue)
    return json.dumps(result, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    # 测试入口
    print("=" * 60)
    print("Recommendation Adapter Test")
    print("=" * 60)
    
    # 模拟上一期数据
    prev = {"front": [5, 12, 19, 27, 33], "back": [3, 9]}
    
    # 获取推荐
    result = get_recommendation(prev_issue=prev)
    
    # 输出结果
    print("\n[Status]", result["status"])
    print("[Timestamp]", result["timestamp"])
    print("\n[Main Recommendation]")
    main = result["data"]["main"]
    print(f"  Front: {main.get('front')}")
    print(f"  Back: {main.get('back')}")
    print(f"  Score: {main.get('score')}")
    print(f"  Reasons: {len(main.get('reasons', []))} items")
    
    print("\n[Backup Recommendations]")
    for i, b in enumerate(result["data"]["backup"], 1):
        print(f"  Backup {i}: {b.get('front')} + {b.get('back')} (Score: {b.get('score')})")
    
    print("\n[Stats]")
    stats = result["data"]["stats"]
    print(f"  Filtered candidates: {stats['filtered_count']}")
    print(f"  Average quality score: {stats['quality_score']}")
    print(f"  Rules applied: {len(stats['rules_applied'])}")
    
    print("\n[Metadata]")
    meta = result["data"]["metadata"]
    print(f"  Mode: {meta['mode']}")
    print(f"  Version: {meta['version']}")
    print(f"  Disclaimer: {meta['disclaimer']}")
