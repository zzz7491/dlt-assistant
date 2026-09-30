# Phase 9-D 实施修改计划

## 一、当前版本状态与本次目标

| 维度 | 说明 |
|------|------|
| **当前版本** | v1.3（稳定运行中） |
| **本次升级** | Phase 9-D：回测体系升级 + final_recommendation 统一输出层 |
| **核心问题** | 现有推荐系统输出多策略多个号码，缺乏统一最终推荐；回测无法验证评分有效性 |
| **设计原则** | 单号推荐原则（前端只展示一个号码）+ 娱乐声明不变 |

## 二、修改范围

### 1. 数据库层（D1）

**修改 `migrations/0001_init_dlt.sql`**：

```sql
-- 新增 unified_recommendations 表（统一最终推荐）
CREATE TABLE IF NOT EXISTS unified_recommendations (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  target_issue TEXT    NOT NULL,
  score_total  INTEGER NOT NULL,
  final_front  TEXT    NOT NULL,  -- 5 个前区号码 JSON 数组
  final_back   TEXT    NOT NULL,  -- 2 个后区号码 JSON 数组
  factors      TEXT,              -- D 策略因素明细（可选）
  basis        TEXT,              -- D 策略依据（可选）
  date         TEXT    NOT NULL,
  generated_at TEXT    NOT NULL,
  UNIQUE(target_issue, date)
);

-- 或扩展现有 dlt_recommendations 表：
ALTER TABLE dlt_recommendations ADD COLUMN final_recommendation INTEGER DEFAULT 0;
-- final_recommendation=1 表示该记录为最终推荐
```

### 2. 推荐算法层（recommender.py）

**修改 `recommend()` 函数返回结构**：

```python
# 原返回结构
{
  "main": [{"front": [...], "back": [...], "strategy": "D-综合评分型", ...}],
  "backup": [...]
}

# 新返回结构
{
  "main": [...],           # 保留 A/B/C/D 多策略输出（供内部分析）
  "backup": [...],
  "final_recommendation": {  # 新增：统一最终推荐
    "front": [...],        # 唯一 5 个前区
    "back": [...],         # 唯一 2 个后区
    "score_total": 85,     # D 策略总分
    "factors": {...},      # D 策略因素明细
    "basis": {...},        # D 策略依据
    "strategy": "D-综合评分型"
  }
}
```

**核心修改点**：
- `_recommendation_cycle()` 函数在策略并行计算后，新增 `final_recommendation` 提取逻辑
- **最终推荐来源**：始终优先选择 `D 策略（综合评分型）` 的 Top1 结果
- **容错逻辑**：若无 D 策略，降级使用 A 策略（均衡统计型）

### 3. 生成器层（generate_recommendation.py）

**修改静态推荐生成逻辑**：

```python
def generate_static_recommendation():
    result = recommend(prev_issue=None, seed=None)
    
    # 优先取 final_recommendation，若无则降级
    final = result.get("final_recommendation")
    if not final:
        main = result.get("main", [{}])[0] if result.get("main") else {}
        final = {
            "front": main.get("front", []),
            "back": main.get("back", []),
            "score_total": main.get("score_total"),
            "strategy": main.get("strategy")
        }
    
    output = {
        "generated_at": datetime.now().isoformat(),
        "issue": "next",
        "version": metadata.get("engine_version", "1.0"),
        "final_recommendation": {
            "front": final.get("front", []),
            "back": final.get("back", []),
            "score_total": final.get("score_total"),
            "factors": final.get("factors"),
            "basis": final.get("basis"),
            "strategy": "D-综合评分型" if final.get("strategy") == "D-综合评分型" else "降级：A-均衡统计型"
        },
        "notice": "本工具仅提供娱乐性选号辅助，不具备预测彩票结果能力。"
    }
```

### 4. 回测层（backtest.py）

**扩展回测验证机制**：

```python
def backtest(recommendations, issues) -> dict[str, Any]:
    # 新增 unified_rec_records：提取 final_recommendation 记录
    unified_records = []
    for r in recommendations:
        if r.get("final_recommendation"):
            fr = r["final_recommendation"]
            unified_records.append({
                "issue": r["target_issue"],
                "front_hit": len(set(fr.get("front")) & set(real.get("front"))),
                "back_hit": len(set(fr.get("back")) & set(real.get("back"))),
                "score_total": fr.get("score_total"),
                "factors": fr.get("factors"),
            })
    
    # 新增回测统计维度
    summary["unified_performance"] = _stats(unified_records)
    summary["factor_validation"] = _factor_analysis_d(unified_records)
    
    return summary
```

**新增回测报告输出字段**：
- `unified_performance`：最终推荐命中率统计
- `factor_validation`：D 策略因素有效性验证（高/低评分组对比）
- `score_correlation`：评分与命中正相关验证（皮尔逊相关系数）

### 5. 前端层（pick.html / pick.js）

**修改前端展示逻辑**：

```javascript
// 展示统一最终推荐
function displayFinalRecommendation(recommendation) {
  const fr = recommendation.final_recommendation;
  displayNumber("front", fr.front);
  displayNumber("back", fr.back);
  
  // 展示评分详情（折叠面板）
  showScoreDetail({
    total: fr.score_total,
    factors: fr.factors,
    basis: fr.basis
  });
}

// 保留策略明细查询入口
async function fetchStrategyDetail(issue) {
  const res = await fetch(`/api/recommendation?issue=${issue}`);
  return res.json();  // 返回 A/B/C/D 多策略输出
}
```

**前端原则**：
- **默认展示**：统一最终推荐（单号）
- **可选查看**：策略明细（通过 API 查询历史期号的多策略输出）
- **机选/手动**：保持原有功能不变

## 三、实施步骤（分阶段执行）

### 阶段 1：数据库迁移（Task #34）

**目标**：创建 unified_recommendations 表

**命令**：
```bash
cd C:\工作空间\dlt\dlt-assistant
wrangler d1 execute dlt-draws --remote --command="
CREATE TABLE IF NOT EXISTS unified_recommendations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  target_issue TEXT NOT NULL,
  score_total INTEGER NOT NULL,
  final_front TEXT NOT NULL,
  final_back TEXT NOT NULL,
  factors TEXT,
  basis TEXT,
  date TEXT NOT NULL,
  generated_at TEXT NOT NULL,
  UNIQUE(target_issue, date)
);"
```

**验证**：
```bash
wrangler d1 execute dlt-draws --remote --command="SELECT name FROM sqlite_master WHERE type='table';"
```

### 阶段 2：推荐算法层修改（Task #35）

**目标**：修改 `recommender.py` 输出 `final_recommendation` 字段

**修改点**：
- `_recommendation_cycle()` 函数末尾添加 final 提取逻辑
- 始终优先选择 D 策略 Top1

**测试**：
```python
# 单元测试
from .recommender import recommend
result = recommend(prev_issue=None, seed=42)
assert "final_recommendation" in result
assert result["final_recommendation"]["strategy"] == "D-综合评分型"
```

### 阶段 3：生成器层修改（Task #36）

**目标**：修改 `generate_recommendation.py` 输出 unified JSON

**修改点**：
- 读取 recommender.py 返回的 `final_recommendation`
- 生成 reports/final_recommendation.json

**测试**：
```bash
cd src
python -m generate_recommendation --output ../reports/final_recommendation.json
cat ../reports/final_recommendation.json
```

### 阶段 4：回测层扩展（Task #37）

**目标**：扩展 `backtest.py` 支持 unified 输出验证

**修改点**：
- 新增 `_unified_analysis()` 函数
- 新增 `score_correlation` 计算（评分与命中正相关）

**测试**：
```bash
cd src
python -m backtest --rec reports/recommendations.json --out reports/backtest_summary.json
cat reports/backtest_summary.json | jq '.unified_performance'
```

### 阶段 5：前端层修改（Task #38）

**目标**：修改 `pick.html` 展示统一最终推荐

**修改点**：
- 加载 `reports/final_recommendation.json`
- 展示 `final_recommendation` 字段
- 保留策略明细查询入口

**测试**：
```bash
cd C:\工作空间\dlt\dlt-assistant\public
python -m http.server 8000
# 访问 http://localhost:8000/pick.html
```

## 四、风险评估

| 风险项 | 影响 | 缓解措施 |
|--------|------|----------|
| D1 表结构修改失败 | 部署失败 | 先读表结构确认，备份后执行 |
| recommender.py 返回结构破坏 | 生成器异常 | 新增容错逻辑（降级到 A 策略） |
| 回测性能下降 | 运行超时 | 限制验证期数（最近 100 期） |
| 前端展示混乱 | 用户体验下降 | 保持单号展示，策略详情折叠 |

## 五、验证矩阵（交付门禁）

| 维度 | 验证项 | 预期结果 |
|------|--------|----------|
| **数据库** | unified_recommendations 表存在 | `SELECT name FROM sqlite_master` 输出包含该表 |
| **算法** | recommender.py 输出 final_recommendation | `result.get("final_recommendation")` 非空 |
| **生成器** | final_recommendation.json 存在 | JSON 包含 `front`, `back`, `score_total` |
| **回测** | backtest_summary.json 包含 unified_performance | 统计字段非空 |
| **前端** | pick.html 展示统一推荐 | 单号显示，评分详情可展开 |
| **娱乐声明** | 所有页面保留免责声明 | 文本不变 |

## 六、交付文档

1. **Phase 9-D 实施报告**（本文档的完整版）
2. **变更日志**（CHANGELOG.md）
3. **回测验证报告**（reports/backtest_summary.json）
4. **最终推荐样本**（reports/final_recommendation.json）

## 七、后续工作（Phase 9-D 之后）

- **Phase 9-E**：前端可视化增强（走势图 + 评分热力图）
- **Phase 10**：数据层升级（引入更多历史期数）
- **Phase 11**：性能优化（缓存策略、API 加速）
