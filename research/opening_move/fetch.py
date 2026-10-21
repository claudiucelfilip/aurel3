"""Fetch historical market data only; no trading endpoint or order method."""
import argparse
import csv
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import gzip
import hashlib
import json
from pathlib import Path
import threading
import time
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

HOST = 'https://data.alpaca.markets/v2/stocks/bars'
lock = threading.Lock()
last_request = 0.0


def credentials(path):
    values = {}
    for line in Path(path).read_text().splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            k, v = line.split('=', 1)
            values[k.strip()] = v.strip().strip('\"').strip("'")
    return {'APCA-API-KEY-ID': values['APCA_API_KEY_ID'],
            'APCA-API-SECRET-KEY': values['APCA_API_SECRET_KEY']}


def request(query, headers):
    global last_request
    for attempt in range(6):
        with lock:
            time.sleep(max(0, .4 - (time.monotonic() - last_request)))
            last_request = time.monotonic()
        try:
            with urllib.request.urlopen(urllib.request.Request(
                    HOST + '?' + urllib.parse.urlencode(query), headers=headers), timeout=45) as r:
                return json.load(r)
        except (urllib.error.URLError, TimeoutError):
            if attempt == 5:
                raise
            time.sleep(min(2 ** attempt, 15))


def fetch_year(year, folder, headers):
    path = folder / f'QQQ_{year}_1min.csv.gz'
    if path.exists():
        return
    query = {'symbols': 'QQQ', 'timeframe': '1Min', 'start': f'{year}-01-01T00:00:00Z',
             'end': f'{year+1}-01-01T00:00:00Z' if year < 2026 else '2026-10-21T00:00:00Z',
             'feed': 'sip', 'adjustment': 'raw', 'limit': 10000, 'sort': 'asc'}
    rows = []
    pages = 0
    while True:
        d = request(query, headers)
        for b in d.get('bars', {}).get('QQQ', []):
            t = datetime.fromisoformat(b['t'].replace('Z', '+00:00')).astimezone(ZoneInfo('America/New_York'))
            if (9, 30) <= (t.hour, t.minute) < (16, 0):
                rows.append([b[k] for k in ['t', 'o', 'h', 'l', 'c', 'v']])
        pages += 1
        token = d.get('next_page_token')
        if not token:
            break
        query['page_token'] = token
    temp = path.with_suffix('.part')
    with gzip.open(temp, 'wt', newline='') as f:
        w = csv.writer(f); w.writerow(['timestamp', 'open', 'high', 'low', 'close', 'volume']); w.writerows(rows)
    temp.replace(path)
    print(f'{year}: {len(rows)} regular-session minutes, {pages} pages', flush=True)


def daily(folder, headers):
    for symbol in ['SPY', 'QQQ']:
        query = {'symbols': symbol, 'timeframe': '1Day', 'start': '2016-01-01T00:00:00Z', 'end': '2026-10-21T00:00:00Z',
                 'feed': 'sip', 'adjustment': 'all', 'limit': 10000, 'sort': 'asc'}
        d = request(query, headers)
        assert not d.get('next_page_token')
        (folder / f'{symbol}_daily_adjusted.json').write_text(json.dumps(d))


def main():
    p = argparse.ArgumentParser(); p.add_argument('--env-file', required=True); p.add_argument('--output', required=True)
    a = p.parse_args(); folder = Path(a.output); folder.mkdir(parents=True, exist_ok=True)
    headers = credentials(a.env_file)
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(lambda y: fetch_year(y, folder, headers), range(2016, 2027)))
    daily(folder, headers)
    manifest = {'source': HOST, 'feed': 'sip', 'minute_adjustment': 'raw', 'daily_adjustment': 'all',
                'regular_session_timezone': 'America/New_York', 'fetched_at': datetime.now().astimezone().isoformat(),
                'files': {f.name: hashlib.sha256(f.read_bytes()).hexdigest()
                          for f in [*sorted(folder.glob('QQQ_*_1min.csv.gz')),
                                    folder/'SPY_daily_adjusted.json', folder/'QQQ_daily_adjusted.json']}}
    (folder / 'manifest.json').write_text(json.dumps(manifest, indent=2))

if __name__ == '__main__':
    main()
