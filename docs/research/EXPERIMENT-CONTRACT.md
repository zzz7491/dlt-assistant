# Research Experiment Contract (P3 onward)

Every future research experiment MUST satisfy all of the following:

1. **Hypothesis before result** — a falsifiable hypothesis + mechanism, written before running.
2. **Immutable dataset version** — pinned dataset SHA256 (current: ba4bfb09...).
3. **Walk-forward** — target t uses only issues < t (no future leakage).
4. **Dev/holdout split** — fixed ratio, frozen; holdout used ONCE for confirmation.
5. **Baseline** — at least a fair null (frequency-matched / random-choice) plus a simple baseline.
6. **Effect size + CI** — report effect size and bootstrap CI, not p-value alone.
7. **Multiple-comparison correction** — Holm (primary) and/or BH-FDR; pre-declared family.
8. **Seed policy** — deterministic seeds; no post-hoc seed selection; document proxy percentiles.
9. **Negative-result retention** — keep and commit null results; do not discard.
10. **No post-hoc production change** — research must not modify the production algorithm; any change goes through a separately authorized production-change Gate.

STOP rules (inherited from P3-5): no feature mining within the current historical-statistics family, no selector tuning, no ML escalation, until a NEW independent hypothesis is pre-registered under this contract.
