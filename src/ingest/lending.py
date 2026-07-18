"""
Dataset 2: IBRD and IDA lending exposure from WBG Finances One.

Bronze layer only: fetches raw loan records and writes loans_raw.csv.
Aggregation to country × fiscal-year lives in src.transform.
"""

from pathlib import Path

import pandas as pd

from .config import IDA_DATASETS, IBRD_DATASETS
from .http import log, pick_col, try_datasets


def _wb_fiscal_year(dates: pd.Series) -> pd.Series:
    """Convert approval/signing dates to WB fiscal year (Jul 1 – Jun 30)."""
    d = pd.to_datetime(dates, errors="coerce")
    return (d.dt.year + (d.dt.month >= 7).astype("Int64")).astype("Int64")


def _prep_lending_frame(df: pd.DataFrame, source: str) -> pd.DataFrame:
    """Normalize a raw IBRD or IDA loans DataFrame to a common schema."""
    loan_id   = pick_col(df, ["loan_number", "credit_number", "id"])
    country   = pick_col(df, ["country", "country_economy", "borrower_country"])
    approval  = pick_col(df, ["board_approval_date", "agreement_signing_date"])
    principal = pick_col(df, ["original_principal_amount",
                               "original_principal_amount_us_",
                               "original_principal_amount_us"])
    disbursed = pick_col(df, ["disbursed_amount",
                               "disbursed_amount_us_",
                               "disbursed_amount_us"])

    if not all([country, approval, principal]):
        log(f"    !! unexpected schema for {source}; "
            f"columns: {list(df.columns)[:15]}...")
        return pd.DataFrame()

    out = pd.DataFrame({
        "loan_id":    df[loan_id].astype(str).str.strip() if loan_id else pd.NA,
        "country":    df[country].astype(str).str.strip(),
        "fiscal_year": _wb_fiscal_year(df[approval]),
        "commitment_amount": pd.to_numeric(df[principal], errors="coerce"),
        "disbursement_amount": (
            pd.to_numeric(df[disbursed], errors="coerce")
            if disbursed else 0.0
        ),
        "source": source,
    })
    return out.dropna(subset=["fiscal_year"])


def fetch_lending_raw(outdir: Path) -> pd.DataFrame:
    """BRONZE: fetch IBRD + IDA loan records, write loans_raw.csv.

    Schema-normalizes both sources to a common set of columns but does NOT
    aggregate. Returns one row per individual loan/credit.
    """
    log("== Dataset 2: IBRD / IDA lending (bronze) ==")
    ibrd = try_datasets(IBRD_DATASETS, "IBRD")
    ida  = try_datasets(IDA_DATASETS,  "IDA")

    frames = []
    if not ibrd.empty:
        frames.append(_prep_lending_frame(ibrd, "IBRD"))
    if not ida.empty:
        frames.append(_prep_lending_frame(ida, "IDA"))
    if not frames:
        return pd.DataFrame()

    loans = pd.concat(frames, ignore_index=True)
    outdir.mkdir(parents=True, exist_ok=True)
    loans.to_csv(outdir / "loans.csv", index=False)
    log(f"  loans.csv: {len(loans):,} rows\n")
    return loans
