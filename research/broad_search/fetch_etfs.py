"""Download adjusted closes for the ETF census in small batches with retries; cached per ticker batch."""
import time
from pathlib import Path
import pandas as pd

DATA = Path(__file__).resolve().parents[2] / 'data' / 'broad_search'


def main():
    import yfinance as yf
    u = pd.read_csv(DATA / 'etf_universe.csv')
    want = u.loc[~u['excluded'], 'Symbol'].astype(str).str.replace('.', '-', regex=False).tolist()
    store = DATA / 'etf_prices'
    store.mkdir(exist_ok=True)
    done = {p.stem for p in store.glob('*.csv')} | {p.stem for p in store.glob('*.none')}
    todo = [t for t in want if t not in done]
    print(len(todo), 'to fetch', flush=True)
    for i in range(0, len(todo), 40):
        batch = todo[i:i + 40]
        for attempt in range(6):
            try:
                f = yf.download(batch, start='2016-10-01', end='2026-10-17', auto_adjust=False,
                                progress=False, threads=False)['Adj Close']
                if isinstance(f, pd.Series):
                    f = f.to_frame(batch[0])
                missing = [t for t in batch if t not in f or f[t].notna().sum() == 0]
                if len(missing) == len(batch):
                    raise RuntimeError('all missing, likely rate limit')
                break
            except Exception as exc:
                print('retry', i, attempt, str(exc)[:60], flush=True)
                time.sleep(60 * (attempt + 1))
        else:
            continue
        for t in batch:
            if t in f and f[t].notna().sum():
                f[t].dropna().to_csv(store / f'{t}.csv')
            else:
                (store / f'{t}.none').write_text('')
        time.sleep(4)
    print('done', len(list(store.glob('*.csv'))), 'priced', flush=True)


if __name__ == '__main__':
    main()
