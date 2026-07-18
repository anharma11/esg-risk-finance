"""
Aggregate loans: sum IBRD+IDA loans by country × fiscal year.
Input:  raw DataFrame (one row per individual loan)
Output: aggregated DataFrame (one row per country-year)
"""

import pandas as pd

from ..ingest.http import log


def aggregate_loans(loans: pd.DataFrame) -> pd.DataFrame:
    """Aggregate raw loan records to one row per country × fiscal year.

    lending_amount = commitment_amount (new approvals that year).
    Returns empty DataFrame if no loan data is available.
    """
    log("== Silver: loans aggregation ==")
    if loans.empty:
        log("  (no loan data — skipping)")
        return pd.DataFrame()

    lending = (
        loans.groupby(["country", "fiscal_year"], as_index=False)
             .agg(
                 commitment_amount   =("commitment_amount",   "sum"),
                 disbursement_amount =("disbursement_amount", "sum"),
                 n_loans             =("country",             "size"),
             )
    )
    lending["lending_amount"] = lending["commitment_amount"]

    log(f"  aggregate_loans: {len(lending):,} rows")
    return lending
