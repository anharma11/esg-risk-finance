"""Entry point for the Databricks transform task."""
import sys
sys.path.insert(0, "/Workspace/{workspace_path}/risk_finance")  # replace

from src.transform.write import run
run(spark)  # spark is injected by Databricks
