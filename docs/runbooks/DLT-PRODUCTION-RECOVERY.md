# DLT PRODUCTION RECOVERY RUNBOOK

P4-4 operational recovery runbook. All commands are read-only or dry-run by
default. Destructive restore requires explicit human authorization (R9).
Nothing here runs the scheduler/publisher or writes production D1.

## Tooling

| Tool | Purpose | Default safety |
|------|---------|----------------|
| `scripts/check_production_readiness.py` | read-only PASS/FAIL + failure_class | read-only |
| `scripts/recovery_check.py` | inspect/validate/compare + authorized restore | dry-run default |
| `scripts/backup_published_store.py` | append-only backup + hash manifest | no auto-delete |
| `scripts/check_cloudflare_account.py` | Cloudflare account guard | fail-closed |

## 0. Daily pre-flight

```bash
# read-only: is the production healthy?
python3 scripts/check_production_readiness.py --offline
# expected on clean tree: RESULT: PASS (account 8770e491... match)
```

If `TRACKED_MODIFICATIONS` appears while mid-work, that is expected locally;
on a clean deployment it should be clean.

## 1. Corrupt / missing published store (symptom: HTTP 200 but JSON broken or gone)

**Diagnosis**
```bash
python3 scripts/recovery_check.py --inspect      # parse status + issues
python3 scripts/recovery_check.py --validate     # verify every snapshot_hash
```

**Do NOT**: re-run scheduler/publisher to "regenerate" history (R1/R3/R5/R11).
The published store is immutable; a corrupt store fails closed (P4-3 F1).

**Safe recovery**
```bash
# create a current backup before touching anything (if store still parseable)
python3 scripts/backup_published_store.py
# if the store is on disk and tracked in Git, restore from Git (authoritative):
git show HEAD:public/data/published_recommendations.json > /tmp/pub.json
python3 scripts/recovery_check.py --check-backup /tmp/pub.json <manifest>
# then explicit, human-authorized restore:
python3 scripts/recovery_check.py --restore /tmp/pub.json \
    --manifest <manifest.json> --authorize "restore 26112/26113 from Git after corrupt-store incident"
# R10: re-verify
python3 scripts/recovery_check.py --validate
```

**Verification**: 26112 hash = `bea8ef87f3f137238686ae52712f922956215408f0cf54187b9295d8f1ae5fad`,
26113 present and unchanged.

## 2. D1 unavailable (symptom: `write_recommendations_d1.py` / `export_recommendations_json.py` fail in CI)

**Diagnosis**: check Cloudflare dashboard + `CLOUDFLARE_API_TOKEN` validity.
**Safe**: `INSERT OR IGNORE` + `UNIQUE(target_issue,strategy,idx)` make D1
writes idempotent — simply re-run after D1 is reachable. No restore needed.
Local JSON publication is independent of D1.

## 3. Cloudflare auth mismatch (symptom: deploy refused / API error 10000)

**Diagnosis**
```bash
python3 scripts/check_cloudflare_account.py        # live whoami
python3 scripts/check_production_readiness.py --offline  # cache-based
```
**Do NOT**: bypass the guard or deploy to the wrong account (R7).
**Safe recovery**: `wrangler login` as `lsv3255@gmail.com` (account
`8770e4917f904aed5df91c883cf058af`) in an interactive terminal, or set a valid
`CLOUDFLARE_API_TOKEN` for that account. Re-run the guard → PASS, then deploy
via `scripts/deploy_production.sh`.

## 4. Conflict on an issue (symptom: upsert returns `conflict`)

**Diagnosis**: the issue already has a *different* immutable snapshot
(e.g. algorithm_version / seed changed, or a manual divergence).
**Do NOT**: overwrite by regenerating (R5). Investigate the root cause.
**Safe**: keep the original; if the new numbers are genuinely wrong, that is a
product bug to fix in the *future* issue, not by rewriting history.

## 5. Scheduler crash before publish

**Diagnosis**: CI step `python -m src.scheduler --once` exit ≠ 0.
**Safe**: fix the crash, re-run. `recommendations.save` merges by
`(target_issue, strategy, idx)` — re-runs are safe. No restore needed.

## 6. Deployment failure

**Diagnosis**: `wrangler pages deploy` exit ≠ 0.
**Note** (R12): a deployment failure is NOT a publication failure — the local
JSON + D1 data are intact; only the Pages static bundle is not updated.
**Safe**: re-run `bash scripts/deploy_production.sh` (guard-protected).

## 7. GitHub push race

**Diagnosis**: `git push` rejected (non-fast-forward).
**Safe**: `git pull --rebase origin master` (audit for overlap), re-run
critical tests + immutable hash check, then push. Never force push.

## Invariants reminder (R1–R12)

published snapshots are never rewritten; corrupt stores fail closed; restore
only from a validated backup/Git (never recomputation); same-issue retry is
idempotent; conflicts are not resolved by regeneration; history lag never
auto-skips; CF mismatch fails closed; recovery is dry-run by default;
destructive restore needs explicit authorization; hashes are re-verified after
restore; recovery never runs predictive optimization; deployment failure ≠
publication failure.
