# P3-2 Window Sensitivity & Strict OOS Study

dataset sha256 `ba4bfb09d46aa66a` · common OOS 1930 draws (dev 1544 / final holdout 386) · equivalence True

> Window semantics: target t 之前 issues[:t]；rolling W 取最后 W；FULL 为 expanding（t 之前全部）。target/未来绝不进入窗口。FULL 在历史不足 1000 期时 = rolling 1000（min(n,W)）。所有 A/B/C/D 调用真实生产 recommend()；C 为不变随机对照。

## Random Baseline (invariant, 50 seeds)

mean 1.0473 · median 1.0464 · std 0.0236 · p05 1.011 · p95 1.0819 · p99 1.1066

## Strategy × Window (mean total hits, common 1930 OOS)

| strategy | 50 | 100 | 300 | 500 | 1000 | FULL |
|---|---|---|---|---|---|---|
| A | 1.0269 | 1.044 | 1.0383 | 1.0301 | 1.0648 | 0.9974 |
| B | 1.0378 | 1.0192 | 1.0606 | 1.0803 | 1.0653 | 1.0539 |
| D | 1.0472 | 1.0223 | 1.0451 | 1.0518 | 1.0513 | 1.0259 |

## FULL vs 1000 (key comparison)

- A: Δ=-0.06736 CI[-0.11295,-0.02176] (excludes 0) p=0.05297; temporal Δ early/mid/late=-0.0575/-0.0373/-0.1071
- B: Δ=-0.0114 CI[-0.06114,0.03782] (contains 0) p=0.4018; temporal Δ early/mid/late=0.0279/-0.0855/0.0233
- D: Δ=-0.02539 CI[-0.04715,-0.00363] (excludes 0) p=0.30685; temporal Δ early/mid/late=-0.0202/-0.0576/0.0015

## Development Selection (frozen before holdout)

- A: dev-best window = 1000 (mean 1.0661 vs 1000 1.0661)
- B: dev-best window = 500 (mean 1.0861 vs 1000 1.068)
- D: dev-best window = 50 (mean 1.0699 vs 1000 1.0693)

## Final Holdout Confirmation

- A: window 1000 → holdout 1.0596 vs 1000 1.0596 (Δ 0.0, p 1.0) → CONFIRMED=False
- B: window 500 → holdout 1.057 vs 1000 1.0544 (Δ 0.00259, p 0.48526) → CONFIRMED=False
- D: window 50 → holdout 0.956 vs 1000 0.9793 (Δ -0.02332, p 0.41479) → CONFIRMED=False

## Per-Strategy Decision

- **A: KEEP_1000**
- **B: NO_WINDOW_EDGE**
- **D: KEEP_1000**

## Production 1000 Cap Finding

**INSUFFICIENT**

(storage retention 与 strategy analysis window 是不同架构问题；本 Gate 不改 production cap)

## Limitations

- cross-source verification = NO（P3-1 单一源）；结论基于 500 单一源 full history。
- D 的 temperature 子窗口（近30/近100）为硬编码 clamp，改外层窗口对它们影响有限（effective window 语义已在 report 记录）。
- 窗口比较为 exploratory；任一 SUPPORTED 结论仍需在 P3-3/P2-4 前做更强 OOS 确认。

## Production Integrity

- production cap / recommender / strategies / selector / final_score / 26112 / frontend: UNCHANGED
- this gate: research only
