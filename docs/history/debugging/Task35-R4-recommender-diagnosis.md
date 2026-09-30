# Task #35-R.4 诊断总结

## 执行目标
确认 `issues → recent → analyze() → analysis → recommend() → strategies` 链条中哪一步变为空。

## 验证步骤

### Step 1：验证 analyzer 输出
- **结果**：✅ 正常
- **数据**：`issues: 1000`, `recent: 1000`, `analysis keys: 25`, `front_hot: 10`, `front_cold: 1`

### Step 2：验证 recommender 输出
- **首次测试**：A/B/C/D 各 0 个 → **异常**
- **手动模拟**：A/B/C 各 1 个 → **正常**
- **重新测试**：A/B/C 各 1 个 → **正常**

### Step 3：验证 stats 参数影响
| stats 参数 | A | B | C | D | final_recommendation |
|------------|---|---|---|---|----------------------|
| `None`     | 1 | 1 | 1 | **0** | 降级为 A 策略 |
| `{}`       | 1 | 1 | 1 | 1 | D 策略（无意义）|
| 有数据     | 1 | 1 | 1 | 1 | D 策略（有效）|

## 根本原因

**`stats=None` 导致 D 策略不执行**

- `recommend()` 逻辑：`if stats is not None:` 才追加 D 策略
- `stats=None` → D 策略不执行 → `strategies` 无 D → `final_recommendation` 降级为 A 策略
- 但 `final_recommendation.json` 仍为空 → 说明问题在 `scheduler.run_once()` 或 `generate_recommendation.py`

## 下一步行动

1. 检查 `scheduler.run_once()` 如何调用 `recommend()`
2. 检查 `generate_recommendation.py` 如何生成 JSON
3. 确认 `stats` 参数传递逻辑

## 建议修复方案

**方案 A**：修改 `recommend()` 条件
```python
# 原代码
if stats is not None:
    strategies["D"] = [...]

# 改为
if stats and len(stats) > 0:
    strategies["D"] = [...]
```

**方案 B**：修改 `scheduler.run_once()` 构造 stats
```python
# 主动构造包含 prev_issue 的 stats
stats = {
    "prev_issue": recent[-1],
    "temperature": {"front": {}, "back": {}},
    "missing_cycle": {"front": {}, "back": {}},
    "overlap": {},
    "structure": {},
}
result = recommend(analysis, cfg, stats=stats)
```

---

执行时间：2026-08-21 23:55
调试脚本：`debug_recommender.py`, `debug_recommender2.py`, `debug_recommender3.py`
