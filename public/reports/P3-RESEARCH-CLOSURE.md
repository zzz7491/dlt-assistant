# P3 Research Phase Closure

## Per-Gate Summary

| Gate | Population | Key evidence | Status |
|---|---|---|---|
| P3-1 | 2930 draws | 1000/1000 exact overlap; SHA ba4bfb09 frozen | PASS |
| P3-2 | 1930 OOS | no window confirmed better; A/D KEEP_1000; B NO_WINDOW_EDGE; cap INSUFFICIENT | PASS |
| P3-3 | 1930 OOS | no identifiable predictive feature; D-ablation all Holm p=1.0; ML not justified | PASS |
| P3-4 | 1930 OOS | no robust selector edge; noise-compatible; seed/era/unstable; ML not warranted | PASS |
| P3-5 | 1930 OOS | closure: direction KEEP_CURRENT_TEMPORARILY; NO production change | PASS |

## WHAT WE LEARNED
- The production chain is a well-implemented **entertainment/analytics** system, not a predictor.
- The strongest fair null (frequency-matched / random-choice among A/B/C/D) is NOT beaten by the CURRENT selector.
- Candidate sets are near-interchangeable (pairwise diff ≈ 0); selection effects are small and unstable.
- C is non-reproducible (seed=None) and its seed×era performance is unstable.

## WHAT FAILED TO SHOW EVIDENCE
- No historical-statistics feature (freq/omission/temperature/overlap/sum/span/odd-even/size/structure/risk) has OOS value (P3-3).
- No selector mechanism has a holdout-confirmed, seed/era-robust edge (P3-4).
- No ML justification (P3-3, P3-4).

## WHAT REMAINS UNKNOWN
- Whether an INDEPENDENT new hypothesis (outside the historical-statistics family) could have signal.
- The exact source of the early P2-2 apparent edge (seed=None non-reproducibility is the leading candidate).

## WHAT PRODUCTION MUST NOT CLAIM
- Improving win probability / predicting next draw / 'AI prediction' / high-probability numbers / 'stable win' / hit model.
- Historical statistics are ENTERTAINMENT/ANALYTIC/TREND and EXPLANATION material only.

## WHAT FUTURE RESEARCH REQUIRES
- A NEW, independent testable hypothesis + pre-registered protocol (docs/research/EXPERIMENT-CONTRACT.md).
- No feature mining / selector tuning / ML escalation until then.
