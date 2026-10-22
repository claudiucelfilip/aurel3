"""Parse cached N-PORT holdings and map CUSIPs to tickers via OpenFIGI (cached)."""
import json
import re
import time
import urllib.request
from pathlib import Path
import pandas as pd

HERE = Path(__file__).resolve().parent
DATA = HERE.parents[1] / 'data' / 'spmo_diagnostic'
FIELDS = ['name', 'cusip', 'balance', 'valUSD', 'pctVal', 'assetCat']


def parse(path):
    s = path.read_text(errors='ignore')
    date = re.search(r'<repPdDate>([^<]+)', s).group(1)
    rows = []
    for block in re.findall(r'<invstOrSec>(.*?)</invstOrSec>', s, re.S):
        row = {f: (m.group(1) if (m := re.search(fr'<{f}>([^<]*)</{f}>', block)) else None) for f in FIELDS}
        isin = re.search(r'<isin value="([^"]+)"', block)
        row['isin'] = isin.group(1) if isin else None
        rows.append(row)
    frame = pd.DataFrame(rows)
    for c in ['balance', 'valUSD', 'pctVal']:
        frame[c] = pd.to_numeric(frame[c], errors='coerce')
    frame['date'] = pd.Timestamp(date)
    frame['filing'] = path.stem.split('_', 1)[1]
    return frame


def all_holdings():
    frames = []
    for path in sorted((DATA / 'nport').glob('*.xml')):
        f = parse(path)
        f['fund'] = path.stem.split('_')[0]
        frames.append(f)
    h = pd.concat(frames, ignore_index=True)
    # Keep the last filing for a report date (amendments supersede originals).
    last = h.groupby(['fund', 'date'])['filing'].max().rename('keep')
    h = h.join(last, on=['fund', 'date'])
    return h[h['filing'] == h['keep']].drop(columns='keep')


def figi_map(cusips):
    path = DATA / 'cusip_figi.json'
    known = json.loads(path.read_text()) if path.exists() else {}
    todo = [c for c in cusips if c and c not in known]
    for i in range(0, len(todo), 10):
        batch = todo[i:i + 10]
        req = urllib.request.Request('https://api.openfigi.com/v3/mapping',
                                     data=json.dumps([{'idType': 'ID_CUSIP', 'idValue': c} for c in batch]).encode(),
                                     headers={'Content-Type': 'application/json'})
        for attempt in range(5):
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    out = json.loads(r.read())
                break
            except urllib.error.HTTPError as exc:
                if exc.code != 429:
                    raise
                time.sleep(15)
        for c, res in zip(batch, out):
            data = res.get('data') or []
            us = [d for d in data if d.get('exchCode') == 'US'] or data
            known[c] = {'ticker': us[0]['ticker'] if us else None,
                        'name': us[0].get('name') if us else None,
                        'error': res.get('error') or res.get('warning')}
        path.write_text(json.dumps(known, indent=1, sort_keys=True))
        time.sleep(2.6)
    return known


if __name__ == '__main__':
    h = all_holdings()
    h.to_csv(DATA / 'holdings.csv', index=False)
    eq = h[h['assetCat'] == 'EC']
    m = figi_map(sorted(eq['cusip'].dropna().unique()))
    miss = [c for c in eq['cusip'].dropna().unique() if not m[c]['ticker']]
    print(h.groupby('fund')['date'].nunique().to_dict(), 'equity cusips', eq['cusip'].nunique(), 'unmapped', len(miss))
