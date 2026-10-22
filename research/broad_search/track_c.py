"""Track C: machine-learning rotation across 22 asset ETFs. See protocol.json track_C_ml_etf_rotation."""
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
from yahoo_chart import adj_close
import common as C

UNIVERSE = ['SPY', 'QQQ', 'IWM', 'EFA', 'EEM', 'XLB', 'XLE', 'XLF', 'XLI', 'XLK', 'XLP', 'XLU', 'XLV', 'XLY',
            'GLD', 'TLT', 'IEF', 'LQD', 'HYG', 'VNQ', 'DBC']
SIDE = .001


def load():
    path = C.DATA / 'track_c_prices.csv'
    if not path.exists():
        px = pd.concat([adj_close(t, '2005-01-01') for t in UNIVERSE + ['BIL']], axis=1, sort=True)
        px.to_csv(path)
    px = pd.read_csv(path, index_col=0, parse_dates=True)
    macro = pd.concat([pd.read_csv(C.DATA / f'fred_{s}.csv', index_col=0, parse_dates=True, na_values='.')[s]
                       for s in ['T10Y3M', 'BAA10Y']], axis=1)
    return px, macro


def features(px, macro):
    m = px.resample('ME').last()
    daily = px.pct_change(fill_method=None)
    vol = daily.rolling(63).std().resample('ME').last() * np.sqrt(252)
    rows = []
    mac = macro.resample('ME').last().shift(1)  # one-month publication lag
    for t in UNIVERSE:
        f = pd.DataFrame({
            'r1': m[t].pct_change(1, fill_method=None), 'r3': m[t].pct_change(3, fill_method=None),
            'r6': m[t].pct_change(6, fill_method=None), 'r12': m[t].pct_change(12, fill_method=None),
            'vol3': vol[t], 'dist10': m[t] / m[t].rolling(10).mean() - 1,
            'target': m[t].pct_change(1, fill_method=None).shift(-1)})
        f = f.join(mac)
        f['etf'] = t
        rows.append(f)
    return pd.concat(rows).dropna(subset=['r1', 'r3', 'r6', 'r12', 'vol3', 'dist10', 'T10Y3M', 'BAA10Y']), m


def predictions(feat, model_name, first='2009-01-31'):
    cols = ['r1', 'r3', 'r6', 'r12', 'vol3', 'dist10', 'T10Y3M', 'BAA10Y']
    months = sorted(d for d in feat.index.unique() if d >= pd.Timestamp(first) - pd.offsets.MonthEnd(1))
    out = {}
    for t in months:
        # Rows whose target month ended by t; prediction made at t for month t+1.
        train = feat[(feat.index < t) & feat['target'].notna()]
        test = feat[feat.index == t]
        if len(test) < 10:
            continue
        if model_name == 'ridge':
            sc = StandardScaler().fit(train[cols])
            mdl = Ridge(alpha=1.0).fit(sc.transform(train[cols]), train['target'])
            pred = mdl.predict(sc.transform(test[cols]))
        else:
            mdl = HistGradientBoostingRegressor(max_iter=200, learning_rate=.05, max_depth=3, random_state=0)
            pred = mdl.fit(train[cols], train['target']).predict(test[cols])
        out[t] = pd.Series(pred, index=test['etf'].values)
    return pd.DataFrame(out).T


def weights_from(pred, k, cash_rate):
    w = pd.DataFrame(0.0, index=pred.index, columns=UNIVERSE + ['BIL'])
    for t, row in pred.iterrows():
        row = row.dropna().sort_values(ascending=False)
        if row.iloc[0] < cash_rate.get(t, 0):
            w.loc[t, 'BIL'] = 1
        else:
            w.loc[t, row.index[:k]] = 1 / k
    return w


def momentum_control(m):
    r12 = m[UNIVERSE].pct_change(12, fill_method=None)
    w = pd.DataFrame(0.0, index=r12.index, columns=UNIVERSE + ['BIL'])
    for t, row in r12.loc['2008-12-31':].iterrows():
        w.loc[t, row.dropna().nlargest(3).index] = 1 / 3
    return w.loc['2008-12-31':]


def equity(px, w, start, end):
    """Weights set at month end t apply to trading days in month t+1."""
    daily = px[UNIVERSE + ['BIL']].pct_change(fill_method=None).loc[start:end]
    wd = w.reindex(daily.index, method='ffill').shift(1).dropna(how='all')
    turnover = w.diff().abs().sum(axis=1)
    cost = pd.Series(0.0, index=daily.index)
    for t, tv in turnover.items():
        nxt = daily.index[daily.index > t]
        if len(nxt):
            cost[nxt[0]] += tv * SIDE
    r = (wd * daily.loc[wd.index].fillna(0)).sum(axis=1) - cost.loc[wd.index]
    return (1 + r).cumprod()


def main():
    px, macro = load()
    feat, m = features(px, macro)
    cash_rate = m['BIL'].pct_change(fill_method=None).fillna(0)  # last month's T-bill return as hurdle
    preds = {name: predictions(feat, name) for name in ['ridge', 'trees']}
    configs = {f'{name}_top{k}': weights_from(preds[name], k, cash_rate) for name in preds for k in (1, 3)}
    spy = px['SPY']
    dev, hold = {}, {}
    for name, w in configs.items():
        eq = equity(px, w, '2009-01-01', '2018-12-31')
        dev[name] = C.metrics(eq, spy.loc[eq.index[0]:eq.index[-1]])
    choice = max(dev, key=lambda k: dev[k]['sharpe'])
    C.record_choice('track_c', choice, dev)
    for name, w in configs.items():
        eq = equity(px, w, '2018-12-31', C.END)
        hold[name] = C.metrics(eq, spy.loc[eq.index[0]:eq.index[-1]])
    ctrl = momentum_control(m)
    control = {'development': C.metrics(e := equity(px, ctrl, '2009-01-01', '2018-12-31'), spy.loc[e.index[0]:e.index[-1]]),
               'holdout': C.metrics(e := equity(px, ctrl, '2018-12-31', C.END), spy.loc[e.index[0]:e.index[-1]])}
    res = C.verdict(dev[choice], hold[choice])
    C.save('track_c', {'choice': choice, 'development': dev, 'holdout': hold, 'momentum_control': control, 'rules': res})
    C.show('C', choice, dev, hold, res)
    print('control dev ex', round(control['development']['excess_pp'], 1), 'hold ex', round(control['holdout']['excess_pp'], 1))


if __name__ == '__main__':
    main()
