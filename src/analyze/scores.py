"""
Phase 1: Dataset validation.
Phases 3–4: Exposure normalization and priority scoring.
"""

import pandas as pd


def validate(df: pd.DataFrame) -> None:
    """Print a coverage and missingness report to stdout."""
    print("=" * 60)
    print("PHASE 1 — DATASET VALIDATION")
    print("=" * 60)
    print(f"  Rows        : {len(df):,}")
    print(f"  Countries   : {df['country'].nunique():,}")
    print(f"  Years       : {sorted(df['year'].unique())}")
    print()
    print("  Column coverage (non-null rows):")
    cols = [
        "environmental_score", "social_score", "governance_score",
        "esg_score", "esg_risk_score",
        "lending_amount", "success_rate",
    ]
    for col in cols:
        n = df[col].notna().sum() if col in df.columns else 0
        print(f"    {col:<30} {n:5,}  ({n / len(df) * 100:.0f}%)")

    all_pillars = (
        df["environmental_score"].notna()
        & df["social_score"].notna()
        & df["governance_score"].notna()
    ).sum()
    print(f"    {'all 3 ESG pillars':<30} {all_pillars:5,}"
          f"  ({all_pillars / len(df) * 100:.0f}%)")
    print()


def add_exposure(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize lending_amount to 0–100 as exposure_score."""
    max_lending = df["lending_amount"].max()
    df = df.copy()
    df["exposure_score"] = (df["lending_amount"] / max_lending * 100).round(1)
    return df


def add_priority(df: pd.DataFrame) -> pd.DataFrame:
    """Compute priority_score = (esg_risk_score / 100) × exposure_score.

    Answers: which countries combine high ESG risk with high WBG exposure?
    """
    df = df.copy()
    df["priority_score"] = (
        (df["esg_risk_score"] / 100) * df["exposure_score"]
    ).round(2)
    return df
