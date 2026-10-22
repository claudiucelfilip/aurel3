"""Fetch split-adjusted close and adjusted close per ticker from Yahoo's chart endpoint; cached to disk.

Adapted from research/broad_search/yahoo_chart.py (returns both close series). >=0.6s per request.
"""
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
import pandas as pd

DATA = Path(__file__).resolve().parents[3] / 'data' / 'broad_search' / 'insider'
UA = {'User-Agent': 'Mozilla/5.0'}


def chart(symbol, start='2005-10-01', end='2026-10-17', pause=0.8, tries=6):
    p1, p2 = int(pd.Timestamp(start).timestamp()), int(pd.Timestamp(end).timestamp())
    sym = urllib.request.quote(symbol)
    url = (f'https://query1.finance.yahoo.com/v8/finance/chart/{sym}?period1={p1}&period2={p2}'
           '&interval=1d&events=div%2Csplits&includeAdjustedClose=true')
    for attempt in range(tries):
        try:
            time.sleep(pause)
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
                res = json.loads(r.read())['chart']['result'][0]
            break
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            time.sleep(30 * (attempt + 1))
        except Exception:
            time.sleep(15 * (attempt + 1))
    else:
        raise RuntimeError(f'failed {symbol}')
    if not res or 'timestamp' not in res:
        return None
    idx = pd.to_datetime(res['timestamp'], unit='s').normalize()
    q = res['indicators']['quote'][0]['close']
    adj = res['indicators'].get('adjclose', [{}])[0].get('adjclose') or q
    df = pd.DataFrame({'close': pd.Series(q, index=idx, dtype=float),
                       'adj': pd.Series(adj, index=idx, dtype=float)}).dropna()
    return df.groupby(level=0).last()


def main(tickers):
    store = DATA / 'prices'
    store.mkdir(exist_ok=True)
    todo = [t for t in tickers if not (store / f'{t}.csv').exists() and not (store / f'{t}.none').exists()]
    print(len(todo), 'to fetch', flush=True)
    for i, t in enumerate(todo):
        try:
            df = chart(t)
        except RuntimeError as exc:
            print(exc, flush=True)
            continue
        if df is None or df.empty:
            (store / f'{t}.none').write_text('')
        else:
            df.to_csv(store / f'{t}.csv', index_label='Date')
        if i % 100 == 0:
            print(i, t, flush=True)
    print('done', flush=True)


if __name__ == '__main__':
    extra = ['SPY', 'BIL', '^IRX']
    need = (DATA / 'tickers_needed.txt').read_text().split() if len(sys.argv) < 2 else sys.argv[1:]
    main(list(dict.fromkeys(extra + need)))
