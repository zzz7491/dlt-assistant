# 生产回滚说明（Rollback Guide）

> 本文档**只说明如何回滚**，不执行任何回滚操作。
> 回滚属于生产修改，执行前必须走 `AGENTS.md` 的「生产修改强制规则 7 步流程」并获得用户确认。

## 基线信息

| 项目 | 值 |
|------|-----|
| **稳定标签** | `production-stable-v1.0` |
| **标签指向 commit** | `36d9bfc`（含 `a1e7e35` 首页错误提示修复） |
| **生产地址** | `https://500wan.mootlsv.com/` |
| **Cloudflare 项目** | `dlt-assistant`（自定义域名绑定至该生产分支） |
| **部署方式** | GitHub Actions → `wrangler pages deploy public` |

---

## 第 0 步：先确认线上真实状态（禁止靠缓存猜测）

在回滚前，**必须实际验证**线上当前版本，避免误判：

```bash
# 运行自动检查脚本（详见 scripts/check-production.sh）
bash scripts/check-production.sh

# 或手工核对关键特征
curl -sL "https://500wan.mootlsv.com/" | grep -i "recommendations.json\|final_recommendation.json"
curl -s -o /dev/null -w "%{http_code}\n" "https://500wan.mootlsv.com/"
```

确认异常属实且确属「线上版本偏离基线」后，再继续回滚。

---

## 第 1 步：本地切回稳定标签

```bash
cd <repo>
git fetch origin
# 方式 A：仅查看（detached HEAD，安全）
git checkout production-stable-v1.0

# 方式 B：将当前分支硬重置到标签（会丢弃标签之后的本地提交，谨慎）
git reset --hard production-stable-v1.0
```

标签 `production-stable-v1.0` 当前指向 `36d9bfc`，即已验证的生产基线。

---

## 第 2 步：重新部署到 Cloudflare Pages

### 方式 A：触发 GitHub Actions 自动部署（推荐）

```bash
# 手动触发 workflow_dispatch（需 gh 已登录）
gh api repos/zzz7491/dlt-assistant/actions/workflows/dlt-analysis.yml/dispatches \
  -X POST -F ref=master
```

 workflow 会在「部署到 Cloudflare Pages」步骤执行：

```bash
npx --yes wrangler@latest pages deploy public \
  --project-name dlt-assistant --branch master --commit-dirty=true
```

> 注意：部署步骤仅在仓库配置了 `CLOUDFLARE_API_TOKEN` secret 时执行；
> 且依赖前序「提交更新」步骤 `git push` 成功，否则 job 失败会跳过部署。
> 触发后务必在 Actions 页面确认该步骤**实际执行并成功**。

### 方式 B：本地 CLI 直接部署（需 `CLOUDFLARE_API_TOKEN` 环境变量）

```bash
export CLOUDFLARE_API_TOKEN="<your-token>"
npx --yes wrangler@latest pages deploy public \
  --project-name dlt-assistant --branch master --commit-dirty=true
```

---

## 第 3 步：线上验证（必须验证正式域名，禁止只看 *.pages.dev）

```bash
bash scripts/check-production.sh
# 期望结果：Result: PASS
# 且首页第 52 行错误提示引用 data/recommendations.json（非 final_recommendation.json）
```

验证矩阵：

| 维度 | 期望 |
|------|------|
| 首页 HTTP | 200 |
| `/app.js` `/data/dlt_history.json` `/data/recommendations.json` | 全部 200 |
| index.html 含「大乐透综合数据分析平台」 | 是 |
| index.html / app.js / recommendations.json 含 `final_recommendation` | 否 |
| recommendations.json 可解析 | 是 |

---

## 第 4 步：记录

回滚完成后，更新 `TASK_STATUS.md` 与 `CHANGELOG.md`，说明回滚原因、目标标签、验证结果。

---

## 紧急降级（仅当自动部署链路完全失效）

若 Actions / wrangler 均不可用，可临时用方式 B 从**任意一台已配置令牌的机器**
对当前 `public/` 目录执行 `wrangler pages deploy`，以恢复静态内容；
但代码来源仍必须是 `production-stable-v1.0` 标签，禁止使用未验证的本地改动。

---

## 红线

- ❌ 禁止未经「线上确认」仅凭缓存/猜测执行回滚。
- ❌ 禁止回滚到未经验证的 commit。
- ❌ 禁止 `git push -f` 强制覆盖远程 master（除非用户明确授权且已备份）。
- ❌ 禁止跳过正式域名验证。
