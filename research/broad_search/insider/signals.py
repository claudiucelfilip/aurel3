"""Build entry signals (ticker, filing_date) for the 'any' and 'cluster2' rules."""
from pathlib import Path
import pandas as pd

DATA = Path(__file__).resolve().parents[3] / 'data' / 'broad_search' / 'insider'
MIN_VALUE = 100_000


def load(cutoff=None):
    df = pd.read_parquet(DATA / 'purchases.parquet')
    if cutoff is not None:
        df = df[df['filing_date'] <= pd.Timestamp(cutoff)]
    return df


def signals(df, rule):
    d = df[df['ticker'] != '']
    if rule == 'any':
        g = d.groupby(['ticker', 'filing_date'], as_index=False)['value'].sum()
        return g.loc[g['value'] >= MIN_VALUE, ['ticker', 'filing_date']].reset_index(drop=True)
    if rule == 'cluster2':
        out = []
        for t, g in d.groupby('ticker'):
            g = g.sort_values('filing_date')
            for day in g['filing_date'].unique():
                w = g[(g['filing_date'] > day - pd.Timedelta(days=30)) & (g['filing_date'] <= day)]
                if w['insider'].nunique() >= 2 and w['value'].sum() >= MIN_VALUE:
                    out.append((t, day))
        return pd.DataFrame(out, columns=['ticker', 'filing_date'])
    raise ValueError(rule)


if __name__ == '__main__':
    df = load()
    allt = set()
    for r in ('any', 'cluster2'):
        s = signals(df, r)
        s.to_parquet(DATA / f'signals_{r}.parquet')
        allt |= set(s['ticker'])
        print(r, len(s), 'signal days', s['ticker'].nunique(), 'tickers')
    (DATA / 'tickers_needed.txt').write_text('\n'.join(sorted(allt)) + '\n')
    print(len(allt), 'tickers needed')
