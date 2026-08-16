-- =========================================================
-- 大乐透历史数据中心 · D1 初始化（阶段14 Task5）
-- 0001_init_dlt.sql
-- 说明：仅建表结构，不导入数据。
-- 修订版（Task 2.1）：dlt_draws 含 issue_num；dlt_analysis 含 version；
--          dlt_scores 含 model_type。
-- ⚠️ 执行必须带 --remote（wrangler v4 默认 local）：
--   wrangler d1 execute dlt-draws --remote --file=migrations/0001_init_dlt.sql
-- =========================================================

-- ① dlt_draws：全历史开奖数据（权威库）
CREATE TABLE IF NOT EXISTS dlt_draws (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  issue      TEXT    NOT NULL UNIQUE,            -- 5 位期号 YYNNN
  issue_num  INTEGER NOT NULL UNIQUE,            -- 数字排序字段（避免字符串期号排序风险）
  date       TEXT    NOT NULL,                   -- 开奖日期 YYYY-MM-DD
  front1     INTEGER NOT NULL CHECK(front1 BETWEEN 1 AND 35),
  front2     INTEGER NOT NULL CHECK(front2 BETWEEN 1 AND 35),
  front3     INTEGER NOT NULL CHECK(front3 BETWEEN 1 AND 35),
  front4     INTEGER NOT NULL CHECK(front4 BETWEEN 1 AND 35),
  front5     INTEGER NOT NULL CHECK(front5 BETWEEN 1 AND 35),
  back1      INTEGER NOT NULL CHECK(back1 BETWEEN 1 AND 12),
  back2      INTEGER NOT NULL CHECK(back2 BETWEEN 1 AND 12),
  source     TEXT    NOT NULL DEFAULT '500',
  verified   INTEGER NOT NULL DEFAULT 1,         -- 1=通过五重校验
  created_at TEXT    NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- ② dlt_analysis：分析缓存
CREATE TABLE IF NOT EXISTS dlt_analysis (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  period      INTEGER NOT NULL,                  -- 窗口期数（50/100/300/1000/0=全历史）
  kind        TEXT    NOT NULL,                  -- front / back
  metric      TEXT    NOT NULL,                  -- frequency/omit/oddEven/bigSmall/consec/zone...
  version     TEXT    NOT NULL DEFAULT 'v1',     -- 算法版本（缓存并存）
  payload     TEXT    NOT NULL,                  -- JSON 结果
  computed_at TEXT    NOT NULL DEFAULT (datetime('now')),
  UNIQUE(period, kind, metric, version)
);

-- ③ dlt_scores：综合评分结果
CREATE TABLE IF NOT EXISTS dlt_scores (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  period         INTEGER NOT NULL,
  kind           TEXT    NOT NULL,               -- front / back
  num            INTEGER NOT NULL,               -- 号码 01-35 / 01-12
  total          INTEGER NOT NULL,               -- 总分 0-100
  parts          TEXT    NOT NULL,               -- 七维分解 JSON
  tag            TEXT    NOT NULL,               -- 🔥热号 / ⚖平衡 / ❄冷号
  model_type     TEXT    NOT NULL DEFAULT 'standard', -- standard/cold-hot/expert 多模型并存
  weight_version TEXT    NOT NULL DEFAULT 'default',
  computed_at    TEXT    NOT NULL DEFAULT (datetime('now')),
  UNIQUE(period, kind, num, model_type, weight_version)
);

-- ④ dlt_recommendations：推荐历史
CREATE TABLE IF NOT EXISTS dlt_recommendations (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  target_issue TEXT    NOT NULL,                 -- 目标期号
  strategy     TEXT    NOT NULL,                 -- A-均衡统计型 / B-冷热组合型 / C-纯随机娱乐型
  idx          INTEGER NOT NULL DEFAULT 0,       -- 同策略第几组
  front        TEXT    NOT NULL,                 -- JSON [5]
  back         TEXT    NOT NULL,                 -- JSON [2]
  score_total  INTEGER,                          -- 可选综合评分
  date         TEXT    NOT NULL,                 -- 生成日期
  UNIQUE(target_issue, strategy, idx)
);
