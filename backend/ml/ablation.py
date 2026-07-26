"""Feature-group ablation on the 2025-26 fold: cumulative additions over the
v1-ish base, then leave-one-out on the full set. Writes a markdown table."""

import logging
from pathlib import Path

from app.db import engine
from ml.features import FEATURES_BY_GROUP, build_training_frame
from ml.metrics import points_metrics
from ml.train_v2 import coerce_features, run_fold

log = logging.getLogger(__name__)

ARTIFACTS = Path(__file__).resolve().parent / "artifacts"
BASE_GROUPS = ["form", "meta"]
ADD_ORDER = [
    "career",
    "opponent",
    "understat",
    "market",
    "schedule",
    "manager",
    "setpiece",
]
FOLD_YEAR, FOLD_SEASON = 2024, "2025-26"


def features_for(groups: list[str]) -> list[str]:
    return [f for g in groups for f in FEATURES_BY_GROUP[g]]


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    df = coerce_features(build_training_frame(engine))
    test = df[df["season_name"] == FOLD_SEASON]

    rows = []

    def evaluate(label: str, groups: list[str]) -> dict:
        preds, _ = run_fold(df, FOLD_YEAR, FOLD_SEASON, features=features_for(groups))
        m = points_metrics(test, preds)
        rows.append(
            (
                label,
                len(features_for(groups)),
                m["mae"],
                m["spearman_per_gw"],
                m["mae_top50"],
            )
        )
        log.info("%-28s mae=%.4f rho=%.4f", label, m["mae"], m["spearman_per_gw"])
        return m

    groups = list(BASE_GROUPS)
    evaluate("base (form+meta)", groups)
    for g in ADD_ORDER:
        groups.append(g)
        evaluate(f"+ {g}", groups)

    all_groups = BASE_GROUPS + ADD_ORDER
    for g in ADD_ORDER:
        evaluate(f"all - {g}", [x for x in all_groups if x != g])

    lines = [
        f"# Ablation — fold {FOLD_SEASON}\n",
        "| config | n_features | MAE | Spearman/GW | top-50 MAE |",
        "|---|---|---|---|---|",
    ]
    for label, n, mae, rho, top in rows:
        lines.append(f"| {label} | {n} | {mae:.4f} | {rho:.4f} | {top:.4f} |")
    out = ARTIFACTS / "ablation_v2.md"
    out.write_text("\n".join(lines) + "\n")
    log.info("wrote %s", out)


if __name__ == "__main__":
    main()
