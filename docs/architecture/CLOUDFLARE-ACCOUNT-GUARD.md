# DLT Cloudflare Account Guard

## 目的

DLT 生产部署会触发 Cloudflare Pages `dlt-assistant` 发布。若 Wrangler 当前
登录的 Cloudflare 账号不是 DLT 生产账号，部署会落到错误账号下的同名项目，
造成资源错乱。本 Guard 在**任何 `wrangler pages deploy` 之前**强制校验账号，
不匹配即 fail-closed（退出码 1），阻断部署。

本 Guard 是**工程安全机制**，不影响 recommendation semantics（不触碰
scoring / weights / algorithm / analysis window / snapshot / UI）。

## DLT 生产 Cloudflare 身份

| 项 | 值 | 说明 |
|---|---|---|
| **Account ID（权威身份）** | `8770e4917f904aed5df91c883cf058af` | 唯一安全判断依据 |
| Human-readable label | `lsv3255@gmail.com` | 仅用于人类诊断，不作为安全键 |
| Pages 项目 | `dlt-assistant`（`dlt-assistant.pages.dev`，自定义域名 `500wan.mootlsv.com`） | |
| D1 | `dlt-draws`（db `d99a8443-f8f3-4baa-8b21-a061e28757e0`） | |
| 错误账号（曾误登） | `jxmm2025@my.com` / `6bbedf3d4f904606559e551e6c19bc9a` | Cloudflare API error 10000 根因 |

## 规则

1. **Account ID 是权威身份**。不依赖 email 字符串做安全判断。
2. 任何 DLT 生产部署前必须执行 `scripts/check_cloudflare_account.py`。
3. 账号不匹配 / 无法确定 / wrangler 命令失败 / 输出歧义 → **FAIL-CLOSED**（exit 1，不得部署）。
4. **不得**通过删除 Guard、注释 Guard、跳过 Guard 强行部署。
5. Guard 不输出任何 OAuth / API token / secret 值；不自动 login / logout / 切号。
6. 其他项目可能使用不同的 Cloudflare 账号；DLT 部署必须通过本 Guard。账号不匹配时正确做法是**切换 Wrangler identity** 到 `lsv3255@gmail.com`（account `8770e491...`）后重跑，而非绕过。

## 集成点

- **CI**：`.github/workflows/dlt-analysis.yml` 两个 `wrangler pages deploy` step
  之前各插入一个 `Cloudflare Account Guard` step，调用 `python scripts/check_cloudflare_account.py`。
- **本地/manual**：`scripts/deploy_production.sh`（可选 `--offline` / `--ci`）——先跑 Guard，PASS 后才 `wrangler pages deploy`。

## 行为

- 默认（live）：`wrangler whoami`（只读）解析 Account ID；失败则回退
  本地 `.wrangler` cache，再回退 `CLOUDFLARE_ACCOUNT_ID` env（CI）。
- `--offline`：仅读 `.wrangler/cache/wrangler-account.json`。
- `--ci`：仅读 `CLOUDFLARE_ACCOUNT_ID` env。
- PASS（实际 == 期望）→ exit 0；否则 → exit 1 并打印期望/实际 Account ID 与处置建议。

## 测试

`tests/test_cloudflare_account_guard.py` 覆盖：正确账号、错误账号、无账号、
malformed 输出、wrangler 命令失败、多账号歧义、secret 不泄漏（共 17 测试）。

## 禁止

- 不记录 OAuth / API token / secret 到仓库。
- 不 force push / 不绕过 Guard 部署。
