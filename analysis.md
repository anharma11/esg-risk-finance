# ESG Risk & WBG Lending Exposure — Analysis Findings

Data covers 217 countries, 2018–2024. Source: World Bank Indicators API (ESG),
WBG Finances One (IBRD/IDA loans, IEG project ratings).

---

## 1. Social Score is the Real Risk Driver

Environmental scores average **94.6** globally — nearly every country scores high.
Social scores (poverty headcount, electricity access, life expectancy, school enrollment)
average only **69.9** and collapse to **28.1** for medium-risk countries.

| Risk Group | Environmental Score | Social Score |
|---|---|---|
| Low (0–33) | 94.9 | 73.3 |
| Medium (34–66) | 96.2 | **28.1** |
| High (67–100) | 0.0 | 47.4 |

**Finding:** ESG risk is fundamentally a social development story, not an environmental one.
The environmental pillar provides almost no differentiation between countries.

> Note: Governance pillar currently has 0% data coverage. All scores are averaged
> across environmental + social only, meaning risk is likely **underestimated**.

---

## 2. The Lending Gap — WBG Does Not Lend Where Risk Is Highest

Correlation between ESG risk and lending amount: **r = −0.02, p = 0.76** — flat, not significant.

Top borrowers by total lending 2018–2024:

| Country | Total Lending (US$B) | ESG Risk Score |
|---|---|---|
| Kenya | 4.3 | 24 (medium-low) |
| Indonesia | 3.1 | ~20 (low) |
| Türkiye | 2.6 | ~19 (low) |
| India | 2.3 | ~18 (low) |

Highest-risk countries with **zero WBG lending** (2024):

| Country | ESG Risk Score |
|---|---|
| South Sudan | 72.2 |
| Palau | 66.5 |
| Chad | 47.9 |
| Niger | 43.7 |

**Finding:** The World Bank concentrates lending in medium-to-low-risk countries.
The countries with the highest ESG risk receive little or no lending exposure.
This creates a structural gap between where risk is greatest and where resources go.

---

## 3. No Correlation Between Risk and Project Success

| Metric | Value |
|---|---|
| Pearson r | 0.033 |
| Spearman r | −0.023 |
| p-value | 0.40 / 0.57 |

**Finding:** Project success rates (IEG ratings) do not vary with a country's ESG risk score.
Two interpretations:
- WBG project design compensates for higher-risk operating environments.
- The IEG sample skews toward countries stable enough to receive and close projects —
  the highest-risk countries rarely appear in IEG evaluations.

Success rate by risk group:

| Risk Group | Avg Success Rate | Projects |
|---|---|---|
| Low (0–33) | 79.2% | 321 |
| Medium (34–66) | 80.0% | 306 |
| High (67–100) | 82.2% | 3 |

The High-risk group has only 3 paired rows — insufficient for conclusions.

---

## 4. ESG Risk Trend (2018–2024)

- **Palau** shows the steepest deterioration (+2.7 pts/year).
- Most apparent "improvements" in small territories (Isle of Man, Channel Islands)
  are statistical artifacts from data gaps resolving, not real changes.
- Genuine improving trajectories to watch: Yemen, Mauritania, Maldives.

---

## 5. Priority Countries (FY2024)

Countries combining the highest ESG risk with the highest WBG lending exposure:

| Country | ESG Risk | Exposure Score | Priority Score |
|---|---|---|---|
| Kenya | 24.1 | 100.0 | 24.1 |
| Bangladesh | 17.9 | 58.3 | 10.4 |
| Togo | 29.0 | 24.8 | 7.2 |
| Côte d'Ivoire | 29.1 | 21.4 | 6.2 |

No country reaches the "High Risk + High Exposure" quadrant simultaneously —
the highest-risk countries receive too little lending to score high on priority.

---

## 6. Key Limitations

| Gap | Impact |
|---|---|
| Governance pillar missing (0% coverage) | ESG scores are underestimated |
| Lending data covers only 17% of country-years | Many high-risk countries have no lending record |
| IEG evaluations only 8% of country-years | Success-rate correlation is statistically thin |
| Trend analysis noisy for small territories | Remove non-sovereign entities for cleaner trends |
