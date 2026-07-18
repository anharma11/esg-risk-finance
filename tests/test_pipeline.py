"""
Unit tests for the esg-risk-finance pipeline.
All tests use synthetic DataFrames — zero network calls.
"""

import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# ingest.lending
# ---------------------------------------------------------------------------

from src.ingest.lending import _wb_fiscal_year, _prep_lending_frame


class TestWbFiscalYear:
    def test_before_july_stays_same_year(self):
        s = pd.Series(["2023-06-30"])
        assert _wb_fiscal_year(s).iloc[0] == 2023

    def test_july_onwards_bumps_year(self):
        s = pd.Series(["2023-07-01", "2023-12-31"])
        result = _wb_fiscal_year(s)
        assert result.iloc[0] == 2024
        assert result.iloc[1] == 2024

    def test_bad_dates_become_na(self):
        s = pd.Series(["not-a-date", None])
        result = _wb_fiscal_year(s)
        assert result.isna().all()


class TestPrepLendingFrame:
    def _make_raw(self):
        return pd.DataFrame({
            "loan_number":               ["L001", "L002"],
            "country":                   ["Brazil", "India"],
            "board_approval_date":       ["2022-03-15", "2022-08-01"],
            "original_principal_amount": [1_000_000, 2_000_000],
            "disbursed_amount":          [500_000,   1_000_000],
        })

    def test_returns_expected_columns(self):
        df = _prep_lending_frame(self._make_raw(), "IBRD")
        assert set(df.columns) == {
            "loan_id", "country", "fiscal_year",
            "commitment_amount", "disbursement_amount", "source",
        }

    def test_fiscal_year_correct(self):
        df = _prep_lending_frame(self._make_raw(), "IBRD")
        # March → FY2022, August → FY2023
        assert df.loc[df["country"] == "Brazil", "fiscal_year"].iloc[0] == 2022
        assert df.loc[df["country"] == "India",  "fiscal_year"].iloc[0] == 2023

    def test_source_tagged(self):
        df = _prep_lending_frame(self._make_raw(), "IDA")
        assert (df["source"] == "IDA").all()

    def test_missing_required_columns_returns_empty(self):
        bad = pd.DataFrame({"loan_number": ["X"], "some_col": [1]})
        df = _prep_lending_frame(bad, "IBRD")
        assert df.empty

    def test_amounts_numeric(self):
        df = _prep_lending_frame(self._make_raw(), "IBRD")
        assert pd.api.types.is_numeric_dtype(df["commitment_amount"])
        assert pd.api.types.is_numeric_dtype(df["disbursement_amount"])


# ---------------------------------------------------------------------------
# ingest.join
# ---------------------------------------------------------------------------

from src.ingest.join import _clean, fuzzy_match_to_canonical


class TestClean:
    def test_lowercases(self):
        s = pd.Series(["Brazil", "INDIA"])
        assert (_clean(s) == pd.Series(["brazil", "india"])).all()

    def test_strips_whitespace(self):
        s = pd.Series(["  Brazil  "])
        assert _clean(s).iloc[0] == "brazil"

    def test_strips_accents(self):
        s = pd.Series(["Côte d'Ivoire"])
        result = _clean(s).iloc[0]
        assert "o" in result  # accent removed
        assert "\u00f4" not in result


class TestFuzzyMatchToCanonical:
    def test_exact_match(self):
        names     = pd.Series(["brazil"])
        canonical = pd.Series(["brazil", "india", "china"])
        result = fuzzy_match_to_canonical(names, canonical, threshold=85)
        assert result.iloc[0] == "brazil"

    def test_close_match(self):
        names     = pd.Series(["Viet Nam"])
        canonical = pd.Series(["Vietnam", "Laos", "Cambodia"])
        result = fuzzy_match_to_canonical(names, canonical, threshold=70)
        assert result.iloc[0] == "vietnam"

    def test_no_match_returns_original(self):
        names     = pd.Series(["zzznomatch"])
        canonical = pd.Series(["brazil", "india"])
        result = fuzzy_match_to_canonical(names, canonical, threshold=90)
        assert result.iloc[0] == "zzznomatch"


# ---------------------------------------------------------------------------
# transform.aggregate_esg
# ---------------------------------------------------------------------------

from src.transform.aggregate_esg import aggregate_esg


def _make_raw_esg() -> pd.DataFrame:
    """Minimal raw ESG DataFrame: 2 countries × 2 years × 2 indicators."""
    rows = []
    for iso, country in [("BRA", "Brazil"), ("IND", "India")]:
        for year in [2022, 2023]:
            rows.append({
                "iso3": iso, "country": country, "year": year,
                "indicator": "GE.EST", "pillar": "governance", "value": 1.0 if iso == "BRA" else 0.0,
            })
            rows.append({
                "iso3": iso, "country": country, "year": year,
                "indicator": "EG.FEC.RNEW.ZS", "pillar": "environmental", "value": 80.0 if iso == "BRA" else 20.0,
            })
    return pd.DataFrame(rows)


class TestAggregateEsg:
    def test_returns_one_row_per_country_year(self):
        result = aggregate_esg(_make_raw_esg())
        assert len(result) == 4  # 2 countries × 2 years

    def test_output_columns_present(self):
        result = aggregate_esg(_make_raw_esg())
        for col in ("esg_score", "esg_risk_score",
                    "governance_score", "environmental_score"):
            assert col in result.columns, f"missing column: {col}"

    def test_esg_risk_is_complement(self):
        result = aggregate_esg(_make_raw_esg())
        diff = (result["esg_score"] + result["esg_risk_score"] - 100).abs()
        assert (diff < 0.2).all(), "esg_risk_score should equal 100 - esg_score"

    def test_scores_bounded_0_to_100(self):
        result = aggregate_esg(_make_raw_esg())
        for col in ("esg_score", "esg_risk_score",
                    "governance_score", "environmental_score"):
            assert result[col].between(0, 100).all(), f"{col} out of [0, 100]"

    def test_higher_value_good_indicator_gives_higher_score(self):
        # GE.EST is +1 direction: Brazil (1.0) should outscore India (0.0)
        result = aggregate_esg(_make_raw_esg())
        bra = result.loc[result["iso3"] == "BRA", "governance_score"].mean()
        ind = result.loc[result["iso3"] == "IND", "governance_score"].mean()
        assert bra > ind

    def test_single_value_per_cell_scores_50(self):
        """If only one country has data for an indicator-year, score = 50."""
        row = pd.DataFrame([{
            "iso3": "BRA", "country": "Brazil", "year": 2022,
            "indicator": "GE.EST", "pillar": "governance", "value": 0.5,
        }])
        result = aggregate_esg(row)
        assert result["governance_score"].iloc[0] == pytest.approx(50.0, abs=0.5)


# ---------------------------------------------------------------------------
# transform.aggregate_loans
# ---------------------------------------------------------------------------

from src.transform.aggregate_loans import aggregate_loans


def _make_raw_loans() -> pd.DataFrame:
    return pd.DataFrame({
        "country":              ["Brazil", "Brazil", "India"],
        "fiscal_year":          [2022,     2022,     2022],
        "commitment_amount":    [1_000_000, 500_000, 2_000_000],
        "disbursement_amount":  [400_000,   200_000, 1_500_000],
    })


class TestAggregateLoans:
    def test_aggregates_to_country_year(self):
        result = aggregate_loans(_make_raw_loans())
        assert len(result) == 2  # Brazil + India

    def test_sums_amounts(self):
        result = aggregate_loans(_make_raw_loans())
        bra = result.loc[result["country"] == "Brazil", "commitment_amount"].iloc[0]
        assert bra == pytest.approx(1_500_000)

    def test_n_loans_counts_rows(self):
        result = aggregate_loans(_make_raw_loans())
        bra = result.loc[result["country"] == "Brazil", "n_loans"].iloc[0]
        assert bra == 2

    def test_lending_amount_equals_commitment(self):
        result = aggregate_loans(_make_raw_loans())
        pd.testing.assert_series_equal(
            result["lending_amount"], result["commitment_amount"],
            check_names=False,
        )

    def test_empty_input_returns_empty(self):
        result = aggregate_loans(pd.DataFrame())
        assert result.empty


# ---------------------------------------------------------------------------
# transform.aggregate_ratings
# ---------------------------------------------------------------------------

from src.transform.aggregate_ratings import aggregate_ratings


def _make_raw_ratings() -> pd.DataFrame:
    return pd.DataFrame({
        "project_id":    ["P001", "P002", "P003", "P004"],
        "country":       ["Brazil", "Brazil", "India", "India"],
        "closing_year":  pd.array([2022, 2022, 2022, 2022], dtype="Int64"),
        "is_successful": [1, 0, 1, 1],
    })


class TestAggregateRatings:
    def test_aggregates_to_country_year(self):
        result = aggregate_ratings(_make_raw_ratings())
        assert len(result) == 2

    def test_success_rate_percentage(self):
        result = aggregate_ratings(_make_raw_ratings())
        bra = result.loc[result["country"] == "Brazil", "success_rate"].iloc[0]
        assert bra == pytest.approx(50.0)  # 1/2 successful

    def test_india_full_success(self):
        result = aggregate_ratings(_make_raw_ratings())
        ind = result.loc[result["country"] == "India", "success_rate"].iloc[0]
        assert ind == pytest.approx(100.0)

    def test_projects_evaluated_count(self):
        result = aggregate_ratings(_make_raw_ratings())
        bra = result.loc[result["country"] == "Brazil", "projects_evaluated"].iloc[0]
        assert bra == 2

    def test_empty_input_returns_empty(self):
        result = aggregate_ratings(pd.DataFrame())
        assert result.empty


# ---------------------------------------------------------------------------
# analyze.scores
# ---------------------------------------------------------------------------

from src.analyze.scores import add_exposure, add_priority


def _make_master() -> pd.DataFrame:
    return pd.DataFrame({
        "country":        ["A", "B", "C"],
        "esg_risk_score": [80.0, 50.0, 20.0],
        "lending_amount": [1_000_000, 500_000, 0],
    })


class TestAddExposure:
    def test_max_lending_gets_100(self):
        result = add_exposure(_make_master())
        assert result.loc[result["country"] == "A", "exposure_score"].iloc[0] == pytest.approx(100.0)

    def test_zero_lending_gets_0(self):
        result = add_exposure(_make_master())
        assert result.loc[result["country"] == "C", "exposure_score"].iloc[0] == pytest.approx(0.0)

    def test_scores_bounded_0_to_100(self):
        result = add_exposure(_make_master())
        assert result["exposure_score"].between(0, 100).all()

    def test_does_not_mutate_input(self):
        original = _make_master()
        add_exposure(original)
        assert "exposure_score" not in original.columns


class TestAddPriority:
    def test_high_risk_high_exposure_tops(self):
        df = add_exposure(_make_master())
        result = add_priority(df)
        # Country A: risk=80, exposure=100 → priority should be highest
        assert result.loc[result["country"] == "A", "priority_score"].iloc[0] == \
               result["priority_score"].max()

    def test_zero_exposure_gives_zero_priority(self):
        df = add_exposure(_make_master())
        result = add_priority(df)
        assert result.loc[result["country"] == "C", "priority_score"].iloc[0] == pytest.approx(0.0)

    def test_does_not_mutate_input(self):
        df = add_exposure(_make_master())
        original_cols = set(df.columns)
        add_priority(df)
        assert "priority_score" not in original_cols


# ---------------------------------------------------------------------------
# analyze.correlation
# ---------------------------------------------------------------------------

from src.analyze.correlation import ieg_analysis, pillar_analysis


def _make_analysis_df(n: int = 30) -> pd.DataFrame:
    import numpy as np
    rng = np.random.default_rng(42)
    risk = rng.uniform(0, 100, n)
    # Negatively correlated: high risk → lower success
    success = 100 - risk + rng.normal(0, 10, n)
    success = success.clip(0, 100)
    return pd.DataFrame({
        "country":              [f"C{i}" for i in range(n)],
        "year":                 [2022] * n,
        "esg_risk_score":       risk,
        "success_rate":         success,
        "environmental_score":  rng.uniform(20, 80, n),
        "social_score":         rng.uniform(20, 80, n),
        "governance_score":     rng.uniform(20, 80, n),
        "lending_amount":       rng.uniform(0, 1e6, n),
    })


class TestIegAnalysis:
    def test_returns_r_and_p(self):
        result = ieg_analysis(_make_analysis_df())
        assert result is not None
        r, p = result
        assert -1.0 <= r <= 1.0
        assert 0.0 <= p <= 1.0

    def test_negative_correlation_detected(self):
        r, _ = ieg_analysis(_make_analysis_df())
        assert r < 0, "synthetic data is negatively correlated"

    def test_too_few_rows_returns_none(self):
        df = _make_analysis_df(3)
        result = ieg_analysis(df)
        assert result is None

    def test_all_nan_success_returns_none(self):
        df = _make_analysis_df(20)
        df["success_rate"] = float("nan")
        result = ieg_analysis(df)
        assert result is None


class TestPillarAnalysis:
    def test_runs_without_error(self):
        """Smoke test — just ensure no exception is raised."""
        pillar_analysis(_make_analysis_df())
