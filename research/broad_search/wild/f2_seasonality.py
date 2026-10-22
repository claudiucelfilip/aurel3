"""F2: same-calendar-month seasonality in stocks (Heston & Sadka). See protocol.json track_F_wild_batch.F2."""
import numpy as np
import pandas as pd
import wild_common as W

MIN_PRICE, MIN_OBS, YEARS = 5.0, 3, 5


def weights(adj, close, n):
    m = adj.groupby(adj.index.to_period('M')).tail(1)
    mr = m.pct_change(fill_method=None)
    mclose = close.groupby(close.index.to_period('M')).tail(1)
    hist = m.notna().rolling(24).sum() >= 24
    w = pd.DataFrame(0.0, index=mr.index, columns=adj.columns)
    for i in range(12 * YEARS, len(mr)):
        # Same calendar month in the prior YEARS years, for the month about to start (i+1 month).
        rows = [i + 1 - 12 * y for y in range(1, YEARS + 1)]
        rows = [r for r in rows if r >= 0]
        past = mr.iloc[rows]
        score = past.mean().where(past.notna().sum() >= MIN_OBS)
        ok = (mclose.iloc[i] >= MIN_PRICE) & hist.iloc[i] & score.notna()
        top = score[ok].nlargest(n).index
        if len(top):
            w.iloc[i, w.columns.get_indexer(top)] = 1 / len(top)
    w.index = W.next_close(adj.index, w.index)
    return w[~w.index.duplicated(keep='last')]


def main():
    adj, close, bad = W.clean_stocks(*W.load_stocks())
    configs = {f'top{n}': weights(adj, close, n) for n in (50, 100)}
    W.evaluate('track_f2_seasonality', configs, adj, extra={'glitch_tickers_dropped': len(bad), 'note':
               'The first run on raw Yahoo data showed +44pp/yr in the holdout, all from unadjusted reverse splits (ALP, SOBR, PROP).'})


if __name__ == '__main__':
    main()
