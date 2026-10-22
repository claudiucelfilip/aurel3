"""SPMO concentration diagnostic: time, factor, holdings and long-history checks. See protocol.json."""
import io
import json
import zipfile
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
LIVE = ROOT / 'data' / 'live_funds'
DATA = ROOT / 'data' / 'spmo_diagnostic'
OUT = ROOT / 'data' / 'gold_grid' / 'results' / 'spmo_diagnostic'
END = pd.Timestamp('2026-10-16')
CUT = pd.Timestamp('2024-01-01')
COST = .001
# Protocol start; SPMO had zero-volume days until 2017-11-24, so 2017-12-29 is the first clean year-end.
START_PROTOCOL = pd.Timestamp('2015-10-12')
START_LIQUID = pd.Timestamp('2017-12-29')


def adj(path):
    return pd.read_csv(path, index_col=0, parse_dates=True)['Adj Close'].dropna()


def load_funds():
    f = {t: adj(LIVE / f'{t}.csv') for t in ['SPMO', 'SPY', 'GLD', 'MTUM']}
    f.update({t: adj(DATA / f'{t}.csv') for t in ['SPYG', 'QQQ', 'RSP', 'IVV', 'XLK']})
    return pd.DataFrame(f).loc[:END]


def window(prices, start, end=END):
    p = prices.loc[start:end].dropna()
    years = (p.index[-1] - p.index[0]).days / 365.25
    eq = p / p.iloc[0] / (1 + COST)
    final = eq.iloc[-1] * (1 - COST)
    return {'start': str(p.index[0].date()), 'end': str(p.index[-1].date()),
            'total': float(final - 1), 'cagr': float(final ** (1 / years) - 1),
            'drawdown': float(1 - (eq / eq.cummax()).min())}


def newey_west(y, x=None, lags=6):
    y = np.asarray(y, float)
    X = np.ones((len(y), 1)) if x is None else np.column_stack([np.ones(len(y)), np.asarray(x, float)])
    beta = np.linalg.lstsq(X, y, rcond=None)[0]
    e = y - X @ beta
    xe = X * e[:, None]
    S = xe.T @ xe
    for lag in range(1, lags + 1):
        w = 1 - lag / (lags + 1)
        g = xe[lag:].T @ xe[:-lag]
        S += w * (g + g.T)
    inv = np.linalg.inv(X.T @ X)
    se = np.sqrt(np.diag(inv @ S @ inv))
    r2 = 1 - (e @ e) / ((y - y.mean()) @ (y - y.mean()))
    return beta, beta / se, float(r2)


def relative_drawdown(a, b):
    ratio = (a / b).dropna()
    under = ratio < ratio.cummax()
    longest, run_start, best = pd.Timedelta(0), None, None
    for day, flag in under.items():
        if flag and run_start is None:
            run_start = day
        if not flag and run_start is not None:
            if day - run_start > longest:
                longest, best = day - run_start, (run_start, day)
            run_start = None
    open_run = None
    if run_start is not None:
        open_run = (str(run_start.date()), 'still below on ' + str(ratio.index[-1].date()))
        if ratio.index[-1] - run_start > longest:
            longest, best = ratio.index[-1] - run_start, (run_start, ratio.index[-1])
    return {'max_depth': float(1 - (ratio / ratio.cummax()).min()),
            'longest_years': round(longest.days / 365.25, 2),
            'longest_span': [str(best[0].date()), str(best[1].date())] if best else None,
            'open_run': open_run}


def q1(f):
    out = {}
    for start, label in [(START_PROTOCOL, 'protocol_start_stale_prices'), (START_LIQUID, 'liquid_start'),
                         (pd.Timestamp('2019-05-22'), 'common_live_start')]:
        logs = np.log(f[['SPMO', 'SPY', 'GLD']].loc[start:]).diff().dropna()
        rows = {}
        for bench in ['SPY', 'GLD']:
            ex = logs['SPMO'] - logs[bench]
            pre, post = ex[ex.index < CUT].sum(), ex[ex.index >= CUT].sum()
            pre_w = {t: window(f[t], start, pd.Timestamp('2023-12-29')) for t in ['SPMO', bench]}
            post_w = {t: window(f[t], pd.Timestamp('2023-12-29')) for t in ['SPMO', bench]}
            full_w = {t: window(f[t], start) for t in ['SPMO', bench]}
            rows[bench] = {
                'log_excess_total': float(pre + post), 'log_excess_before_2024': float(pre),
                'log_excess_2024_on': float(post),
                'share_from_2024': float(post / (pre + post)) if pre + post != 0 else None,
                'annualized_excess_before_2024_pp': 100 * (pre_w['SPMO']['cagr'] - pre_w[bench]['cagr']),
                'annualized_excess_2024_on_pp': 100 * (post_w['SPMO']['cagr'] - post_w[bench]['cagr']),
                'annualized_excess_full_pp': 100 * (full_w['SPMO']['cagr'] - full_w[bench]['cagr']),
                'relative_drawdown': relative_drawdown(f['SPMO'].loc[start:], f[bench].loc[start:])}
        out[label] = rows
    ye = f.resample('YE').last()
    ye.loc[pd.Timestamp('2015-10-12')] = f.loc['2015-10-12']
    ye = ye.sort_index()
    annual = ye.pct_change().iloc[1:]
    annual.index = annual.index.year
    out['annual_returns'] = {str(y): {t: (None if pd.isna(v) else float(v)) for t, v in r.items()}
                             for y, r in annual.iterrows()}
    blocks = {}
    for a, b in [(2016, 2017), (2018, 2019), (2020, 2021), (2022, 2023), (2024, 2025), (2026, 2026)]:
        s = ye.loc[ye.index < pd.Timestamp(f'{a}-01-01')].iloc[-1]
        e = ye.loc[ye.index <= pd.Timestamp(f'{b}-12-31')].iloc[-1]
        blocks[f'{a}-{b}' if a != b else f'{a} to Oct 16'] = {t: float(e[t] / s[t] - 1) for t in ['SPMO', 'SPY', 'GLD', 'MTUM', 'SPYG', 'QQQ']}
    out['two_year_blocks'] = blocks
    # MTUM: separate, liquid momentum implementation since 2013.
    m = np.log(f[['MTUM', 'SPY']].dropna()).diff().dropna()
    exm = m['MTUM'] - m['SPY']
    out['MTUM_vs_SPY'] = {'start': str(m.index[0].date()), 'log_excess_total': float(exm.sum()),
                          'log_excess_before_2024': float(exm[exm.index < CUT].sum()),
                          'log_excess_2024_on': float(exm[exm.index >= CUT].sum()),
                          'relative_drawdown': relative_drawdown(f['MTUM'].dropna(), f['SPY'].loc[f['MTUM'].dropna().index[0]:])}
    mon = f.resample('ME').last().pct_change()
    tstats = {}
    for label, start in [('liquid_start', START_LIQUID), ('common_live_start', pd.Timestamp('2019-05-22'))]:
        ex = (mon['SPMO'] - mon['SPY']).loc[start + pd.offsets.MonthEnd(1):].dropna()
        for part, sl in [('all', ex), ('before_2024', ex[ex.index < CUT]), ('2024_on', ex[ex.index >= CUT])]:
            b, t, _ = newey_west(sl.values)
            tstats[f'{label}:{part}'] = {'months': len(sl), 'mean_monthly_pp': float(100 * b[0]), 't_nw6': float(t[0]),
                                         'share_months_ahead': float((sl > 0).mean())}
    out['monthly_excess_vs_SPY'] = tstats
    return out


def french(name, section_marker=None):
    with zipfile.ZipFile(DATA / name) as z:
        text = z.read(z.namelist()[0]).decode('latin1')
    lines = text.splitlines()
    start = 0
    if section_marker:
        start = next(i for i, l in enumerate(lines) if section_marker in l)
    head = next(i for i in range(start, len(lines)) if lines[i].strip().startswith(','))
    rows = []
    for l in lines[head + 1:]:
        parts = [p.strip() for p in l.split(',')]
        if len(parts[0]) != 6 or not parts[0].isdigit():
            break
        rows.append(parts)
    cols = [c.strip() for c in lines[head].split(',')][1:]
    df = pd.DataFrame([r[1:] for r in rows], index=pd.to_datetime([r[0] for r in rows], format='%Y%m') + pd.offsets.MonthEnd(0),
                      columns=cols).astype(float) / 100
    # French missing codes are -99.99 and -999 before scaling.
    return df.mask(df <= -.9998)


def q2(f):
    ff5 = french('ff5_monthly.zip')
    mom = french('mom_monthly.zip')
    fac = ff5.join(mom, how='inner')
    mon = f.resample('ME').last().pct_change()
    out = {'factor_regression': {}, 'etf_control_regression': {}, 'buy_and_hold': {}}
    y_all = (mon['SPMO'] - fac['RF']).dropna()
    for label, start in [('liquid_start', START_LIQUID), ('common_live_start', pd.Timestamp('2019-05-22'))]:
        for part in ['all', 'before_2024', '2024_on']:
            y = y_all.loc[start + pd.offsets.MonthEnd(1):]
            y = y[y.index < CUT] if part == 'before_2024' else y[y.index >= CUT] if part == '2024_on' else y
            x = fac.loc[y.index, ['Mkt-RF', 'SMB', 'HML', 'RMW', 'CMA', 'Mom']]
            b, t, r2 = newey_west(y.values, x.values)
            out['factor_regression'][f'{label}:{part}'] = {
                'months': len(y), 'first': str(y.index[0].date()), 'last': str(y.index[-1].date()),
                'alpha_annual_pp': float(100 * 12 * b[0]), 't_alpha': float(t[0]), 'r2': r2,
                'betas': {k: float(v) for k, v in zip(x.columns, b[1:])},
                't_betas': {k: float(v) for k, v in zip(x.columns, t[1:])}}
    # Same alpha with market only, to show how much the momentum loading explains.
    y = y_all.loc[START_LIQUID + pd.offsets.MonthEnd(1):]
    for spec, cols in [('market_only', ['Mkt-RF']), ('market_plus_mom', ['Mkt-RF', 'Mom'])]:
        b, t, r2 = newey_west(y.values, fac.loc[y.index, cols].values)
        out['factor_regression'][f'liquid_start:{spec}'] = {'alpha_annual_pp': float(100 * 12 * b[0]),
                                                           't_alpha': float(t[0]), 'r2': r2,
                                                           'betas': {k: float(v) for k, v in zip(cols, b[1:])}}
    ex = mon.loc[START_LIQUID + pd.offsets.MonthEnd(1):]
    yy = (ex['SPMO'] - ex['SPY']).dropna()
    xx = pd.DataFrame({c: ex[c] - ex['SPY'] for c in ['SPYG', 'QQQ', 'RSP']}).loc[yy.index]
    b, t, r2 = newey_west(yy.values, xx.values)
    out['etf_control_regression'] = {'months': len(yy), 'alpha_annual_pp': float(100 * 12 * b[0]), 't_alpha': float(t[0]),
                                     'r2': r2, 'betas': dict(zip(xx.columns, map(float, b[1:]))),
                                     't_betas': dict(zip(xx.columns, map(float, t[1:])))}
    wins = {'liquid_start': (START_LIQUID, END), 'common_live': (pd.Timestamp('2019-05-22'), END),
            'before_2024_liquid': (START_LIQUID, pd.Timestamp('2023-12-29')), 'since_2024': (pd.Timestamp('2023-12-29'), END),
            'protocol_start_stale': (START_PROTOCOL, END)}
    for w, (a, b2) in wins.items():
        out['buy_and_hold'][w] = {t: window(f[t], a, b2) for t in f.columns if f[t].loc[:a].notna().any()}
    return out


def holdings_frame():
    h = pd.read_csv(DATA / 'holdings_tickers.csv', parse_dates=['date'])
    fix = json.loads((HERE / 'ticker_fixes.json').read_text())
    h['ticker'] = h['ticker'].map(lambda t: fix.get(t, t) if isinstance(t, str) else t)
    return h


def prices_table():
    a = pd.read_csv(DATA / 'stock_prices.csv', index_col=0, parse_dates=True)
    b = pd.read_csv(DATA / 'stock_prices_extra.csv', index_col=0, parse_dates=True)
    px = a.combine_first(b)
    return px.loc[:, px.notna().any()]


def at(px, day):
    return px.loc[:day].ffill().iloc[-1]


def rebalance_dates():
    # S&P momentum indices rebalance after the close of the third Friday of March and September.
    out = []
    for y in range(2019, 2027):
        for m in (3, 9):
            fridays = pd.date_range(f'{y}-{m:02d}-01', f'{y}-{m:02d}-28', freq='W-FRI')
            out.append(fridays[2])
    return out


def segments(spmo):
    dates = sorted(pd.Timestamp(d) for d in spmo['date'].unique())
    segs = []
    for i, d0 in enumerate(dates):
        d1 = dates[i + 1] if i + 1 < len(dates) else END
        reb = [r for r in rebalance_dates() if d0 < r < d1]
        if reb and i + 1 < len(dates):
            segs.append((d0, reb[0], d0, 'filing'))
            segs.append((reb[0], d1, d1, 'next_filing_shares'))
        else:
            segs.append((d0, d1, d0, 'filing' if not reb else 'filing_spans_unobserved_rebalance'))
    return segs


def q3(f):
    h = holdings_frame()
    px = prices_table()
    spmo = h[h['fund'] == 'SPMO']
    ivv = h[h['fund'] == 'IVV']
    periods, contrib = [], []
    for d0, d1, src_date, mode in segments(spmo):
        p0, p1 = at(px, d0), at(px, d1)
        s = spmo[spmo['date'] == src_date].copy()
        fresh = s['ticker'].map(lambda t: isinstance(t, str) and t in px.columns
                                and px[t].loc[:d0].last_valid_index() is not None
                                and (d0 - px[t].loc[:d0].last_valid_index()).days < 7 and pd.notna(p1.get(t)))
        if mode == 'next_filing_shares':
            # Post-rebalance weights: next filing's values deflated by each stock's own return since
            # the rebalance; split-safe, unlike filing shares times back-adjusted prices.
            growth = s['ticker'].map(lambda t: p1.get(t) / p0.get(t) if isinstance(t, str) and t in px.columns else np.nan)
            s['w'] = s['valUSD'] / growth.where(fresh, 1.0)
        else:
            s['w'] = s['valUSD']
        s['w'] = s['w'] / s['w'].sum()
        s['r'] = [p1[t] / p0[t] - 1 if ok else np.nan for t, ok in zip(s['ticker'], fresh)]
        s['src'] = np.where(fresh, 'yahoo', 'missing')
        if mode == 'filing':
            # Fallback: N-PORT implied price when still held at the next filing date (= d1).
            nxt = spmo[spmo['date'] == d1].drop_duplicates('cusip').set_index('cusip')
            for idx in s.index[~fresh.values]:
                c = s.at[idx, 'cusip']
                if c in nxt.index and nxt.at[c, 'balance'] > 0 and s.at[idx, 'balance'] > 0:
                    s.at[idx, 'r'] = (nxt.at[c, 'valUSD'] / nxt.at[c, 'balance']) / (s.at[idx, 'valUSD'] / s.at[idx, 'balance']) - 1
                    s.at[idx, 'src'] = 'nport_price'
        q = max(pd.Timestamp(d) for d in ivv['date'].unique() if pd.Timestamp(d) <= d0)
        b = ivv[ivv['date'] == q].copy()
        b['w'] = b['valUSD'] / b['valUSD'].sum()
        pq = at(px, q)
        drift = b['ticker'].map(lambda t: p0.get(t) / pq.get(t) if isinstance(t, str) and t in px.columns
                                and pd.notna(p0.get(t)) and pd.notna(pq.get(t)) else 1.0)
        b['w'] = b['w'] * drift
        b['w'] /= b['w'].sum()
        b['r'] = b['ticker'].map(lambda t: p1[t] / p0[t] - 1 if isinstance(t, str) and t in px.columns
                                 and pd.notna(p0.get(t)) and pd.notna(p1.get(t)) else np.nan)
        spy_r = f['SPY'].loc[:d1].iloc[-1] / f['SPY'].loc[:d0].iloc[-1] - 1
        sw = s.groupby('ticker', dropna=False).agg(w=('w', 'sum'), r=('r', 'first'), name=('name', 'first'))
        bw = b.groupby('ticker', dropna=False).agg(w=('w', 'sum'), r=('r', 'first'), name=('name', 'first'))
        allt = sw.join(bw, how='outer', lsuffix='_s', rsuffix='_b')
        allt['r'] = allt['r_s'].combine_first(allt['r_b'])
        allt['name'] = allt['name_s'].combine_first(allt['name_b'])
        allt = allt.fillna({'w_s': 0, 'w_b': 0})
        allt['active'] = (allt['w_s'] - allt['w_b']) * allt['r']
        allt['selection_vs_spy'] = allt['w_s'] * (allt['r'] - spy_r)
        actual = {t: float(f[t].loc[:d1].iloc[-1] / f[t].loc[:d0].iloc[-1] - 1) for t in ['SPMO', 'SPY', 'IVV']}
        priced = s['r'].notna()
        periods.append({
            'start': str(d0.date()), 'end': str(d1.date()), 'weights': mode, 'holdings_date': str(src_date.date()),
            'ivv_holdings_date': str(q.date()),
            'spmo_actual': actual['SPMO'], 'spy_actual': actual['SPY'], 'ivv_actual': actual['IVV'],
            'spmo_implied': float((s['w'] * s['r']).sum() / s.loc[priced, 'w'].sum()),
            'ivv_implied': float((b['w'] * b['r']).sum() / b.loc[b['r'].notna(), 'w'].sum()),
            'spmo_weight_priced': float(s.loc[priced, 'w'].sum()),
            'spmo_weight_nport_fallback': float(s.loc[s['src'] == 'nport_price', 'w'].sum()),
            'ivv_weight_priced': float(b.loc[b['r'].notna(), 'w'].sum()),
            'spmo_names': int(len(s)), 'spmo_top10_weight': float(s['w'].nlargest(10).sum()),
            'spmo_effective_names': float(1 / (s['w'] ** 2).sum()),
            'ivv_top10_weight': float(b['w'].nlargest(10).sum())})
        allt = allt.reset_index().rename(columns={'index': 'ticker'})
        allt['start'] = str(d0.date())
        contrib.append(allt[['start', 'ticker', 'name', 'w_s', 'w_b', 'r', 'active', 'selection_vs_spy']])
    return pd.DataFrame(periods), pd.concat(contrib, ignore_index=True)


def sector_table(per, con, since, until='9999'):
    sec = json.loads((DATA / 'sectors.json').read_text())
    p = per[(per['start'] >= since) & (per['start'] < until)]
    days = (pd.to_datetime(p['end']) - pd.to_datetime(p['start'])).dt.days.set_axis(p['start'])
    c = con[(con['start'] >= since) & (con['start'] < until)].copy()
    c['sector'] = c['ticker'].map(lambda t: sec.get(t) if isinstance(t, str) else None).fillna('Unlabelled')
    c['days'] = c['start'].map(days)
    g = c.groupby('sector').apply(lambda x: pd.Series({
        'active_sum_pp': 100 * x['active'].sum(), 'selection_vs_spy_sum_pp': 100 * x['selection_vs_spy'].sum(),
        'avg_spmo_weight': (x['w_s'] * x['days']).sum() / days.sum(),
        'avg_ivv_weight': (x['w_b'] * x['days']).sum() / days.sum()}), include_groups=False)
    return {k: {a: float(b) for a, b in v.items()} for k, v in g.sort_values('active_sum_pp', ascending=False).iterrows()}


def factor_contributions(f, start, end=None):
    fac = french('ff5_monthly.zip').join(french('mom_monthly.zip'), how='inner')
    mon = f['SPMO'].resample('ME').last().pct_change()
    spy = f['SPY'].resample('ME').last().pct_change()
    idx = fac.index[(fac.index >= start) & ((fac.index <= end) if end else True)].intersection(mon.dropna().index)
    cols = ['Mkt-RF', 'SMB', 'HML', 'RMW', 'CMA', 'Mom']
    out = {}
    for name, y in [('SPMO', mon), ('SPY', spy)]:
        b, t, r2 = newey_west((y.loc[idx] - fac.loc[idx, 'RF']).values, fac.loc[idx, cols].values)
        out[name] = {'alpha_pp': float(1200 * b[0]),
                     **{k: float(1200 * v * fac.loc[idx, k].mean()) for k, v in zip(cols, b[1:])}}
    out['SPMO_minus_SPY_pp'] = {k: out['SPMO'][k] - out['SPY'][k] for k in out['SPMO']}
    out['months'] = len(idx)
    out['mean_factor_annual_pp'] = {k: float(1200 * fac.loc[idx, k].mean()) for k in cols}
    return out


def topk(per, con, since):
    p = per[per['start'] >= since].copy()
    c = con[con['start'] >= since]
    years = (pd.Timestamp(p['end'].iloc[-1]) - pd.Timestamp(p['start'].iloc[0])).days / 365.25
    total = c.groupby('ticker')[['active', 'selection_vs_spy']].sum().join(c.groupby('ticker')['name'].first())
    out = {'from': p['start'].iloc[0], 'to': p['end'].iloc[-1], 'years': years}

    def ann(series):
        return float(np.prod(1 + series) ** (1 / years) - 1)
    spy = ann(p['spy_actual'])
    out['spmo_actual_cagr'] = ann(p['spmo_actual'])
    out['spy_cagr'] = spy
    out['ivv_actual_cagr'] = ann(p['ivv_actual'])
    out['actual_excess_vs_spy_pp'] = 100 * (out['spmo_actual_cagr'] - spy)
    out['implied_excess_vs_ivv_pp'] = 100 * (ann(p['spmo_implied']) - ann(p['ivv_implied']))
    for key in ['active', 'selection_vs_spy']:
        rank = total.sort_values(key, ascending=False)
        res = {'top': [{'ticker': t, 'name': r['name'], 'sum_pp': float(100 * r[key])} for t, r in rank.head(10).iterrows()]}
        for k in [1, 3, 5, 10]:
            names = rank.index[:k]
            removed = c[c['ticker'].isin(names)].groupby('start')[key].sum().reindex(p['start']).fillna(0).values
            if key == 'active':
                ex = ann(p['spmo_implied'].values - removed) - ann(p['ivv_implied'].values)
            else:
                ex = ann(p['spmo_actual'].values - removed) - spy
            res[f'excess_without_top{k}_pp'] = float(100 * ex)
        out[key] = res
    return out


def q4():
    six = french('size_mom_6_monthly.zip', 'Average Value Weighted Returns -- Monthly')
    ff3 = french('ff3_monthly.zip')
    df = pd.DataFrame({'big_high': six['BIG HiPRIOR'], 'market': ff3['Mkt-RF'] + ff3['RF']}).dropna()
    out = {'first': str(df.index[0].date()), 'last': str(df.index[-1].date())}
    for drag in [0, .01, .02]:
        bh = df['big_high'] - drag / 12
        yr = pd.DataFrame({'bh': (1 + bh).groupby(df.index.year).prod() - 1,
                           'mkt': (1 + df['market']).groupby(df.index.year).prod() - 1})
        yr = yr[yr.index <= 2025]
        decades = {}
        for a in range(1927, 2027, 10):
            sl = df.loc[f'{a}':f'{a + 9}']
            if len(sl) < 60:
                continue
            n = len(sl) / 12
            decades[f'{a}-{min(a + 9, 2026)}'] = float(100 * ((1 + bh.loc[sl.index]).prod() ** (1 / n) - (1 + sl['market']).prod() ** (1 / n)))
        wealth = (1 + bh).cumprod() / (1 + df['market']).cumprod()
        rd = relative_drawdown(wealth, pd.Series(1.0, index=wealth.index))
        rolling = {}
        for n in [3, 5, 10]:
            r = ((1 + bh).rolling(12 * n).apply(np.prod, raw=True) / (1 + df['market']).rolling(12 * n).apply(np.prod, raw=True)) ** (1 / n) - 1
            r = r.dropna()
            rolling[f'{n}y'] = {'windows': len(r), 'share_ahead': float((r > 0).mean()),
                                'share_ahead_by_3pp': float((r > .03).mean())}
        n = len(df) / 12
        out[f'drag_{int(drag * 100)}pct'] = {
            'annualized_excess_pp': float(100 * ((1 + bh).prod() ** (1 / n) - (1 + df['market']).prod() ** (1 / n))),
            'calendar_years': len(yr), 'years_ahead': int((yr['bh'] > yr['mkt']).sum()),
            'decades_excess_pp': decades,
            'decades_at_least_1pp': int(sum(v >= 1 for v in decades.values())),
            'relative_drawdown': rd, 'rolling_relative': rolling,
            'since_2016_excess_pp': float(100 * ((1 + bh.loc['2016':]).prod() ** (12 / len(bh.loc['2016':])) - (1 + df['market'].loc['2016':]).prod() ** (12 / len(bh.loc['2016':])))),
            'before_2024_since_2016_excess_pp': float(100 * ((1 + bh.loc['2016':'2023']).prod() ** (1 / 8) - (1 + df['market'].loc['2016':'2023']).prod() ** (1 / 8)))}
    yr = pd.DataFrame({'big_high': (1 + df['big_high']).groupby(df.index.year).prod() - 1,
                       'market': (1 + df['market']).groupby(df.index.year).prod() - 1})
    out['annual_recent'] = {str(y): {k: float(v) for k, v in r.items()} for y, r in yr.loc[2014:].iterrows()}
    return out, df


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    f = load_funds()
    res = {'protocol_sha256': __import__('hashlib').sha256((HERE / 'protocol.json').read_bytes()).hexdigest()}
    res['Q1'] = q1(f)
    res['Q2'] = q2(f)
    per, con = q3(f)
    per.to_csv(OUT / 'holding_periods.csv', index=False)
    con.to_csv(OUT / 'stock_contributions.csv', index=False)
    res['Q3'] = {'periods': len(per),
                 'fidelity': {'spmo_mean_abs_gap_pp': float(100 * (per['spmo_implied'] - per['spmo_actual']).abs().mean()),
                              'spmo_max_abs_gap_pp': float(100 * (per['spmo_implied'] - per['spmo_actual']).abs().max()),
                              'ivv_mean_abs_gap_pp': float(100 * (per['ivv_implied'] - per['ivv_actual']).abs().mean()),
                              'min_spmo_weight_priced': float(per['spmo_weight_priced'].min()),
                              'min_ivv_weight_priced': float(per['ivv_weight_priced'].min())},
                 'since_2023_11_30': topk(per, con, '2023-11-30'),
                 'before_2023_11_30': topk(per[per['start'] < '2023-11-30'], con[con['start'] < '2023-11-30'], '2019-11-30'),
                 'clean_segments_only_fidelity': {'mean_abs_gap_pp': float(100 * (per.loc[per['weights'] != 'filing_spans_unobserved_rebalance', 'spmo_implied'] - per.loc[per['weights'] != 'filing_spans_unobserved_rebalance', 'spmo_actual']).abs().mean())},
                 'all': topk(per, con, '2019-11-30')}
    res['Q3']['sectors_since_2023_11_30'] = sector_table(per, con, '2023-11-30')
    res['Q3']['sectors_before_2023_11_30'] = sector_table(per, con, '2019-11-30', '2023-11-30')
    res['Q2']['factor_contributions_2024_on'] = factor_contributions(f, pd.Timestamp('2024-01-31'))
    res['Q2']['factor_contributions_2018_2023'] = factor_contributions(f, pd.Timestamp('2018-01-31'), pd.Timestamp('2023-12-31'))
    q4res, fr = q4()
    res['Q4'] = q4res
    mon = f['SPMO'].resample('ME').last().pct_change()
    j = pd.DataFrame({'spmo': mon, 'french': fr['big_high']}).loc['2018':].dropna()
    res['Q4']['spmo_vs_french_big_high_monthly_corr_2018_on'] = float(j.corr().iloc[0, 1])
    (OUT / 'results.json').write_text(json.dumps(res, indent=2, allow_nan=False, default=str))
    print(json.dumps(res, indent=1, default=str)[:200])


if __name__ == '__main__':
    main()
