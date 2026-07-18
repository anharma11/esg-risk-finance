"""
Join logic: fuzzy country-name matching and building the esg_lending_master table.

Uses rapidfuzz to match lending/IEG country names against the canonical ESG
name list, tolerating spelling differences, abbreviations, and transliterations.
"""

from pathlib import Path

import pandas as pd
from rapidfuzz import fuzz, process, utils

from .http import log

# Minimum fuzzy match score (0–100) to accept a candidate as a match.
# Below this threshold the original name is kept, and the row will not join.
MATCH_THRESHOLD = 85


def _clean(s: pd.Series) -> pd.Series:
    """Basic cleaning applied to both sides before fuzzy matching."""
    return (
        s.astype(str)
         .str.strip()
         .str.lower()
         .str.normalize("NFKD")
         .str.encode("ascii", "ignore")
         .str.decode("ascii")
    )


def fuzzy_match_to_canonical(
    names: pd.Series,
    canonical: pd.Series,
    threshold: int = MATCH_THRESHOLD,
) -> pd.Series:
    """Map each name in `names` to its best match in `canonical`.

    Uses WRatio (handles abbreviations, word-order differences, partial
    matches) with a minimum score threshold. Unmatched names are returned
    as-is so they produce NaN in the join rather than a wrong match.

    Returns a Series of the same length as `names`.
    """
    canon_clean  = _clean(canonical).unique().tolist()
    names_clean  = _clean(names)

    matched = names_clean.map(
        lambda n: _best_match(n, canon_clean, threshold)
    )
    return matched


def _best_match(name: str, choices: list[str], threshold: int) -> str:
    result = process.extractOne(
        name, choices,
        scorer=fuzz.WRatio,
        processor=utils.default_process,
        score_cutoff=threshold,
    )
    return result[0] if result else name  # keep original if no match found


def build_master(
    esg:     pd.DataFrame,
    lending: pd.DataFrame,
    success: pd.DataFrame,
    outdir:  Path,
) -> None:
    """Left-join ESG scores with lending and IEG success, write master CSV.

    Country names are fuzzy-matched against the ESG canonical list so
    abbreviations, transliterations, and minor spelling differences all resolve
    without a hand-maintained fixes dictionary.
    """
    log("== Building joined master table ==")
    master = esg.copy()
    # ESG names are the canonical reference — clean them once
    master["join_key"] = _clean(master["country"])

    if not lending.empty:
        lend = lending.copy()
        lend["join_key"] = fuzzy_match_to_canonical(
            lend["country"], master["country"]
        )
        # Re-aggregate on canonical key in case multiple source names mapped to
        # the same country (e.g. "Co-operative Republic of Guyana" + "Guyana"
        # both resolving to "guyana" — avoids row multiplication on join).
        lend = (
            lend.groupby(["join_key", "fiscal_year"], as_index=False)
                .agg(
                    lending_amount      =("lending_amount",      "sum"),
                    commitment_amount   =("commitment_amount",   "sum"),
                    disbursement_amount =("disbursement_amount", "sum"),
                )
        )
        master = master.merge(
            lend[["join_key", "fiscal_year", "lending_amount",
                  "commitment_amount", "disbursement_amount"]],
            left_on=["join_key", "year"],
            right_on=["join_key", "fiscal_year"],
            how="left",
        ).drop(columns=["fiscal_year"])

    if success is not None and not success.empty:
        succ = success.copy()
        succ["join_key"] = fuzzy_match_to_canonical(
            succ["country"], master["country"]
        )
        # Re-aggregate on canonical key for same reason as lending above.
        # Weighted mean for success_rate (weight by projects_evaluated).
        succ["_weighted"] = succ["success_rate"] * succ["projects_evaluated"]
        succ = (
            succ.groupby(["join_key", "year"], as_index=False)
                .agg(
                    projects_evaluated=("projects_evaluated", "sum"),
                    _weighted         =("_weighted",          "sum"),
                )
        )
        succ["success_rate"] = (succ["_weighted"] / succ["projects_evaluated"]).round(1)
        succ = succ.drop(columns=["_weighted"])
        master = master.merge(
            succ[["join_key", "year", "projects_evaluated", "success_rate"]],
            on=["join_key", "year"],
            how="left",
        )

    master = master.drop(columns=["join_key"])
    master.to_csv(outdir / "esg_lending_master.csv", index=False)
    log(f"  esg_lending_master.csv: {len(master):,} rows")

    # Sanity preview — top borrowers in the latest year with both ESG + lending
    if "lending_amount" not in master.columns:
        log("  (no lending data; skipping preview)")
        return

    both = master.dropna(subset=["esg_score", "lending_amount"])
    if both.empty:
        return

    latest  = both["year"].max()
    preview = (
        both[both["year"] == latest]
        .nlargest(10, "lending_amount")
        [["country", "year", "environmental_score", "social_score",
          "governance_score", "esg_risk_score", "lending_amount"]]
    )
    log(f"\nTop 10 borrowers by new commitments, FY{latest}:")
    log(preview.to_string(index=False))
