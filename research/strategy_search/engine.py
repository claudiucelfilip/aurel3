"""Evaluate registered candidates against protocol.json pass rules. Monthly, long-only, cash-funded."""
import json
import zipfile
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DATA = ROOT / 'data' / 'strategy_search'
OUT = ROOT / 'data' / 'gold_grid' / 'results' / 'strategy_search'
SIDE = .001


def french(name, marker='Value Weighted Returns -- Monthly'):
    with zipfile.ZipFile(DATA / f'{name}.zip') as z:
        lines = z.read(z.namelist()[0]).decode('latin1').splitlines()
    start = next((i for i, l in enumerate(lines) if marker in l), 0) if marker else 0
    head = next(i for i in range(start, len(lines)) if lines[i].strip().startswith(','))
    cols = [c.strip() for c in lines[head].split(',')][1:]
    rows = []
    for l in lines[head + 1:]:
        p = [x.strip() for x in l.split(',')]
        if len(p[0]) != 6 or not p[0].isdigit():
            break
        rows.append(p)
    idx = pd.to_datetime([r[0] for r in rows], format='%Y%m') + pd.offsets.MonthEnd(0)
    df = pd.DataFrame([r[1:len(cols) + 1] for r in rows], index=idx, columns=cols).astype(float)
    return df.mask(df <= -99.99) / 100


def market():
    ff = french('F-F_Research_Data_Factors_CSV', marker=None)
    return ff['Mkt-RF'] + ff['RF'], ff['RF']


def etf_monthly():
    px = pd.read_csv(DATA / 'etf_adj_close.csv', index_col=0, parse_dates=True)
    px = px.join(pd.read_csv(DATA / 'etf_adj_close_b2.csv', index_col=0, parse_dates=True), how='outer')
    return px.resample('ME').last().pct_change(fill_method=None)


def turnover_cost(weights):
    """weights: DataFrame of target weights per month (held during that month). Returns monthly cost."""
    w = weights.fillna(0)
    return w.diff().abs().sum(axis=1).fillna(w.iloc[0].abs().sum()) * SIDE


def newey_west_t(x, lags=12):
    x = np.asarray(x, float)
    e = x - x.mean()
    s = e @ e / len(x)
    for l in range(1, lags + 1):
        s += 2 * (1 - l / (lags + 1)) * (e[l:] @ e[:-l]) / len(x)
    return float(x.mean() / np.sqrt(s / len(x)))


def cagr(r):
    r = r.dropna()
    return float((1 + r).prod() ** (12 / len(r)) - 1)


def max_dd(r):
    w = (1 + r.dropna()).cumprod()
    return float(1 - (w / w.cummax()).min())


def evaluate(strat, mkt, oos_start, etf=None):
    j = pd.DataFrame({'s': strat, 'm': mkt}).dropna()
    oos = j.loc[oos_start:]
    rec = j.loc['2007-01':]
    ins = j.loc[:pd.Timestamp(oos_start) - pd.offsets.MonthEnd(1)]
    years = len(oos) / 12
    res = {
        'in_sample': {'from': str(ins.index[0].date()) if len(ins) else None, 'excess_pp': 100 * (cagr(ins['s']) - cagr(ins['m'])) if len(ins) > 12 else None},
        'oos': {'from': str(oos.index[0].date()), 'to': str(oos.index[-1].date()), 'years': years,
                'cagr': cagr(oos['s']), 'market_cagr': cagr(oos['m']),
                'excess_pp': 100 * (cagr(oos['s']) - cagr(oos['m'])),
                't_nw12': newey_west_t(oos['s'] - oos['m']),
                'dd': max_dd(oos['s']), 'market_dd': max_dd(oos['m'])},
        'recent_2007_excess_pp': 100 * (cagr(rec['s']) - cagr(rec['m'])),
        'decades': {f'{a}-{a + 9}': 100 * (cagr(j.loc[f'{a}':f'{a + 9}', 's']) - cagr(j.loc[f'{a}':f'{a + 9}', 'm']))
                    for a in range(1930, 2030, 10) if len(j.loc[f'{a}':f'{a + 9}']) >= 60},
    }
    o = res['oos']
    res['P1'] = o['excess_pp'] >= 3
    res['P2'] = o['t_nw12'] >= 2.64
    res['P3'] = res['recent_2007_excess_pp'] >= 0
    res['P4'] = o['dd'] <= o['market_dd'] + .10
    res['min_years_ok'] = years >= 14
    if etf is not None:
        res['etf'] = etf
        res['P5'] = etf['cagr'] >= etf['spy_cagr']
    else:
        res['P5'] = False
        res['etf'] = None
    res['passed'] = all(res[k] for k in ['P1', 'P2', 'P3', 'P4', 'P5', 'min_years_ok'])
    return res


def etf_eval(r, spy, gld, label):
    # P5 uses the ETF's own live history vs SPY; gold and the 50/50 mix only where GLD exists.
    a = pd.DataFrame({'s': r, 'spy': spy}).dropna()
    g = pd.DataFrame({'s': r, 'spy': spy, 'gld': gld}).dropna()
    mix = .5 * g['spy'] + .5 * g['gld']
    return {'label': label, 'from': str(a.index[0].date()), 'to': str(a.index[-1].date()), 'cagr': cagr(a['s']),
            'spy_cagr': cagr(a['spy']), 'dd': max_dd(a['s']), 'spy_dd': max_dd(a['spy']),
            'gold_window_from': str(g.index[0].date()), 'gold_window_cagr': cagr(g['s']),
            'gld_cagr': cagr(g['gld']), 'mix_cagr': cagr(mix)}


def top_k_rotation(rets, k, lookback, fee_annual=0.0):
    """Hold top-k by trailing `lookback`-month total return, equal weight, rebalanced monthly; signal uses data to t-1."""
    trail = (1 + rets).rolling(lookback).apply(np.prod, raw=True) - 1
    rank = trail.shift(1).rank(axis=1, ascending=False, method='first')
    w = (rank <= k).astype(float).div(k).where(trail.shift(1).notna().sum(axis=1) >= k, np.nan)
    w = w.dropna(how='all')
    gross = (w * rets.loc[w.index]).sum(axis=1)
    return gross - turnover_cost(w) - fee_annual / 12, w


def candidates():
    mkt, rf = market()
    e = etf_monthly()
    spy, gld = e['SPY'], e['GLD']
    out = {}

    ind = french('12_Industry_Portfolios_CSV')
    s, _ = top_k_rotation(ind, 3, 6, .0015)
    sec = e[['XLB', 'XLE', 'XLF', 'XLI', 'XLK', 'XLP', 'XLU', 'XLV', 'XLY']].loc['1999-01':]
    se, _ = top_k_rotation(sec, 3, 6)
    out['C1_industry_momentum'] = (s, '1995-08', etf_eval(se, spy, gld, 'Top 3 of 9 SPDR sectors by 6-month return'))

    bm = french('6_Portfolios_2x3_CSV')
    out['C2_small_value'] = (bm['SMALL HiBM'] - .01 / 12, '1991-01', etf_eval(e['IJS'], spy, gld, 'IJS'))

    op = french('6_Portfolios_ME_OP_2x3_CSV')
    out['C3_big_profitable'] = (op['BIG HiOP'] - .005 / 12, '2011-01', etf_eval(e['QUAL'], spy, gld, 'QUAL'))

    inv = french('6_Portfolios_ME_INV_2x3_CSV')
    out['C4_big_conservative_investment'] = (inv['BIG LoINV'] - .005 / 12, '1997-01', None)

    months = mkt.index.month
    hold = pd.Series(np.isin(months, [11, 12, 1, 2, 3, 4]), index=mkt.index)
    switch = hold.ne(hold.shift()).astype(float) * 2 * SIDE
    hw = (mkt.where(hold, rf) - switch)
    eh = pd.DataFrame({'spy': spy, 'bil': e['BIL']}).dropna()
    hold_e = pd.Series(np.isin(eh.index.month, [11, 12, 1, 2, 3, 4]), index=eh.index)
    he = eh['spy'].where(hold_e, eh['bil']) - hold_e.ne(hold_e.shift()).astype(float) * 2 * SIDE
    out['C5_halloween'] = (hw, '1998-09', etf_eval(he, spy, gld, 'SPY Nov-Apr, BIL May-Oct'))

    dev = french('Developed_ex_US_3_Factors_CSV', marker=None)
    exus = dev['Mkt-RF'] + dev['RF']
    out['C6_global_dual_momentum'] = (dual_momentum(mkt, exus, rf, rf), '2012-01',
                                      etf_eval(dual_momentum(spy, e['EFA'], e['BIL'].fillna(rf.reindex(e.index)), e['AGG']),
                                               spy, gld, 'SPY / EFA / AGG dual momentum'))
    mom = french('6_Portfolios_ME_Prior_12_2_CSV')
    out['C7_value_momentum_blend'] = (.5 * bm['BIG HiBM'] + .5 * mom['BIG HiPRIOR'] - .0125 / 12, '2011-08', None)
    out['C8_small_cap_momentum'] = (mom['SMALL HiPRIOR'] - .025 / 12, '1990-01', etf_eval(e['XSMO'], spy, gld, 'XSMO'))
    ni = french('Portfolios_Formed_on_NI_CSV')
    out['C9_net_repurchasers'] = (ni['< 0'] - .005 / 12, '2004-01', etf_eval(e['PKW'], spy, gld, 'PKW'))
    out['C10_market_trend_filter'] = (trend(mkt, rf), '2006-01',
                                      etf_eval(trend(spy, e['BIL'].fillna(rf.reindex(e.index))), spy, gld, 'SPY / BIL 10-month trend'))
    ee = pd.DataFrame({'a': e['IJS'], 'b': e['XSMO']}).dropna()
    out['C11_small_value_momentum_blend'] = (.5 * bm['SMALL HiBM'] + .5 * mom['SMALL HiPRIOR'] - .0175 / 12, '2011-08',
                                             etf_eval(.5 * ee['a'] + .5 * ee['b'] - .5 * (ee['a'] - ee['b']).abs() * SIDE, spy, gld, '50% IJS + 50% XSMO'))
    return out, mkt


def trend(r, cash):
    j = pd.DataFrame({'r': r, 'c': cash}).dropna()
    level = (1 + j['r']).cumprod()
    on = (level > level.rolling(10).mean()).shift(1)
    on = on[level.rolling(10).mean().shift(1).notna()].astype(bool)
    out = j.loc[on.index, 'r'].where(on, j.loc[on.index, 'c'])
    return out - on.ne(on.shift()).astype(float).iloc[1:].reindex(on.index, fill_value=0) * 2 * SIDE


def dual_momentum(us, intl, cash, safe):
    j = pd.DataFrame({'us': us, 'intl': intl, 'cash': cash, 'safe': safe}).dropna()
    t = (1 + j).rolling(12).apply(np.prod, raw=True).shift(1) - 1
    pick = np.where(t['us'] > t['cash'], np.where(t['us'] >= t['intl'], 'us', 'intl'), 'safe')
    pick = pd.Series(pick, index=j.index)[t['us'].notna()]
    w = pd.get_dummies(pick).astype(float).reindex(columns=['us', 'intl', 'safe'], fill_value=0)
    r = (w * j.loc[w.index, ['us', 'intl', 'safe']]).sum(axis=1)
    return r - turnover_cost(w)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    prot = json.loads((HERE / 'protocol.json').read_text())
    cands, mkt = candidates()
    res = {}
    for name, (s, oos, etf) in cands.items():
        res[name] = evaluate(s, mkt, oos, etf)
    (OUT / 'results.json').write_text(json.dumps(res, indent=2, default=float))
    for n, r in res.items():
        o = r['oos']
        print(f"{n:32s} OOS {o['from'][:7]} {o['years']:.0f}y  ex {o['excess_pp']:+.2f}  t {o['t_nw12']:.2f}  "
              f"rec07 {r['recent_2007_excess_pp']:+.2f}  dd {o['dd']:.2f}/{o['market_dd']:.2f}  "
              f"insample {r['in_sample']['excess_pp'] if r['in_sample']['excess_pp'] is None else round(r['in_sample']['excess_pp'], 2)}  "
              f"P {[k for k in ['P1', 'P2', 'P3', 'P4', 'P5'] if r[k]]} PASS={r['passed']}")
        if r['etf']:
            x = r['etf']
            print(f"   ETF {x['label']} {x['from'][:7]}: {x['cagr']:.3f} vs SPY {x['spy_cagr']:.3f} dd {x['dd']:.2f}/{x['spy_dd']:.2f} | from {x['gold_window_from'][:7]}: {x['gold_window_cagr']:.3f} GLD {x['gld_cagr']:.3f} mix {x['mix_cagr']:.3f}")


if __name__ == '__main__':
    main()
