"""Minimal Yahoo chart-endpoint client (adjusted close), throttled; used when yfinance is rate-limited."""
import json
import time
import urllib.request
import pandas as pd

UA = {'User-Agent': 'Mozilla/5.0'}


def adj_close(symbol, start='2006-01-01', end='2026-10-17', pause=0.6, tries=5):
    p1, p2 = int(pd.Timestamp(start).timestamp()), int(pd.Timestamp(end).timestamp())
    url = (f'https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?period1={p1}&period2={p2}'
           '&interval=1d&events=div%2Csplits&includeAdjustedClose=true')
    for attempt in range(tries):
        try:
            time.sleep(pause)
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
                res = json.loads(r.read())['chart']['result'][0]
            break
        except urllib.error.HTTPError as exc:
            if exc.code in (400, 404):  # 400: no data for the requested start (fund too young)
                return pd.Series(dtype=float, name=symbol)
            time.sleep(20 * (attempt + 1))
        except Exception:
            time.sleep(10 * (attempt + 1))
    else:
        raise RuntimeError(f'failed {symbol}')
    if 'timestamp' not in res:
        return pd.Series(dtype=float, name=symbol)
    idx = pd.to_datetime(res['timestamp'], unit='s').normalize()
    adj = res['indicators'].get('adjclose', [{}])[0].get('adjclose') or res['indicators']['quote'][0]['close']
    return pd.Series(adj, index=idx, name=symbol, dtype=float).dropna().groupby(level=0).last()
