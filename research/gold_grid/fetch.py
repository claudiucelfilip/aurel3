"""Read-only download of Dukascopy's public one-minute bid/ask archive."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta, datetime, timezone
import hashlib
import json
import lzma
from pathlib import Path
import struct
import time
import urllib.error
import urllib.request

import numpy as np
import pandas as pd

SOURCE = 'https://www.dukascopy.com/api/data/get/historical-data-export'
# Public archive HTTP works here; HTTPS handshakes repeatedly stall. No credentials are sent.
FEED = 'http://datafeed.dukascopy.com/datafeed'


def download(day, side, root):
    path = root / 'raw' / f'{day}_{side}.bi5'
    url = f'{FEED}/XAUUSD/{day.year}/{day.month-1:02d}/{day.day:02d}/{side}_candles_min_1.bi5'
    status = 'cached'
    if not path.exists():
        for attempt in range(4):
            try:
                with urllib.request.urlopen(url, timeout=30) as response:
                    raw = response.read()
                path.write_bytes(raw)
                status = 'downloaded'
                break
            except urllib.error.HTTPError as error:
                if error.code == 404:
                    return day, side, None, {'url': url, 'status': '404'}
                if attempt == 3:
                    raise
            except (TimeoutError, urllib.error.URLError):
                if attempt == 3:
                    raise
            time.sleep(attempt + 1)
    raw = path.read_bytes()
    meta = {'url': url, 'status': status, 'bytes': len(raw),
            'sha256': hashlib.sha256(raw).hexdigest()}
    if not raw:
        return day, side, None, meta
    rows = np.asarray(list(struct.iter_unpack('>5If', lzma.decompress(raw))))
    assert rows.ndim == 2 and rows.shape[1] == 6, (day, side)
    # Archive layout is seconds, open, close, low, high, volume; gold prices use 1/1000.
    frame = pd.DataFrame(rows[:, [1, 4, 3, 2]] / 1000,
                         columns=[side.lower() + '_' + c for c in ['open', 'high', 'low', 'close']])
    frame[side.lower() + '_volume'] = rows[:, 5]
    frame.index = pd.to_datetime(day, utc=True) + pd.to_timedelta(rows[:, 0], unit='s')
    assert frame.index.is_unique
    assert np.all(rows[:, 0] % 60 == 0)
    assert np.all((rows[:, 0] >= 0) & (rows[:, 0] < 86400))
    return day, side, frame, meta


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--start', default='2019-01-01')
    parser.add_argument('--end', default='2026-10-21', help='Exclusive UTC date')
    parser.add_argument('--output', default='data/gold_grid')
    args = parser.parse_args()
    root = Path(args.output)
    (root / 'raw').mkdir(parents=True, exist_ok=True)
    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    days = [start + timedelta(days=i) for i in range((end-start).days)]
    frames, manifest, errors = {}, [], []
    with ThreadPoolExecutor(max_workers=12) as pool:
        futures = {pool.submit(download, day, side, root): (day, side)
                   for day in days for side in ['BID', 'ASK']}
        for n, future in enumerate(as_completed(futures), 1):
            day, side = futures[future]
            try:
                _, _, frame, meta = future.result()
                manifest.append(meta)
                if frame is not None:
                    frames.setdefault(day, {})[side] = frame
            except Exception as error:
                errors.append({'day': str(day), 'side': side, 'error': str(error)})
            if n % 200 == 0:
                print(f'{n}/{len(futures)} archives; {len(errors)} errors', flush=True)
    (root / 'download_manifest.json').write_text(json.dumps({
        'source': SOURCE, 'retrieved_at': datetime.now(timezone.utc).isoformat(),
        'start': args.start, 'end_exclusive': args.end, 'files': manifest, 'errors': errors}, indent=2))
    if errors:
        raise RuntimeError(f'{len(errors)} download failures; rerun to retry cached download')
    combined, mismatches = [], []
    for day, sides in sorted(frames.items()):
        if len(sides) != 2:
            mismatches.append(str(day))
            continue
        assert sides['BID'].index.equals(sides['ASK'].index), day
        combined.append(sides['BID'].join(sides['ASK']))
    assert not mismatches, mismatches
    frame = pd.concat(combined).sort_index()
    assert frame.index.is_unique
    for side in ['bid', 'ask']:
        assert (frame[f'{side}_low'] <= frame[[f'{side}_open', f'{side}_close']].min(axis=1)).all()
        assert (frame[f'{side}_high'] >= frame[[f'{side}_open', f'{side}_close']].max(axis=1)).all()
    assert (frame[['ask_'+x for x in ['open','high','low','close']]].to_numpy() >=
            frame[['bid_'+x for x in ['open','high','low','close']]].to_numpy()).all()
    active = ((frame.bid_high > frame.bid_low) | (frame.ask_high > frame.ask_low)
              | (frame.bid_volume > 0) | (frame.ask_volume > 0))
    inactive_minutes = int((~active).sum())
    frame = frame[active]
    frame.to_parquet(root / 'XAUUSD_m1.parquet')
    counts = frame.groupby(frame.index.date).size()
    frame_gaps = frame.index.to_series().diff().dt.total_seconds().div(60)
    quality = {'rows': len(frame), 'start': str(frame.index[0]), 'end': str(frame.index[-1]),
               'days': len(counts), 'days_under_1000_minutes': {str(k): int(v) for k,v in counts[counts<1000].items()},
               'inactive_flat_zero_volume_minutes_removed': inactive_minutes,
               'gaps_over_120_minutes': int((frame_gaps > 120).sum()),
               'median_open_spread': float((frame.ask_open-frame.bid_open).median()),
               'first_bid': float(frame.bid_open.iloc[0]), 'last_bid': float(frame.bid_close.iloc[-1]),
               'sha256': hashlib.sha256((root/'XAUUSD_m1.parquet').read_bytes()).hexdigest()}
    (root / 'quality.json').write_text(json.dumps(quality, indent=2))
    print(json.dumps(quality, indent=2), flush=True)


if __name__ == '__main__':
    main()
