"""
Six-panel dashboard surfacing the key findings in the data.

Visuals:
  ① Top 20 highest-risk countries (bar chart)
  ② Social score is the risk driver (social vs environmental, colored by risk)
  ③ Lending gap — high-risk countries with little/no WBG lending
  ④ ESG risk trend — improving vs worsening countries
  ⑤ Project success rate vs ESG risk (scatter + regression)
  ⑥ Priority Matrix — High Risk × High Exposure quadrant
"""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats


def dashboard(df: pd.DataFrame, year: int | None, out_path: Path) -> None:
    """Render and save the 6-panel dashboard PNG."""
    print("=" * 60)
    print("DASHBOARD")
    print("=" * 60)

    if year is None:
        year_counts = df.groupby("year")["lending_amount"].count()
        year = int(year_counts.idxmax())
        print(f"  Using year {year} (most lending data points)")

    snapshot = df[df["year"] == year].copy()
    print(f"  Snapshot rows for {year}: {len(snapshot):,}")
    print()

    fig, axes = plt.subplots(3, 2, figsize=(18, 21))
    fig.suptitle(
        f"ESG Risk & WBG Lending Exposure  ·  FY{year}",
        fontsize=16, fontweight="bold", y=0.99,
    )

    # ① Top 20 Highest-Risk Countries ----------------------------------------
    ax1 = axes[0, 0]
    top20 = (
        snapshot[["country", "esg_risk_score"]]
        .dropna()
        .nlargest(20, "esg_risk_score")
        .sort_values("esg_risk_score")
    )
    colors = [
        "#d32f2f" if x >= 67 else "#f57c00" if x >= 34 else "#388e3c"
        for x in top20["esg_risk_score"]
    ]
    ax1.barh(top20["country"], top20["esg_risk_score"], color=colors)
    ax1.axvline(33, color="#388e3c", linestyle="--", linewidth=0.8, alpha=0.5)
    ax1.axvline(66, color="#f57c00", linestyle="--", linewidth=0.8, alpha=0.5)
    ax1.set_xlim(0, 100)
    ax1.set_xlabel("ESG Risk Score")
    ax1.set_title("① Top 20 Highest-Risk Countries")

    # ② Social Score is the Risk Driver (social vs environmental) -------------
    ax2 = axes[0, 1]
    v2 = snapshot.dropna(subset=["social_score", "environmental_score", "esg_risk_score"])
    sc2 = ax2.scatter(
        v2["environmental_score"], v2["social_score"],
        c=v2["esg_risk_score"], cmap="RdYlGn_r", vmin=0, vmax=100,
        s=40, alpha=0.7, edgecolors="grey", linewidths=0.2,
    )
    plt.colorbar(sc2, ax=ax2, label="ESG Risk Score")
    # label the outliers
    for _, row in v2.nlargest(4, "esg_risk_score").iterrows():
        ax2.annotate(row["country"], (row["environmental_score"], row["social_score"]),
                     fontsize=7, xytext=(4, 2), textcoords="offset points")
    ax2.set_xlabel("Environmental Score (0–100)")
    ax2.set_ylabel("Social Score (0–100)")
    ax2.set_title("② What Drives ESG Risk?\nSocial score separates low from high risk")

    # ③ Lending Gap — High-risk with no lending --------------------------------
    ax3 = axes[1, 0]
    gap = snapshot[
        (snapshot["esg_risk_score"] >= 35)
    ].copy()
    gap["has_lending"] = gap["lending_amount"].notna() & (gap["lending_amount"] > 0)
    gap_sorted = gap.sort_values("esg_risk_score", ascending=True).tail(25)
    bar_colors = ["#1565c0" if h else "#e53935" for h in gap_sorted["has_lending"]]
    ax3.barh(gap_sorted["country"], gap_sorted["esg_risk_score"], color=bar_colors)
    from matplotlib.patches import Patch
    ax3.legend(handles=[
        Patch(color="#1565c0", label="Has WBG lending"),
        Patch(color="#e53935", label="No WBG lending (gap)"),
    ], fontsize=8, loc="lower right")
    ax3.set_xlabel("ESG Risk Score")
    ax3.set_title("③ Lending Gap\nHigh-risk countries receiving no WBG lending (red)")

    # ④ ESG Risk Trend — improving vs worsening --------------------------------
    ax4 = axes[1, 1]
    if "risk_trend" in df.columns:
        trends = (
            df.groupby("country")["risk_trend"].first()
              .dropna()
              .sort_values()
        )
        improving  = trends[trends < -0.5].head(10)
        worsening  = trends[trends >  0.5].tail(10)
        both = pd.concat([improving, worsening])
        trend_colors = ["#388e3c" if v < 0 else "#d32f2f" for v in both]
        ax4.barh(both.index, both.values, color=trend_colors)
        ax4.axvline(0, color="black", linewidth=0.8)
        ax4.set_xlabel("Annual change in ESG Risk Score\n(negative = improving)")
        ax4.set_title("④ ESG Risk Trend (2018–2024)\nGreen = improving  ·  Red = worsening")
    else:
        ax4.text(0.5, 0.5, "risk_trend not computed\n(run add_risk_trend first)",
                 ha="center", va="center", transform=ax4.transAxes, fontsize=10)
        ax4.set_title("④ ESG Risk Trend")

    # ⑤ Success Rate vs ESG Risk (all years) ---------------------------------
    ax5 = axes[2, 0]
    v5 = df[["esg_risk_score", "success_rate"]].dropna()
    ax5.scatter(v5["esg_risk_score"], v5["success_rate"],
                alpha=0.45, color="#1565c0", s=30,
                edgecolors="white", linewidths=0.3)
    if len(v5) >= 5:
        m, b, r, p, _ = stats.linregress(v5["esg_risk_score"], v5["success_rate"])
        x_line = np.linspace(v5["esg_risk_score"].min(), v5["esg_risk_score"].max(), 200)
        ax5.plot(x_line, m * x_line + b, color="#e53935", linewidth=1.5,
                 label=f"r = {r:.2f},  p = {p:.3f}")
        ax5.legend(fontsize=9)
    ax5.set_ylim(0, 105)
    ax5.set_xlabel("ESG Risk Score")
    ax5.set_ylabel("IEG Project Success Rate (%)")
    ax5.set_title("⑤ Project Success Rate vs ESG Risk\n(all years, country-level)")

    # ⑥ Priority Matrix -------------------------------------------------------
    ax6 = axes[2, 1]
    v6 = snapshot.dropna(subset=["esg_risk_score", "exposure_score"])
    sc6 = ax6.scatter(
        v6["exposure_score"], v6["esg_risk_score"],
        s=60, alpha=0.7,
        c=v6["priority_score"], cmap="YlOrRd",
        edgecolors="grey", linewidths=0.3,
    )
    plt.colorbar(sc6, ax=ax6, label="Priority Score")
    ax6.axvline(50, color="grey", linestyle="--", linewidth=0.8, alpha=0.7)
    ax6.axhline(50, color="grey", linestyle="--", linewidth=0.8, alpha=0.7)
    _bbox = dict(boxstyle="round,pad=0.3", alpha=0.8)
    ax6.text(75, 90, "⚠ High Risk\nHigh Exposure", ha="center", fontsize=8,
             color="#b71c1c", bbox={**_bbox, "fc": "#ffebee"})
    ax6.text(25, 90, "High Risk\nLow Exposure",  ha="center", fontsize=8,
             color="#e65100", bbox={**_bbox, "fc": "#fff3e0"})
    ax6.text(75, 10, "Low Risk\nHigh Exposure",  ha="center", fontsize=8,
             color="#1b5e20", bbox={**_bbox, "fc": "#e8f5e9"})
    for _, row in v6.nlargest(5, "priority_score").iterrows():
        ax6.annotate(row["country"], (row["exposure_score"], row["esg_risk_score"]),
                     fontsize=7, ha="left", va="bottom",
                     xytext=(4, 4), textcoords="offset points")
    ax6.set_xlabel("Exposure Score (normalized lending, 0–100)")
    ax6.set_ylabel("ESG Risk Score (0–100)")
    ax6.set_title("⑥ Priority Matrix\n(High Risk + High Exposure = Attention Needed)")

    fig.tight_layout(rect=[0, 0, 1, 0.98])
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    print(f"  Dashboard saved → {out_path.resolve()}")
    plt.close(fig)
