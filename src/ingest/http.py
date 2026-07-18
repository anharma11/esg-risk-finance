"""
Shared HTTP helpers: a persistent requests.Session, the World Bank Indicators
pager, the Finances One pager, and small utilities used by multiple fetch modules.
"""

import time

import pandas as pd
import requests

from .config import FONE_API

# Single session reused across all API calls.
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "esg-risk-scoring/1.0 (research script)"})


def log(msg: str) -> None:
    print(msg, flush=True)


# ---------------------------------------------------------------------------
# World Bank Indicators API helpers
# ---------------------------------------------------------------------------

def wb_get(url: str, params: dict, retries: int = 3) -> list:
    """GET a WB Indicators URL with retry/back-off. Returns parsed JSON."""
    for attempt in range(retries):
        try:
            r = SESSION.get(url, params=params, timeout=60)
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError) as exc:
            if attempt == retries - 1:
                raise
            time.sleep(2 * (attempt + 1))
            log(f"    retrying after error: {exc}")


# ---------------------------------------------------------------------------
# Finances One API helpers
# ---------------------------------------------------------------------------

def fone_fetch_all(dataset_id: str, resource_id: str,
                   page_size: int = 1000) -> pd.DataFrame:
    """Page through a Finances One dataset and return all rows as a DataFrame.

    Response envelope: {"count": <total>, "data": [{...}, ...]}.
    API caps each request at 1000 rows; we page with top/skip.
    """
    rows: list[dict] = []
    skip = 0
    while True:
        params = {
            "datasetId":  dataset_id,
            "resourceId": resource_id,
            "type":       "json",
            "top":        page_size,
            "skip":       skip,
        }
        r = SESSION.get(FONE_API, params=params, timeout=120)
        r.raise_for_status()
        payload = r.json()
        batch = payload.get("data", []) if isinstance(payload, dict) else []
        total = payload.get("count")    if isinstance(payload, dict) else None
        rows.extend(batch)
        log(f"    {dataset_id}: fetched {len(rows):,}"
            + (f"/{total:,}" if total else "") + " rows so far")
        if not batch:
            break
        if total is not None and len(rows) >= total:
            break
        if len(batch) < page_size:
            break
        skip += page_size
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Shared utilities
# ---------------------------------------------------------------------------

def pick_col(df: pd.DataFrame, candidates: list[str]) -> str | None:
    """Return the first matching column name (case-insensitive) or None."""
    cols = {c.lower(): c for c in df.columns}
    for cand in candidates:
        if cand in cols:
            return cols[cand]
    return None


def try_datasets(datasets: list[tuple[str, str]], label: str) -> pd.DataFrame:
    """Try each (datasetId, resourceId) pair in order; return first non-empty result."""
    for dataset_id, resource_id in datasets:
        try:
            log(f"  trying {label} dataset {dataset_id} (resource {resource_id})")
            df = fone_fetch_all(dataset_id, resource_id)
            if not df.empty:
                return df
        except requests.RequestException as exc:
            log(f"    {dataset_id} failed ({exc}); trying next candidate")
    log(f"  !! could not fetch any {label} dataset")
    return pd.DataFrame()
