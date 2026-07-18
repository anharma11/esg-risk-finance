"""
Country summary: one row per country with latest ESG values, trend, and lending.
"""

from pathlib import Path
import pandas as pd


def build_country_summary(df: pd.DataFrame, outdir: Path) -> pd.DataFrame:
    """Build a one-row-per-country summary using the latest available year.

    Columns:
        country, iso3, latest_year,
        environmental_score, social_score, governance_score,
        esg_score, esg_risk_score,
        risk_trend          (annual slope — negative = improving)
        total_lending_usd   (sum of lending_amount across all years)
        avg_success_rate    (mean success_rate across all years)
        lending_gap         (1 if high risk + no lending)
        priority_score      (from latest year)
    """
    # Latest ESG values per country
    latest = (
        df.sort_values("year")
          .groupby("country", as_index=False)
          .last()
    )

    # Total lending per country across all years
    total_lending = (
        df.groupby("country")["lending_amount"]
          .sum()
          .reset_index()
          .rename(columns={"lending_amount": "total_lending_usd"})
    )

    # Average success rate per country
    avg_success = (
        df.groupby("country")["success_rate"]
          .mean()
          .round(1)
          .reset_index()
          .rename(columns={"success_rate": "avg_success_rate"})
    )

    summary = (
        latest[[
            "country", "iso3", "year",
            "environmental_score", "social_score", "governance_score",
            "esg_score", "esg_risk_score",
            "risk_trend", "lending_gap", "priority_score",
        ]]
        .rename(columns={"year": "latest_year"})
        .merge(total_lending, on="country", how="left")
        .merge(avg_success,   on="country", how="left")
        .sort_values("esg_risk_score", ascending=False)
        .reset_index(drop=True)
    )

    summary.to_csv(outdir / "country_summary.csv", index=False)
    print(f"  country_summary.csv: {len(summary):,} countries")
    return summary
