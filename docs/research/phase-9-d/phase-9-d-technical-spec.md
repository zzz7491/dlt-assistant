# Phase 9-D 技术规格说明书

## 一、架构变更总览

```
┌─────────────────────────────────────────────────────────┐
│  原有架构（Phase 9-C）                                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │ A 策略       │  │ B 策略       │  │ C 策略       │ │
│  │ + D 策略     │  │ + D 策略     │  │ + D 策略     │ │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘ │
│         │                 │                 │           │
│         ▼                 ▼                 ▼           │
│  ┌───────────────────────────────────────────────┐     │
│  │  输出：多个号码（main + backup）               │     │
│  └───────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  新架构（Phase 9-D）                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │ A 策略       │  │ B 策略       │  │ C 策略       │ │
│  │ + D 策略     │  │ + D 策略     │  │ + D 策略     │ │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘ │
│         │                 │                 │           │
│         ▼                 ▼                 ▼           │
│  ┌───────────────────────────────────────────────┐     │
│  │  内部计算层：多策略并行                         │     │
│  └───────────────────────────────────────────────┘     │
│                        │                                │
│                        ▼                                │
│  ┌───────────────────────────────────────────────┐     │
│  │  统一输出层：提取 D 策略 Top1 → final_recommendation │ │
│  └───────────────────────────────────────────────┘     │
│                        │                                │
│                        ▼                                │
│  ┌───────────────────────────────────────────────┐     │
│  │  前端展示：单号推荐（保留策略明细查询）          │     │
│  └───────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────┘
```

## 二、数据结构变更

### 1. recommender.py 输出变更

**旧结构**：
```json
{
  "main": [
    {"front": [1,2,3,4,5], "back": [6,7], "strategy": "A-均衡统计型"},
    {"front": [1,2,3,4,5], "back": [6,7], "strategy": "D-综合评分型", "score_total": 85}
  ],
  "backup": [...]
}
```

**新结构**：
```json
{
  "main": [...],  // 保留原结构（供内部分析）
  "backup": [...],
  "final_recommendation": {
    "front": [1,2,3,4,5],
    "back": [6,7],
    "score_total": 85,
    "factors": {
      "heat": 78.5,
      "missing": 82.3,
      "trend": 75.2,
      "inherit": 65.0
    },
    "basis": {
      "heat": "近 100 期高频",
      "missing": "周期内",
      "trend": "上升趋势",
      "inherit": "弱继承"
    },
    "strategy": "D-综合评分型"
  }
}
```

### 2. unified_recommendations 表结构

```sql
CREATE TABLE unified_recommendations (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  target_issue TEXT    NOT NULL,          -- 目标期号
  score_total  INTEGER NOT NULL,          -- 综合评分（0-100）
  final_front  TEXT    NOT NULL,          -- JSON 数组：[1,2,3,4,5]
  final_back   TEXT    NOT NULL,          -- JSON 数组：[6,7]
  factors      TEXT,                      -- JSON 对象：单号因素明细（可选）
  basis        TEXT,                      -- JSON 对象：策略依据（可选）
  date         TEXT    NOT NULL,          -- 生成日期
  generated_at TEXT    NOT NULL,          -- ISO 时间戳
  UNIQUE(target_issue, date)
);
```

### 3. backtest_summary 输出变更

**旧输出**：
```json
{
  "strategies": {
    "A": { "count": 100, "avg_total_hit": 2.5 },
    "B": { ... },
    "C": { ... },
    "D": { ... }
  },
  "factor_analysis": {
    "D": { "median_score": 75, "high_score": {...}, "low_score": {...} }
  }
}
```

**新输出**：
```json
{
  "strategies": { ... },
  "unified_performance": {
    "count": 100,
    "avg_total_hit": 3.2,
    "max_total_hit": 7,
    "hit_level_dist": { "0": 10, "1": 20, "2": 30, "3": 25, "4": 15 }
  },
  "factor_validation": {
    "median_score": 75,
    "high_score": { "avg_total_hit": 4.2 },
    "low_score": { "avg_total_hit": 2.1 },
    "score_correlation": 0.65  // 新增：评分与命中正相关
  },
  "recommendation_quality": { ... }
}
```

## 三、核心算法逻辑

### 1. final_recommendation 提取逻辑

```python
def _recommendation_cycle(analysis, cfg, rng, stats):
    # 多策略并行计算
    a_result = _strategy_balanced(analysis, cfg, rng, stats)
    b_result = _strategy_hotcold(analysis, cfg, rng, stats)
    c_result = _strategy_random(analysis, cfg, rng, stats)
    d_result = _strategy_scored(analysis, cfg, rng, stats)  # D 策略
    
    # 统一输出层：提取 D 策略 Top1
    final = d_result if d_result and d_result.get("score_total") else a_result
    
    return {
        "main": [a_result, b_result, c_result, d_result],
        "backup": [b_result, c_result],
        "final_recommendation": final
    }
```

### 2. 容错降级逻辑

**规则**：
1. 优先使用 D 策略（综合评分型）
2. 若无 D 策略（异常/失败），降级使用 A 策略（均衡统计型）
3. 若无 A 策略，返回空结构并记录日志

**实现**：
```python
final = result.get("final_recommendation")
if not final:
    main = result.get("main", [{}])[0] if result.get("main") else {}
    final = {
        "front": main.get("front", []),
        "back": main.get("back", []),
        "score_total": main.get("score_total"),
        "strategy": "降级：A-均衡统计型"
    }
```

## 四、回测验证机制

### 1. 统一推荐命中统计

```python
def _unified_analysis(records) -> dict[str, Any]:
    """最终推荐命中统计。"""
    n = len(records)
    if not n:
        return {"count": 0}
    
    hits = [r["total_hit"] for r in records]
    distances = [r["distance_score"] for r in records]
    
    return {
        "count": n,
        "avg_hit": round(sum(hits) / n, 3),
        "max_hit": max(hits),
        "avg_distance": round(sum(distances) / n, 2),
        "hit_rate": {
            "0_hit": sum(1 for h in hits if h == 0) / n,
            "1_2_hit": sum(1 for h in hits if 1 <= h <= 2) / n,
            "3_4_hit": sum(1 for h in hits if 3 <= h <= 4) / n,
            "5_hit": sum(1 for h in hits if h >= 5) / n,
        }
    }
```

### 2. 评分相关性验证

```python
def _score_correlation(records) -> dict[str, Any]:
    """计算评分与命中正相关（皮尔逊相关系数）。"""
    scores = [r.get("score_total") for r in records if isinstance(r.get("score_total"), (int, float))]
    hits = [r.get("total_hit") for r in records if isinstance(r.get("total_hit"), (int, float))]
    
    if len(scores) != len(hits) or len(scores) < 2:
        return {"n": len(scores), "note": "样本不足"}
    
    # 皮尔逊相关系数
    n = len(scores)
    mean_s = sum(scores) / n
    mean_h = sum(hits) / n
    
    numerator = sum((s - mean_s) * (h - mean_h) for s, h in zip(scores, hits))
    denom_s = math.sqrt(sum((s - mean_s) ** 2 for s in scores))
    denom_h = math.sqrt(sum((h - mean_h) ** 2 for h in hits))
    
    corr = numerator / (denom_s * denom_h) if denom_s * denom_h != 0 else 0
    
    return {
        "n": n,
        "correlation": round(corr, 3),
        "interpretation": {
            0.7: "强正相关",
            0.4: "中等相关",
            0.2: "弱相关",
            0: "无相关"
        }.get(round(corr, 1), "无法判断")
    }
```

## 五、API 接口变更

### 1. `/api/recommendation` 接口

**请求**：
```
GET /api/recommendation?issue=2026085
```

**响应**（新增 unified 字段）：
```json
{
  "issue": "2026085",
  "strategies": {
    "A": { "front": [...], "back": [...], "score_total": 72 },
    "B": { ... },
    "C": { ... },
    "D": { ... }
  },
  "final_recommendation": {
    "front": [...],
    "back": [...],
    "score_total": 85,
    "factors": {...},
    "basis": {...}
  },
  "generated_at": "2026-08-21T20:16:59"
}
```

### 2. `/api/backtest` 接口

**请求**：
```
GET /api/backtest
```

**响应**（新增 unified_performance）：
```json
{
  "total_periods": 100,
  "strategies": { "A": {...}, "B": {...}, "C": {...}, "D": {...} },
  "unified_performance": {
    "count": 100,
    "avg_hit": 3.2,
    "hit_rate": { "0_hit": 0.1, "1_2_hit": 0.2, "3_4_hit": 0.3, "5_hit": 0.4 }
  },
  "factor_validation": {
    "median_score": 75,
    "high_score": { "avg_total_hit": 4.2 },
    "low_score": { "avg_total_hit": 2.1 },
    "score_correlation": 0.65
  }
}
```

## 六、前端组件变更

### 1. RecommendationCard 组件

```vue
<template>
  <div class="recommendation-card">
    <!-- 统一最终推荐（默认展示） -->
    <div v-if="finalRecommendation" class="final-recommendation">
      <div class="numbers">
        <span v-for="n in finalRecommendation.front" :key="n">{{ n }}</span>
        <span v-for="n in finalRecommendation.back" :key="n">🔴{{ n }}</span>
      </div>
      <div class="score">评分：{{ finalRecommendation.score_total }}</div>
    </div>
    
    <!-- 策略明细（折叠面板） -->
    <details class="strategy-details">
      <summary>查看多策略明细</summary>
      <div v-for="(strategy, name) in strategies" :key="name">
        <h4>{{ name }}</h4>
        <div class="numbers">{{ strategy.front.join(",") }}</div>
        <div class="score">评分：{{ strategy.score_total }}</div>
      </div>
    </details>
    
    <!-- 评分因素分析 -->
    <div v-if="finalRecommendation.factors" class="factors-analysis">
      <div v-for="(value, key) in finalRecommendation.factors" :key="key">
        {{ key }}: {{ value }}
      </div>
    </div>
  </div>
</template>
```

### 2. 加载逻辑

```javascript
async function loadRecommendation(issue) {
  const res = await fetch(`/api/recommendation?issue=${issue}`);
  const data = await res.json();
  
  // 展示最终推荐
  renderFinalRecommendation(data.final_recommendation);
  
  // 渲染策略明细（可选）
  renderStrategyDetails(data.strategies);
}
```

## 七、测试用例

### 1. 单元测试

```python
def test_final_recommendation_extraction():
    """测试 final_recommendation 提取逻辑。"""
    result = recommend(prev_issue=None, seed=42)
    
    assert "final_recommendation" in result
    assert "front" in result["final_recommendation"]
    assert "back" in result["final_recommendation"]
    assert "score_total" in result["final_recommendation"]
    assert result["final_recommendation"]["strategy"] == "D-综合评分型"

def test_fallback_to_strategy_a():
    """测试降级到 A 策略。"""
    # 模拟 D 策略失败
    with patch.object(recommender, '_strategy_scored', return_value=None):
        result = recommend(prev_issue=None, seed=42)
        assert result["final_recommendation"]["strategy"] == "降级：A-均衡统计型"
```

### 2. 集成测试

```bash
# 测试生成器
python -m generate_recommendation --output /tmp/test_final.json
cat /tmp/test_final.json | jq '.final_recommendation'

# 测试回测
python -m backtest --rec /tmp/test_final.json --out /tmp/backtest.json
cat /tmp/backtest.json | jq '.unified_performance'
```

## 八、部署清单

1. **数据库迁移**
   - 执行 `CREATE TABLE unified_recommendations`
   - 验证表存在

2. **代码部署**
   - 更新 `recommender.py`
   - 更新 `generate_recommendation.py`
   - 更新 `backtest.py`

3. **前端部署**
   - 更新 `pick.html`
   - 更新 `pick.js`

4. **CI/CD 配置**
   - GitHub Actions 自动部署
   - 每日 02:00 UTC 运行

5. **监控验证**
   - Cloudflare Pages 预览
   - API 响应测试
   - 回测报告生成
