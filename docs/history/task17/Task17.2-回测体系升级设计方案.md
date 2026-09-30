# Task 17.2 Phase 1 — 回测体系升级设计方案

**日期：** 2026-08-20  
**范围：** 仅设计，不修改代码  

---

## 一、现有体系问题诊断

### 1.1 当前回测流程（静态比对）

```
recommendations.json（已生成的推荐记录）
    ↓ 按 target_issue 匹配
dlt_history.json（历史开奖数据）
    ↓ 命中统计
backtest_summary.json
```

**根本缺陷：**
| 问题 | 现状 | 后果 |
|------|------|------|
| 样本量 | 仅1期验证 (26093) | 无任何统计意义 |
| 方向性 | 回顾式比对已有记录 | 无法证明预测有效性 |
| D策略 | count=0 | 核心策略从未被验证 |
| 滚动能力 | 无 | 不能模拟真实预测场景 |

### 1.2 现有工具链分析

| 模块 | 位置 | 功能 | 缺口 |
|------|------|------|------|
| `backtest.py` | `src/backtest.py` | 静态比对 | 无滚动/实验机制 |
| `experiment.py` | `src/experiment.py` | walk_forward 框架 | **未接入生产调度** |
| `recommender.py` | `src/recommender.py` | A/B/C/D 策略实现 | D 策略调用依赖 stats |
| `reflection.py` | `src/reflection.py` | 因素三态分析 | 无数据驱动，输出全零 |
| `analyzer.py` | `src/analyzer.py` | C-1 四因素统计 | ✅ 完整可用 |

### 1.3 experiment.py 已具备能力

```python
def walk_forward() -> dict:
    # 对每期 t：使用 issues[:t] 计算统计 → 生成D推荐 → 对比 issues[t]
    # 特征缓存加速组合评分（84k → 数千唯一特征）
```

**关键缺口：** experiment.py 未绑定到 scheduler，未形成自动闭环。

---

## 二、升级目标

### 2.1 核心目标

构建可复现的、基于真实历史数据的**滚动回测体系**，为权重调优提供量化依据。

### 2.2 量化指标要求

| 指标 | 说明 |
|------|------|
| 前区平均命中数 | 期望 > 1.0（随机基准约 0.71） |
| 后区平均命中数 | 期望 > 0.3（随机基准约 0.29） |
| 总命中分布 | 0/1/2/3+ 各档位占比 |
| D策略vs随机基线 | 提升幅度统计显著性 |
| 因子贡献排序 | 各因子区分度排名 |

---

## 三、系统设计

### 3.1 滚动回测架构

```
                    ┌─────────────────────────────────────┐
                    │         dlt_history.json            │
                    │       1000 期完整历史数据           │
                    └───────────────┬─────────────────────┘
                                    │
          ┌─────────────────────────┼─────────────────────────┐
          ▼                         ▼                         ▼
   ┌─────────────┐          ┌─────────────┐          ┌─────────────┐
   │ 100期窗口   │          │ 300期窗口   │          │ 500期窗口   │
   │ walk-forward│          │ walk-forward│          │ walk-forward│
   └──────┬──────┘          └──────┬──────┘          └──────┬──────┘
          │                        │                        │
          ▼                        ▼                        ▼
   ┌─────────────┐          ┌─────────────┐          ┌─────────────┐
   │ 生成推荐    │          │ 生成推荐    │          │ 生成推荐    │
   │ 对比实际开奖│          │ 对比实际开奖│          │ 对比实际开奖│
   └──────┬──────┘          └──────┬──────┘          └──────┬──────┘
          └────────────────────────┼────────────────────────┘
                                   ▼
                    ┌─────────────────────────────────────┐
                    │     汇总分析报告（per-period + agg）   │
                    │  - A/B/C/D 策略命中率对比             │
                    │  - 各因子贡献分析                     │
                    │  - 随机基准对比                       │
                    │  - 时间序列表现趋势                   │
                    └─────────────────────────────────────┘
```

### 3.2 窗口启动点选择原则

| 窗口大小 | 启动点 | 有效预测期数 | 说明 |
|---------|--------|------------|------|
| 100期 | issue ~250 | ~750期 | 最小实验窗口 |
| 300期 | issue ~350 | ~650期 | 推荐主实验窗口 |
| 500期 | issue ~500 | ~500期 | 大样本稳健性验证 |

**理由：** 分析器需要至少30期数据才能计算有意义的热号/遗漏/趋势，100期是安全起始点。

### 3.3 单期处理流程

```python
for t in range(start_issue, len(issues)):
    hist = issues[:t]           # 防未来信息泄漏，只取历史
    stats = build_stats(hist)   # 复用 analyzer + scorer
    
    for strategy in ["A", "B", "C", "D"]:
        rec = recommend(stats, cfg, strategy)
        
        actual = issues[t]      # 真实开奖
        result = compare(rec, actual)
        
        records.append({
            "issue": issues[t].issue,
            "strategy": strategy,
            "recommendation": rec,
            "actual": actual,
            "result": result,
            "stats_snapshot": {...}  # 当期统计快照，供因子分析
        })
```

---

## 四、输出报告结构

### 4.1 文件输出

```
reports/backtest_rolling/
├── summary_100.json      # 100期窗口汇总
├── summary_300.json      # 300期窗口汇总
├── summary_500.json      # 500期窗口汇总
├── periods_300.jsonl     # 300期窗口逐期详细记录（JSONL 格式）
└── factor_analysis_300.json  # 300期窗口因子深度分析
```

### 4.2 汇总报告结构

```json
{
  "window_size": 300,
  "start_issue": "202xxxx",
  "end_issue": "26094",
  "total_periods": 650,
  "strategies": {
    "A": { "avg_front_hit": x.x, "avg_back_hit": x.x, ... },
    "B": { ... },
    "C": { ... },
    "D": { "avg_front_hit": x.x, "avg_total_hit": x.x, ... }
  },
  "random_baseline": {
    "expected_front_hit": 0.71,
    "expected_back_hit": 0.29,
    "expected_total_hit": 1.00
  },
  "strategy_vs_random": {
    "A": { "front_lift": "+x.x%", "total_lift": "+x.x%" },
    "B": { ... },
    "C": { ... },
    "D": { "front_lift": "+x.x%", "total_lift": "+x.x%" }
  },
  "hit_distribution": {
    "A": { "0": xx, "1": xx, "2": xx, "3+": xx },
    "B": { ... },
    "D": { ... }
  },
  "factor_contribution": {
    "inherit": { "correlation": 0.x, "lift_when_positive": +x.x },
    "heat": { ... },
    "missing": { ... },
    "trend": { ... },
    "structure": { ... }
  },
  "time_series": [
    {"issue": "...", "date": "...", "strategy_D_score": x.xx, "total_hit": x}
  ]
}
```

### 4.3 因子贡献分析方法

**方法一：分组对比**
- 将每期的四个因子值按中位数分为高/低两组
- 对比两组的平均命中数，差值即为因子贡献

**方法二：相关性分析**
- 计算每个因子值与当期命中数的 Pearson 相关系数
- 绝对值越大表示区分度越高

**方法三：置换检验（进阶）**
- 随机打乱因子值重跑统计，建立零分布
- 实际值落在零分布尾部则因子显著

---

## 五、与现有代码的关系

### 5.1 复用代码

| 代码 | 来源 | 用途 |
|------|------|------|
| `analyze()` | `src/analyzer.py` | 四因素统计（温度/遗漏/奇偶/区间） |
| `calculate_number_score()` | `src/scorer.py` | 单号评分 |
| `calculate_combination_score()` | `src/scorer.py` | 组合结构评分 |
| `_strategy_scored()` | `src/recommender.py` | D策略推荐逻辑 |
| `buildOmissionProfile()` | `public/trend-v2.js` | S3遗留，本次不用 |

### 5.2 新增代码（不涉及）

| 新增内容 | 位置 | 说明 |
|---------|------|------|
| walk_forward 调度循环 | `src/backtest.py` 或独立模块 | 滚动执行逻辑 |
| 多窗口配置解析 | 复用 `config/settings.yaml` | 扩展 window_sizes 字段 |
| 报告聚合函数 | `src/reporter.py` | 格式化输出 |

### 5.3 不改动的约束

- ❌ 不修改 `settings.yaml` 权重
- ❌ 不修改 `scorer.py` 评分公式
- ❌ 不修改 `recommender.py` 策略逻辑
- ❌ 不修改 `dlt_history.json` 数据
- ❌ 不部署到生产环境

---

## 六、实施步骤（待确认后执行）

### Step 1：扩展 backtest.py（约80行）
添加 `walk_forward_backtest(issues, window_size)` 函数，实现滚动回测主循环。

### Step 2：扩展 reporter.py（约60行）
添加 `generate_backtest_report(results)` 函数，输出 JSON 汇总报告。

### Step 3：扩展 scheduler.py（约30行）
添加回测调度任务（可选：每日手动触发或定时运行）。

### Step 4：运行实验
- 300期窗口为主实验（约650个预测样本）
- 100期、500期窗口为辅实验（样本校验稳健性）

---

## 七、预期产出

| 产出物 | 内容 |
|--------|------|
| `backtest_summary_300.json` | 主要实验结果 |
| `factor_contribution_ranking.md` | 各因子区分度排名 |
| `strategy_comparison_table.md` | A/B/C/D 策略横向对比表 |
| `weight_adjustment_suggestion.md` | 基于数据的权重优化建议（非强制执行） |

---

## 八、风险评估

| 风险 | 概率 | 缓解措施 |
|------|------|---------|
| 回测耗时过长 | 中 | 300期约650轮，每轮约50ms，总计约30秒，可接受 |
| 内存占用过大 | 低 | 逐期处理，不缓存全部结果，仅保留汇总统计 |
| 结果无显著差异 | 高 | 滚动回测本身即可揭示各策略在历史中的相对表现 |

---

**设计冻结，等待确认后进 Phase 2 实施。**
