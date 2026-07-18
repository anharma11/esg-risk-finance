"""
End-to-end ingest → Delta write pipeline.

Reads UC paths and ingest settings from src/config.yaml, pulls raw data from
the three APIs, saves CSVs to the UC volume, then merges each into its Delta
table with deduplication.

Designed to run inside a Databricks notebook or job where a SparkSession
is already active (spark is in scope).

Usage (Databricks notebook — Python cell):
    import sys
    sys.path.insert(0, "/Workspace/path/to/risk_finance")
    from src.ingest.write import run
    run(spark)

    # Override config values at call time if needed:
    run(spark, start_year=2020, end_year=2024, skip_ieg=True)
"""

from __future__ import annotations

from pathlib import Path
import yaml

from .esg     import fetch_esg_raw
from .ieg     import fetch_ieg_raw
from .lending import fetch_lending_raw


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"


def _load_config() -> dict:
    with open(_CONFIG_PATH) as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# Delta write helpers
# ---------------------------------------------------------------------------

def _full_table(catalog: str, schema: str, table: str) -> str:
    return f"{catalog}.{schema}.{table}"


def _ensure_table(spark, sdf, full_name: str) -> None:
    if not spark.catalog.tableExists(full_name):
        sdf.limit(0).write.format("delta").saveAsTable(full_name)


def _merge(spark, sdf, full_name: str, merge_keys: list[str]) -> None:
    from delta.tables import DeltaTable

    condition  = " AND ".join(f"t.{k} = s.{k}" for k in merge_keys)
    update_map = {c: f"s.{c}" for c in sdf.columns if c not in merge_keys}
    insert_map = {c: f"s.{c}" for c in sdf.columns}

    (
        DeltaTable.forName(spark, full_name)
        .alias("t")
        .merge(sdf.alias("s"), condition)
        .whenMatchedUpdate(set=update_map)
        .whenNotMatchedInsert(values=insert_map)
        .execute()
    )


# ---------------------------------------------------------------------------
# Per-table write functions
# ---------------------------------------------------------------------------

def _write_esg(spark, df, catalog: str, schema: str) -> None:
    """Merge esg raw DataFrame → Delta table. Dedup key: (iso3, year, indicator)."""
    full_name  = _full_table(catalog, schema, "esg")
    merge_keys = ["iso3", "year", "indicator"]

    sdf = spark.createDataFrame(df).dropDuplicates(merge_keys)
    _ensure_table(spark, sdf, full_name)
    _merge(spark, sdf, full_name, merge_keys)
    print(f"  ✓ {full_name}: {sdf.count():,} rows merged")


def _write_loans(spark, df, catalog: str, schema: str) -> None:
    """Merge loans DataFrame → Delta table.

    Dedup key: loan_id if the column is present (raw bronze loans),
    otherwise (country, fiscal_year, source) for pre-aggregated data.
    """
    full_name = _full_table(catalog, schema, "loans")

    sdf = spark.createDataFrame(df)

    if "loan_id" in df.columns:
        merge_keys = ["loan_id"]
        sdf = sdf.dropDuplicates(merge_keys)
    else:
        merge_keys = ["country", "fiscal_year", "source"]
        sdf = sdf.dropDuplicates(merge_keys)

    _ensure_table(spark, sdf, full_name)
    _merge(spark, sdf, full_name, merge_keys)
    print(f"  ✓ {full_name}: {sdf.count():,} rows written")



def _write_ratings(spark, df, catalog: str, schema: str) -> None:
    """Merge ratings raw DataFrame → Delta table. Dedup key: project_id."""
    full_name  = _full_table(catalog, schema, "ratings")
    merge_keys = ["project_id"]

    sdf = (
        spark.createDataFrame(df)
             .filter("project_id IS NOT NULL")
             .dropDuplicates(merge_keys)
    )
    _ensure_table(spark, sdf, full_name)
    _merge(spark, sdf, full_name, merge_keys)
    print(f"  ✓ {full_name}: {sdf.count():,} rows merged")


# ---------------------------------------------------------------------------
# End-to-end entry point
# ---------------------------------------------------------------------------

def run(
    spark,
    skip_ieg: bool | None = None,
) -> None:
    """Full pipeline: ingest from APIs → save to UC volume → merge to Delta.

    All settings (years, catalog, schema, volume path) are read from
    src/config.yaml. Pass skip_ieg=True to skip the IEG ratings pull.
    """
    cfg  = _load_config()
    uc   = cfg["uc"]
    ing  = cfg["ingest"]

    catalog     = uc["catalog"]
    schema      = uc["schema"]
    volume_path = Path(uc["volume_path"])
    skip_ieg    = skip_ieg if skip_ieg is not None else ing["skip_ieg"]

    print(f"=== Ingest | catalog={catalog} | schema={schema} ===")

    # 1. Pull raw data → save to UC volume
    esg_df   = fetch_esg_raw(volume_path)
    loans_df = fetch_lending_raw(volume_path)
    ieg_df   = fetch_ieg_raw(volume_path) if not skip_ieg else None

    # 2. Merge into Delta tables
    print("\n=== Writing to Delta ===")
    _write_esg(spark, esg_df, catalog, schema)
    _write_loans(spark, loans_df, catalog, schema)
    if ieg_df is not None and not ieg_df.empty:
        _write_ratings(spark, ieg_df, catalog, schema)
    else:
        print(f"  (IEG skipped)")

    print("\nDone.")

