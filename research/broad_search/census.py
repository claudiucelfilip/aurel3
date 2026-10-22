"""Track A: live-fund census against SPY with a selection-aware bootstrap. See protocol.json track_A_live_fund_census."""
import json
import zipfile
from pathlib import Path
import numpy as np
import pandas as pd
import common as C

START, END, MID = '2016-10-14', '2026-10-16', '2021-10-15'
SPMO_DATA = C.ROOT / 'data' / 'spmo_diagnostic'


def french(name):
    with zipfile.ZipFile(SPMO_DATA / name) as z:
        lines = z.read(z.namelist()[0]).decode('latin1').splitlines()
    head = next(i for i, l in enumerate(lines) if l.strip().startswith(','))
    cols = [c.strip() for c in lines[head].split(',')][1:]
    rows = [[x.strip() for x in l.split(',')] for l in lines[head + 1:]]
    rows = [r for r in rows if len(r[0]) == 6 and r[0].isdigit()]
    rows = rows[:next((i for i in range(1, len(rows)) if rows[i][0] < rows[i - 1][0]), len(rows))]
    idx = pd.to_datetime([r[0] for r in rows], format='%Y%m') + pd.offsets.MonthEnd(0)
    return pd.DataFrame([r[1:len(cols) + 1] for r in rows], index=idx, columns=cols).astype(float) / 100


def load():
    prices = {}
    for p in (C.DATA / 'etf_prices').glob('*.csv'):
        s = pd.read_csv(p, index_col=0, parse_dates=True).iloc[:, 0]
        if s.loc[:START].notna().any() and s.loc['2026-10-09':END].notna().any():
            prices[p.stem] = s
    return pd.DataFrame(prices).loc[START:END]


def stationary_bootstrap_max_t(ex, draws=2000, mean_block=6, seed=0):
    """Null: every fund's true mean excess is zero. Resample months jointly (keeps cross-fund correlation)."""
    rng = np.random.default_rng(seed)
    x = ex.values - np.nanmean(ex.values, axis=0)
    n = len(x)
    out = np.empty(draws)
    for d in range(draws):
        idx, i = [], rng.integers(n)
        while len(idx) < n:
            idx.append(i)
            i = rng.integers(n) if rng.random() < 1 / mean_block else (i + 1) % n
        s = x[idx]
        m, sd = np.nanmean(s, axis=0), np.nanstd(s, axis=0, ddof=1)
        out[d] = np.nanmax(m / (sd / np.sqrt(np.sum(~np.isnan(s), axis=0))))
    return out


def main():
    px = load()
    spy = px['SPY']
    cagr = {t: C.cagr(px[t].dropna()) for t in px}
    years = (pd.Timestamp(END) - pd.Timestamp(START)).days / 365.25
    net = {t: ((1 + cagr[t]) ** years * (1 - .001) / (1 + .001)) ** (1 / years) - 1 for t in cagr}
    spy_net = net['SPY']
    mon = px.resample('ME').last().pct_change(fill_method=None).iloc[1:]
    ex = mon.sub(mon['SPY'], axis=0).drop(columns='SPY')
    t_simple = ex.mean() / (ex.std(ddof=1) / np.sqrt(ex.notna().sum()))
    null = stationary_bootstrap_max_t(ex)
    crit = float(np.quantile(null, .95))
    fac = french('ff5_monthly.zip').join(french('mom_monthly.zip'), how='inner')
    rows = []
    for t in ex.columns:
        a, b = px[t].loc[:MID].dropna(), px[t].loc[MID:].dropna()
        dd = float(1 - (px[t] / px[t].cummax()).min())
        row = {'ticker': t, 'cagr': cagr[t], 'excess_pp': 100 * (net[t] - spy_net), 't': float(t_simple[t]),
               'first_half_pp': 100 * (C.cagr(a) - C.cagr(spy.loc[a.index])),
               'second_half_pp': 100 * (C.cagr(b) - C.cagr(spy.loc[b.index])), 'dd': dd}
        rows.append(row)
    df = pd.DataFrame(rows).set_index('ticker')
    spy_dd = float(1 - (spy / spy.cummax()).min())
    df['A1'] = df['excess_pp'] >= 3
    df['A2'] = df['t'] >= crit
    df['A3'] = (df['first_half_pp'] > 0) & (df['second_half_pp'] > 0)
    df['A4'] = df['dd'] <= spy_dd + .10
    # Factor alpha only where it can matter (A1 met), to keep the run light.
    cols = ['Mkt-RF', 'SMB', 'HML', 'RMW', 'CMA', 'Mom']
    df['alpha_pp'], df['alpha_t'] = np.nan, np.nan
    for t in df.index[df['A1']]:
        y = (mon[t] - fac['RF']).dropna()
        y = y.loc[y.index.intersection(fac.index)]
        X = np.column_stack([np.ones(len(y)), fac.loc[y.index, cols].values])
        beta = np.linalg.lstsq(X, y.values, rcond=None)[0]
        e = y.values - X @ beta
        xe = X * e[:, None]
        S = xe.T @ xe
        for l in range(1, 7):
            g = xe[l:].T @ xe[:-l]
            S += (1 - l / 7) * (g + g.T)
        inv = np.linalg.inv(X.T @ X)
        df.loc[t, 'alpha_pp'] = 1200 * beta[0]
        df.loc[t, 'alpha_t'] = beta[0] / np.sqrt((inv @ S @ inv)[0, 0])
    df['A5'] = (df['alpha_pp'] >= 2) & (df['alpha_t'] >= 2)
    df['passed'] = df[['A1', 'A2', 'A3', 'A4', 'A5']].all(axis=1)
    names = pd.read_csv(C.DATA / 'etf_universe.csv').set_index('Symbol')['Security Name']
    df['name'] = [names.get(t.replace('-', '.'), names.get(t, '')) for t in df.index]
    out = {'funds_with_full_history': int(len(df)), 'spy_net_cagr': spy_net, 'spy_dd': spy_dd,
           'bootstrap_max_t_95': crit, 'counts': {k: int(df[k].sum()) for k in ['A1', 'A2', 'A3', 'A4', 'A5', 'passed']},
           'top_by_excess': df.sort_values('excess_pp', ascending=False).head(40).reset_index().to_dict('records')}
    df.to_csv(C.OUT / 'census_table.csv')
    C.OUT.mkdir(parents=True, exist_ok=True)
    (C.OUT / 'census_results.json').write_text(json.dumps(out, indent=2, default=float))
    (Path(__file__).resolve().parent / 'census_snapshot.json').write_text(json.dumps(out, indent=2, default=float))
    print(json.dumps({k: v for k, v in out.items() if k != 'top_by_excess'}, indent=1, default=float))
    print(df.sort_values('excess_pp', ascending=False).head(30)[['name', 'excess_pp', 't', 'first_half_pp', 'second_half_pp', 'dd', 'alpha_pp', 'alpha_t', 'passed']].round(2).to_string())


if __name__ == '__main__':
    main()
