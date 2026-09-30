# 大乐透项目当前状态与下一阶段路线图

> 盘点日期：2026-08-19（周三）｜执行：DLT-Progress-Review（纯只读，未修改任何代码/配置/部署）
> 范围：仅大乐透 AI 娱乐分析项目（dlt-assistant）

---

## 一、当前版本

| 项 | 值 | 说明 |
| --- | --- | --- |
| Git 版本 | `master @ d1417f2` | `feat(analyzer): implement analyze_sum_span`，与远端 `origin/master` 一致（FETCH_HEAD 同哈希，无领先/落后） |
| 模型版本 | `C-2-D-v1` | D 综合评分策略 model_version |
| 权重版本 | `G0` | number: heat 0.30 / missing 0.30 / trend 0.25 / inherit 0.15；combo 五因子各 0.20；single/combo 0.7/0.3 |
| 部署版本 | Cloudflare Pages Production `7b6a1b17`（= d1417f2） | 生产地址 https://dlt-assistant.pages.dev，线上 5 页面 + 数据均 200，运行正常 |

工作树：无已跟踪文件修改；存在 7 个未跟踪文件（规划文档 PRODUCT-PLAN/V2-ROADMAP/v1.2-ROADMAP、Task16.5-Cline-0 报告、weight 实验/验证结果），按约定不入库。

---

## 二、已完成

### 16.5-D 系列（前端体验优化 · 全部收官上线）
- D-1 只读分析 → D-2 **推荐卡 2×2**（`.rec-grid` ≥560px 3 列改 2 列，修复 A/B/C/D 四卡桌面 3+1 错位）+ 文案更新 → D-3 **CSS 优化**（删 `.quick-nav` 死代码、header 规则归并）→ D-4 导航间距微调 → D-5 收口提交 `ff1c525`（含删除 trend.css 死文件）→ D-6 部署 `4a6be324`。
- **四策略展示**：首页推荐卡 A/B/C/D 四张齐全；线上实测 2×2、四策略文案生效。

### 16.5-E 系列（analyze_sum_span · 已上线）
- E-1 设计 → E-2+E-3 实施与验收（测试 19/19 PASS）→ E-4 正式上线。
- **链路确认**（代码级，均真实生效）：
  - `src/analyzer.py:308` `analyze_sum_span`：输出 front_sum/front_span/back_span 分位数分布；
  - `src/scheduler.py:60` stats 组装 `"sum_span": analyze_sum_span(issues)`；
  - `src/recommender.py:193` D 策略调用 `stats.get("sum_span")` → `calculate_combination_score`；
  - `src/scorer.py:36` 权重 `sum_span_match: 0.20`。
- **生效状态**：代码链路已生效并部署（commit `d1417f2`，部署 `7b6a1b17`）；本地端到端实测 sum_span_match 从旧 50.0 → 真实值 100.0。线上**真实数据值**需今晚首次运行新代码生成（见「待执行」）。

### F 系列（稳定性观察与设计 · 全部完成，均为只读/设计）
- **F-1 生产稳定观察**：全绿。HEAD=远端=d1417f2、clean；Pages 7b6a1b17；5 页面 200；dlt_history 1000 期最新 26093 无异常；recommendations 4 策略 D 字段齐；无 NaN/空字段/重复写入；workflow 连续 success。
- **F-2 监控分析**：完成缺口分析（workflow 失败无主动通知、D1 容错静默、无数据质量自动检测、无探活告警；方案分 P0/P1/P2）。
- **F-3 一致性检查设计**：完成 `src/health_check.py` 独立模块设计（P0 error 阻断 / P1 warning / P2 info，输出健康报告 + 分级告警）。

---

## 三、待执行

### 必须完成（今晚自动发生，无需人工）
- **T1 · 26094 开奖闭环验收**：今日（8-19 周三）21:25 开奖，21:45 workflow 自动抓取 → 回测/复盘 → 22:10 定时任务自动完成闭环验收。
  - **执行条件已满足**：推荐已锁定（D1 已写 26094 四策略 + 前端 JSON 已导出）；dlt_history 当前缺 26094（正常，待今晚写入）。
- **T2 · sum_span 真实效果首次验证**：今晚 workflow 首次用 d1417f2 新代码运行，生成 sum_span_match 真实值（本地已证 100 vs 旧 50），纳入 D 策略记录与回测。

### 等待真实数据
- **T3 · factor_performance 长期积累**：D 策略当前仅 1 期有效记录（26093 回测 D count=0），需 ≥30 期 D 记录后才具备权重校准条件；随每日 workflow 自然积累，每 7-10 期复盘一次即可。

### 可以优化（非阻塞，随时可做）
- **T4 · 推荐依据可视化**：前端展示 D 策略 basis（heat/missing/trend/inherit/structure 含 sum_span_match）。
- **T5 · 报告链接动态化 / 数据术语说明页**（D-Review 中 P5/P6，可暂停级）。

---

## 四、暂停事项

| 事项 | 状态 | 原因 |
| --- | --- | --- |
| F-4 健康检查系统实施 | 待指令 | 设计已完成；实施需用户提供飞书 webhook（当前 `notify.feishu.enabled=false`） |
| 权重动态调整（C-2-Step5） | 暂缓 | 依赖 T3 的 ≥30 期 D 数据 |
| 首页大改 / my 页大改 / 可视化重做 | 取消或暂缓 | D-Review 判定收益低 |
| V3 D1 全历史库主线 / V4 用户体系 / 多源采集 / 达人推荐 | 暂缓 | V2-ROADMAP 长期规划，不开发 |

---

## 五、稳定性核查（阶段一基线结论）

- **Git**：HEAD 与远端一致，无未提交修改，最近提交记录正常。
- **Cloudflare Pages**：生产版本 7b6a1b17 与 Git 最新（d1417f2）一致，线上正常。
- **GitHub Actions**：workflow `dlt-analysis.yml` 存在；cron 正常（每日 02:00 UTC 兜底 + 开奖日 13:45 UTC = 北京 21:45）；最近 3 次运行 success；8-16 曾有 3 次失败（wrangler 部署 token 权限问题），后续已恢复，非当前问题。
- **数据**：dlt_history.json 1000 期、最新 26093、重复期号 0、前/后区范围异常 0、NaN/None 0；「非连续」仅 19150→20001 一处（年度期号切换，正常）。recommendations.json：26094 四策略已生成并锁定（D 含 model_version/score_total/basis），线上精简版与 reports 完整版双文件体系正常。

---

## 六、推荐下一步（唯一最高优先任务）

**T1+T2 合并为一件事：今晚 8-19 21:45 自动 workflow 运行，完成「26094 开奖闭环验收 + sum_span 真实效果首次验证」。**

理由：
1. 这是整条主线唯一在等待的自然节点（D/E 系列已交付、推荐已锁定、今日即开奖日）；
2. 一次运行同时闭合两个最高优先级验证（26094 生产闭环 + sum_span 真实值）；
3. 全程无需任何代码改动、无需人工干预——22:10 后读取 reports/backtest_summary.json 与 reflection_report.json 确认即可。

**执行纪律**：不做任何代码/配置/部署修改；F-4 与 basis 可视化等一律待 T1+T2 闭环结果确认后再排期。
