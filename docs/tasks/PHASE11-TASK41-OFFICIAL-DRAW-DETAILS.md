# DLT Phase 11 Task #41 — Official draw details

Date: 2026-10-09 (Asia/Shanghai)

## Baseline and incident

- Production before repair showed issue 26113 (2026-10-05); issue 26114 was officially drawn on 2026-10-07.
- Scheduled runs 91–95 failed after the 26114 published snapshot failed the pre-publish hash gate.
- The original 26114 frozen fields and displayed recommendation were unchanged; only its stored digest was inconsistent with the canonical hasher. Commit dc4fe129 corrected the digest. Independent recomputation passes 26112, 26113 and 26114.
- Commit 2bb89f4 adds a workflow-file-only push trigger. Run 37923370464 succeeded, deployed Pages, and production shows 26114, target 26115, and authoritative 26114 review.
- Rollback for these changes: use the preceding Git commits. Do not remove the frozen snapshot or recalculate its numbers.

## This work package

- Source: Jiangsu Provincial Sports Lottery Center public draw list and its linked official notices.
- Append-only archive public/data/draw_details.json, separate from the number-only data/dlt_history.json.
- Accept a notice only when issue/date/front/back match the number history. Store sales, seven prize tiers (basic/extra for first and second), per-ticket amounts, jackpot, deadline and source URL.
- On an unavailable or incomplete official notice, keep the last verified archive and show a pending state for the latest issue. Do not block number updates or invent monetary values.
- A post-publish snapshot integrity gate blocks a bad snapshot from being committed.
- Page selectors show verified recent draws with an official source link.

## Validation

- Isolated branch workflow 37923877821: 10 notices parsed.
- Isolated branch workflow 37924025556: PASS for cross-check against history, all prize tiers and payout arithmetic; issue 26114 values match the source notice.
- public/app.js syntax checked with node --check.
- Production deployment and live page testing are still required after merge.

## Remaining gaps

- Initial index exposes ten recent draws. Older details must be backfilled before this can be called a complete all-period archive.
- Official next-draw sale cutoff, expected first prize, special notices, and historical rule variations need separate verified contracts.
- Automatic detection of source corrections and source redundancy remain future work.
- The official sporttery API was blocked by its security layer in the cloud browser; no API scraping was introduced on this evidence.

## Source

https://www.js-lottery.com/wfzq/dlt/data
