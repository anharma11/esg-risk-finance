import re, urllib.parse, json, base64, sys, os
sys.stdout.reconfigure(encoding='utf-8')

html = open(r'c:\Users\asharma77\Downloads\risk_finance\New Notebook 2026-07-18 16_23_08 (1).html', encoding='utf-8').read()
m = re.search(r"__DATABRICKS_NOTEBOOK_MODEL = '([^']+)'", html)
nb = json.loads(urllib.parse.unquote(base64.b64decode(m.group(1)).decode('utf-8')))

# Extract combined Plotly HTML from cell 5 results
chart_html = nb['commands'][5]['results']['data'][0]['data']['text/html']

os.makedirs(r'c:\Users\asharma77\Downloads\risk_finance\charts', exist_ok=True)

standalone = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ESG Risk & WBG Lending — Interactive Charts</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
           max-width: 1200px; margin: 40px auto; padding: 0 20px; background: #fafafa; }}
    h1   {{ color: #1a1a2e; border-bottom: 3px solid #3498db; padding-bottom: 10px; }}
    h2   {{ color: #2c3e50; margin-top: 40px; }}
    p    {{ color: #555; line-height: 1.6; }}
    .chart-container {{ background: white; border-radius: 8px;
                        box-shadow: 0 2px 8px rgba(0,0,0,.08);
                        padding: 16px; margin-bottom: 32px; }}
  </style>
</head>
<body>
  <h1>ESG Risk &amp; WBG Lending Exposure — Interactive Charts</h1>
  <p>
    Interactive visualizations derived from the
    <a href="https://github.com/anharma11/esg-risk-finance">esg-risk-finance</a> pipeline.
    Data sources: World Bank Indicators API (ESG), WBG Finances One (lending &amp; IEG ratings).
    All scores are min-max normalized to 0–100 within each year.
  </p>

  <h2>1. E/S/G Pillar Scores — Top 15 Countries by ESG Score</h2>
  <p>
    Grouped bar chart showing Environmental, Social, and Governance pillar scores for
    the 15 highest-scoring countries (averaged across all available years).
    Higher scores indicate better ESG performance.
  </p>
  <div class="chart-container">{chart_html}</div>
</body>
</html>"""

with open(r'c:\Users\asharma77\Downloads\risk_finance\charts\esg_risk_charts.html', 'w', encoding='utf-8') as f:
    f.write(standalone)

print('Saved charts/esg_risk_charts.html')
print(f'File size: {os.path.getsize(r"c:\Users\asharma77\Downloads\risk_finance\charts\esg_risk_charts.html"):,} bytes')

print('commands:', len(nb.get('commands', [])))
for i, cmd in enumerate(nb.get('commands', [])):
    src = cmd.get('command', '')[:100].replace('\n', ' ')
    results = cmd.get('results') or {}
    rtype = results.get('type', 'none')
    data_keys = list(results.keys()) if results else []
    print(f'  [{i}] type={rtype:12s}  src={src}')
    if rtype not in ('none', 'text'):
        print(f'       result_keys={data_keys}')
