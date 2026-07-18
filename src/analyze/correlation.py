"""
Correlation analysis: ESG risk vs lending exposure and project success rates.
"""

import pandas as pd
from scipy import stats

RISK_BINS   = [0, 33, 66, 100]
RISK_LABELS = ["Low (0–33)", "Medium (34–66)", "High (67–100)"]


def ieg_analysis(df: pd.DataFrame) -> tuple[float, float] | None:
    """Pearson + Spearman correlation and group-level comparison for
    ESG risk vs project success rate."""
    print("=" * 60)
    print("CORRELATION: ESG Risk vs Project Success Rate")
    print("=" * 60)

    paired = df[["esg_risk_score", "success_rate"]].dropna()
    print(f"  Paired rows: {len(paired):,}")

    if len(paired) < 5:
        print("  !! too few paired rows — skipping")
        return None

    r,  p  = stats.pearsonr(paired["esg_risk_score"], paired["success_rate"])
    rs, ps = stats.spearmanr(paired["esg_risk_score"], paired["success_rate"])
    print(f"  Pearson  r = {r:.3f}  (p={p:.4f})")
    print(f"  Spearman r = {rs:.3f}  (p={ps:.4f})")
    sig = p < 0.05 or ps < 0.05
    print(f"  → {'Statistically significant' if sig else 'Not significant'} at p<0.05")
    print()

    print("  Success rate by ESG risk group:")
    tmp = paired.copy()
    tmp["risk_group"] = pd.cut(
        tmp["esg_risk_score"], bins=RISK_BINS, labels=RISK_LABELS, right=True
    )
    grp = (
        tmp.groupby("risk_group", observed=False)["success_rate"]
           .agg(avg_success_rate="mean", n="count")
    )
    grp["avg_success_rate"] = grp["avg_success_rate"].round(1)
    print(grp.to_string())
    print()
    return float(r), float(p)


def pillar_analysis(df: pd.DataFrame) -> None:
    """Show which ESG pillar drives the risk score most."""
    print("=" * 60)
    print("PILLAR BREAKDOWN: What drives ESG risk?")
    print("=" * 60)

    latest = df[df["year"] == df["year"].max()].copy()
    latest["risk_group"] = pd.cut(
        latest["esg_risk_score"], bins=RISK_BINS, labels=RISK_LABELS, right=True
    )
    cols = ["environmental_score", "social_score", "governance_score"]
    grp = latest.groupby("risk_group", observed=False)[cols].mean().round(1)
    print(grp.to_string())
    print()
    print("  Global averages (latest year):")
    for c in cols:
        if latest[c].notna().sum() > 0:
            print(f"    {c:<25} {latest[c].mean():.1f}")
        else:
            print(f"    {c:<25} no data")
    print()


def lending_gap_analysis(df: pd.DataFrame) -> None:
    """Report high-risk countries that receive no WBG lending."""
    print("=" * 60)
    print("LENDING GAP: High-risk countries with no WBG lending")
    print("=" * 60)

    latest = df[df["year"] == df["year"].max()]
    gap = (
        latest[
            (latest["esg_risk_score"] >= 40)
            & (latest["lending_amount"].isna() | (latest["lending_amount"] == 0))
        ]
        .nlargest(10, "esg_risk_score")
        [["country", "esg_risk_score", "social_score", "environmental_score"]]
    )
    print(f"  {len(gap)} highest-risk countries with zero WBG lending:")
    print(gap.round(1).to_string(index=False))
    print()
