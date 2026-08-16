# 大乐透 AI 娱乐分析助手

> ⚠️ **免责声明**：本程序仅用于**娱乐性历史数据统计分析**，**不预测、不保证中奖**。
> 彩票开奖为独立随机事件，任何历史规律都不能推导未来结果。请理性购彩、量力而行。

自动抓取中国体育彩票超级大乐透最近 300 期开奖结果，进行统计娱乐分析，
并基于「历史统计权重 + 随机扰动」生成**仅供娱乐讨论**的下一期号码，输出 Markdown 报告。
支持 Docker 部署、每日定时运行，并预留飞书通知 / Web 展示 / 图表分析扩展。

---

## 功能

1. 自动抓取超级大乐透最近 300 期开奖结果（数据源：500彩票网历史数据页）
2. 保存为 JSON 数据库（`data/dlt_history.json`，按 期号 去重合并）
3. Python 历史分析：
   - 号码出现频率
   - 热号 / 冷号
   - 遗漏次数（当前遗漏 + 历史最大遗漏）
   - 奇偶比例
   - 大小比例
   - 连号概率
   - 区间分布
4. 娱乐推荐算法：历史统计权重 + 随机扰动（明确标注**不预测中奖**）
5. 每日自动运行：抓取 → 分析 → 推荐 → 生成报告
6. 输出 Markdown 报告（`reports/report_YYYYMMDD.md`）
7. 可扩展：飞书通知、Web 页面、图表分析（接口已预留，配置开启）

---

## 目录结构

```
dlt-assistant/
├── Dockerfile / docker-compose.yml / crontab   # Docker 与定时任务
├── requirements.txt                            # Python 依赖
├── config/settings.yaml                        # 全部配置（期数/时间/扩展开关）
├── src/
│   ├── scraper.py        # 抓取最近 300 期
│   ├── database.py       # JSON 数据库读写
│   ├── analyzer.py       # 频率/热冷/遗漏/奇偶/大小/连号/区间
│   ├── recommender.py    # 娱乐推荐（统计权重+随机扰动）
│   ├── reporter.py       # Markdown 报告生成
│   ├── scheduler.py      # 每日编排入口
│   └── notifier/         # 通知接口（feishu 已实现，base 抽象）
├── web/app.py            # Web 展示（FastAPI，可关闭）
├── charts/generate.py    # 图表生成（matplotlib，可关闭）
├── data/                 # JSON 数据库（运行生成，建议挂载 volume）
├── reports/              # 每日 Markdown 报告
└── logs/                 # 运行日志
```

---

## 部署（Ubuntu 家庭服务器，如 X260）

```bash
# 1. 拷贝项目到服务器后构建并后台运行
docker compose build
docker compose up -d

# 容器内 crontab 默认每日 10:00（Asia/Shanghai）自动执行完整流程
# 查看日志
docker compose logs -f

# 2. 想立即跑一次验证
docker compose run --rm dlt-assistant python -m src.scheduler --once
```

> 本机（Windows 开发环境）未安装 Docker，构建/运行请在 Ubuntu X260 上进行。
> 本地纯 Python 调试：`pip install -r requirements.txt && python -m src.scheduler --once`

---

## 配置（`config/settings.yaml`）

| 配置项 | 说明 |
|---|---|
| `scrape.recent_issues` | 抓取/分析期数（默认 300） |
| `analysis.front_zones / back_zones` | 区间划分个数 |
| `recommend.combos` | 生成几组娱乐号码（默认 5） |
| `recommend.perturb` | 随机扰动强度（0=纯按频率，越大越随机） |
| `recommend.seed` | 随机种子，null=每次不同 |
| `schedule.cron` | 容器内每日运行时间 |
| `notify.feishu.enabled` | 飞书通知开关 |
| `web.enabled` / `charts.enabled` | 扩展功能开关 |

---

## 扩展

- **飞书通知**：在 `config/settings.yaml` 填入 `notify.feishu.webhook`（及可选 `secret`），并设 `enabled: true`。
- **Web 展示**：设 `web.enabled: true`，运行 `python web/app.py` 启动服务（默认 8080）。
- **图表分析**：设 `charts.enabled: true`，报告生成时额外输出频率/区间 PNG 图。

---

## 理性购彩提示

彩票为随机游戏，不存在可稳定盈利的“预测”。本工具所有输出仅作技术娱乐演示。
