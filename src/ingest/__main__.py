"""
Entry point for: python -m src.ingest  (BRONZE layer)

Pulls raw data from three APIs and writes three CSV files. No scoring,
aggregation, or joining — that is handled by src.transform.

Outputs written to --outdir (default: ./output):
  esg.csv        one row per country-year-indicator
  loans.csv      one row per IBRD/IDA loan (un-aggregated)
  ratings.csv    one row per evaluated project

Usage:
    python -m src.ingest
    python -m src.ingest --start 2018 --end 2024
    python -m src.ingest --skip-ieg
    python -m src.ingest --outdir data/bronze

> NOTE: disconnect from WBG VPN before running — the Finances One API
> (loans and IEG) is blocked on the internal network.
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

from .esg     import fetch_esg_raw
from .ieg     import fetch_ieg_raw
from .lending import fetch_lending_raw


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start",    type=int, default=2000)
    ap.add_argument("--end",      type=int, default=pd.Timestamp.now().year)
    ap.add_argument("--outdir",   default="output")
    ap.add_argument("--skip-ieg", action="store_true",
                    help="skip Dataset 3 (IEG project ratings)")
    args = ap.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    fetch_esg_raw(outdir)
    fetch_lending_raw(outdir)
    if not args.skip_ieg:
        fetch_ieg_raw(outdir)

    print(f"\nBronze layer written to: {outdir.resolve()}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(1)
