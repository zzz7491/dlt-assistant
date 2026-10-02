# P4-5 DAILY PIPELINE FAILURE-MODE AUDIT (F1–F24)

For each mode: DETECTION · CURRENT BEHAVIOR · DATA RISK · SAFE TO RETRY ·
AUTO RETRY ALLOWED · HUMAN ACTION · DESIRED (post P4-5).

| F# | Mode | Detection | Current behavior | Data risk | Safe retry | Auto retry? | Human action | P4-5 desired |
|----|------|-----------|------------------|-----------|------------|-------------|--------------|--------------|
| F1 | GitHub checkout/fetch fail | step exit≠0 | job fails early | none (nothing written yet) | yes | yes (rerun) | none | surface exit; no publication touched |
| F2 | dependency install fail | pip exit≠0 | job fails before scheduler | none | yes | yes | none | surface exit |
| F3 | history source unavailable | scheduler scrape error → SystemExit(1) | job stops | `data/dlt_history.json` not updated | yes | no (data fetch) | check 500彩票网 | classify HISTORY_SOURCE_FAILURE |
| F4 | malformed history update | validator / JSON parse error | scheduler fails or validator skip | corrupt history possible | conditional | no | inspect history | HISTORY_VALIDATION_FAILURE |
| F5 | history unchanged | no new issues | normal no-op | none | yes | yes | none | NOOP_NO_CHANGE |
| F6 | history lag behind published | published_latest>history_latest | scheduler targets already-published issue → conflict/unchanged | none (conflict protects) | yes | yes (idempotent) | none | explicit HISTORY_LAG + target_already_published (P4-5 P11) |
| F7 | scheduler exception | SystemExit(1) | job stops before publisher | partial `reports/*` possible | yes | no | fix crash | SCHEDULER_FAILURE + exit 1 (P4-5 P12/D5) |
| F8 | scheduler partial artifact | reports incomplete | publisher `--safe` may build recs from partial | display could be odd | yes | no | inspect | publisher reads D1-locked values, not raw partial |
| F9 | publisher corrupt store | upsert → `corrupt` | fail-closed, no write | none (P4-3 F1) | yes | no | restore via backup/Git | PUBLICATION_CORRUPT classified (P4-5) |
| F10 | publisher conflict | upsert → `conflict` | original preserved | none | yes | no | investigate | PUBLICATION_CONFLICT classified |
| F11 | publisher unchanged retry | upsert → `unchanged` | no write | none | yes | yes | none | D7: legitimate idempotent result |
| F12 | D1 unavailable | wrangler d1 execute exit≠0 | `set +e` continue; previously silent | D1 stale (local JSON fine) | yes | yes (idempotent) | check CF/D1 | LOCAL_PUBLISHED_D1_FAILED + D1_FAILURE visible (P4-5 P15) |
| F13 | D1 duplicate lock | INSERT OR IGNORE no-op | expected (一期固定) | none | yes | yes | none | D13/D15: reuse authoritative value |
| F14 | backup failure | backup script exit≠0 | N/A pre-P4-5 (no backup step) | would publish without safety net | yes | no | none | P4-5 P9: backup-failure blocks publisher (D2) |
| F15 | git commit nothing-to-commit | `git diff --cached --quiet` | "无变更，跳过提交" | none | yes | yes | none | NOOP recognized as normal (D17) |
| F16 | git push race | push rejected (non-fast-forward) | old: blind `pull --rebase \|\| true` → could rebase over unknown changes | low | yes | no | audit overlap | P4-5 P14: overlap-aware rebase, fail-closed on overlap, never force |
| F17 | git push auth failure | push exit≠0 (credentials) | old: `git push` hard-fails the step | none | yes | no | credentials | GIT_PUSH_FAILURE classified |
| F18 | Cloudflare account mismatch | guard exit 1 | blocks deploy | wrong-account deploy prevented | no | no | switch identity | CLOUDFLARE_ACCOUNT_MISMATCH (P4-5 P16) |
| F19 | Cloudflare OAuth/token failure | wrangler whoami/deploy fail | pre-P4-5: ambiguous | none (deploy only) | no | no | refresh token | CLOUDFLARE_AUTH_FAILURE, ≠ publication failure (D12) |
| F20 | Pages deploy failure | wrangler pages deploy exit≠0 | deploy step fails | Pages stale (data fine) | yes | yes (same artifact) | none | DEPLOY_FAILURE, ≠ publication failure (D12) |
| F21 | workflow cancelled mid-run | GitHub cancel | partial run | partial artifacts | yes | no | rerun | concurrency group ensures no overlapping writer |
| F22 | concurrent scheduled/manual | two jobs same window | `concurrency.group: experiment-ci` + `cancel-in-progress:false` serialize | none | yes | yes | none | D14: lock-protected |
| F23 | retry after partial failure | manual rerun | deterministic (P4-1) + D1 INSERT OR IGNORE + upsert unchanged/conflict | none | yes | yes | none | D15: retry reuses authoritative snapshot |
| F24 | next scheduled run after previous | cron catches up | idempotent path | none | yes | yes | none | same authoritative snapshot; no new one |

## Confirmed in-scope gaps fixed by P4-5
- **G-5a**: no pre-run backup before publisher write → P9 backup step (D1/D2).
- **G-5b**: no local pre-publish integrity gate → P10 `check_local_prepublish.py`.
- **G-5c**: history-lag not surfaced → P11 explicit `history_lag` / `target_already_published`.
- **G-5d**: D1 failure swallowed → P15 `LOCAL_PUBLISHED_D1_FAILED` + `D1_FAILURE`.
- **G-5e**: blind `git pull --rebase || true` → P14 overlap-aware, fail-closed, no force.
- **G-5f**: no failure taxonomy / status artifact → P12/P17 `ops_status.py` + `last-run-status.json`.
- **G-5g**: deploy auth vs account vs api vs deploy not distinguished → P16.

## Not defects (by design, retained)
- `--safe` publisher never blocks the pipeline (F9/F10 fail-closed internally; display not
  written on conflict/corrupt).
- D1 is a double-write mirror; local JSON publication is authoritative for the static
  frontend. D1 failure is recoverable and idempotent.
