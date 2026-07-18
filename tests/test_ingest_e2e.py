"""
End-to-end integration tests for src.ingest — hits real APIs, no mocks.

Tests the full data-pull chain:
  fetch_esg_raw     → World Bank Indicators API (public)
  fetch_lending_raw → WBG Finances One (needs off-VPN)
  fetch_ieg_raw     → WBG Finances One (needs off-VPN)

Each dataset is fetched ONCE via a session-scoped fixture and reused across
all assertions — no redundant API calls.
ESG years are pinned to 2022 only to keep the run fast (~12 indicator calls).

Run:
    pytest tests/test_ingest_e2e.py -v
"""

import pandas as pd
import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch

from src.ingest.esg import fetch_esg_raw
from src.ingest.lending import fetch_lending_raw
from src.ingest.ieg import fetch_ieg_raw


# ---------------------------------------------------------------------------
# Session fixtures — each API is called exactly once for the whole test run
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def esg_df():
    with tempfile.TemporaryDirectory() as d:
        with patch("src.ingest.esg._ingest_years", return_value=(2022, 2022)):
            return fetch_esg_raw(Path(d))


@pytest.fixture(scope="session")
def loans_df():
    with tempfile.TemporaryDirectory() as d:
        return fetch_lending_raw(Path(d))


@pytest.fixture(scope="session")
def ieg_df():
    with tempfile.TemporaryDirectory() as d:
        return fetch_ieg_raw(Path(d))


# ---------------------------------------------------------------------------
# Dataset 1: ESG  (World Bank Indicators API)
# ---------------------------------------------------------------------------

def test_esg_returns_dataframe(esg_df):
    assert isinstance(esg_df, pd.DataFrame), "expected a DataFrame"
    assert not esg_df.empty, "ESG DataFrame is empty — API returned nothing"


def test_esg_schema(esg_df):
    missing = {"iso3", "country", "year", "indicator", "value", "pillar"} - set(esg_df.columns)
    assert not missing, f"ESG DataFrame missing columns: {missing}"


def test_esg_covers_multiple_countries(esg_df):
    n = esg_df["iso3"].nunique()
    assert n > 50, f"only {n} countries — expected 50+"


def test_esg_covers_all_three_pillars(esg_df):
    pillars = set(esg_df["pillar"].unique())
    # Governance indicators (WGI) lag ~2 years in the WB API — may be absent
    # for the pinned year (2022). Require at least 2 of the 3 pillars.
    assert pillars.issubset({"governance", "social", "environmental"}), \
        f"unexpected pillar values: {pillars}"
    assert len(pillars) >= 2, \
        f"only {len(pillars)} pillar(s) present: {pillars} — expected at least 2"


def test_esg_no_aggregate_countries(esg_df):
    assert "WLD" not in esg_df["iso3"].values, \
        "aggregate 'WLD' slipped through country filter"


def test_esg_values_are_float(esg_df):
    assert pd.api.types.is_float_dtype(esg_df["value"]), \
        "value column is not float"


def test_esg_no_null_values(esg_df):
    assert esg_df["value"].notna().all(), "null values in ESG data"


def test_esg_year_correct(esg_df):
    assert (esg_df["year"] == 2022).all(), \
        f"unexpected years: {esg_df['year'].unique()}"


# ---------------------------------------------------------------------------
# Dataset 2: IBRD + IDA lending  (Finances One)
# ---------------------------------------------------------------------------

def test_lending_returns_dataframe(loans_df):
    assert isinstance(loans_df, pd.DataFrame), "expected a DataFrame"
    assert not loans_df.empty, \
        "loans DataFrame is empty — Finances One returned nothing"


def test_lending_schema(loans_df):
    missing = {"loan_id", "country", "fiscal_year",
               "commitment_amount", "disbursement_amount", "source"} - set(loans_df.columns)
    assert not missing, f"loans DataFrame missing columns: {missing}"


def test_lending_row_count(loans_df):
    assert len(loans_df) > 500, \
        f"only {len(loans_df)} loan rows — suspiciously few"


def test_lending_source_values(loans_df):
    assert set(loans_df["source"]).issubset({"IBRD", "IDA"}), \
        f"unexpected source values: {set(loans_df['source'])}"


def test_lending_fiscal_years_populated(loans_df):
    null_pct = loans_df["fiscal_year"].isna().mean()
    assert null_pct < 0.05, f"{null_pct:.0%} of fiscal_year values are null"


def test_lending_amounts_non_negative(loans_df):
    assert (loans_df["commitment_amount"].dropna() >= 0).all(), \
        "negative commitment amounts found"


def test_lending_covers_multiple_countries(loans_df):
    n = loans_df["country"].nunique()
    assert n > 50, f"only {n} countries in loans — expected 50+"


# ---------------------------------------------------------------------------
# Dataset 3: IEG project ratings  (Finances One)
# ---------------------------------------------------------------------------

def test_ieg_returns_dataframe(ieg_df):
    assert isinstance(ieg_df, pd.DataFrame), "expected a DataFrame"
    assert not ieg_df.empty, \
        "IEG DataFrame is empty — Finances One returned nothing"


def test_ieg_schema(ieg_df):
    missing = {"project_id", "country", "outcome_rating",
               "closing_year", "is_successful"} - set(ieg_df.columns)
    assert not missing, f"IEG DataFrame missing columns: {missing}"


def test_ieg_row_count(ieg_df):
    assert len(ieg_df) > 100, \
        f"only {len(ieg_df)} IEG rows — suspiciously few"


def test_ieg_is_successful_binary(ieg_df):
    assert set(ieg_df["is_successful"].unique()).issubset({0, 1}), \
        f"is_successful has non-binary values: {ieg_df['is_successful'].unique()}"


def test_ieg_success_rate_plausible(ieg_df):
    rate = ieg_df["is_successful"].mean()
    assert 0.3 < rate < 1.0, \
        f"success rate {rate:.1%} is implausible — check SUCCESS_RATINGS vocab"


def test_ieg_closing_years_in_range(ieg_df):
    valid = ieg_df["closing_year"].dropna()
    # IEG portfolio goes back to early 1970s; upper bound is near-future
    assert (valid >= 1970).all() and (valid <= 2030).all(), \
        f"closing years out of range: min={valid.min()}, max={valid.max()}"


def test_ieg_countries_stripped(ieg_df):
    has_ws = ieg_df["country"].str.startswith(" ") | ieg_df["country"].str.endswith(" ")
    assert not has_ws.any(), \
        "country names have leading/trailing whitespace"
