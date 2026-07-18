"""
End-to-end aggregation pipeline.

Reads raw Delta tables, aggregates each dataset, joins them into a master
table, and writes all results back to Unity Catalog. Designed to run inside
Databricks.

Usage (Databricks notebook):
    from src.transform.write import run
    run(spark)
"""

from __future__ import annotations

from pathlib import Path
import tempfile
import pandas as pd
import yaml

from .aggregate_esg     import aggregate_esg
from .aggregate_loans   import aggregate_loans
from .aggregate_ratings import aggregate_ratings
from ..ingest.join      import build_master

_CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"


def _load_config() -> dict:
    with open(_CONFIG_PATH) as f:
        return yaml.safe_load(f)


def _overwrite(spark, df: pd.DataFrame, full_name: str) -> None:
    """Write a DataFrame to a Delta table, replacing all existing data."""
    sdf = spark.createDataFrame(df)
    (sdf.write
        .format("delta")
        .mode("overwrite")
        .option("overwriteSchema", "true")
        .saveAsTable(full_name))
    print(f"  ✓ {full_name}: {sdf.count():,} rows written")


def run(spark) -> None:
    """Aggregate raw tables and write results to Unity Catalog.

    Reads catalog/schema from src/config.yaml.

    Raw tables read:
        {catalog}.{schema}.esg
        {catalog}.{schema}.loans
        {catalog}.{schema}.ratings

    Aggregated tables written:
        {catalog}.{schema}.aggregate_esg          ESG risk scores per country-year
        {catalog}.{schema}.aggregate_loans        Lending totals per country-year
        {catalog}.{schema}.aggregate_ratings      Project success rates per country-year
        {catalog}.{schema}.esg_lending_master     All three joined into one master table
    """
    cfg     = _load_config()
    catalog = cfg["uc"]["catalog"]
    schema  = cfg["uc"]["schema"]

    def tbl(name: str) -> str:
        return f"{catalog}.{schema}.{name}"

    print(f"=== Aggregation | catalog={catalog} | schema={schema} ===")

    # --- Read raw tables ---
    print("\n== Reading raw tables ==")
    esg_raw     = spark.table(tbl("esg")).toPandas()
    loans_raw   = spark.table(tbl("loans")).toPandas()
    ratings_raw = spark.table(tbl("ratings")).toPandas()

    # --- Aggregate each dataset ---
    print("\n== Aggregating ==")
    print("  ESG indicators → scores")
    esg = aggregate_esg(esg_raw)

    print("  Loans → commitments by country-year")
    lending = aggregate_loans(loans_raw)

    print("  Project ratings → success rates by country-year")
    success = aggregate_ratings(ratings_raw)

    # --- Join into master table ---
    print("\n== Building master table ==")
    _tmp = Path(tempfile.mkdtemp())
    build_master(esg, lending, success, _tmp)
    master = pd.read_csv(_tmp / "esg_lending_master.csv")

    # --- Write aggregated tables ---
    print("\n== Writing aggregated tables ==")
    _overwrite(spark, esg,    tbl("aggregate_esg"))
    if not lending.empty:
        _overwrite(spark, lending, tbl("aggregate_loans"))
    if not success.empty:
        _overwrite(spark, success, tbl("aggregate_ratings"))
    _overwrite(spark, master, tbl("esg_lending_master"))

    print("\nDone.")

