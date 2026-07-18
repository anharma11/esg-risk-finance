import re, urllib.parse, json, base64, sys
sys.stdout.reconfigure(encoding='utf-8')

html = open(r'c:\Users\asharma77\Downloads\risk_finance\New Notebook 2026-07-18 16_23_08 (1).html', encoding='utf-8').read()
m = re.search(r"__DATABRICKS_NOTEBOOK_MODEL = '([^']+)'", html)
nb = json.loads(urllib.parse.unquote(base64.b64decode(m.group(1)).decode('utf-8')))

# Print full cell 5 source
print(nb['commands'][5]['command'])

# Save the plotly HTML as standalone file
chart_html = nb['commands'][5]['results']['data'][0]['data']['text/html']
out = open(r'c:\Users\asharma77\Downloads\risk_finance\output\esg_chart.html', 'w', encoding='utf-8')
out.write(f'<!DOCTYPE html><html><head><meta charset="utf-8"></head><body>{chart_html}</body></html>')
out.close()
print('\nSaved output/esg_chart.html')

print('commands:', len(nb.get('commands', [])))
for i, cmd in enumerate(nb.get('commands', [])):
    src = cmd.get('command', '')[:100].replace('\n', ' ')
    results = cmd.get('results') or {}
    rtype = results.get('type', 'none')
    data_keys = list(results.keys()) if results else []
    print(f'  [{i}] type={rtype:12s}  src={src}')
    if rtype not in ('none', 'text'):
        print(f'       result_keys={data_keys}')
