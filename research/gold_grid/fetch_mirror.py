"""Download pinned archival data and cross-check all available original samples."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import lzma
from pathlib import Path
import struct
import subprocess

import numpy as np
import pandas as pd


def main():
    root = Path('data/gold_grid')
    target = root / 'mirror'
    target.mkdir(parents=True, exist_ok=True)
    ref = '78fd60f8bf3a1cebe198828147e54e4ed32385d8'
    tree = json.loads(subprocess.check_output([
        'gh', 'api', f'repos/kevingtlin/Market-Data-Lab/git/trees/{ref}?recursive=1']))
    (root/'mirror_tree.json').write_text(json.dumps(tree))
    selected = [f for f in tree['tree'] if '/xauusd_' in f['path']
                and f['path'].endswith('.csv') and int(f['path'].split('_')[-2]) >= 2019]

    def fetch(item):
        path = target / Path(item['path']).name
        if not path.exists():
            data = subprocess.check_output(['gh','api',item['url'],
                                           '-H','Accept: application/vnd.github.raw+json'])
            path.write_bytes(data)
        data = path.read_bytes()
        sha = hashlib.sha1(f'blob {len(data)}\0'.encode()+data).hexdigest()
        assert sha == item['sha'], (path.name,sha,item['sha'])
        return {'path': item['path'], 'url': item['url'], 'git_sha1': sha,
                'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}

    manifest = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        for n, f in enumerate(as_completed([pool.submit(fetch,x) for x in selected]),1):
            manifest.append(f.result())
            if n%20==0:
                print(f'{n}/{len(selected)} monthly archives',flush=True)
    sides = {}
    for side in ['bid','ask']:
        frames = [pd.read_csv(p) for p in sorted(target.glob(f'xauusd_{side}_*.csv'))]
        frame = pd.concat(frames,ignore_index=True).set_index('timestamp')
        frame.index = pd.to_datetime(frame.index,unit='ms',utc=True)
        assert frame.index.is_unique and frame.index.is_monotonic_increasing
        sides[side] = frame.add_prefix(side+'_')
    left_only = len(sides['bid'].index.difference(sides['ask'].index))
    right_only = len(sides['ask'].index.difference(sides['bid'].index))
    unmatched = {'bid_only':[str(x) for x in sides['bid'].index.difference(sides['ask'].index)],
                 'ask_only':[str(x) for x in sides['ask'].index.difference(sides['bid'].index)]}
    assert left_only+right_only <= 10, unmatched
    frame = sides['bid'].join(sides['ask'],how='inner')
    checks = []
    for original in sorted((root/'raw').glob('*.bi5')):
        raw = original.read_bytes()
        if not raw:
            continue
        day, side = original.stem.split('_')
        rows = np.asarray(list(struct.iter_unpack('>5If',lzma.decompress(raw))))
        idx = pd.to_datetime(day,utc=True)+pd.to_timedelta(rows[:,0],unit='s')
        overlap = idx.intersection(frame.index)
        if len(overlap) == 0:
            continue
        values = pd.DataFrame(rows[:,[1,4,3,2]]/1000,index=idx)
        observed = frame.loc[overlap,[side.lower()+'_'+x for x in ['open','high','low','close']]]
        error = np.max(np.abs(observed.to_numpy()-values.loc[overlap].to_numpy()))
        assert error < 1e-8, (original.name,error)
        checks.append({'archive': original.name,'minutes':len(overlap),'max_error':float(error),
                       'sha256':hashlib.sha256(raw).hexdigest()})
    assert len(checks) >= 2, 'Need original-provider overlap checks'
    for side in ['bid','ask']:
        assert (frame[side+'_low'] <= frame[[side+'_open',side+'_close']].min(axis=1)).all()
        assert (frame[side+'_high'] >= frame[[side+'_open',side+'_close']].max(axis=1)).all()
    assert (frame.to_numpy()>0).all()
    assert (frame[[f'ask_{x}' for x in ['open','high','low','close']]].to_numpy() >=
            frame[[f'bid_{x}' for x in ['open','high','low','close']]].to_numpy()).all()
    # Mirror omits volume. Exclude entirely flat minutes to avoid fills on stale weekend quotes.
    active = (frame.bid_high>frame.bid_low)|(frame.ask_high>frame.ask_low)
    flat_removed = int((~active).sum())
    frame = frame[active]
    frame.to_parquet(root/'XAUUSD_m1.parquet')
    counts = frame.groupby(frame.index.date).size()
    gaps = frame.index.to_series().diff().dt.total_seconds()/60
    quality = {'source':'https://www.dukascopy.com/api/data/get/historical-data-export',
               'mirror':'https://github.com/kevingtlin/Market-Data-Lab/blob/main/XAUUSD_DUKASCOPY_M1_BID_ASK_README.md',
               'mirror_commit':tree['sha'],'rows':len(frame),'start':str(frame.index[0]),'end':str(frame.index[-1]),
               'days':len(counts),'flat_minutes_removed':flat_removed,
               'matching_original_archives':len(checks),'matching_original_side_minutes':sum(x['minutes'] for x in checks),
               'bid_only_minutes':left_only,'ask_only_minutes':right_only,
               'unmatched_minutes_excluded':unmatched,
               'gaps_over_120_minutes':int((gaps>120).sum()),
               'median_open_spread':float((frame.ask_open-frame.bid_open).median()),
               'first_bid':float(frame.bid_open.iloc[0]),'last_bid':float(frame.bid_close.iloc[-1]),
               'sha256':hashlib.sha256((root/'XAUUSD_m1.parquet').read_bytes()).hexdigest(),
               'limitations':['Mirror data; original-provider checks cover only the downloaded sample.',
                              'Flat minutes excluded because mirror has no volume; some genuine quiet quotes may be omitted.',
                              'Intraminute bid/ask extrema are not synchronized ticks.']}
    (root/'quality.json').write_text(json.dumps(quality,indent=2))
    (root/'mirror_manifest.json').write_text(json.dumps({'quality':quality,'files':manifest,'original_checks':checks},indent=2))
    counts.to_csv(root/'daily_minute_counts.csv')
    print(json.dumps(quality,indent=2),flush=True)


if __name__ == '__main__':
    main()
