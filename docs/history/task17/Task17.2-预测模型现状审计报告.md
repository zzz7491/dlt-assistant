# Task 17.2 预测模型现状审计报告

**日期：** 2026-08-20  
**范围：** 只读检查，不修改任何代码/权重/数据  

---

## 一、A/B/C/D 四策略完整实现状态

### 1.1 策略定义位置
| 文件 | 说明 |
|------|------|
| `src/recommender.py` | A/B/C/D 四个策略函数实现 |
| `src/scorer.py` | D 策略的评分计算引擎 |
| `src/experiment.py` | 回测框架（不接入生产） |

### 1.2 各策略实现情况

| 策略 | 函数名 | 实现状态 | 说明 |
|------|--------|---------|------|
| **A 均衡统计型** | `_strategy_balanced()` | ✅ 完整 | 热号+冷号混合抽样，强制奇偶/大小平衡 |
| **B 冷热组合型** | `_strategy_hotcold()` | ✅ 完整 | 前区约60%热号+40%冷号 |
| **C 纯随机娱乐型** | `_strategy_random()` | ✅ 完整 | 合法规则下纯随机生成 |
| **D 综合评分型** | `_strategy_scored()` | ✅ 完整 | C-2-Step2：单号评分+组合遍历取Top1 |

### 1.3 策略调用链
```python
_STRATEGY_FUNCS = {
    "A": _strategy_balanced,
    "B": _strategy_hotcold,
    "C": _strategy_random,
    "D": _strategy_scored,
}

def recommend(analysis, cfg, stats=None) -> dict[str, list]:
    # stats 非空时追加 D 策略
```

---

## 二、D策略 C-2-D-v1 当前评分公式

### 2.1 单层评分（单号码）

**公式：** `score_total = Σ(w_k × factor_k)`

| 因子 | 默认权重 | 计算逻辑 | 来源函数 |
|------|---------|---------|---------|
| `heat` | 30% | 近100期频率归一化到0-100分 | `analyze_number_temperature` |
| `missing` | 30% | 遗漏周期状态映射 | `MISSING_STATUS_SCORES` 表 |
| `trend` | 25% | 近期每期频率差裁剪[-1,1]→0-100 | `temp.trend` |
| `inherit` | 15%上限 | 上期开出号码重复概率 | `overlap_dist.front_overlap_distribution` |

**硬性约束：**
```python
INHERIT_MAX_WEIGHT = 0.15  # 继承因素硬上限15%，scorer 双保险 clamp
```

**遗漏状态分数表：**
```python
MISSING_STATUS_SCORES = {
    "just_hit": 40.0,      # 刚开出
    "within_cycle": 55.0,  # 周期内
    "over_avg": 80.0,      # 超平均遗漏（回补观察窗口）
    "at_max": 88.0,        # 接近历史最大遗漏
}
```

### 2.2 双层评分（组合结构）

**公式：** `total = normalize_score(w_single × avg_single + w_combo × score_combo)`

| 因子 | 默认权重 | 计算逻辑 |
|------|---------|---------|
| `inherit_match` | 20% | 组合继承上期个数匹配历史分布概率 |
| `odd_even_match` | 20% | 奇偶比例在历史分布中的占比 |
| `big_small_match` | 20% | 大小比例在历史分布中的占比 |
| `zone_match` | 20% | 区间分布贴合历史分布均值 |
| `sum_span_match` | 20% | 和值落入[p25,p75]得满分，否则线性衰减 |

**综合分参数：**
```yaml
single_vs_combo:
  single: 0.7  # 单号均分权重
  combo: 0.3   # 结构分权重
```

### 2.3 候选池大小
```yaml
top_front: 15  # 前区取单号评分Top 15
top_back: 8    # 后区取单号评分Top 8
# 组合数：C(15,5) × C(8,2) = 3003 × 28 = 84,084 种组合遍历
```

---

## 三、五因素权重来源

### 3.1 权重配置文件

**文件：** `config/settings.yaml`

```yaml
recommend:
  weights:
    number:
      heat: 0.30
      missing: 0.30
      trend: 0.25
      inherit: 0.15
    combo:
      inherit_match: 0.20
      odd_even_match: 0.20
      big_small_match: 0.20
      zone_match: 0.20
      sum_span_match: 0.20
    single_vs_combo:
      single: 0.7
      combo: 0.3
```

### 3.2 权重计算流程

```
settings.yaml 读取
    ↓
cfg["recommend"]["weights"]
    ↓
strategy_scored() 传入
    ↓
normalize_weights(weights, defaults) → Σw=1 归一化
    ↓
inherit 硬上限 0.15 clamp
```

### 3.3 当前权重有效性分析

| 权重组 | 问题 |
|------|------|
| 单号权重 | heat/missing 各30%过高，可能导致过度偏向单一信号 |
| 组合权重 | 5个因子均等20%，未区分各因子区分度 |
| 综合分 | single:combo=0.7:0.3，单号主导可能忽略结构合理性 |

---

## 四、回测当前能力

### 4.1 回测模块位置
- `src/backtest.py` - 核心回测引擎
- `reports/backtest_summary.json` - 最新回测结果

### 4.2 当前回测数据量

| 指标 | 数值 |
|------|------|
| 已验证期数 | **仅 1 期** (26093) |
| A策略命中 | 前区0 / 后区1 / 总计1 |
| B策略命中 | 前区0 / 后区0 / 总计0 |
| C策略命中 | 前区1 / 后区0 / 总计1 |
| D策略命中 | **无数据**（未生成推荐） |

### 4.3 回测能力评估

**问题1：样本量不足**
- 仅1期验证数据，统计意义为零
- 无法判断任何策略优劣

**问题2：D策略从未成功回测**
- `backtest_summary.json` 中 `"D": {"count": 0}`
- reflection_report.json 中 D 策略因子的 positive/neutral/negative 全为 0

**问题3：命中率基准线低**
- A/B/C 三策略在前区的平均命中约 0.33（预期随机基准）
- 说明当前策略没有明显超越随机水平

---

## 五、recommendations.json 数据结构

### 5.1 记录格式

```json
{
  "date": "2026-08-17",
  "target_issue": "26093",
  "strategy": "A-均衡统计型",
  "idx": 0,
  "front": [2, 7, 20, 24, 31],
  "back": [4, 10]
}
```

### 5.2 D策略特殊字段

```json
{
  "strategy": "D-综合评分型",
  "model_version": "C-2-D-v1",
  "score_total": 38.87,
  "factors": {...},
  "basis": {
    "heat": 17.86,
    "missing": 80.0,
    "trend": 48.93,
    "inherit": 0.0,
    "structure": {
      "inherit_match": 56.11,
      "odd_even_match": 36.3,
      "big_small_match": 0.0,
      "zone_match": 20.13,
      "sum_span_match": 50.0
    }
  }
}
```

### 5.3 当前数据统计

- 总记录数：7条
- A策略：2条
- B策略：2条
- C策略：2条
- D策略：1条（仅1次成功生成）

---

## 六、reflection_report 反馈机制

### 6.1 反馈模块位置
- `src/reflection.py` - 复盘分析引擎

### 6.2 反馈输出内容

| 分析项 | 说明 | 当前状态 |
|--------|------|---------|
| 单期复盘 | 每期推荐 vs 实际开奖的命中统计 | ✅ 有 |
| 因素三态判定 | positive/neutral/negative 分类 | ⚠️ 仅A/B/C有效，D全零 |
| 累计统计 | 各因素命中率、得分 | ⚠️ 样本不足 |
| 策略排行 | 按命中数排序 | ✅ 有 |
| 结论摘要 | 规则化结论文本 | ✅ 有 |

### 6.3 因素三态判定逻辑

```python
# median_map 为历史累计中位数
if value >= median:
    status = "positive" if hit > 0 else "neutral"
else:
    status = "negative"
```

### 6.4 当前反馈数据缺陷

```json
"factor_performance": {
    "inherit": {"times": 0, "positive": 0, "neutral": 0, "negative": 0, "score": 0.0},
    "heat": {"times": 0, ...},
    "missing": {"times": 0, ...},
    "trend": {"times": 0, ...},
    "structure": {"times": 0, ...}
}
```

**所有因子 times=0，因为 D 策略的回测记录为空。**

---

## 七、问题总结

### 7.1 架构问题

| 问题 | 影响 | 优先级 |
|------|------|--------|
| 回测样本量过少 | 无法验证策略有效性 | 🔴 高 |
| D策略未能稳定运行 | 综合评分优势无法体现 | 🔴 高 |
| 权重无自适应调整 | 固定权重可能不适合当前数据分布 | 🟡 中 |
| 反馈机制未闭环 | reflection 不影响后续推荐 | 🟡 中 |

### 7.2 数据问题

| 问题 | 详情 |
|------|------|
| recommendations.json 仅7条记录 | 覆盖26093、26094两期，样本太少 |
| 缺少时间序列对比 | 无法观察策略随时间的表现变化 |
| 无失败案例分析 | 不知道哪些因子在什么场景下失效 |

### 7.3 算法问题

| 问题 | 分析 |
|------|------|
| heat/missing 权重对半 | 两个因子可能高度相关，信息重叠 |
| 组合遍历84k种计算量大 | 实验模式需要优化缓存 |
| 无负反馈机制 | 连续低效模式无法自动规避 |

---

## 八、改进方向建议（待确认后实施）

### 8.1 短期可执行
1. **扩大回测样本**：至少积累10-20期推荐记录
2. **D策略稳定性修复**：确保每期都生成D推荐
3. **添加因子相关性分析**：检测 heat/trend 是否冗余

### 8.2 中期可探索
1. **权重自适应**：基于 reflection 反馈动态调整权重
2. **因子重要性排序**：用历史数据计算各因子区分度
3. **策略融合**：结合A/B/C的优势模式

### 8.3 长期展望
1. **引入强化学习**：根据奖励信号自动调优
2. **多目标优化**：同时优化命中率、多样性、稳定性
3. **外部特征注入**：如走势图视觉特征

---

## 九、审计结论

**当前预测模型状态：基础功能完整，但缺乏验证闭环**

- ✅ A/B/C/D 四策略均已实现
- ✅ D策略评分公式完备（四层加权）
- ✅ 权重可通过 settings.yaml 配置
- ✅ 回测和反馈框架已搭建
- ❌ 回测样本严重不足（仅1期）
- ❌ D策略未形成有效验证数据
- ❌ 反馈机制未形成闭环调整

**核心瓶颈：数据积累不足，无法科学调优权重和策略。**

---

**报告完成，等待确认后进 Phase 1 改进设计。**
