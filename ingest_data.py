#!/usr/bin/env python3
"""
Ingest pipeline — pull ESG, lending, and IEG datasets and write CSVs.

Usage:
    python ingest_data.py                    # full pull 2000..current year
    python ingest_data.py --start 2018 --end 2024
    python ingest_data.py --skip-ieg         # skip IEG dataset 3
    python ingest_data.py --outdir data/raw

Outputs (written to --outdir, default: ./output):
  esg_indicators_raw.csv          country-year-indicator level raw values
  esg_scores.csv                  ESG pillar scores + esg_risk_score per country-year
  lending_by_country_year.csv     IBRD+IDA commitments and disbursements per country-year
  ieg_project_ratings.csv         project-level IEG outcome ratings
  ieg_success_by_country_year.csv aggregated project success rates per country-year
  esg_lending_master.csv          final joined table (ESG + lending + success rate)
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

from src.ingest.esg     import fetch_esg
from src.ingest.ieg     import fetch_ieg
from src.ingest.join    import build_master
from src.ingest.lending import fetch_lending

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start",  type=int, default=2000)
    ap.add_argument("--end",    type=int, default=pd.Timestamp.now().year)
    ap.add_argument("--outdir", default="output")
    ap.add_argument("--skip-ieg", action="store_true",
                    help="skip Dataset 3 (IEG project success rates)")
    args = ap.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    esg     = fetch_esg(args.start, args.end, outdir)
    lending = fetch_lending(outdir)
    success = pd.DataFrame()
    if not args.skip_ieg:
        _, success = fetch_ieg(outdir)

    build_master(esg, lending, success, outdir)
    print(f"\nDone. Files written to: {outdir.resolve()}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(1)


# WBG "Finances One" data API (replaced the retired Socrata platform at
# finances.worldbank.org/resource/*.json). Each dataset is addressed by a
# datasetId + resourceId pair and paged with top/skip (max 1000 rows/page).
FONE_API = "https://datacatalogapi.worldbank.org/dexapps/fone/api/apiservice"

# ESG indicators (a focused subset of the Sovereign ESG Data Framework).
# direction: +1 means "higher value = better ESG", -1 means "higher = worse".
ESG_INDICATORS = {
    "governance": {
        "GE.EST":            ("Government Effectiveness (estimate)", +1),
        "RL.EST":            ("Rule of Law (estimate)", +1),
        "CC.EST":            ("Control of Corruption (estimate)", +1),
        "PV.EST":            ("Political Stability / Absence of Violence (estimate)", +1),
    },
    "social": {
        "SI.POV.DDAY":       ("Poverty headcount ratio at $2.15/day (%)", -1),
        "EG.ELC.ACCS.ZS":    ("Access to electricity (% of population)", +1),
        "SP.DYN.LE00.IN":    ("Life expectancy at birth (years)", +1),
        "SE.SEC.ENRR":       ("School enrollment, secondary (% gross)", +1),
    },
    "environmental": {
        # CO2 per capita: the classic code was archived; the AR5 GHG code replaced it.
        # Both are listed; the loader keeps whichever returns data.
        "EN.ATM.CO2E.PC":         ("CO2 emissions (metric tons per capita)", -1),
        "EN.GHG.CO2.PC.CE.AR5":   ("CO2 emissions per capita (AR5)", -1),
        "AG.LND.FRST.ZS":         ("Forest area (% of land area)", +1),
        "EG.FEC.RNEW.ZS":         ("Renewable energy consumption (% of total)", +1),
        "EN.ATM.PM25.MC.M3":      ("PM2.5 air pollution, mean annual exposure", -1),
    },
}

# WBG Finances One datasets, as (datasetId, resourceId) pairs tried in order.
# These are the "Latest Available Snapshot" datasets (one snapshot only, so no
# end_of_period filtering is needed).
#   IBRD Statement of Loans and Guarantees      -> DS00047 / RS00049
#   IDA  Statement of Credits, Grants & Guarantees -> DS00001 / RS00001
#   IEG  World Bank Project Performance Ratings  -> DS00053 / RS00055
IBRD_DATASETS = [("DS00047", "RS00049")]
IDA_DATASETS = [("DS00001", "RS00001")]
IEG_DATASETS = [("DS00053", "RS00055")]

# IEG outcome ratings counted as "successful"
SUCCESS_RATINGS = {
    "highly satisfactory", "satisfactory", "moderately satisfactory",
}

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "esg-risk-scoring/1.0 (research script)"})


def log(msg: str):
    print(msg, flush=True)


# ---------------------------------------------------------------------------
# Dataset 1: Sovereign ESG indicators (World Bank Indicators API)
# ---------------------------------------------------------------------------

def wb_get(url: str, params: dict, retries: int = 3):
    for attempt in range(retries):
        try:
            r = SESSION.get(url, params=params, timeout=60)
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError) as e:
            if attempt == retries - 1:
                raise
            time.sleep(2 * (attempt + 1))
            log(f"    retrying after error: {e}")


def fetch_country_list() -> pd.DataFrame:
    """Real countries only (drops regional/income aggregates)."""
    data = wb_get(f"{WB_API}/country", {"format": "json", "per_page": 400})
    rows = []
    for c in data[1]:
        if c.get("region", {}).get("value") == "Aggregates":
            continue
        rows.append({
            "iso3": c["id"],
            "iso2": c["iso2Code"],
            "country": c["name"],
            "region": c["region"]["value"],
            "income_level": c["incomeLevel"]["value"],
        })
    return pd.DataFrame(rows)


def fetch_indicator(code: str, start: int, end: int) -> pd.DataFrame:
    """Pull one indicator for all countries, all years in range."""
    rows, page = [], 1
    while True:
        data = wb_get(
            f"{WB_API}/country/all/indicator/{code}",
            {"format": "json", "per_page": 20000, "page": page,
             "date": f"{start}:{end}"},
        )
        if not isinstance(data, list) or len(data) < 2 or data[1] is None:
            break  # bad code or no data
        meta, obs = data[0], data[1]
        for o in obs:
            if o["value"] is None:
                continue
            rows.append({
                "iso3": o["countryiso3code"],
                "country": o["country"]["value"],
                "year": int(o["date"]),
                "indicator": code,
                "value": float(o["value"]),
            })
        if page >= meta.get("pages", 1):
            break
        page += 1
    return pd.DataFrame(rows)


def fetch_esg(start: int, end: int, outdir: Path) -> pd.DataFrame:
    log("== Dataset 1: Sovereign ESG indicators ==")
    countries = fetch_country_list()
    iso_ok = set(countries["iso3"])

    frames, directions, pillars = [], {}, {}
    for pillar, indicators in ESG_INDICATORS.items():
        for code, (name, direction) in indicators.items():
            log(f"  pulling {code}  ({name})")
            df = fetch_indicator(code, start, end)
            if df.empty:
                log(f"    -> no data returned, skipping {code}")
                continue
            df = df[df["iso3"].isin(iso_ok)]
            frames.append(df)
            directions[code] = direction
            pillars[code] = pillar

    raw = pd.concat(frames, ignore_index=True)
    raw["pillar"] = raw["indicator"].map(pillars)
    raw.to_csv(outdir / "esg_indicators_raw.csv", index=False)
    log(f"  raw indicator rows: {len(raw):,}")

    # --- Normalize each indicator to 0-100 within each year (cross-country
    #     min-max), flipping direction so 100 is always "best". -------------
    def normalize(group: pd.DataFrame) -> pd.Series:
        lo, hi = group["value"].min(), group["value"].max()
        if hi == lo:
            return pd.Series(50.0, index=group.index)
        scaled = (group["value"] - lo) / (hi - lo) * 100
        if directions[group.name[0]] < 0:
            scaled = 100 - scaled
        return scaled

    raw = raw.sort_values(["indicator", "year"])
    raw["norm"] = (
        raw.groupby(["indicator", "year"], group_keys=False)
           .apply(normalize, include_groups=False)
    )

    # Pillar score = mean of available normalized indicators
    pillar_scores = (
        raw.groupby(["iso3", "country", "year", "pillar"])["norm"]
           .mean().unstack("pillar").reset_index()
    )
    for col in ("environmental", "social", "governance"):
        if col not in pillar_scores:
            pillar_scores[col] = pd.NA

    pillar_scores = pillar_scores.rename(columns={
        "environmental": "environmental_score",
        "social": "social_score",
        "governance": "governance_score",
    })
    score_cols = ["environmental_score", "social_score", "governance_score"]
    pillar_scores["esg_score"] = pillar_scores[score_cols].mean(axis=1)
    pillar_scores["esg_risk_score"] = 100 - pillar_scores["esg_score"]
    pillar_scores[score_cols + ["esg_score", "esg_risk_score"]] = (
        pillar_scores[score_cols + ["esg_score", "esg_risk_score"]].round(1)
    )

    pillar_scores.to_csv(outdir / "esg_scores.csv", index=False)
    log(f"  esg_scores.csv: {len(pillar_scores):,} country-year rows\n")
    return pillar_scores


# ---------------------------------------------------------------------------
# Finances One helpers (WBG datacatalog API)
# ---------------------------------------------------------------------------

def fone_fetch_all(dataset_id: str, resource_id: str,
                   page_size: int = 1000) -> pd.DataFrame:
    """Page through a Finances One dataset and return everything as a DataFrame.

    The API returns {"count": <total>, "data": [ {row}, ... ]} and caps each
    request at 1000 rows, so we page with top/skip until we've pulled `count`.
    """
    rows, skip = [], 0
    while True:
        params = {
            "datasetId": dataset_id,
            "resourceId": resource_id,
            "type": "json",
            "top": page_size,
            "skip": skip,
        }
        r = SESSION.get(FONE_API, params=params, timeout=120)
        r.raise_for_status()
        payload = r.json()
        batch = payload.get("data", []) if isinstance(payload, dict) else []
        total = payload.get("count") if isinstance(payload, dict) else None
        rows.extend(batch)
        log(f"    {dataset_id}: fetched {len(rows):,}"
            + (f"/{total:,}" if total else "") + " rows so far")
        if not batch or (total is not None and len(rows) >= total):
            break
        if len(batch) < page_size:
            break
        skip += page_size
    return pd.DataFrame(rows)


def pick_col(df: pd.DataFrame, candidates: list[str]) -> str | None:
    cols = {c.lower(): c for c in df.columns}
    for cand in candidates:
        if cand in cols:
            return cols[cand]
    return None


def try_datasets(datasets: list[tuple[str, str]], label: str) -> pd.DataFrame:
    """Try each candidate (datasetId, resourceId) pair until one returns data."""
    for dataset_id, resource_id in datasets:
        try:
            log(f"  trying {label} dataset {dataset_id} (resource {resource_id})")
            df = fone_fetch_all(dataset_id, resource_id)
            if not df.empty:
                return df
        except requests.RequestException as e:
            log(f"    {dataset_id} failed ({e}); trying next candidate")
    log(f"  !! could not fetch any {label} dataset")
    return pd.DataFrame()


# ---------------------------------------------------------------------------
# Dataset 2: IBRD / IDA lending exposure
# ---------------------------------------------------------------------------

def wb_fiscal_year(dates: pd.Series) -> pd.Series:
    """World Bank fiscal year runs July 1 - June 30 (FY named for the June year)."""
    d = pd.to_datetime(dates, errors="coerce")
    return (d.dt.year + (d.dt.month >= 7).astype("Int64")).astype("Int64")


def prep_lending_frame(df: pd.DataFrame, source: str) -> pd.DataFrame:
    country = pick_col(df, ["country", "country_economy", "borrower_country"])
    approval = pick_col(df, ["board_approval_date", "agreement_signing_date"])
    principal = pick_col(df, ["original_principal_amount",
                              "original_principal_amount_us_",
                              "original_principal_amount_us"])
    disbursed = pick_col(df, ["disbursed_amount",
                              "disbursed_amount_us_",
                              "disbursed_amount_us"])
    if not all([country, approval, principal]):
        log(f"    !! unexpected schema for {source}; columns: {list(df.columns)[:15]}...")
        return pd.DataFrame()

    out = pd.DataFrame({
        "country": df[country].astype(str).str.strip(),
        "fiscal_year": wb_fiscal_year(df[approval]),
        "commitment_amount": pd.to_numeric(df[principal], errors="coerce"),
        "disbursement_amount": pd.to_numeric(df[disbursed], errors="coerce")
                               if disbursed else 0.0,
        "source": source,
    })
    return out.dropna(subset=["fiscal_year"])


def fetch_lending(outdir: Path) -> pd.DataFrame:
    log("== Dataset 2: IBRD / IDA lending (WBG Finances) ==")
    ibrd = try_datasets(IBRD_DATASETS, "IBRD")
    ida = try_datasets(IDA_DATASETS, "IDA")

    frames = []
    if not ibrd.empty:
        frames.append(prep_lending_frame(ibrd, "IBRD"))
    if not ida.empty:
        frames.append(prep_lending_frame(ida, "IDA"))
    if not frames:
        return pd.DataFrame()

    loans = pd.concat(frames, ignore_index=True)
    lending = (
        loans.groupby(["country", "fiscal_year"], as_index=False)
             .agg(commitment_amount=("commitment_amount", "sum"),
                  disbursement_amount=("disbursement_amount", "sum"),
                  n_loans=("country", "size"))
    )
    # "lending_amount" = new commitments approved in that fiscal year
    lending["lending_amount"] = lending["commitment_amount"]
    lending.to_csv(outdir / "lending_by_country_year.csv", index=False)
    log(f"  lending_by_country_year.csv: {len(lending):,} rows\n")
    return lending


# ---------------------------------------------------------------------------
# Dataset 3: IEG project performance ratings
# ---------------------------------------------------------------------------

def fetch_ieg(outdir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    log("== Dataset 3: IEG project performance ratings ==")
    raw = try_datasets(IEG_DATASETS, "IEG")
    if raw.empty:
        return pd.DataFrame(), pd.DataFrame()

    project = pick_col(raw, ["project_id", "proj_id"])
    country = pick_col(raw, ["country", "country_economy"])
    outcome = pick_col(raw, ["ieg_outcome", "outcome", "ieg_outcome_rating"])
    sector = pick_col(raw, ["sector_board", "global_practice", "sector",
                            "agreement_type", "practice_group"])
    closing = pick_col(raw, ["exit_fy", "closing_fy", "final_closing_fy",
                             "evaluation_fy", "exit_fiscal_year", "closing_date"])

    ieg = pd.DataFrame({
        "project_id": raw[project] if project else pd.NA,
        "country": raw[country].astype(str).str.strip() if country else pd.NA,
        "outcome_rating": raw[outcome].astype(str).str.strip() if outcome else pd.NA,
        "sector": raw[sector] if sector else pd.NA,
        "closing_year": pd.to_numeric(
            raw[closing].astype(str).str.extract(r"(\d{4})")[0], errors="coerce"
        ).astype("Int64") if closing else pd.NA,
    })
    ieg["is_successful"] = (
        ieg["outcome_rating"].str.lower().isin(SUCCESS_RATINGS).astype(int)
    )
    ieg.to_csv(outdir / "ieg_project_ratings.csv", index=False)
    log(f"  ieg_project_ratings.csv: {len(ieg):,} projects")

    success = (
        ieg.dropna(subset=["closing_year"])
           .groupby(["country", "closing_year"], as_index=False)
           .agg(projects_evaluated=("project_id", "size"),
                success_rate=("is_successful", "mean"))
           .rename(columns={"closing_year": "year"})
    )
    success["success_rate"] = (success["success_rate"] * 100).round(1)
    success.to_csv(outdir / "ieg_success_by_country_year.csv", index=False)
    log(f"  ieg_success_by_country_year.csv: {len(success):,} rows\n")
    return ieg, success


# ---------------------------------------------------------------------------
# Join: the end-state table
# ---------------------------------------------------------------------------

def normalize_country_name(s: pd.Series) -> pd.Series:
    """Light harmonization so ESG API names join to Finances names."""
    fixes = {
        "egypt, arab republic of": "egypt, arab rep.",
        "yemen, republic of": "yemen, rep.",
        "venezuela, republica bolivariana de": "venezuela, rb",
        "iran, islamic republic of": "iran, islamic rep.",
        "korea, republic of": "korea, rep.",
        "congo, democratic republic of": "congo, dem. rep.",
        "congo, republic of": "congo, rep.",
        "cote d'ivoire": "cote d'ivoire",
        "lao people's democratic republic": "lao pdr",
        "macedonia, former yugoslav republic of": "north macedonia",
        "turkiye": "turkiye", "turkey": "turkiye",
        "viet nam": "vietnam",
    }
    key = (s.astype(str).str.strip().str.lower()
            .str.replace("’", "'", regex=False)
            .str.normalize("NFKD").str.encode("ascii", "ignore").str.decode("ascii"))
    return key.replace(fixes)


def build_master(esg: pd.DataFrame, lending: pd.DataFrame,
                 success: pd.DataFrame, outdir: Path):
    log("== Building joined master table ==")
    esg = esg.copy()
    esg["join_key"] = normalize_country_name(esg["country"])

    master = esg
    if not lending.empty:
        l = lending.copy()
        l["join_key"] = normalize_country_name(l["country"])
        master = master.merge(
            l[["join_key", "fiscal_year", "lending_amount",
               "commitment_amount", "disbursement_amount"]],
            left_on=["join_key", "year"], right_on=["join_key", "fiscal_year"],
            how="left",
        ).drop(columns=["fiscal_year"])

    if success is not None and not success.empty:
        s = success.copy()
        s["join_key"] = normalize_country_name(s["country"])
        master = master.merge(
            s[["join_key", "year", "projects_evaluated", "success_rate"]],
            on=["join_key", "year"], how="left",
        )

    master = master.drop(columns=["join_key"])
    master.to_csv(outdir / "esg_lending_master.csv", index=False)
    log(f"  esg_lending_master.csv: {len(master):,} rows")

    if "lending_amount" not in master.columns:
        log("  (no lending data available; skipping ESG+lending preview)")
        return

    # Quick sanity preview: latest year with both ESG + lending
    both = master.dropna(subset=["esg_score", "lending_amount"])
    if not both.empty:
        latest = both["year"].max()
        preview = (both[both["year"] == latest]
                   .nlargest(10, "lending_amount")
                   [["country", "year", "environmental_score", "social_score",
                     "governance_score", "esg_risk_score", "lending_amount"]])
        log(f"\nTop 10 borrowers by new commitments, FY{latest}:")
        log(preview.to_string(index=False))


# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start", type=int, default=2000)
    ap.add_argument("--end", type=int, default=pd.Timestamp.now().year)
    ap.add_argument("--outdir", default="output")
    ap.add_argument("--skip-ieg", action="store_true",
                    help="skip Dataset 3 (project success rates)")
    args = ap.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    esg = fetch_esg(args.start, args.end, outdir)
    lending = fetch_lending(outdir)
    success = pd.DataFrame()
    if not args.skip_ieg:
        _, success = fetch_ieg(outdir)

    build_master(esg, lending, success, outdir)
    log("\nDone. Files written to: " + str(outdir.resolve()))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(1)