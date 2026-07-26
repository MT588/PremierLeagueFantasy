"""Feature-group ablation for v3 — cumulative additions, then leave-one-out.

Same shape as ml/ablation.py, with two differences that matter.

**Per fold, not one fold.** v2's table reported a single season, which cannot
distinguish a real effect from a fold-specific one; several groups there moved
MAE by less than the seed noise. Every configuration here is scored on all four
folds and the table shows each, so a group that only helps once is visible as
such.

**Scored on the metrics v3 is judged by.** A group is kept on rank correlation
and haul pricing, not MAE alone: v3's purpose is to price the tail, and MAE
rewards shading predictions toward the mean.

    uv run python -m ml.ablation_v3 [--draws 400] [--folds 2025-26]

Writes docs/ablation_v3.md.
"""

import argparse
import json
import logging
from pathlib import Path

import pandas as pd

from app.db import engine
from ml.components import team_defence
from ml.features import FEATURES_BY_GROUP, build_training_frame
from ml.features.context import load_context
from ml.train_v2 import coerce_features
from ml.train_v3 import FOLDS, evaluate_fold

log = logging.getLogger(__name__)

DOCS = Path(__file__).resolve().parent.parent.parent / "docs"

BASE_GROUPS = ["form", "meta"]
ADD_ORDER = [
    "form_eb",
    "career",
    "understat",
    "setpiece",
    "opponent",
    "market",
    "schedule",
    "manager",
    "tournament",
]


def features_for(groups: list[str]) -> list[str]:
    return [f for g in groups for f in FEATURES_BY_GROUP[g]]


def configs() -> dict[str, list[str]]:
    """Cumulative additions over the base, then leave-one-out from the full set."""
    out: dict[str, list[str]] = {"base (form+meta)": list(BASE_GROUPS)}
    groups = list(BASE_GROUPS)
    for group in ADD_ORDER:
        groups = groups + [group]
        out[f"+ {group}"] = list(groups)
    everything = BASE_GROUPS + ADD_ORDER
    for group in ADD_ORDER:
        out[f"all - {group}"] = [g for g in everything if g != group]
    return out


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    parser = argparse.ArgumentParser()
    parser.add_argument("--draws", type=int, default=400)
    parser.add_argument(
        "--folds", nargs="*", help="fold names to run (default: all)"
    )
    args = parser.parse_args()

    ctx = load_context(engine)
    df = coerce_features(build_training_frame(engine))
    team_df = team_defence.build_team_frame(engine, ctx)
    folds = [f for f in FOLDS if not args.folds or f.name in args.folds]
    log.info("ablation over %d configs x %d folds", len(configs()), len(folds))

    rows: list[dict] = []
    for label, groups in configs().items():
        features = features_for(groups)
        # every component sees the same pool; each adds its own extras internally
        overrides = {
            name: features
            for name in ("goals", "assists", "saves", "bonus", "discipline", "defcon")
        }
        for fold in folds:
            report, _, _ = evaluate_fold(
                df, team_df, fold, args.draws, features=overrides
            )
            rows.append(
                {
                    "config": label,
                    "n_features": len(features),
                    "fold": fold.name,
                    "mae": report["v3"]["full"]["mae"],
                    "rho": report["v3"]["full"]["spearman_per_gw"],
                    "mae_gw1_8": report["v3"]["early"].get("mae"),
                    "rmse_hauls_ge8": report["v3"]["tail"].get("rmse_hauls_ge8"),
                    "haul_brier": report["v3"]["haul"]["brier"],
                }
            )
            log.info(
                "%-22s %-11s mae=%.4f rho=%.4f brier=%.5f",
                label,
                fold.name,
                rows[-1]["mae"],
                rows[-1]["rho"],
                rows[-1]["haul_brier"],
            )

    table = pd.DataFrame(rows)
    DOCS.mkdir(exist_ok=True)
    (DOCS / "ablation_v3.json").write_text(json.dumps(rows, indent=2))
    write_markdown(table, folds)
    print("\n" + table.to_string(index=False, float_format=lambda v: f"{v:.4f}"))


def write_markdown(table: pd.DataFrame, folds) -> None:
    lines = [
        "# Ablation — v3 components",
        "",
        "Per-fold so a group that only helps in one season cannot pass as a win.",
        "Scored on rank correlation and haul pricing as well as MAE: v3 exists to",
        "price the tail, and MAE alone rewards shading toward the mean.",
        "",
    ]
    for metric, label, better in (
        ("rho", "Spearman per gameweek", "higher"),
        ("mae", "MAE", "lower"),
        ("mae_gw1_8", "MAE, gameweeks 1-8", "lower"),
        ("haul_brier", "P(haul) Brier", "lower"),
    ):
        pivot = table.pivot_table(
            index=["config", "n_features"], columns="fold", values=metric, sort=False
        )
        lines += [f"## {label} ({better} is better)", ""]
        header = "| config | n | " + " | ".join(str(c) for c in pivot.columns) + " |"
        lines += [header, "|" + "---|" * (len(pivot.columns) + 2)]
        for (config, n), row in pivot.iterrows():
            values = " | ".join(
                "—" if pd.isna(v) else f"{v:.4f}" for v in row.to_numpy()
            )
            lines.append(f"| {config} | {n} | {values} |")
        lines.append("")

    (DOCS / "ablation_v3.md").write_text("\n".join(lines) + "\n")
    log.info("wrote %s", DOCS / "ablation_v3.md")


if __name__ == "__main__":
    main()
