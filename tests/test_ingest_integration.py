"""
Integration tests — hit real APIs and validate the returned DataFrames.

Requires outbound internet (disconnect from WBG VPN before running).
Run with:
    pytest tests/test_ingest_integration.py -v
"""

import pandas as pd
import pytest
from pathlib import Path

from src.ingest.esg import fetch_country_list, fetch_indicator, fetch_esg_raw
from src.ingest.lending import fetch_lending_raw
from src.ingest.ieg import fetch_ieg_raw
from src.ingest.http import fone_fetch_all
from src.ingest.config import IBRD_DATASETS, IDA_DATASETS, IEG_DATASETS


# ---------------------------------------------------------------------------
# World Bank Indicators API — fetch_country_list
# ---------------------------------------------------------------------------

class TestLiveCountryList:
    def test_returns_nonempty_dataframe(self):
        df = fetch_country_list()
        assert isinstance(df, pd.DataFrame)
        assert len(df) > 100, "expected 100+ real countries"

    def test_schema(self):
        df = fetch_country_list()
        assert set(df.columns) >= {"iso3", "iso2", "country", "region", "income_level"}

    def test_no_aggregates(self):
        df = fetch_country_list()
        assert "WLD" not in df["iso3"].values
        assert "EAP" not in df["iso3"].values

    def test_iso3_codes_are_three_chars(self):
        df = fetch_country_list()
        assert (df["iso3"].str.len() == 3).all()

    def test_no_null_country_names(self):
        df = fetch_country_list()
        assert df["country"].notna().all()


# ---------------------------------------------------------------------------
# World Bank Indicators API — fetch_indicator
# ---------------------------------------------------------------------------

class TestLiveFetchIndicator:
    def test_governance_indicator_returns_data(self):
        df = fetch_indicator("GE.EST", 2022, 2022)
        assert isinstance(df, pd.DataFrame)
        assert len(df) > 50

    def test_schema(self):
        df = fetch_indicator("GE.EST", 2022, 2022)
        assert set(df.columns) >= {"iso3", "country", "year", "indicator", "value"}

    def test_values_are_float(self):
        df = fetch_indicator("GE.EST", 2022, 2022)
        assert pd.api.types.is_float_dtype(df["value"])

    def test_no_null_values(self):
        df = fetch_indicator("GE.EST", 2022, 2022)
        assert df["value"].notna().all()

    def test_year_column_correct(self):
        df = fetch_indicator("GE.EST", 2022, 2022)
        assert (df["year"] == 2022).all()

    def test_indicator_code_in_column(self):
        df = fetch_indicator("GE.EST", 2022, 2022)
        assert (df["indicator"] == "GE.EST").all()

    def test_social_indicator_returns_data(self):
        df = fetch_indicator("SP.DYN.LE00.IN", 2022, 2022)
        assert len(df) > 50

    def test_environmental_indicator_returns_data(self):
        df = fetch_indicator("AG.LND.FRST.ZS", 2022, 2022)
        assert len(df) > 50


# ---------------------------------------------------------------------------
# fetch_esg_raw (full pipeline, 1-year slice to keep it fast)
# ---------------------------------------------------------------------------

class TestLiveFetchEsgRaw:
    def test_returns_nonempty_dataframe(self, tmp_path):
        df = fetch_esg_raw.__wrapped__(tmp_path) if hasattr(fetch_esg_raw, "__wrapped__") else _esg_raw_one_year(tmp_path)
        assert isinstance(df, pd.DataFrame)
        assert len(df) > 0

    def test_schema(self, tmp_path):
        df = _esg_raw_one_year(tmp_path)
        assert set(df.columns) >= {"iso3", "country", "year", "indicator", "value", "pillar"}

    def test_pillar_values(self, tmp_path):
        df = _esg_raw_one_year(tmp_path)
        assert set(df["pillar"]).issubset({"governance", "social", "environmental"})

    def test_no_aggregate_iso3(self, tmp_path):
        df = _esg_raw_one_year(tmp_path)
        assert "WLD" not in df["iso3"].values

    def test_values_numeric(self, tmp_path):
        df = _esg_raw_one_year(tmp_path)
        assert pd.api.types.is_float_dtype(df["value"])

    def test_csv_written(self, tmp_path):
        _esg_raw_one_year(tmp_path)
        assert (tmp_path / "esg.csv").exists()

    def test_csv_row_count_matches_df(self, tmp_path):
        df = _esg_raw_one_year(tmp_path)
        csv = pd.read_csv(tmp_path / "esg.csv")
        assert len(csv) == len(df)


def _esg_raw_one_year(tmp_path: Path) -> pd.DataFrame:
    """Run fetch_esg_raw with years patched to a single year for speed."""
    from unittest.mock import patch
    with patch("src.ingest.esg._ingest_years", return_value=(2022, 2022)):
        return fetch_esg_raw(tmp_path)


# ---------------------------------------------------------------------------
# Finances One API — IBRD loans
# ---------------------------------------------------------------------------

class TestLiveIbrdLoans:
    def test_fone_returns_data(self):
        dataset_id, resource_id = IBRD_DATASETS[0]
        df = fone_fetch_all(dataset_id, resource_id)
        assert isinstance(df, pd.DataFrame)
        assert len(df) > 100, "expected thousands of IBRD loan records"

    def test_has_country_column(self):
        dataset_id, resource_id = IBRD_DATASETS[0]
        df = fone_fetch_all(dataset_id, resource_id)
        country_cols = [c for c in df.columns if "country" in c.lower()]
        assert len(country_cols) > 0, f"no country column found; cols={list(df.columns)}"

    def test_has_amount_column(self):
        dataset_id, resource_id = IBRD_DATASETS[0]
        df = fone_fetch_all(dataset_id, resource_id)
        amount_cols = [c for c in df.columns if "principal" in c.lower() or "amount" in c.lower()]
        assert len(amount_cols) > 0, f"no amount column found; cols={list(df.columns)}"

    def test_fetch_lending_raw_schema(self, tmp_path):
        df = fetch_lending_raw(tmp_path)
        assert not df.empty
        assert set(df.columns) >= {
            "loan_id", "country", "fiscal_year",
            "commitment_amount", "disbursement_amount", "source",
        }

    def test_fetch_lending_raw_fiscal_years_populated(self, tmp_path):
        df = fetch_lending_raw(tmp_path)
        assert df["fiscal_year"].notna().all()

    def test_fetch_lending_raw_amounts_positive(self, tmp_path):
        df = fetch_lending_raw(tmp_path)
        assert (df["commitment_amount"] >= 0).all()

    def test_fetch_lending_raw_source_values(self, tmp_path):
        df = fetch_lending_raw(tmp_path)
        assert set(df["source"]).issubset({"IBRD", "IDA"})

    def test_fetch_lending_raw_csv_written(self, tmp_path):
        fetch_lending_raw(tmp_path)
        assert (tmp_path / "loans.csv").exists()


# ---------------------------------------------------------------------------
# Finances One API — IDA credits
# ---------------------------------------------------------------------------

class TestLiveIdaLoans:
    def test_fone_returns_data(self):
        dataset_id, resource_id = IDA_DATASETS[0]
        df = fone_fetch_all(dataset_id, resource_id)
        assert isinstance(df, pd.DataFrame)
        assert len(df) > 100

    def test_has_country_column(self):
        dataset_id, resource_id = IDA_DATASETS[0]
        df = fone_fetch_all(dataset_id, resource_id)
        country_cols = [c for c in df.columns if "country" in c.lower()]
        assert len(country_cols) > 0, f"cols={list(df.columns)}"


# ---------------------------------------------------------------------------
# Finances One API — IEG ratings
# ---------------------------------------------------------------------------

class TestLiveIegRatings:
    def test_fone_returns_data(self):
        dataset_id, resource_id = IEG_DATASETS[0]
        df = fone_fetch_all(dataset_id, resource_id)
        assert isinstance(df, pd.DataFrame)
        assert len(df) > 100

    def test_fetch_ieg_raw_schema(self, tmp_path):
        df = fetch_ieg_raw(tmp_path)
        assert not df.empty
        assert set(df.columns) >= {
            "project_id", "country", "outcome_rating",
            "closing_year", "is_successful",
        }

    def test_is_successful_binary(self, tmp_path):
        df = fetch_ieg_raw(tmp_path)
        assert set(df["is_successful"].unique()).issubset({0, 1})

    def test_success_rate_reasonable(self, tmp_path):
        df = fetch_ieg_raw(tmp_path)
        rate = df["is_successful"].mean()
        assert 0.3 < rate < 1.0, f"success rate {rate:.2f} looks wrong"

    def test_closing_years_in_range(self, tmp_path):
        df = fetch_ieg_raw(tmp_path)
        valid = df["closing_year"].dropna()
        assert (valid >= 1990).all()
        assert (valid <= 2030).all()

    def test_csv_written(self, tmp_path):
        fetch_ieg_raw(tmp_path)
        assert (tmp_path / "ratings.csv").exists()
