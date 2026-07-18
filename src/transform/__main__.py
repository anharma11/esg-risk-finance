"""
Entry point for: python -m src.transform  (SILVER + GOLD layers)

Reads the three bronze CSVs produced by src.ingest, scores/aggregates them
(silver), then joins them into the master table (gold).

Outputs written to --outdir (default: ./output):
  Silver:
    aggregate_esg.csv              one row per country-year with pillar scores
    aggregate_loans.csv             one row per country-year with loan totals
    aggregate_ratings.csv           one row per country-year with success rate
  Gold:
    esg_lending_master.csv          all three silver tables joined

Usage:
    python -m src.transform
    python -m src.transform --bronze output/bronze --outdir output
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

from ..ingest.join import build_master
from .aggregate_esg     import aggregate_esg
from .aggregate_loans   import aggregate_loans
from .aggregate_ratings import aggregate_ratings


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bronze", default="output",
                    help="folder containing the bronze CSVs (default: output)")
    ap.add_argument("--outdir", default="output",
                    help="folder to write silver + gold CSVs (default: output)")
    args = ap.parse_args()

    bronze = Path(args.bronze)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    # --- Silver 1: ESG scores ---
    raw_esg = pd.read_csv(bronze / "esg.csv")
    esg = aggregate_esg(raw_esg)
    esg.to_csv(outdir / "aggregate_esg.csv", index=False)

    # --- Silver 2: Lending aggregation ---
    loans_path = bronze / "loans.csv"
    loans   = pd.read_csv(loans_path) if loans_path.exists() else pd.DataFrame()
    lending = aggregate_loans(loans)
    if not lending.empty:
        lending.to_csv(outdir / "aggregate_loans.csv", index=False)

    # --- Silver 3: Ratings aggregation ---
    ratings_path = bronze / "ratings.csv"
    ratings = pd.read_csv(ratings_path) if ratings_path.exists() else pd.DataFrame()
    success = aggregate_ratings(ratings)
    if not success.empty:
        success.to_csv(outdir / "aggregate_ratings.csv", index=False)

    # --- Gold: master join ---
    build_master(esg, lending, success, outdir)

    print(f"\nSilver + Gold written to: {outdir.resolve()}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(1)
