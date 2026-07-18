"""
Trend analysis: computes per-country ESG risk trajectory over time.
"""

import numpy as np
import pandas as pd


def add_risk_trend(df: pd.DataFrame) -> pd.DataFrame:
    """Add risk_trend column: annualised change in esg_risk_score (OLS slope).

    Negative = risk improving (score falling).
    Positive = risk worsening (score rising).
    NaN if fewer than 3 data points for a country.
    """
    df = df.copy()

    def _slope(g: pd.DataFrame) -> float:
        g = g.dropna(subset=["esg_risk_score"])
        if len(g) < 3:
            return np.nan
        slope, *_ = np.polyfit(g["year"], g["esg_risk_score"], 1)
        return round(float(slope), 3)

    trends = (
        df.groupby("country", group_keys=False)
          .apply(_slope, include_groups=False)
          .reset_index()
    )
    trends.columns = ["country", "risk_trend"]
    return df.merge(trends, on="country", how="left")


def add_lending_gap(df: pd.DataFrame) -> pd.DataFrame:
    """Flag countries with high ESG risk but no WBG lending.

    lending_gap = 1 if esg_risk_score >= 40 and lending_amount is NaN/zero.
    """
    df = df.copy()
    df["lending_gap"] = (
        (df["esg_risk_score"] >= 40)
        & (df["lending_amount"].isna() | (df["lending_amount"] == 0))
    ).astype(int)
    return df
