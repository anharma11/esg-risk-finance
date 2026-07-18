"""
Tests for src.ingest — fetch_esg_raw, fetch_lending_raw, fetch_ieg_raw.

All HTTP calls are patched at the module level where they are used;
zero network traffic, zero API keys required.
"""

import pandas as pd
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

# ---------------------------------------------------------------------------
# Shared fake API response builders
# ---------------------------------------------------------------------------

def _wb_country_response():
    """Mimics the WB /country JSON envelope."""
    return [
        {"page": 1, "pages": 1, "per_page": 400, "total": 3},
        [
            {
                "id": "BRA", "iso2Code": "BR", "name": "Brazil",
                "region": {"value": "Latin America & Caribbean"},
                "incomeLevel": {"value": "Upper middle income"},
            },
            {
                "id": "IND", "iso2Code": "IN", "name": "India",
                "region": {"value": "South Asia"},
                "incomeLevel": {"value": "Lower middle income"},
            },
            # Aggregate row — must be filtered out
            {
                "id": "WLD", "iso2Code": "1W", "name": "World",
                "region": {"value": "Aggregates"},
                "incomeLevel": {"value": "Aggregates"},
            },
        ],
    ]


def _wb_indicator_response(code: str, iso3: str = "BRA", value: float = 0.5):
    """Mimics the WB /country/all/indicator/{code} JSON envelope."""
    return [
        {"page": 1, "pages": 1, "per_page": 20000, "total": 2},
        [
            {
                "countryiso3code": "BRA",
                "country": {"value": "Brazil"},
                "date": "2022",
                "value": 0.5,
                "indicator": {"id": code},
            },
            {
                "countryiso3code": "IND",
                "country": {"value": "India"},
                "date": "2022",
                "value": 0.2,
                "indicator": {"id": code},
            },
            # None value — must be skipped
            {
                "countryiso3code": "USA",
                "country": {"value": "United States"},
                "date": "2022",
                "value": None,
                "indicator": {"id": code},
            },
        ],
    ]


def _fake_loans_df():
    return pd.DataFrame({
        "loan_number":               ["L001", "L002", "L003"],
        "country":                   ["Brazil", "India", "Brazil"],
        "board_approval_date":       ["2022-03-15", "2022-08-01", "2023-01-10"],
        "original_principal_amount": [1_000_000, 2_000_000, 500_000],
        "disbursed_amount":          [500_000, 1_000_000, 250_000],
    })


def _fake_ieg_df():
    return pd.DataFrame({
        "project_id": ["P001", "P002", "P003", "P004"],
        "country":    ["Brazil", "Brazil", "India", "India"],
        "ieg_outcome": [
            "Satisfactory",
            "Unsatisfactory",
            "Moderately Satisfactory",
            "Highly Satisfactory",
        ],
        "sector_board": ["Finance", "Transport", "Health", "Education"],
        "exit_fy":      ["2022", "2022", "2021", "2021"],
    })


# ---------------------------------------------------------------------------
# fetch_esg_raw
# ---------------------------------------------------------------------------

from src.ingest.esg import fetch_esg_raw, fetch_country_list, fetch_indicator


class TestFetchCountryList:
    def test_filters_aggregates(self):
        with patch("src.ingest.esg.wb_get", return_value=_wb_country_response()):
            df = fetch_country_list()
        assert "WLD" not in df["iso3"].values

    def test_returns_real_countries(self):
        with patch("src.ingest.esg.wb_get", return_value=_wb_country_response()):
            df = fetch_country_list()
        assert set(df["iso3"]) == {"BRA", "IND"}

    def test_schema(self):
        with patch("src.ingest.esg.wb_get", return_value=_wb_country_response()):
            df = fetch_country_list()
        assert set(df.columns) >= {"iso3", "iso2", "country", "region", "income_level"}


class TestFetchIndicator:
    def test_drops_null_values(self):
        with patch("src.ingest.esg.wb_get",
                   return_value=_wb_indicator_response("GE.EST")):
            df = fetch_indicator("GE.EST", 2022, 2022)
        # USA row had value=None — must not appear
        assert "USA" not in df["iso3"].values

    def test_returns_float_values(self):
        with patch("src.ingest.esg.wb_get",
                   return_value=_wb_indicator_response("GE.EST")):
            df = fetch_indicator("GE.EST", 2022, 2022)
        assert pd.api.types.is_float_dtype(df["value"])

    def test_schema(self):
        with patch("src.ingest.esg.wb_get",
                   return_value=_wb_indicator_response("GE.EST")):
            df = fetch_indicator("GE.EST", 2022, 2022)
        assert set(df.columns) >= {"iso3", "country", "year", "indicator", "value"}

    def test_year_is_int(self):
        with patch("src.ingest.esg.wb_get",
                   return_value=_wb_indicator_response("GE.EST")):
            df = fetch_indicator("GE.EST", 2022, 2022)
        assert df["year"].dtype in (int, "int64", "int32")

    def test_empty_on_no_data(self):
        """WB sometimes returns data[1]=None — should return empty DataFrame."""
        with patch("src.ingest.esg.wb_get",
                   return_value=[{"page": 1, "pages": 1}, None]):
            df = fetch_indicator("GE.EST", 2022, 2022)
        assert df.empty

    def test_paginates(self):
        """If pages > 1, wb_get is called more than once."""
        page1 = [{"page": 1, "pages": 2, "per_page": 1, "total": 2},
                 [{"countryiso3code": "BRA", "country": {"value": "Brazil"},
                   "date": "2022", "value": 0.5, "indicator": {"id": "GE.EST"}}]]
        page2 = [{"page": 2, "pages": 2, "per_page": 1, "total": 2},
                 [{"countryiso3code": "IND", "country": {"value": "India"},
                   "date": "2022", "value": 0.2, "indicator": {"id": "GE.EST"}}]]
        with patch("src.ingest.esg.wb_get", side_effect=[page1, page2]) as mock_get:
            df = fetch_indicator("GE.EST", 2022, 2022)
        assert mock_get.call_count == 2
        assert len(df) == 2


class TestFetchEsgRaw:
    def _wb_get_router(self, url, params, **kwargs):
        """Return country list for /country, indicator data for /indicator/."""
        if "/indicator/" in url:
            code = url.split("/indicator/")[-1]
            return _wb_indicator_response(code)
        return _wb_country_response()

    def test_returns_dataframe(self, tmp_path):
        with patch("src.ingest.esg.wb_get", side_effect=self._wb_get_router), \
             patch("src.ingest.esg._ingest_years", return_value=(2022, 2022)):
            df = fetch_esg_raw(tmp_path)
        assert isinstance(df, pd.DataFrame)
        assert not df.empty

    def test_writes_csv(self, tmp_path):
        with patch("src.ingest.esg.wb_get", side_effect=self._wb_get_router), \
             patch("src.ingest.esg._ingest_years", return_value=(2022, 2022)):
            fetch_esg_raw(tmp_path)
        assert (tmp_path / "esg.csv").exists()

    def test_schema(self, tmp_path):
        with patch("src.ingest.esg.wb_get", side_effect=self._wb_get_router), \
             patch("src.ingest.esg._ingest_years", return_value=(2022, 2022)):
            df = fetch_esg_raw(tmp_path)
        assert set(df.columns) >= {"iso3", "country", "year", "indicator", "value", "pillar"}

    def test_filters_to_real_countries_only(self, tmp_path):
        """USA had value=None → dropped; WLD is aggregate → filtered out."""
        with patch("src.ingest.esg.wb_get", side_effect=self._wb_get_router), \
             patch("src.ingest.esg._ingest_years", return_value=(2022, 2022)):
            df = fetch_esg_raw(tmp_path)
        assert "WLD" not in df["iso3"].values
        assert "USA" not in df["iso3"].values

    def test_pillar_tagged(self, tmp_path):
        with patch("src.ingest.esg.wb_get", side_effect=self._wb_get_router), \
             patch("src.ingest.esg._ingest_years", return_value=(2022, 2022)):
            df = fetch_esg_raw(tmp_path)
        assert df["pillar"].notna().all()
        assert set(df["pillar"]).issubset({"governance", "social", "environmental"})

    def test_csv_matches_returned_df(self, tmp_path):
        with patch("src.ingest.esg.wb_get", side_effect=self._wb_get_router), \
             patch("src.ingest.esg._ingest_years", return_value=(2022, 2022)):
            df = fetch_esg_raw(tmp_path)
        csv = pd.read_csv(tmp_path / "esg.csv")
        assert len(csv) == len(df)


# ---------------------------------------------------------------------------
# fetch_lending_raw
# ---------------------------------------------------------------------------

from src.ingest.lending import fetch_lending_raw


class TestFetchLendingRaw:
    def test_returns_dataframe(self, tmp_path):
        with patch("src.ingest.lending.try_datasets", return_value=_fake_loans_df()):
            df = fetch_lending_raw(tmp_path)
        assert isinstance(df, pd.DataFrame)
        assert not df.empty

    def test_writes_csv(self, tmp_path):
        with patch("src.ingest.lending.try_datasets", return_value=_fake_loans_df()):
            fetch_lending_raw(tmp_path)
        assert (tmp_path / "loans.csv").exists()

    def test_schema(self, tmp_path):
        with patch("src.ingest.lending.try_datasets", return_value=_fake_loans_df()):
            df = fetch_lending_raw(tmp_path)
        assert set(df.columns) >= {
            "loan_id", "country", "fiscal_year",
            "commitment_amount", "disbursement_amount", "source",
        }

    def test_row_count_matches_source(self, tmp_path):
        """Bronze layer must NOT aggregate — one row per loan.
        try_datasets is called twice (IBRD + IDA); with identical fake data
        the result is 2 × the source length.
        """
        with patch("src.ingest.lending.try_datasets", return_value=_fake_loans_df()):
            df = fetch_lending_raw(tmp_path)
        assert len(df) == len(_fake_loans_df()) * 2  # IBRD rows + IDA rows

    def test_fiscal_year_populated(self, tmp_path):
        with patch("src.ingest.lending.try_datasets", return_value=_fake_loans_df()):
            df = fetch_lending_raw(tmp_path)
        assert df["fiscal_year"].notna().all()

    def test_empty_api_returns_empty_df(self, tmp_path):
        with patch("src.ingest.lending.try_datasets", return_value=pd.DataFrame()):
            df = fetch_lending_raw(tmp_path)
        assert df.empty

    def test_ibrd_source_tagged(self, tmp_path):
        """Only IBRD returns data; IDA returns empty."""
        def fake_try(datasets, label):
            return _fake_loans_df() if label == "IBRD" else pd.DataFrame()

        with patch("src.ingest.lending.try_datasets", side_effect=fake_try):
            df = fetch_lending_raw(tmp_path)
        assert (df["source"] == "IBRD").all()

    def test_ida_source_tagged(self, tmp_path):
        """When IDA try_datasets returns data the source tag should be IDA."""
        def fake_try(datasets, label):
            return _fake_loans_df() if label == "IDA" else pd.DataFrame()

        with patch("src.ingest.lending.try_datasets", side_effect=fake_try):
            df = fetch_lending_raw(tmp_path)
        assert (df["source"] == "IDA").all()

    def test_csv_matches_returned_df(self, tmp_path):
        with patch("src.ingest.lending.try_datasets", return_value=_fake_loans_df()):
            df = fetch_lending_raw(tmp_path)
        csv = pd.read_csv(tmp_path / "loans.csv")
        assert len(csv) == len(df)


# ---------------------------------------------------------------------------
# fetch_ieg_raw
# ---------------------------------------------------------------------------

from src.ingest.ieg import fetch_ieg_raw


class TestFetchIegRaw:
    def test_returns_dataframe(self, tmp_path):
        with patch("src.ingest.ieg.try_datasets", return_value=_fake_ieg_df()):
            df = fetch_ieg_raw(tmp_path)
        assert isinstance(df, pd.DataFrame)
        assert not df.empty

    def test_writes_csv(self, tmp_path):
        with patch("src.ingest.ieg.try_datasets", return_value=_fake_ieg_df()):
            fetch_ieg_raw(tmp_path)
        assert (tmp_path / "ratings.csv").exists()

    def test_schema(self, tmp_path):
        with patch("src.ingest.ieg.try_datasets", return_value=_fake_ieg_df()):
            df = fetch_ieg_raw(tmp_path)
        assert set(df.columns) >= {
            "project_id", "country", "outcome_rating",
            "closing_year", "is_successful",
        }

    def test_is_successful_binary(self, tmp_path):
        with patch("src.ingest.ieg.try_datasets", return_value=_fake_ieg_df()):
            df = fetch_ieg_raw(tmp_path)
        assert set(df["is_successful"].unique()).issubset({0, 1})

    def test_success_ratings_classified_correctly(self, tmp_path):
        """Satisfactory / Moderately Satisfactory / Highly Satisfactory → 1."""
        with patch("src.ingest.ieg.try_datasets", return_value=_fake_ieg_df()):
            df = fetch_ieg_raw(tmp_path)
        sat_rows = df[df["outcome_rating"].str.lower().isin({
            "satisfactory", "moderately satisfactory", "highly satisfactory"
        })]
        assert (sat_rows["is_successful"] == 1).all()

    def test_unsatisfactory_classified_zero(self, tmp_path):
        with patch("src.ingest.ieg.try_datasets", return_value=_fake_ieg_df()):
            df = fetch_ieg_raw(tmp_path)
        unsat = df[df["outcome_rating"] == "Unsatisfactory"]
        assert (unsat["is_successful"] == 0).all()

    def test_closing_year_extracted_from_string(self, tmp_path):
        """exit_fy is a plain year string like '2022' — must parse to Int64."""
        with patch("src.ingest.ieg.try_datasets", return_value=_fake_ieg_df()):
            df = fetch_ieg_raw(tmp_path)
        assert df["closing_year"].notna().all()
        assert df["closing_year"].iloc[0] == 2022

    def test_empty_api_returns_empty_df(self, tmp_path):
        with patch("src.ingest.ieg.try_datasets", return_value=pd.DataFrame()):
            df = fetch_ieg_raw(tmp_path)
        assert df.empty

    def test_country_stripped(self, tmp_path):
        """Countries with leading/trailing whitespace should be stripped."""
        dirty = _fake_ieg_df().copy()
        dirty["country"] = "  Brazil  "
        with patch("src.ingest.ieg.try_datasets", return_value=dirty):
            df = fetch_ieg_raw(tmp_path)
        assert (df["country"] == "Brazil").all()

    def test_csv_matches_returned_df(self, tmp_path):
        with patch("src.ingest.ieg.try_datasets", return_value=_fake_ieg_df()):
            df = fetch_ieg_raw(tmp_path)
        csv = pd.read_csv(tmp_path / "ratings.csv")
        assert len(csv) == len(df)
