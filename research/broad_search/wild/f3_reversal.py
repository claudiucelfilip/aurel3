"""F3: buy the k ETFs that fell most last week / month. See protocol.json track_F_wild_batch.F3."""
import pandas as pd
import wild_common as W
import pairs as P


def weights(px, freq, k):
    if freq == 'weekly':
        p = px.groupby(px.index.to_period('W-FRI')).tail(1)
    else:
        p = px.groupby(px.index.to_period('M')).tail(1)
    r = p.pct_change(fill_method=None)
    w = pd.DataFrame(0.0, index=r.index, columns=px.columns)
    for t, row in r.iterrows():
        row = row.dropna()
        if len(row) >= k:
            w.loc[t, row.nsmallest(k).index] = 1 / k
    w.index = W.next_close(px.index, w.index)
    return w[~w.index.duplicated(keep='last')]


def main():
    px = P.load()
    configs = {f'{f}_k{k}': weights(px, f, k) for f in ('weekly', 'monthly') for k in (3, 5)}
    W.evaluate('track_f3_reversal', configs, px)


if __name__ == '__main__':
    main()
