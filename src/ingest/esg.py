"""
Dataset 1: Sovereign ESG indicators from the World Bank Indicators API.

Bronze layer only: fetches raw indicator values and writes
esg_indicators_raw.csv. Scoring/normalization lives in src.transform.
"""

from pathlib import Path

import pandas as pd

from .config import ESG_INDICATORS, WB_API
from .http import log, wb_get

_CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"


def _ingest_years() -> tuple[int, int]:
    import yaml
    with open(_CONFIG_PATH) as f:
        cfg = yaml.safe_load(f)
    ing = cfg["ingest"]
    return ing["start_year"], ing["end_year"]


def fetch_country_list() -> pd.DataFrame:
    """Return all real countries (excludes regional/income-group aggregates)."""
    data = wb_get(f"{WB_API}/country", {"format": "json", "per_page": 400})
    rows = []
    for c in data[1]:
        if c.get("region", {}).get("value") == "Aggregates":
            continue
        rows.append({
            "iso3":         c["id"],
            "iso2":         c["iso2Code"],
            "country":      c["name"],
            "region":       c["region"]["value"],
            "income_level": c["incomeLevel"]["value"],
        })
    return pd.DataFrame(rows)


def fetch_indicator(code: str, start: int, end: int) -> pd.DataFrame:
    """Pull one indicator for all countries over [start, end]."""
    rows, page = [], 1
    while True:
        data = wb_get(
            f"{WB_API}/country/all/indicator/{code}",
            {"format": "json", "per_page": 20000, "page": page,
             "date": f"{start}:{end}"},
        )
        if not isinstance(data, list) or len(data) < 2 or data[1] is None:
            break
        meta, obs = data[0], data[1]
        for o in obs:
            if o["value"] is None:
                continue
            rows.append({
                "iso3":      o["countryiso3code"],
                "country":   o["country"]["value"],
                "year":      int(o["date"]),
                "indicator": code,
                "value":     float(o["value"]),
            })
        if page >= meta.get("pages", 1):
            break
        page += 1
    return pd.DataFrame(rows)


def _fetch_all_indicators(start: int, end: int) -> pd.DataFrame:
    """Pull every ESG indicator, filter to real countries, tag with pillar."""
    iso_ok  = set(fetch_country_list()["iso3"])
    frames: list[pd.DataFrame] = []
    pillars: dict[str, str]    = {}

    for pillar, indicators in ESG_INDICATORS.items():
        for code, (name, _direction) in indicators.items():
            log(f"  pulling {code}  ({name})")
            df = fetch_indicator(code, start, end)
            if df.empty:
                log(f"    -> no data returned, skipping {code}")
                continue
            frames.append(df[df["iso3"].isin(iso_ok)])
            pillars[code] = pillar

    raw = pd.concat(frames, ignore_index=True)
    raw["pillar"] = raw["indicator"].map(pillars)
    return raw


def fetch_esg_raw(outdir: Path) -> pd.DataFrame:
    """BRONZE: pull raw indicator values for all countries, write esg.csv.

    Reads start/end year from src/config.yaml.
    Returns one row per country-year-indicator.
    """
    start, end = _ingest_years()
    log("== Dataset 1: Sovereign ESG indicators (bronze) ==")
    raw = _fetch_all_indicators(start, end)
    outdir.mkdir(parents=True, exist_ok=True)
    raw.to_csv(outdir / "esg.csv", index=False)
    log(f"  esg.csv: {len(raw):,} rows\n")
    return raw
