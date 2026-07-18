"""
All constants: API base URLs, ESG indicator definitions, Finances One dataset
IDs, and IEG success-rating vocabulary.
"""

# ---------------------------------------------------------------------------
# API base URLs
# ---------------------------------------------------------------------------

WB_API = "https://api.worldbank.org/v2"

# WBG Finances One data API (replaced the retired Socrata platform).
# Addressed with (datasetId, resourceId), paged via top/skip, max 1000 rows/page.
FONE_API = "https://datacatalogapi.worldbank.org/dexapps/fone/api/apiservice"

# ---------------------------------------------------------------------------
# ESG indicators
# Direction: +1 = higher value → better ESG, -1 = higher value → worse ESG.
# ---------------------------------------------------------------------------

ESG_INDICATORS: dict[str, dict[str, tuple[str, int]]] = {
    "governance": {
        "GE.EST": ("Government Effectiveness (estimate)", +1),
        "RL.EST": ("Rule of Law (estimate)", +1),
        "CC.EST": ("Control of Corruption (estimate)", +1),
        "PV.EST": ("Political Stability / Absence of Violence (estimate)", +1),
    },
    "social": {
        "SI.POV.DDAY":    ("Poverty headcount ratio at $2.15/day (%)", -1),
        "EG.ELC.ACCS.ZS": ("Access to electricity (% of population)", +1),
        "SP.DYN.LE00.IN": ("Life expectancy at birth (years)", +1),
        "SE.SEC.ENRR":    ("School enrollment, secondary (% gross)", +1),
    },
    "environmental": {
        # Classic CO2 code was archived; AR5 GHG code is the replacement.
        # Both listed — loader keeps whichever returns data.
        "EN.ATM.CO2E.PC":       ("CO2 emissions (metric tons per capita)", -1),
        "EN.GHG.CO2.PC.CE.AR5": ("CO2 emissions per capita (AR5)", -1),
        "AG.LND.FRST.ZS":       ("Forest area (% of land area)", +1),
        "EG.FEC.RNEW.ZS":       ("Renewable energy consumption (% of total)", +1),
        "EN.ATM.PM25.MC.M3":    ("PM2.5 air pollution, mean annual exposure", -1),
    },
}

# ---------------------------------------------------------------------------
# WBG Finances One datasets — (datasetId, resourceId) pairs, tried in order.
#
#   IBRD Statement of Loans and Guarantees (latest snapshot)  DS00047 / RS00049
#   IDA  Statement of Credits, Grants & Guarantees (latest)   DS00001 / RS00001
#   IEG  World Bank Project Performance Ratings               DS00053 / RS00055
# ---------------------------------------------------------------------------

IBRD_DATASETS: list[tuple[str, str]] = [("DS00047", "RS00049")]
IDA_DATASETS:  list[tuple[str, str]] = [("DS00001", "RS00001")]
IEG_DATASETS:  list[tuple[str, str]] = [("DS00053", "RS00055")]

# ---------------------------------------------------------------------------
# IEG vocabulary
# ---------------------------------------------------------------------------

SUCCESS_RATINGS: frozenset[str] = frozenset({
    "highly satisfactory",
    "satisfactory",
    "moderately satisfactory",
})
