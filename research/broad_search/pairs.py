"""Track E: buy Y after X falls. See protocol.json track_E_inverse_reaction_pairs."""
import numpy as np
import pandas as pd
from yahoo_chart import adj_close
import common as C

PAIRS_UNIVERSE = [
    'SPY', 'QQQ', 'DIA', 'IWM', 'MDY', 'IJR', 'IWD', 'IWF', 'IVE', 'IVW',
    'XLB', 'XLE', 'XLF', 'XLI', 'XLK', 'XLP', 'XLU', 'XLV', 'XLY', 'IYR', 'IYT', 'IBB', 'SMH', 'XHB', 'XME',
    'KBE', 'KRE', 'OIH', 'IGV', 'ITB', 'IHI',
    'EWA', 'EWC', 'EWG', 'EWH', 'EWJ', 'EWW', 'EWY', 'EWZ', 'EWT', 'EWU', 'EWS', 'EWP', 'EWI', 'EWQ', 'EWL',
    'EWN', 'EWD', 'EWK', 'EWO', 'EWM', 'FXI', 'EZA', 'EEM', 'EFA', 'VGK', 'EPP', 'ILF',
    'TLT', 'IEF', 'SHY', 'LQD', 'AGG', 'TIP', 'HYG',
    'GLD', 'IAU', 'SLV', 'USO', 'DBC', 'DBA', 'UNG', 'GDX',
    'FXE', 'FXY', 'FXB', 'FXA', 'FXC', 'FXF', 'UUP',
    'VNQ', 'ICF', 'RWR']
DEV = ('2008-01-01', '2018-12-31')
SIDE = .001
K, MAX_PER_Y, MIN_TRIG, HIT = 10, 2, 60, .56


def load():
    path = C.DATA / 'pairs_prices.csv'
    if not path.exists():
        cols = []
        for t in PAIRS_UNIVERSE:
            s = adj_close(t, '2007-01-01', pause=0.8)
            if len(s):
                cols.append(s.rename(t))
        pd.concat(cols, axis=1, sort=True).to_csv(path)
    px = pd.read_csv(path, index_col=0, parse_dates=True)
    px = px.loc[px['SPY'].notna()].ffill(limit=5)
    keep = [t for t in px if px[t].loc[:'2007-12-31'].notna().any()]
    return px[keep].loc[:C.END]


def frames(px, freq, trigger, optimistic=False):
    """Per signal date: trigger matrix, Y outcome, entry day. Outcome uses a one-day delay unless optimistic."""
    days = px.index
    if freq == 'daily':
        p = px
        lookback = 252
    else:
        p = px.groupby(days.to_period('W-FRI')).tail(1)
        lookback = 52
    r = p.pct_change(fill_method=None)
    if trigger == 'down':
        trig = r < 0
    else:
        trig = r < r.rolling(lookback, min_periods=lookback // 2).quantile(.1).shift(1)
    pos = days.get_indexer(p.index)
    entry_pos = pos if optimistic else np.minimum(pos + 1, len(days) - 1)
    entry = pd.Series(days[entry_pos], index=p.index)
    ent_px = px.loc[entry.values].set_axis(p.index)
    out = ent_px.shift(-1) / ent_px - 1
    return trig & r.notna(), out, entry


def nw_t(x, lags=4):
    x = np.asarray(x, float)
    if len(x) < 10 or x.std() == 0:
        return 0.0
    return C.nw_t(x, lags)


def pair_stats(trig, out, a, b):
    """Every ordered pair (X != Y) over signal dates in [a, b]: triggers, hit rate, mean excess vs SPY, t."""
    T, O = trig.loc[a:b], out.loc[a:b]
    ok = O.notna().all(axis=1) | O['SPY'].notna()
    T, O = T[ok], O[ok]
    ex = O.sub(O['SPY'], axis=0)
    rows = []
    for x in T.columns:
        m = T[x].values
        n = int(m.sum())
        if n < 10:
            continue
        sub, sub_ex = O.values[m], ex.values[m]
        for j, y in enumerate(O.columns):
            if y == x:
                continue
            v = sub[:, j]
            v, e = v[~np.isnan(v)], sub_ex[:, j][~np.isnan(sub_ex[:, j])]
            if len(v) < 10:
                continue
            rows.append((x, y, len(v), float((v > 0).mean()), float(e.mean()), nw_t(e)))
    return pd.DataFrame(rows, columns=['x', 'y', 'n', 'hit', 'mean_ex', 't'])


def select(stats):
    c = stats[(stats['hit'] >= HIT) & (stats['n'] >= MIN_TRIG)].sort_values('t', ascending=False)
    picked, per_y = [], {}
    for _, row in c.iterrows():
        if per_y.get(row['y'], 0) < MAX_PER_Y:
            picked.append(row)
            per_y[row['y']] = per_y.get(row['y'], 0) + 1
        if len(picked) == K:
            break
    return pd.DataFrame(picked).reset_index(drop=True)


def equity(px, trig, entry, pairs, start, end):
    """Weights chosen at signal t are bought at the entry close and held until the next entry close."""
    cols = list(px.columns)
    w = pd.DataFrame(0.0, index=trig.index, columns=cols)
    for t in trig.index:
        ys = sorted({p.y for p in pairs.itertuples() if trig.at[t, p.x]})
        if ys:
            w.loc[t, ys] = 1 / len(ys)
        else:
            w.loc[t, 'SPY'] = 1.0
    w.index = entry.values
    w = w[~w.index.duplicated(keep='last')]
    daily = px.pct_change(fill_method=None).loc[start:end].fillna(0)
    held = w.reindex(px.index).ffill().shift(1).loc[start:end].fillna(0)
    held.loc[held.sum(axis=1) == 0, 'SPY'] = 1.0
    turnover = held.diff().abs().sum(axis=1).fillna(0)
    r = (held * daily).sum(axis=1) - turnover * SIDE
    return (1 + r).cumprod()


def persistence(dev_pairs, hold_stats):
    m = dev_pairs[['x', 'y']].merge(hold_stats, on=['x', 'y'], how='left')
    return float(((m['hit'] >= HIT) & (m['mean_ex'] > 0)).mean()), m


def main():
    px = load()
    spy = px['SPY']
    configs = {f'{f}_{g}': (f, g) for f in ('daily', 'weekly') for g in ('down', 'bottom10')}
    dev, hold, chosen_pairs, diag = {}, {}, {}, {}
    rng = np.random.default_rng(0)
    for name, (f, g) in configs.items():
        trig, out, entry = frames(px, f, g)
        dstats = pair_stats(trig, out, *DEV)
        pairs = select(dstats)
        chosen_pairs[name] = pairs
        eq = equity(px, trig, entry, pairs, '2008-01-01', DEV[1])
        dev[name] = C.metrics(eq, spy.loc[eq.index[0]:eq.index[-1]])
        hstats = pair_stats(trig, out, '2019-01-01', C.END)
        share, merged = persistence(pairs, hstats)
        placebo = []
        both = dstats.merge(hstats, on=['x', 'y'], suffixes=('_dev', '_hold'))
        for _ in range(1000):
            s = both.sample(len(pairs), random_state=rng.integers(1 << 31))
            placebo.append(float(((s['hit_hold'] >= HIT) & (s['mean_ex_hold'] > 0)).mean()))
        diag[name] = {
            'pairs_tested': int(len(dstats)), 'pairs_meeting_56pct_dev': int(((dstats['hit'] >= HIT) & (dstats['n'] >= MIN_TRIG)).sum()),
            'selected': merged.rename(columns={'n': 'n_hold', 'hit': 'hit_hold', 'mean_ex': 'mean_ex_hold', 't': 't_hold'})
                .join(pairs[['n', 'hit', 'mean_ex', 't']].add_suffix('_dev')).to_dict('records'),
            'holdout_persistence': share, 'placebo_persistence_mean': float(np.mean(placebo)),
            'placebo_persistence_p95': float(np.quantile(placebo, .95)),
            'dev_vs_hold_hit_corr_all_pairs': float(both['hit_dev'].corr(both['hit_hold'])),
            'dev_vs_hold_excess_corr_all_pairs': float(both['mean_ex_dev'].corr(both['mean_ex_hold']))}
        print(name, 'pairs', diag[name]['pairs_tested'], 'dev>=56%', diag[name]['pairs_meeting_56pct_dev'],
              'persist', round(share, 2), 'placebo', round(diag[name]['placebo_persistence_mean'], 2), flush=True)
    choice = max(dev, key=lambda k: dev[k]['sharpe'])
    C.record_choice('track_e', choice, dev)
    optimistic = {}
    for name, (f, g) in configs.items():
        trig, out, entry = frames(px, f, g)
        eq = equity(px, trig, entry, chosen_pairs[name], '2018-12-31', C.END)
        hold[name] = C.metrics(eq, spy.loc[eq.index[0]:eq.index[-1]])
        trig_o, _, entry_o = frames(px, f, g, optimistic=True)
        eq_o = equity(px, trig_o, entry_o, chosen_pairs[name], '2018-12-31', C.END)
        optimistic[name] = C.metrics(eq_o, spy.loc[eq_o.index[0]:eq_o.index[-1]])
    res = C.verdict(dev[choice], hold[choice])
    C.save('track_e', {'choice': choice, 'universe': list(px.columns), 'development': dev, 'holdout': hold,
                       'holdout_same_close_upper_bound': optimistic, 'diagnostics': diag, 'rules': res})
    C.show('E', choice, dev, hold, res)
    for k in optimistic:
        print('E same-close upper bound', k, round(optimistic[k]['excess_pp'], 1))


if __name__ == '__main__':
    main()
