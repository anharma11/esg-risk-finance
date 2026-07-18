"""
Aggregate ESG: normalize raw indicators to 0-100 and compute pillar scores.
Input:  raw DataFrame (one row per country-year-indicator)
Output: scored DataFrame (one row per country-year)
"""

import pandas as pd

from ..ingest.config import ESG_INDICATORS
from ..ingest.http import log


def aggregate_esg(raw: pd.DataFrame) -> pd.DataFrame:
    """Normalize raw ESG indicators and average into pillar scores.

    Returns one row per country-year with environmental_score, social_score,
    governance_score, esg_score, esg_risk_score.
    """
    log("== Silver: ESG scoring ==")

    directions = {
        code: direction
        for _pillar, indicators in ESG_INDICATORS.items()
        for code, (_name, direction) in indicators.items()
    }

    def _normalize(group: pd.DataFrame) -> pd.Series:
        lo, hi = group["value"].min(), group["value"].max()
        if hi == lo:
            return pd.Series(50.0, index=group.index)
        scaled = (group["value"] - lo) / (hi - lo) * 100
        if directions.get(group.name[0], 1) < 0:
            scaled = 100 - scaled
        return scaled

    raw = raw.sort_values(["indicator", "year"]).copy()
    raw["norm"] = (
        raw.groupby(["indicator", "year"], group_keys=False)
           .apply(_normalize, include_groups=False)
           .to_numpy()  # detach index — avoids MultiIndex alignment issues in pandas 3.x
    )

    pillar_scores = (
        raw.groupby(["iso3", "country", "year", "pillar"])["norm"]
           .mean().unstack("pillar").reset_index()
    )
    for col in ("environmental", "social", "governance"):
        if col not in pillar_scores:
            pillar_scores[col] = pd.NA

    pillar_scores = pillar_scores.rename(columns={
        "environmental": "environmental_score",
        "social":        "social_score",
        "governance":    "governance_score",
    })
    score_cols = ["environmental_score", "social_score", "governance_score"]
    pillar_scores["esg_score"]      = pillar_scores[score_cols].mean(axis=1)
    pillar_scores["esg_risk_score"] = 100 - pillar_scores["esg_score"]
    pillar_scores[score_cols + ["esg_score", "esg_risk_score"]] = (
        pillar_scores[score_cols + ["esg_score", "esg_risk_score"]].round(1)
    )

    log(f"  aggregate_esg: {len(pillar_scores):,} country-year rows")
    return pillar_scores
