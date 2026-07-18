"""
Entry point for: python -m src.analyze

Usage:
    python -m src.analyze                   # auto-selects year with most lending data
    python -m src.analyze --year 2024
    python -m src.analyze --indir data/raw --outdir data/out
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

from .correlation import ieg_analysis, lending_gap_analysis, pillar_analysis
from .dashboard   import dashboard
from .scores      import add_exposure, add_priority, validate
from .summary     import build_country_summary
from .trends      import add_lending_gap, add_risk_trend


def _print_priority_table(df: pd.DataFrame, year: int | None) -> None:
    snapshot = df if year is None else df[df["year"] == year]
    top = (
        snapshot.dropna(subset=["priority_score"])
        .nlargest(15, "priority_score")
        [["country", "year", "esg_risk_score", "exposure_score",
          "priority_score", "success_rate"]]
        .reset_index(drop=True)
    )
    top = top.round({"esg_risk_score": 1, "exposure_score": 1,
                     "priority_score": 2, "success_rate": 1})
    print("=" * 60)
    print(f"TOP 15 PRIORITY COUNTRIES  (year={year or 'all'})")
    print("=" * 60)
    print(top.to_string(index=False))
    print()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--year",   type=int, default=None,
                    help="Pin snapshot charts to this year (default: auto)")
    ap.add_argument("--indir",  default="output")
    ap.add_argument("--outdir", default="output")
    args = ap.parse_args()

    in_dir  = Path(args.indir)
    out_dir = Path(args.outdir)
    out_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(in_dir / "esg_lending_master.csv")

    validate(df)
    df = add_exposure(df)
    df = add_priority(df)
    df = add_risk_trend(df)
    df = add_lending_gap(df)
    ieg_analysis(df)
    pillar_analysis(df)
    lending_gap_analysis(df)
    _print_priority_table(df, args.year)
    dashboard(df, args.year, out_dir / "dashboard.png")

    build_country_summary(df, out_dir)

    cols = [
        "iso3", "country", "year",
        "environmental_score", "social_score", "governance_score",
        "esg_score", "esg_risk_score",
        "lending_amount", "commitment_amount", "disbursement_amount",
        "exposure_score", "priority_score",
        "projects_evaluated", "success_rate",
    ]
    df[[c for c in cols if c in df.columns]].to_csv(
        out_dir / "analysis.csv", index=False
    )
    print(f"  Analysis CSV saved → {(out_dir / 'analysis.csv').resolve()}")
    print("\nDone.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(1)
