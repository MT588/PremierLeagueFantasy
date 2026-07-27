# v3 training report

Per-component expected points with a Monte-Carlo distribution, against v2
retrained under the identical walk-forward protocol.

Monte-Carlo draws per player-gameweek: 1500.

## Points accuracy

| fold | model | MAE | Spearman/GW | MAE GW1-8 | RMSE hauls>=8 | P(haul) Brier |
|---|---|---|---|---|---|---|
| 2023-24 | v3 | 0.9555 | 0.6918 | 1.0390 | 7.567 | 0.01583 |
| 2023-24 | v2 | 0.9680 | 0.6947 | 1.0639 | 7.844 | 0.01653 |
| 2024-25 | v3 | 0.9767 | 0.7083 | 1.0510 | 7.205 | 0.01446 |
| 2024-25 | v2 | 0.9842 | 0.7088 | 1.0680 | 7.257 | 0.01530 |
| 2025-26 | v3 | 0.9509 | 0.7167 | 1.0409 | 7.553 | 0.01642 |
| 2025-26 | v2 | 0.9575 | 0.7202 | 1.0609 | 7.531 | 0.01687 |
| 2025-26 H2 | v3 | 0.9272 | 0.7218 | nan | 6.959 | 0.01540 |
| 2025-26 H2 | v2 | 0.9171 | 0.7229 | nan | 7.199 | 0.01617 |

## Distribution quality (v3)

| fold | P(haul) predicted | P(haul) empirical | P(return) predicted | P(return) empirical | p10-p90 coverage |
|---|---|---|---|---|---|
| 2023-24 | 0.0168 | 0.0180 | 0.0903 | 0.0828 | 0.939 |
| 2024-25 | 0.0172 | 0.0164 | 0.0922 | 0.0863 | 0.937 |
| 2025-26 | 0.0120 | 0.0181 | 0.0802 | 0.0863 | 0.929 |
| 2025-26 H2 | 0.0155 | 0.0173 | 0.0855 | 0.0839 | 0.944 |

## P(haul) reliability, per fold

### 2023-24

| predicted | empirical | n |
|---|---|---|
| 0.0074 | 0.0077 | 26623 |
| 0.0905 | 0.1031 | 1338 |
| 0.1570 | 0.1804 | 449 |
| 0.2247 | 0.2472 | 178 |
| 0.2873 | 0.2717 | 92 |

### 2024-25

| predicted | empirical | n |
|---|---|---|
| 0.0069 | 0.0068 | 24776 |
| 0.0843 | 0.0808 | 1225 |
| 0.1475 | 0.1121 | 464 |
| 0.2065 | 0.1886 | 228 |
| 0.2676 | 0.3333 | 123 |
| 0.3291 | 0.3684 | 57 |

### 2025-26

| predicted | empirical | n |
|---|---|---|
| 0.0060 | 0.0113 | 27941 |
| 0.0969 | 0.1156 | 960 |
| 0.1688 | 0.1903 | 289 |
| 0.2380 | 0.2826 | 92 |

### 2025-26 H2

| predicted | empirical | n |
|---|---|---|
| 0.0076 | 0.0097 | 14270 |
| 0.1029 | 0.0921 | 619 |
| 0.1783 | 0.2123 | 179 |
| 0.2538 | 0.2105 | 57 |

## Choices made per fold

| fold | goals | assists | saves | team | bonus | DC available |
|---|---|---|---|---|---|---|
| 2023-24 | nb | poisson | poisson | poisson | bps | False |
| 2024-25 | nb | poisson | poisson | poisson | bps | False |
| 2025-26 | nb | poisson | poisson | poisson | direct | False |
| 2025-26 H2 | nb | poisson | poisson | poisson | direct | True |

## Captaincy blend

The captaincy view ranks by `ev + 0.0 x P(haul)`.

Both curves below are measured over the top-3 shortlist of every held-out gameweek across all folds. The rule is among the weights whose mean points stay within 2% of the best available, the one with the highest shortlist haul rate — but only if that gain clears one standard error (0.02337) of the lambda=0 rate, otherwise zero.

**The blend fits to zero.** No weight buys a haul rate distinguishable from ranking on expected points alone: the best candidate gained one extra haul across 399 picks. Expected points already rank the ceiling picks, so the view ranks by them and surfaces P(haul), P(return) and p90 as sortable columns instead of folding a weight the data rejects into a single number.

| lambda | mean points of shortlist | haul rate of shortlist |
|---|---|---|
| 0.0 **<-** | 7.348 | 0.3208 |
| 1.0 | 7.333 | 0.3208 |
| 2.0 | 7.286 | 0.3183 |
| 4.0 | 7.311 | 0.3233 |
| 6.0 | 7.281 | 0.3208 |
| 8.0 | 7.296 | 0.3233 |
| 12.0 | 7.301 | 0.3208 |
| 20.0 | 7.318 | 0.3208 |
| 50.0 | 7.271 | 0.3183 |
| 200.0 | 7.336 | 0.3208 |

## Acceptance

Fold `2025-26` — **PASSED**

| check | v3 | v2 | result |
|---|---|---|---|
| Spearman/GW (within -0.005) | 0.71673 | 0.72024 | pass |
| P(haul) Brier (lower) | 0.01642 | 0.01687 | pass |
| MAE (within +0.01) | 0.95085 | 0.95749 | pass |

### Tail RMSE, over the folds where the component is fittable

The acceptance fold is excluded: it tests on 2025-26 while training only on
earlier seasons, so its actuals carry defensive-contribution points the
component had no data to fit. Every fold below has to improve.

| fold | v3 | v2 | result |
|---|---|---|---|
| 2023-24 | 7.567 | 7.844 | pass |
| 2024-25 | 7.205 | 7.257 | pass |
| 2025-26 H2 | 6.959 | 7.199 | pass |

Excluded: `2025-26`.
