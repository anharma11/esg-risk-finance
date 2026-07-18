"""
Aggregate ratings: compute project success rate by country × year.
Input:  raw DataFrame (one row per evaluated project)
Output: aggregated DataFrame (one row per country-year)
"""

import pandas as pd

from ..ingest.http import log


def aggregate_ratings(ieg: pd.DataFrame) -> pd.DataFrame:
    """Aggregate IEG project ratings to success rate per country × closing year.

    success_rate = % of projects rated Moderately Satisfactory or better.
    Returns empty DataFrame if no ratings data is available.
    """
    log("== Silver: ratings aggregation ==")
    if ieg.empty:
        log("  (no ratings data — skipping)")
        return pd.DataFrame()

    success = (
        ieg.dropna(subset=["closing_year"])
           .groupby(["country", "closing_year"], as_index=False)
           .agg(
               projects_evaluated=("project_id",    "size"),
               success_rate      =("is_successful", "mean"),
           )
           .rename(columns={"closing_year": "year"})
    )
    success["success_rate"] = (success["success_rate"] * 100).round(1)

    log(f"  aggregate_ratings: {len(success):,} rows")
    return success
