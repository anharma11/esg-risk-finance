"""
Tests for src.ingest.write — Delta merge logic.

SparkSession and DeltaTable are fully mocked so these run locally
without Databricks. The tests verify merge keys, dedup, table creation
calls, and that the right functions are invoked for each dataset.
"""

import pandas as pd
import pytest
from unittest.mock import MagicMock, patch, call


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def spark():
    """Minimal SparkSession mock."""
    s = MagicMock(name="SparkSession")
    s.catalog.tableExists.return_value = True   # table already exists by default
    # createDataFrame returns a Spark DataFrame mock
    sdf = MagicMock(name="SparkDataFrame")
    sdf.columns = []          # overridden per test
    sdf.count.return_value = 10
    sdf.dropDuplicates.return_value = sdf
    sdf.filter.return_value = sdf
    sdf.limit.return_value = sdf
    sdf.write.format.return_value.saveAsTable = MagicMock()
    s.createDataFrame.return_value = sdf
    return s


@pytest.fixture()
def esg_df():
    return pd.DataFrame({
        "iso3":      ["BRA", "BRA", "IND"],
        "country":   ["Brazil", "Brazil", "India"],
        "year":      [2022, 2022, 2022],
        "indicator": ["GE.EST", "GE.EST", "GE.EST"],  # duplicate BRA row
        "pillar":    ["governance", "governance", "governance"],
        "value":     [0.5, 0.5, 0.2],
    })


@pytest.fixture()
def loans_df():
    return pd.DataFrame({
        "loan_id":              ["L001", "L002"],
        "country":              ["Brazil", "India"],
        "fiscal_year":          [2022, 2022],
        "commitment_amount":    [1_000_000, 2_000_000],
        "disbursement_amount":  [500_000, 1_000_000],
        "source":               ["IBRD", "IDA"],
    })


@pytest.fixture()
def loans_df_no_id():
    """Aggregated loans without loan_id — uses composite merge key."""
    return pd.DataFrame({
        "country":              ["Brazil", "India"],
        "fiscal_year":          [2022, 2022],
        "commitment_amount":    [1_500_000, 2_000_000],
        "disbursement_amount":  [700_000, 1_000_000],
        "source":               ["IBRD", "IDA"],
    })


@pytest.fixture()
def ratings_df():
    return pd.DataFrame({
        "project_id":    ["P001", "P002", "P003"],
        "country":       ["Brazil", "India", "Brazil"],
        "outcome_rating":["Satisfactory", "Unsatisfactory", "Highly Satisfactory"],
        "sector":        ["Finance", "Health", "Transport"],
        "closing_year":  pd.array([2022, 2021, 2020], dtype="Int64"),
        "is_successful": [1, 0, 1],
    })


# ---------------------------------------------------------------------------
# _write_esg
# ---------------------------------------------------------------------------

from src.ingest.write import _write_esg, _write_loans, _write_ratings, _merge, _ensure_table


class TestWriteEsg:
    @pytest.fixture(autouse=True)
    def _no_delta(self):
        with patch("src.ingest.write._merge"):
            yield

    def test_calls_create_dataframe(self, spark, esg_df):
        _write_esg(spark, esg_df, "cat", "sch")
        spark.createDataFrame.assert_called_once()

    def test_deduplicates_on_merge_keys(self, spark, esg_df):
        sdf = spark.createDataFrame.return_value
        sdf.columns = list(esg_df.columns)
        _write_esg(spark, esg_df, "cat", "sch")
        sdf.dropDuplicates.assert_called_once_with(["iso3", "year", "indicator"])

    def test_creates_table_when_missing(self, spark, esg_df):
        spark.catalog.tableExists.return_value = False
        sdf = spark.createDataFrame.return_value
        sdf.columns = list(esg_df.columns)
        _write_esg(spark, esg_df, "cat", "sch")
        sdf.limit.assert_called_with(0)
        sdf.limit.return_value.write.format.assert_called_with("delta")

    def test_skips_create_when_table_exists(self, spark, esg_df):
        spark.catalog.tableExists.return_value = True
        sdf = spark.createDataFrame.return_value
        sdf.columns = list(esg_df.columns)
        _write_esg(spark, esg_df, "cat", "sch")
        sdf.limit.assert_not_called()

    def test_full_table_name_used(self, spark, esg_df):
        with patch("src.ingest.write._merge") as mock_merge:
            _write_esg(spark, esg_df, "mycat", "mysch")
        mock_merge.assert_called_once()
        full_name = mock_merge.call_args[0][2]   # (spark, sdf, full_name, keys)
        assert full_name == "mycat.mysch.esg"

    def test_merge_keys(self, spark, esg_df):
        with patch("src.ingest.write._merge") as mock_merge:
            _write_esg(spark, esg_df, "cat", "sch")
        keys = mock_merge.call_args[0][3]   # (spark, sdf, full_name, keys)
        assert keys == ["iso3", "year", "indicator"]


# ---------------------------------------------------------------------------
# _write_loans
# ---------------------------------------------------------------------------

class TestWriteLoans:
    @pytest.fixture(autouse=True)
    def _no_delta(self):
        with patch("src.ingest.write._merge") as m:
            self._merge_mock = m
            yield m

    def test_uses_loan_id_when_present(self, spark, loans_df):
        sdf = spark.createDataFrame.return_value
        sdf.columns = list(loans_df.columns)
        _write_loans(spark, loans_df, "cat", "sch")
        keys = self._merge_mock.call_args[0][3]   # (spark, sdf, full_name, keys)
        assert keys == ["loan_id"]

    def test_uses_composite_key_without_loan_id(self, spark, loans_df_no_id):
        sdf = spark.createDataFrame.return_value
        sdf.columns = list(loans_df_no_id.columns)
        _write_loans(spark, loans_df_no_id, "cat", "sch")
        keys = self._merge_mock.call_args[0][3]   # (spark, sdf, full_name, keys)
        assert keys == ["country", "fiscal_year", "source"]

    def test_full_table_name_used(self, spark, loans_df):
        _write_loans(spark, loans_df, "mycat", "mysch")
        full_name = self._merge_mock.call_args[0][2]   # (spark, sdf, full_name, keys)
        assert full_name == "mycat.mysch.loans"

    def test_creates_table_when_missing(self, spark, loans_df):
        spark.catalog.tableExists.return_value = False
        sdf = spark.createDataFrame.return_value
        sdf.columns = list(loans_df.columns)
        _write_loans(spark, loans_df, "cat", "sch")
        sdf.limit.assert_called_with(0)


# ---------------------------------------------------------------------------
# _write_ratings
# ---------------------------------------------------------------------------

class TestWriteRatings:
    @pytest.fixture(autouse=True)
    def _no_delta(self):
        with patch("src.ingest.write._merge") as m:
            self._merge_mock = m
            yield m

    def test_filters_null_project_ids(self, spark, ratings_df):
        sdf = spark.createDataFrame.return_value
        sdf.columns = list(ratings_df.columns)
        _write_ratings(spark, ratings_df, "cat", "sch")
        sdf.filter.assert_called_with("project_id IS NOT NULL")

    def test_deduplicates_on_project_id(self, spark, ratings_df):
        sdf = spark.createDataFrame.return_value
        sdf.columns = list(ratings_df.columns)
        _write_ratings(spark, ratings_df, "cat", "sch")
        sdf.filter.return_value.dropDuplicates.assert_called_once_with(["project_id"])

    def test_full_table_name_used(self, spark, ratings_df):
        _write_ratings(spark, ratings_df, "mycat", "mysch")
        full_name = self._merge_mock.call_args[0][2]   # (spark, sdf, full_name, keys)
        assert full_name == "mycat.mysch.ratings"

    def test_merge_keys(self, spark, ratings_df):
        _write_ratings(spark, ratings_df, "cat", "sch")
        keys = self._merge_mock.call_args[0][3]   # (spark, sdf, full_name, keys)
        assert keys == ["project_id"]


# ---------------------------------------------------------------------------
# run() — end-to-end orchestration
# ---------------------------------------------------------------------------

from src.ingest.write import run


class TestRun:
    def _make_spark(self):
        s = MagicMock(name="SparkSession")
        s.catalog.tableExists.return_value = True
        sdf = MagicMock(name="SparkDataFrame")
        sdf.columns = []
        sdf.count.return_value = 5
        sdf.dropDuplicates.return_value = sdf
        sdf.filter.return_value = sdf
        s.createDataFrame.return_value = sdf
        return s

    def test_calls_all_three_writers(self):
        spark = self._make_spark()
        fake_df = pd.DataFrame({"a": [1]})
        with patch("src.ingest.write.fetch_esg_raw",     return_value=fake_df), \
             patch("src.ingest.write.fetch_lending_raw", return_value=fake_df), \
             patch("src.ingest.write.fetch_ieg_raw",     return_value=fake_df), \
             patch("src.ingest.write._write_esg")     as we, \
             patch("src.ingest.write._write_loans")   as wl, \
             patch("src.ingest.write._write_ratings") as wr:
            run(spark)
        we.assert_called_once()
        wl.assert_called_once()
        wr.assert_called_once()

    def test_skips_ieg_when_flag_set(self):
        spark = self._make_spark()
        fake_df = pd.DataFrame({"a": [1]})
        with patch("src.ingest.write.fetch_esg_raw",     return_value=fake_df), \
             patch("src.ingest.write.fetch_lending_raw", return_value=fake_df), \
             patch("src.ingest.write.fetch_ieg_raw")   as ieg_mock, \
             patch("src.ingest.write._write_esg"), \
             patch("src.ingest.write._write_loans"), \
             patch("src.ingest.write._write_ratings") as wr:
            run(spark, skip_ieg=True)
        ieg_mock.assert_not_called()
        wr.assert_not_called()

    def test_skips_write_ratings_when_ieg_empty(self):
        spark = self._make_spark()
        fake_df = pd.DataFrame({"a": [1]})
        with patch("src.ingest.write.fetch_esg_raw",     return_value=fake_df), \
             patch("src.ingest.write.fetch_lending_raw", return_value=fake_df), \
             patch("src.ingest.write.fetch_ieg_raw",     return_value=pd.DataFrame()), \
             patch("src.ingest.write._write_esg"), \
             patch("src.ingest.write._write_loans"), \
             patch("src.ingest.write._write_ratings") as wr:
            run(spark)
        wr.assert_not_called()

    def test_uses_catalog_and_schema_from_config(self):
        spark = self._make_spark()
        fake_df = pd.DataFrame({"a": [1]})
        with patch("src.ingest.write.fetch_esg_raw",     return_value=fake_df), \
             patch("src.ingest.write.fetch_lending_raw", return_value=fake_df), \
             patch("src.ingest.write.fetch_ieg_raw",     return_value=fake_df), \
             patch("src.ingest.write._write_esg") as we, \
             patch("src.ingest.write._write_loans"), \
             patch("src.ingest.write._write_ratings"):
            run(spark)
        _, _, catalog, schema = we.call_args[0]
        assert catalog == "prd_datascience_ifcwbcpm"
        assert schema  == "risk_monitoring_innov_proj"
