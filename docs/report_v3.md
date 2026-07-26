# v3 training report

Per-component expected points with a Monte-Carlo distribution, against v2
retrained under the identical walk-forward protocol.

Monte-Carlo draws per player-gameweek: 1500.

## Points accuracy

| fold | model | MAE | Spearman/GW | MAE GW1-8 | RMSE hauls>=8 | P(haul) Brier |
|---|---|---|---|---|---|---|
| 2023-24 | v3 | 0.9476 | 0.6925 | 1.0300 | 7.600 | 0.01583 |
| 2023-24 | v2 | 0.9680 | 0.6947 | 1.0639 | 7.844 | 0.01653 |
| 2024-25 | v3 | 0.9686 | 0.7090 | 1.0411 | 7.237 | 0.01446 |
| 2024-25 | v2 | 0.9842 | 0.7088 | 1.0680 | 7.257 | 0.01530 |
| 2025-26 | v3 | 0.9449 | 0.7175 | 1.0341 | 7.576 | 0.01642 |
| 2025-26 | v2 | 0.9575 | 0.7202 | 1.0609 | 7.531 | 0.01687 |
| 2025-26 H2 | v3 | 0.9210 | 0.7220 | nan | 6.988 | 0.01540 |
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

The captaincy view ranks by `ev + 12.0 x P(haul)`. Both
curves below are measured over the top-3 shortlist of every held-out gameweek across all folds; the chosen weight is
the largest whose mean points stay within 2% of the best available.

| lambda | mean points of shortlist | haul rate of shortlist |
|---|---|---|
| 0.0 | 7.368 | 0.3258 |
| 1.0 | 7.348 | 0.3208 |
| 2.0 | 7.311 | 0.3208 |
| 4.0 | 7.198 | 0.3133 |
| 6.0 | 7.281 | 0.3208 |
| 8.0 | 7.318 | 0.3233 |
| 12.0 **<-** | 7.313 | 0.3233 |

## Acceptance

Fold `2025-26` — **FAILED**

| check | v3 | v2 | result |
|---|---|---|---|
| Spearman/GW (higher) | 0.71747 | 0.72024 | FAIL |
| RMSE hauls>=8 (lower) | 7.57627 | 7.53069 | FAIL |
| P(haul) Brier (lower) | 0.01642 | 0.01687 | pass |
| MAE (within +0.01) | 0.94492 | 0.95749 | pass |
