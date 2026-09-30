# P2-1 Recommendation Evaluation Baseline Report

Evaluation version: `p21-v1`
Data: 19148 → 26111 (1000 periods, 100 warmup excluded)
Evaluated draws: **900**
Random seeds: 25
Cost per ticket: 2.0 RMB
Elapsed: 1022.5s

## Strategy Comparison Table

| Strategy | N | Front Mean | Back Mean | Total Mean | >=3 Front | 2 Back | Prize Hits | Cost | Known Payout | ROI (lower bound) |
|---|---|---|---|---|---|---|---|---|---|---|
| A | 900 | 0.689 | 0.307 | 0.996 | 17 | 10 | 50 (0+0+50) | 1800.0 | 415.0 | -0.7694 (exact) |
| B | 900 | 0.681 | 0.342 | 1.023 | 14 | 10 | 60 (0+0+60) | 1800.0 | 350.0 | -0.8056 (exact) |
| C | 900 | 0.684 | 0.352 | 1.037 | 14 | 20 | 65 (0+0+65) | 1800.0 | 580.0 | -0.6778 (exact) |
| D | 900 | 0.672 | 0.323 | 0.996 | 9 | 11 | 57 (0+0+57) | 1800.0 | 490.0 | -0.7278 (exact) |
| SIMPLE_FREQ | 900 | 0.719 | 0.344 | 1.063 | 9 | 12 | 68 (0+0+68) | 1800.0 | 400.0 | -0.7778 (exact) |
| SELECTOR | 890 | 0.772 | 0.362 | 1.134 | 19 | 13 | 72 (0+0+72) | 1780.0 | 535.0 | -0.6994 (exact) |

## Random Baseline Statistics (multi-seed)

- Seeds: 25
- Total hit mean: 1.0481
- Total hit median: 1.05
- Total hit std: 0.0311
- Total hit p05: 1.0024
- Total hit p95: 1.1026
- Front hit mean: 0.7135
- Back hit mean: 0.3346

## Comparison vs Random

| Strategy | Total Mean | Diff vs Random | In p05-p95 | Within 1σ |
|---|---|---|---|---|
| A | 0.9956 | -0.0525 | NO | NO |
| B | 1.0233 | -0.0248 | YES | YES |
| C | 1.0367 | -0.0114 | YES | YES |
| D | 0.9956 | -0.0525 | NO | NO |
| SIMPLE_FREQ | 1.0633 | +0.0152 | YES | YES |
| SELECTOR | 1.1337 | +0.0856 | NO | NO |

## Interpretation

This report is a **historical measurement only**. It does NOT recommend
purchasing any lottery ticket or predict future outcomes.
Lottery draws are independent random events; any strategy
observed to outperform random over a finite sample
does not guarantee future performance.
