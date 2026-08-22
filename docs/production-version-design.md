# 生产版本标识方案设计（Phase 10 Recovery R5 · Step 4）

> 本文档只做**方案设计**，不修改任何生产文件（含首页）。
> 实施需等待用户确认（R5 Step 4 明确要求「等待确认后再实施」）。

## 背景

当前生产环境 `https://500wan.mootlsv.com/` 已冻结于 `production-stable-v1.0`（`36d9bfc`）。
但「线上到底跑的是哪个版本 / 哪个 commit」**无法在页面之外被独立确认**，只能靠内容特征反推
（如 grep `final_recommendation` 是否残留）。这不利于自动验收与回滚判定。

目标：引入一个**稳定、可独立校验、零侵入首页**的版本标识机制，使监控脚本可一键确认
「线上版本 = 基线版本」。

## 方案 A：HTML meta 版本

在 `public/index.html` 的 `<head>` 中增加：

```html
<meta name="production-version" content="production-stable-v1.0" />
<meta name="production-commit" content="36d9bfc" />
```

- ✅ 优点：浏览器内可直接查看；监控脚本 curl 首页即可 grep 校验。
- ❌ 缺点：**需要修改冻结中的首页**。当前 `AGENTS.md` 冻结纪律禁止修改首页/UI，
  必须经完整 7 步生产修改流程并获用户明确授权；改动面虽小但有纪律成本。

## 方案 B：version.json（推荐）

新增静态文件 `public/version.json`，随部署发布：

```json
{
  "version": "production-stable-v1.0",
  "tag": "production-stable-v1.0",
  "commit": "36d9bfc",
  "deployedAt": "2026-08-22T13:09:00Z"
}
```

- ✅ 优点：
  1. **零侵入**：不触碰首页 / UI / 算法 / 数据结构，完全符合冻结纪律。
  2. **独立可校验**：`curl /version.json` 即可比对，监控脚本直接判等。
  3. **溯源完整**：同时携带 version + commit + 部署时间。
  4. **可自动化**：可由 workflow 部署步骤在 `wrangler pages deploy` 前自动写入
     （`commit` 取 `$GITHUB_SHA`，`deployedAt` 取 `date -u`），**每次部署自动同步，杜绝手工遗漏**。
- ❌ 缺点：需保证文件随部署更新（由 workflow 生成即可解决）。

## 方案 C：release.json

与 B 类似，但承载更多发布元信息（changelog 链接、环境、构建号、组件版本等）。

- ✅ 优点：信息最全，便于以后做发布看板。
- ❌ 缺点：与 B 本质相同，当前阶段只需「版本 + commit」即可，**属于过度设计**。

## 选择结论

**推荐方案 B（version.json）。**

理由：
1. 最稳定 —— 不改动冻结的首页，规避纪律风险；
2. 最轻量 —— 单一静态文件，监控脚本可直接比对；
3. 最可自动化 —— workflow 部署步骤自动写入，始终与部署同步；
4. 对比 A（需改首页）、C（过度设计），B 在当前阶段性价比最高。

## 建议落地方式（待用户确认后实施）

1. 新增 `public/version.json`（初始内容对齐 `production-stable-v1.0` / `36d9bfc`）。
2. workflow 部署步骤在 `wrangler pages deploy` 前插入：
   ```bash
   cat > public/version.json <<EOF
   {"version":"production-stable-v1.0","tag":"production-stable-v1.0","commit":"${GITHUB_SHA:0:7}","deployedAt":"$(date -u +%Y-%m-%dT%H:%M:%SZ)"}
   EOF
   ```
3. 监控脚本（Step 3）可增加可选增强：拉取 `/version.json`，比对 `commit` 与本地标签 commit，
   输出 `Version: MATCH / MISMATCH`，实现「线上 = 基线」的硬校验。
4. 全部改动仍走 7 步流程（任务编号 → baseline → 本地验证 → commit → 部署 → 正式域名验证 → CHANGELOG）。
