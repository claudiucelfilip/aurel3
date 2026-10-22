"""Download adjusted closes for the ETF census via the Yahoo chart endpoint; one cached CSV per ticker."""
from pathlib import Path
import pandas as pd
from yahoo_chart import adj_close

DATA = Path(__file__).resolve().parents[2] / 'data' / 'broad_search'


def main():
    u = pd.read_csv(DATA / 'etf_universe.csv')
    want = u.loc[~u['excluded'], 'Symbol'].astype(str).str.replace('.', '-', regex=False).tolist()
    store = DATA / 'etf_prices'
    store.mkdir(exist_ok=True)
    done = {p.stem for p in store.glob('*.csv')} | {p.stem for p in store.glob('*.none')}
    for i, t in enumerate(t for t in want if t not in done):
        try:
            s = adj_close(t, start='2016-10-01', pause=1.0)
        except RuntimeError:
            print('failed', t, flush=True)  # retried on the next run
            continue
        if len(s):
            s.to_csv(store / f'{t}.csv')
        else:
            (store / f'{t}.none').write_text('')
        if i % 200 == 0:
            print(i, t, flush=True)
    print('done', len(list(store.glob('*.csv'))), 'priced', flush=True)


if __name__ == '__main__':
    main()
