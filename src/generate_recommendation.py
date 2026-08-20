"""静态推荐数据生成器

职责：
1. 调用 new_recommender.py 生成推荐
2. 生成格式化的 JSON 文件供前端读取
3. 包含元数据和娱乐声明

输出文件：
- public/data/recommendation_new.json

版本：v1.0
日期：2026-08-20
"""
import json
import sys
from pathlib import Path
from datetime import datetime

# 添加src到路径
sys.path.insert(0, str(Path(__file__).parent))

from new_recommender import recommend


def generate_static_recommendation():
    """生成静态推荐JSON数据"""
    
    # 调用新引擎生成推荐
    result = recommend(prev_issue=None, seed=None)
    
    # 提取主推荐和备选
    main = result.get("main", [{}])[0] if result.get("main") else {}
    backup = result.get("backup", [])[:2]
    stats = result.get("stats", {})
    metadata = result.get("metadata", {})
    
    # 构建输出格式
    output = {
        "generated_at": datetime.now().isoformat(),
        "issue": "next",  # 下一期
        "version": metadata.get("engine_version", "1.0"),
        "mode": "assistant",
        
        # 主推荐
        "main": {
            "front": main.get("front", []),
            "back": main.get("back", []),
            "score": main.get("score", 0),
            "reasons": main.get("reasons", []),
            "score_details": main.get("score_details", {})
        },
        
        # 备选方案
        "backup": [
            {
                "front": b.get("front", []),
                "back": b.get("back", []),
                "score": b.get("score", 0),
                "reasons": b.get("reasons", [])
            }
            for b in backup
        ],
        
        # 统计信息
        "stats": {
            "filtered_count": stats.get("total_candidates", 0),
            "avg_quality_score": stats.get("avg_quality_score", 0),
            "max_quality_score": stats.get("max_quality_score", 0),
            "rules_applied": [
                "five_consecutive",
                "all_odd",
                "all_even",
                "all_big",
                "all_small",
                "extreme_sum",
                "extreme_span",
                "duplicate_previous"
            ]
        },
        
        # 娱乐声明
        "notice": "本工具仅提供娱乐性选号辅助，不具备预测彩票结果能力。彩票开奖为独立随机事件，请理性购彩。"
    }
    
    return output


def save_recommendation(output_data, output_path):
    """保存推荐数据到JSON文件"""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    
    return path


def main():
    """主入口"""
    print("\n" + "=" * 60)
    print("Static Recommendation Generator")
    print("=" * 60)
    
    # 生成推荐数据
    print("\n[1/2] Generating recommendation...")
    output_data = generate_static_recommendation()
    
    print(f"   Main front: {output_data['main']['front']}")
    print(f"   Main back: {output_data['main']['back']}")
    print(f"   Score: {output_data['main']['score']}")
    print(f"   Backup count: {len(output_data['backup'])}")
    
    # 保存文件
    print("\n[2/2] Saving to JSON file...")
    base_dir = Path(__file__).parent.parent
    output_path = base_dir / "public" / "data" / "recommendation_new.json"
    
    saved_path = save_recommendation(output_data, output_path)
    
    print(f"   Saved: {saved_path}")
    print(f"   File size: {saved_path.stat().st_size} bytes")
    
    print(f"\n{'='*60}")
    print("Generation complete!")
    print(f"{'='*60}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
