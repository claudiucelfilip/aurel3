"""Track B: SPY + Bitcoin, static or trend-filtered sleeve. See protocol.json track_B_crypto_with_spy."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from yahoo_chart import adj_close
import common as C

DATA = C.DATA
COST = {'SPY': .001, 'BTC': .0025, 'CASH': .001}


def load():
    path = DATA / 'track_b_prices.csv'
    if not path.exists():
        px = pd.concat([adj_close('SPY', '2014-09-01'), adj_close('BTC-USD', '2014-09-01'), adj_close('BIL', '2014-09-01')], axis=1)
        px.columns = ['SPY', 'BTC', 'CASH']
        px.to_csv(path)
    px = pd.read_csv(path, index_col=0, parse_dates=True)
    btc_sma = {n: px['BTC'].dropna().rolling(n).mean() for n in (100, 200)}
    days = px['SPY'].dropna().index  # trade on US trading days; BTC weekend moves accrue to the next session
    out = px.loc[days].ffill()
    for n, s in btc_sma.items():
        out[f'sma{n}'] = s.reindex(days, method='ffill')
    return out


def simulate(px, w_btc, trend_n=None, start='2015-01-02', end=C.END):
    p = px.loc[start:end]
    rets = p[['SPY', 'BTC', 'CASH']].pct_change().fillna(0)
    on = pd.Series(True, index=p.index) if trend_n is None else (p['BTC'] > p[f'sma{trend_n}'])
    on = on.shift(1).fillna(False) if trend_n else on  # signal at close, trade next close
    month = p.index.to_period('M')
    rebalance = pd.Series(month != np.roll(month, 1), index=p.index)
    hold = np.array([1 - w_btc, w_btc, 0.0])
    if trend_n and not on.iloc[0]:
        hold = np.array([1 - w_btc, 0.0, w_btc])
    value, vals = 1.0, []
    cost_vec = np.array([COST['SPY'], COST['BTC'], COST['CASH']])
    for i, day in enumerate(p.index):
        if i:
            hold = hold * (1 + rets.iloc[i].values)
            value = hold.sum()
        target = np.array([1 - w_btc, w_btc if on.iloc[i] else 0.0, 0.0 if on.iloc[i] else w_btc]) * value
        drift = hold / value
        flip = trend_n is not None and i and on.iloc[i] != on.iloc[i - 1]
        if rebalance.iloc[i] or flip:
            trade = np.abs(target - hold)
            value -= (trade * cost_vec).sum()
            hold = target / target.sum() * value
        vals.append(value)
    return pd.Series(vals, index=p.index)


def main():
    px = load()
    configs = {}
    for w in (.10, .25):
        configs[f'static_{int(w * 100)}'] = (w, None)
        for n in (100, 200):
            configs[f'trend{n}_{int(w * 100)}'] = (w, n)
    spy = px['SPY']
    dev, choice = {}, None
    for name, (w, n) in configs.items():
        eq = simulate(px, w, n, end='2018-12-31')
        dev[name] = C.metrics(eq, spy.loc[eq.index[0]:eq.index[-1]])
    choice = max(dev, key=lambda k: dev[k]['sharpe'])
    C.record_choice('track_b', choice, dev)
    hold = {}
    for name, (w, n) in configs.items():
        eq = simulate(px, w, n, start='2018-12-31')
        hold[name] = C.metrics(eq, spy.loc[eq.index[0]:])
    res = C.verdict(dev[choice], hold[choice])
    out = {'choice': choice, 'development': dev, 'holdout': hold, 'rules': res}
    C.save('track_b', out)
    C.show('B', choice, dev, hold, res)


if __name__ == '__main__':
    main()
