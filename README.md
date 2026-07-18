# ESG Risk & WBG Lending Exposure

Automated pipeline that pulls sovereign ESG indicators, WBG lending records, and IEG project ratings from public APIs, scores countries on ESG risk, and joins everything into a master table in Unity Catalog.

![ESG Risk Dashboard](output/dashboard.png)

**[📊 Interactive Charts](https://htmlpreview.github.io/?https://github.com/anharma11/esg-risk-finance/blob/main/charts/esg_risk_charts.html)** — ESG pillar scores, lending exposure, and project success rate analysis (hover, zoom, filter)

**[📓 Analysis Notebook](esg_risk_analysis.ipynb)** — full pipeline: install → ingest → transform → write → visualize

> 📊 [Open interactive charts](https://htmlpreview.github.io/?https://github.com/anharma11/esg-risk-finance/blob/main/New%20Notebook%202026-07-18%2016_23_08%20(1).html)

---

## What it produces

| Delta Table | Contents |
|---|---|
| `esg` | Raw ESG indicator values — one row per country × year × indicator |
| `loans` | Raw IBRD + IDA loan records — one row per individual loan |
| `ratings` | Raw IEG project ratings — one row per evaluated project |
| `aggregate_esg` | ESG pillar scores + risk score (0–100) — one row per country × year |
| `aggregate_loans` | Total lending commitments — one row per country × fiscal year |
| `aggregate_ratings` | Project success rates — one row per country × year |
| `esg_lending_master` | All three joined — one row per country × year |

---

## Quick start (Databricks)

### 1. Install the package

```python
# With internet access:
%pip install git+https://github.com/anharma11/esg-risk-finance.git

# Offline (bundle pre-downloaded to volume):
%pip install /Volumes/.../bundle/esg_risk_finance-0.1.0-py3-none-any.whl \
  --no-index --find-links /Volumes/.../bundle/ --force-reinstall --quiet
```

### 2. Ingest raw data

```python
from pathlib import Path
from src.ingest.esg     import fetch_esg_raw
from src.ingest.lending import fetch_lending_raw
from src.ingest.ieg     import fetch_ieg_raw

vol = Path("/Volumes/prd_datascience_ifcwbcpm/risk_monitoring_innov_proj/api_tests_data/wheels")
esg_df     = fetch_esg_raw(vol)          # WB Indicators API
loans_df   = fetch_lending_raw(vol)      # Finances One — disconnect VPN first
ratings_df = fetch_ieg_raw(vol)          # Finances One — disconnect VPN first
```

> ⚠️ `fetch_lending_raw` and `fetch_ieg_raw` call the Finances One API which is blocked on the WBG internal network. Disconnect VPN before running, or load from pre-uploaded CSVs.

### 3. Write to Unity Catalog

```python
from src.ingest.write import _write_esg, _write_loans, _write_ratings

catalog = "prd_datascience_ifcwbcpm"
schema  = "risk_monitoring_innov_proj"

_write_esg(spark,     esg_df,     catalog, schema)
_write_loans(spark,   loans_df,   catalog, schema)
_write_ratings(spark, ratings_df, catalog, schema)
```

### 4. Transform & aggregate

```python
from src.transform.write import _overwrite
from src.transform.aggregate_esg     import aggregate_esg
from src.transform.aggregate_loans   import aggregate_loans
from src.transform.aggregate_ratings import aggregate_ratings
from src.ingest.join                 import build_master

agg_esg     = aggregate_esg(esg_df)
agg_loans   = aggregate_loans(loans_df)
agg_ratings = aggregate_ratings(ratings_df)
master      = build_master(agg_esg, agg_loans, agg_ratings)

_overwrite(spark, agg_esg,     f"{catalog}.{schema}.aggregate_esg")
_overwrite(spark, agg_loans,   f"{catalog}.{schema}.aggregate_loans")
_overwrite(spark, agg_ratings, f"{catalog}.{schema}.aggregate_ratings")
_overwrite(spark, master,      f"{catalog}.{schema}.esg_lending_master")
```

---

## Scheduled workflow

Deploy as a daily Databricks job via `workflow.yaml`:

1. Go to **Workflows → Jobs → Create Job → Edit as YAML**
2. Paste `workflow.yaml` and fill in the three placeholders:

| Placeholder | Example |
|---|---|
| `{email}` | `asharma77@ifc.org` |
| `{workspace_path}` | `/Users/asharma77@ifc.org` |
| `{cluster_id}` | `0120-230534-bfpoz0db` |

---

## Data sources

### 1. Sovereign ESG Indicators

12 indicators across three pillars from the **World Bank Indicators API**, normalized to 0–100 per year and averaged into pillar scores.

| Pillar | Code | Metric |
|---|---|---|
| Governance | `GOV_WGI_GE.EST` | Government Effectiveness |
| Governance | `GOV_WGI_RL.EST` | Rule of Law |
| Governance | `GOV_WGI_CC.EST` | Control of Corruption |
| Governance | `GOV_WGI_PV.EST` | Political Stability |
| Social | `SI.POV.DDAY` | Poverty headcount at $2.15/day (%) |
| Social | `EG.ELC.ACCS.ZS` | Access to electricity (%) |
| Social | `SP.DYN.LE00.IN` | Life expectancy at birth |
| Social | `SE.SEC.ENRR` | Secondary school enrollment (%) |
| Environmental | `EN.GHG.CO2.PC.CE.AR5` | CO₂ emissions per capita (AR5) |
| Environmental | `AG.LND.FRST.ZS` | Forest area (% of land) |
| Environmental | `EG.FEC.RNEW.ZS` | Renewable energy (% of total) |
| Environmental | `EN.ATM.PM25.MC.M3` | PM2.5 air pollution |

### 2. IBRD + IDA Lending — Finances One

> ⚠️ Blocked on WBG internal network — disconnect VPN before running.

| Dataset | `datasetId` | `resourceId` |
|---|---|---|
| IBRD Statement of Loans | `DS00047` | `RS00049` |
| IDA Statement of Credits | `DS00001` | `RS00001` |

### 3. IEG Project Performance Ratings — Finances One

> ⚠️ Blocked on WBG internal network — disconnect VPN before running.

| Dataset | `datasetId` | `resourceId` |
|---|---|---|
| IEG Project Ratings | `DS00053` | `RS00055` |

---

## Country name matching

Loans and ratings use different country name conventions to ESG. They are fuzzy-matched to the canonical ESG country list using `rapidfuzz.WRatio` (threshold: 85/100).

| Raw name | Matched to |
|---|---|
| `"Co-operative Republic of Guyana"` | `"Guyana"` |
| `"Federative Republic of Brazil"` | `"Brazil"` |
| `"Federated States of Micronesia"` | `"Micronesia, Fed. Sts."` |

---

## Configuration

Edit `src/config.yaml` to change the date range or Unity Catalog target:

```yaml
uc:
  catalog: prd_datascience_ifcwbcpm
  schema:  risk_monitoring_innov_proj

ingest:
  start_year: 2018
  end_year:   2024
  skip_ieg:   false
```

Dates can also be overridden at call time: `fetch_esg_raw(outdir, start=2020, end=2023)`.

**Task 2 — `transform`** (`scripts/run_transform.py`) — runs after ingest completes
Aggregates the raw tables and joins them into a master table:

| Table | Contents |
|---|---|
| `{catalog}.{schema}.aggregate_esg` | ESG pillar scores + risk score — one row per country × year |
| `{catalog}.{schema}.aggregate_loans` | Total lending commitments — one row per country × fiscal year |
| `{catalog}.{schema}.aggregate_ratings` | Project success rates — one row per country × year |
| `{catalog}.{schema}.esg_lending_master` | All three joined — one row per country × year |

---

## Country Name Matching

The three sources use different country name conventions. Before joining, the
`country` column from `loans.csv` and `ratings.csv` is fuzzy-matched against
the canonical `country` column from `esg_scores.csv` using `rapidfuzz.WRatio`
(score threshold: 85/100).

**Examples resolved automatically:**

| Raw name (Finances One) | Matched to (WB Indicators) |
|---|---|
| `"Co-operative Republic of Guyana"` | `"Guyana"` |
| `"Federative Republic of Brazil"` | `"Brazil"` |
| `"Federated States of Micronesia"` | `"Micronesia, Fed. Sts."` |

