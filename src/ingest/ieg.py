"""
Dataset 3: IEG World Bank Project Performance Ratings from WBG Finances One.

Bronze layer only: fetches project-level ratings and writes
ieg_project_ratings.csv. Aggregation to success rates lives in src.transform.
"""

from pathlib import Path

import pandas as pd

from .config import IEG_DATASETS, SUCCESS_RATINGS
from .http import log, pick_col, try_datasets


def fetch_ieg_raw(outdir: Path) -> pd.DataFrame:
    """BRONZE: fetch IEG project ratings, write ieg_project_ratings.csv.

    Returns one row per evaluated project. Does NOT aggregate to success rates.
    """
    log("== Dataset 3: IEG project performance ratings (bronze) ==")
    raw = try_datasets(IEG_DATASETS, "IEG")
    if raw.empty:
        return pd.DataFrame()

    project = pick_col(raw, ["project_id", "proj_id"])
    country = pick_col(raw, ["country", "country_economy"])
    outcome = pick_col(raw, ["ieg_outcome", "outcome", "ieg_outcome_rating"])
    sector  = pick_col(raw, ["sector_board", "global_practice", "sector",
                              "agreement_type", "practice_group"])
    closing = pick_col(raw, ["exit_fy", "closing_fy", "final_closing_fy",
                              "evaluation_fy", "exit_fiscal_year", "closing_date"])

    ieg = pd.DataFrame({
        "project_id":    raw[project]                         if project else pd.NA,
        "country":       raw[country].astype(str).str.strip() if country else pd.NA,
        "outcome_rating":raw[outcome].astype(str).str.strip() if outcome else pd.NA,
        "sector":        raw[sector]                          if sector  else pd.NA,
        "closing_year":  (
            pd.to_numeric(
                raw[closing].astype(str).str.extract(r"(\d{4})")[0],
                errors="coerce",
            ).astype("Int64")
            if closing else pd.NA
        ),
    })
    ieg["is_successful"] = (
        ieg["outcome_rating"].str.lower().isin(SUCCESS_RATINGS).astype(int)
    )

    ieg.to_csv(outdir / "ratings.csv", index=False)
    log(f"  ratings.csv: {len(ieg):,} projects\n")
    return ieg
