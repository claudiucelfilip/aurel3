"""Download 8-K item 2.02 filing dates for every priced stock, and Berkshire's 13F-HR infotables. See protocol.json track_F_wild_batch."""
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PRICES = ROOT / 'data' / 'broad_search' / 'insider' / 'prices'
OUT = ROOT / 'data' / 'broad_search' / 'wild'
UA = {'User-Agent': 'Aurel3-research personal-noncommercial admin@example.org'}
BRK = 1067983


def get(url, tries=4):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            if getattr(e, 'code', None) == 404:
                return None
            time.sleep(2 * (i + 1))
    return None


def filings(cik):
    """All (form, items, filingDate, accession) for a CIK, including the older paginated files."""
    d = json.loads(get(f'https://data.sec.gov/submissions/CIK{cik:010d}.json'))
    pages = [d['filings']['recent']] + [json.loads(get(f'https://data.sec.gov/submissions/{f["name"]}')) for f in d['filings']['files']]
    rows = []
    for p in pages:
        rows += zip(p['form'], p.get('items', [''] * len(p['form'])), p['filingDate'], p['accessionNumber'])
    return rows


def earnings_dates():
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / 'earnings_8k.json'
    done = json.loads(path.read_text()) if path.exists() else {}
    tickers = json.loads(get('https://www.sec.gov/files/company_tickers.json'))
    cik_of = {v['ticker'].replace('.', '-'): v['cik_str'] for v in tickers.values()}
    want = [p.stem for p in PRICES.glob('*.csv') if p.stem in cik_of and p.stem not in done]
    print(len(want), 'tickers to fetch', flush=True)

    def one(t):
        try:
            rows = filings(cik_of[t])
            return t, sorted({dt for form, items, dt, _ in rows if form in ('8-K', '8-K/A') and '2.02' in items})
        except Exception as e:  # noqa: BLE001
            print('failed', t, e, flush=True)
            return t, None

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(5) as ex:  # SEC fair-use limit is 10 requests/s
        for i, (t, dates) in enumerate(ex.map(one, want)):
            done[t] = dates
            if i % 100 == 0:
                path.write_text(json.dumps(done))
                print(i, t, len(dates or []), flush=True)
    path.write_text(json.dumps(done))


def berkshire():
    OUT.mkdir(parents=True, exist_ok=True)
    rows = [(dt, acc) for form, _, dt, acc in filings(BRK) if form == '13F-HR']
    out = {}
    for dt, acc in rows:
        folder = f'https://www.sec.gov/Archives/edgar/data/{BRK}/{acc.replace("-", "")}/'
        idx = get(folder)
        if not idx:
            continue
        xmls = [m for m in re.findall(r'href="([^"]+\.xml)"', idx.decode()) if 'primary_doc' not in m]
        if not xmls:
            continue  # pre-2013 filings are plain text; recorded as unavailable
        x = get('https://www.sec.gov' + xmls[0]).decode()
        info = re.findall(r'<(?:\w+:)?infoTable>(.*?)</(?:\w+:)?infoTable>', x, re.S)
        rows_ = []
        for it in info:
            g = lambda tag: (re.search(rf'<(?:\w+:)?{tag}>(.*?)</(?:\w+:)?{tag}>', it, re.S) or [None, ''])[1].strip()
            rows_.append({'issuer': g('nameOfIssuer'), 'cusip': g('cusip'), 'value': float(g('value') or 0), 'shares': float(g('sshPrnamt') or 0)})
        out[dt] = rows_
        print(dt, len(rows_), flush=True)
        time.sleep(0.2)
    (OUT / 'berkshire_13f.json').write_text(json.dumps(out, indent=1))


if __name__ == '__main__':
    {'earnings': earnings_dates, 'berkshire': berkshire}[sys.argv[1]]()
