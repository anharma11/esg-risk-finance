# ESG Risk & WBG Lending Exposure

## Data Sources

### 1. Sovereign ESG Indicators

**What:** Country-level environmental, social, and governance metrics for 217 countries.
Pulls 12 indicators from the World Bank Indicators API, normalizes each to 0–100 (cross-country min-max within each year), and averages into pillar scores. Output is one row per country per year.

**Source:** `https://api.worldbank.org/v2/country/all/indicator/{code}`

**Request**
```
GET https://api.worldbank.org/v2/country/all/indicator/{code}
    ?format=json
    &per_page=20000
    &page=1
    &date=2018:2024
```

**Response**
```json
[
  { "page": 1, "pages": 3, "total": 48000 },
  [
    {
      "countryiso3code": "KEN",
      "country": { "value": "Kenya" },
      "date": "2022",
      "value": 66.7
    }
  ]
]
```
Paginate by incrementing `page` until `page >= pages`.

**Indicator codes**

| Pillar | Code | Metric |
|---|---|---|
| Social | `SI.POV.DDAY` | Poverty headcount at $2.15/day (%) |
| Social | `EG.ELC.ACCS.ZS` | Access to electricity (%) |
| Social | `SP.DYN.LE00.IN` | Life expectancy at birth |
| Social | `SE.SEC.ENRR` | Secondary school enrollment (%) |
| Environmental | `EN.GHG.CO2.PC.CE.AR5` | CO₂ emissions per capita (AR5) |
| Environmental | `AG.LND.FRST.ZS` | Forest area (% of land) |
| Environmental | `EG.FEC.RNEW.ZS` | Renewable energy (% of total) |
| Environmental | `EN.ATM.PM25.MC.M3` | PM2.5 air pollution exposure |
| Governance | `GE.EST` | Government Effectiveness |
| Governance | `RL.EST` | Rule of Law |
| Governance | `CC.EST` | Control of Corruption |
| Governance | `PV.EST` | Political Stability |

---

### 2. IBRD + IDA Lending

**What:** Every loan and credit the World Bank has ever issued — approval date, country, principal amount, disbursed amount. Aggregated to one row per country per fiscal year (WB fiscal year = Jul 1 – Jun 30).

> ⚠️ Requires WBG VPN to be **disconnected** — this endpoint is blocked on the internal network.

**Source:** `https://datacatalogapi.worldbank.org/dexapps/fone/api/apiservice`

**Request**
```
GET https://datacatalogapi.worldbank.org/dexapps/fone/api/apiservice
    ?datasetId=DS00047    (IBRD) or DS00001 (IDA)
    &resourceId=RS00049   (IBRD) or RS00001 (IDA)
    &type=json
    &top=1000
    &skip=0
```

**Response**
```json
{
  "count": 9494,
  "data": [
    {
      "country": "Kenya",
      "board_approval_date": "15-Jun-2022",
      "original_principal_amount": 500000000,
      "disbursed_amount": 320000000
    }
  ]
}
```
Paginate by incrementing `skip` by `top` until `len(rows) >= count`.

| Dataset | `datasetId` | `resourceId` |
|---|---|---|
| IBRD Statement of Loans | `DS00047` | `RS00049` |
| IDA Statement of Credits | `DS00001` | `RS00001` |

---

### 3. IEG Project Performance Ratings

**What:** Independent Evaluation Group (IEG) outcome ratings for every completed World Bank project (~12,500 projects). Aggregated to one row per country per closing year as a success rate.

> ⚠️ Requires WBG VPN to be **disconnected** — this endpoint is blocked on the internal network.

**Source:** `https://datacatalogapi.worldbank.org/dexapps/fone/api/apiservice`

**Request**
```
GET https://datacatalogapi.worldbank.org/dexapps/fone/api/apiservice
    ?datasetId=DS00053
    &resourceId=RS00055
    &type=json
    &top=1000
    &skip=0
```

**Response**
```json
{
  "count": 12570,
  "data": [
    {
      "project_id": "P001234",
      "country": "Kenya",
      "outcome": "Satisfactory",
      "global_practice": "Education",
      "final_closing_fy": 2022
    }
  ]
}
```

| Dataset | `datasetId` | `resourceId` |
|---|---|---|
| IEG Project Performance Ratings | `DS00053` | `RS00055` |

---

## Running the Workflow (Databricks)

1. Go to **Databricks → Workflows → Jobs and Pipelines**
2. Click **Create Job → Edit as YAML**
3. Upload `workflow.yaml` from this repo
4. Replace the three placeholder values:

| Placeholder | Replace with |
|---|---|
| `{email}` | your email e.g. `asharma77@ifc.org` |
| `{workspace_path}` | Databricks workspace path e.g. `/Users/asharma77@ifc.org` |
| `{cluster_id}` | your cluster ID e.g. `0120-230534-bfpoz0db` |

5. Click **Run Now**

The workflow runs two tasks in sequence:

**Task 1 — `ingest`** (`scripts/run_ingest.py`)
Fetches raw data from the three source APIs and writes to Unity Catalog:

| Table | Contents |
|---|---|
| `{catalog}.{schema}.esg` | Raw ESG indicator values — one row per country × year × indicator |
| `{catalog}.{schema}.loans` | Raw IBRD + IDA loan records — one row per individual loan |
| `{catalog}.{schema}.ratings` | Raw IEG project ratings — one row per evaluated project |

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

