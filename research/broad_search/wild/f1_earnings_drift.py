"""F1: buy stocks that jumped on their earnings 8-K day, hold 20 or 60 trading days. See protocol.json track_F_wild_batch.F1."""
import json
import numpy as np
import pandas as pd
import wild_common as W

MIN_PRICE, MAX_POS, TOP_SHARE = 5.0, 50, .20


def events(adj, close):
    """One row per (filing day, ticker) with the stock's excess return over SPY on that day."""
    raw = json.loads((W.WILD / 'earnings_8k.json').read_text())
    r = adj.pct_change(fill_method=None)
    ex = r.sub(r['SPY'], axis=0)
    rows = []
    for t, dates in raw.items():
        if not dates or t not in adj.columns:
            continue
        d = pd.to_datetime(dates)
        d = adj.index[np.minimum(adj.index.searchsorted(d), len(adj.index) - 1)]  # filing on a non-trading day -> next session
        d = d[(d >= '2007-01-01') & (d <= W.C.END)]
        v = ex.loc[d, t]
        ok = v.notna() & (close.loc[d, t] >= MIN_PRICE)
        rows.append(pd.DataFrame({'date': d[ok.values], 'ticker': t, 'ex': v[ok].values}))
    ev = pd.concat(rows).sort_values('date').reset_index(drop=True)
    # Threshold = top 20% of the trailing 252 trading days' events (first year: +5%).
    thr = ev.set_index('date')['ex'].rolling('365D').quantile(1 - TOP_SHARE).shift(1)
    thr = thr.groupby(level=0).last().reindex(ev['date']).values
    ev['threshold'] = np.where(ev['date'] < ev['date'].min() + pd.Timedelta(days=365), .05, thr)
    return ev[ev['ex'] > ev['threshold']]


def weights(adj, ev, hold_days):
    """Each selected event enters at the next close and stays hold_days sessions; at most MAX_POS names, oldest dropped."""
    idx = adj.index
    entry_pos = np.minimum(idx.searchsorted(ev['date'].values, side='right'), len(idx) - 1)
    book = {}  # ticker -> exit position
    w = pd.DataFrame(0.0, index=idx, columns=adj.columns)
    ev = ev.assign(pos=entry_pos).groupby('pos')['ticker'].apply(list)
    for i in range(len(idx)):
        book = {t: e for t, e in book.items() if e > i}
        for t in ev.get(i, []):
            book[t] = i + hold_days
        if len(book) > MAX_POS:
            book = dict(sorted(book.items(), key=lambda kv: kv[1])[-MAX_POS:])
        if book:
            w.iloc[i, w.columns.get_indexer(list(book))] = 1 / len(book)
    return w


def main():
    adj, close, bad = W.clean_stocks(*W.load_stocks())
    ev = events(adj, close)
    configs = {f'hold{h}': weights(adj, ev, h) for h in (60, 20)}
    W.evaluate('track_f1_earnings_drift', configs, adj,
               extra={'events_selected': int(len(ev)), 'glitch_tickers_dropped': len(bad)})


if __name__ == '__main__':
    main()
