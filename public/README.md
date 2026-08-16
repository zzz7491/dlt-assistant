# public/ — 静态网站发布目录

本目录是 **Cloudflare Pages** 的构建输出目录（Build output directory = `public`），
包含由 GitHub Actions 自动生成、供网页展示的全部静态文件。

## 目录内容

| 路径 | 说明 |
| --- | --- |
| `index.html` | 移动端优先的分析主页（号码频率 / 热冷 / 遗漏 / 奇偶 / 大小 / 区间等） |
| `style.css` | 页面样式 |
| `app.js` | 纯 JavaScript 复算分析（与 `src/analyzer.py` 口径一致） |
| `data/` | 站点数据：`dlt_history.json`（历史开奖）、`recommendations.json`（A/B/C 娱乐推荐） |
| `reports/` | 历史 Markdown 分析报告（`report_YYYYMMDD.md` 等），由 GitHub Actions 每次运行同步 |

## 部署说明（Cloudflare Pages）

创建项目时配置：

- **Framework preset**：None
- **Build command**：留空
- **Build output directory**：`public`

> 本项目已提前生成静态文件，Cloudflare 无需执行构建，直接发布本目录即可。
> 每次 GitHub Actions 运行后会自动更新 `data/` 与 `reports/`，Cloudflare Pages 随之重新部署。

---

> ⚠️ 免责声明：本目录所有内容仅用于历史数据的娱乐性分析，**不预测彩票结果**。
> 彩票开奖为独立随机事件，请理性购彩、量力而行。
