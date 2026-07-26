# Ablation — v3 components

Per-fold so a group that only helps in one season cannot pass as a win.
Scored on rank correlation and haul pricing as well as MAE: v3 exists to
price the tail, and MAE alone rewards shading toward the mean.

## Spearman per gameweek (higher is better)

| config | n | 2025-26 |
|---|---|---|
| base (form+meta) | 33 | 0.7178 |
| + form_eb | 47 | 0.7176 |
| + career | 55 | 0.7180 |
| + understat | 64 | 0.7142 |
| + setpiece | 68 | 0.7141 |
| + opponent | 76 | 0.7145 |
| + market | 79 | 0.7141 |
| + schedule | 86 | 0.7146 |
| + manager | 90 | 0.7142 |
| + tournament | 97 | 0.7149 |
| all - form_eb | 83 | 0.7144 |
| all - career | 89 | 0.7149 |
| all - understat | 88 | 0.7178 |
| all - setpiece | 93 | 0.7140 |
| all - opponent | 89 | 0.7144 |
| all - market | 94 | 0.7143 |
| all - schedule | 90 | 0.7143 |
| all - manager | 93 | 0.7145 |
| all - tournament | 90 | 0.7142 |

## MAE (lower is better)

| config | n | 2025-26 |
|---|---|---|
| base (form+meta) | 33 | 0.9764 |
| + form_eb | 47 | 0.9768 |
| + career | 55 | 0.9803 |
| + understat | 64 | 0.9622 |
| + setpiece | 68 | 0.9581 |
| + opponent | 76 | 0.9580 |
| + market | 79 | 0.9595 |
| + schedule | 86 | 0.9599 |
| + manager | 90 | 0.9607 |
| + tournament | 97 | 0.9598 |
| all - form_eb | 83 | 0.9597 |
| all - career | 89 | 0.9593 |
| all - understat | 88 | 0.9786 |
| all - setpiece | 93 | 0.9602 |
| all - opponent | 89 | 0.9609 |
| all - market | 94 | 0.9607 |
| all - schedule | 90 | 0.9610 |
| all - manager | 93 | 0.9608 |
| all - tournament | 90 | 0.9607 |

## MAE, gameweeks 1-8 (lower is better)

| config | n | 2025-26 |
|---|---|---|
| base (form+meta) | 33 | 1.0798 |
| + form_eb | 47 | 1.0746 |
| + career | 55 | 1.0820 |
| + understat | 64 | 1.0544 |
| + setpiece | 68 | 1.0476 |
| + opponent | 76 | 1.0495 |
| + market | 79 | 1.0498 |
| + schedule | 86 | 1.0515 |
| + manager | 90 | 1.0504 |
| + tournament | 97 | 1.0497 |
| all - form_eb | 83 | 1.0517 |
| all - career | 89 | 1.0471 |
| all - understat | 88 | 1.0757 |
| all - setpiece | 93 | 1.0505 |
| all - opponent | 89 | 1.0527 |
| all - market | 94 | 1.0504 |
| all - schedule | 90 | 1.0506 |
| all - manager | 93 | 1.0502 |
| all - tournament | 90 | 1.0504 |

## P(haul) Brier (lower is better)

| config | n | 2025-26 |
|---|---|---|
| base (form+meta) | 33 | 0.0169 |
| + form_eb | 47 | 0.0170 |
| + career | 55 | 0.0169 |
| + understat | 64 | 0.0164 |
| + setpiece | 68 | 0.0164 |
| + opponent | 76 | 0.0164 |
| + market | 79 | 0.0164 |
| + schedule | 86 | 0.0164 |
| + manager | 90 | 0.0164 |
| + tournament | 97 | 0.0165 |
| all - form_eb | 83 | 0.0164 |
| all - career | 89 | 0.0165 |
| all - understat | 88 | 0.0170 |
| all - setpiece | 93 | 0.0165 |
| all - opponent | 89 | 0.0164 |
| all - market | 94 | 0.0164 |
| all - schedule | 90 | 0.0164 |
| all - manager | 93 | 0.0165 |
| all - tournament | 90 | 0.0164 |

