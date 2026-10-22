"""Track G: equal-weighted long legs of Lewellen's characteristics, from OSAP decile portfolios. See protocol.json track_G_lewellen_composite."""
import json
import sys
import zipfile
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import common as C  # noqa: E402

OSAP = C.DATA / 'osap'
SETS = {'3': ['Size', 'BM', 'Mom12m'],
        '7': ['Size', 'BM', 'Mom12m', 'Accruals', 'roaq', 'AssetGrowth', 'ShareIss1Y'],
        '15': ['Size', 'BM', 'Mom12m', 'Accruals', 'roaq', 'AssetGrowth', 'ShareIss1Y', 'ShareIss5Y', 'LRreversal', 'Beta',
               'RealizedVol', 'VolMkt', 'Leverage', 'SP']}
MONTHLY = {'Mom12m', 'roaq', 'LRreversal', 'Beta', 'RealizedVol'}
SIDE, TURN_ANNUAL, TURN_MONTHLY = .001, .05, .25
DEV = ('1974-01-31', '2013-12-31')
HOLD = ('2014-01-31', '2024-12-31')
SPLIT = '2018-12-31'


def market():
    with zipfile.ZipFile(C.ROOT / 'data' / 'spmo_diagnostic' / 'ff5_monthly.zip') as z:
        lines = z.read(z.namelist()[0]).decode('latin1').splitlines()
    rows = [l.split(',') for l in lines if len(l) > 6 and l[:6].isdigit() and l[6] == ',']
    rows = rows[:next((i for i in range(1, len(rows)) if rows[i][0] < rows[i - 1][0]), len(rows))]
    df = pd.DataFrame(rows).set_index(0).astype(float) / 100
    df.index = pd.to_datetime(df.index, format='%Y%m') + pd.offsets.MonthEnd(0)
    return df[1] + df[6]  # Mkt-RF + RF


def long_legs(universe):
    d = pd.read_parquet(OSAP / f'{universe}.parquet')
    d = d[d['port'] != 'LS']
    # The liquidity-screened file keeps each paper's own quantile count, so the long leg is the top port, not always '10'.
    top = d.groupby('signalname')['port'].transform('max')
    d = d[d['port'] == top]
    d['date'] = pd.to_datetime(d['date']) + pd.offsets.MonthEnd(0)
    return d.pivot(index='date', columns='signalname', values='ret') / 100


def composite(legs, names, cost_mult=1.0):
    r = legs[names]
    cost = sum((TURN_MONTHLY if n in MONTHLY else TURN_ANNUAL) for n in names) / len(names) * 2 * SIDE * cost_mult
    return r.mean(axis=1).where(r.notna().sum(axis=1) >= max(2, len(names) * 2 // 3)) - cost


def metrics(ret, mkt, a, b):
    r, m = ret.loc[a:b].dropna(), mkt.loc[a:b]
    m = m.reindex(r.index)
    eq, meq = (1 + r).cumprod(), (1 + m).cumprod()
    cagr = lambda e: float(e.iloc[-1] ** (12 / len(e)) - 1)
    out = {'from': str(r.index[0].date()), 'to': str(r.index[-1].date()), 'cagr': cagr(eq), 'spy_cagr': cagr(meq),  # benchmark is the French market here
           'excess_pp': 100 * (cagr(eq) - cagr(meq)), 't_nw6': C.nw_t((r - m).values), 'sharpe': float(r.mean() / r.std() * np.sqrt(12)),
           'dd': float(1 - (eq / eq.cummax()).min()), 'spy_dd': float(1 - (meq / meq.cummax()).min())}
    for label, s, e in [('first_half', None, SPLIT), ('second_half', SPLIT, None)]:
        rr, mm = r.loc[s:e], m.loc[s:e]
        if len(rr) > 24:
            out[label] = 100 * (cagr((1 + rr).cumprod()) - cagr((1 + mm).cumprod()))
    return out


def main():
    mkt = market()
    legs = {u: long_legs(u) for u in ('deciles_vw', 'ex_nyse_p20_me')}
    configs = {f'{u}_{k}': (u, k) for u in legs for k in SETS}
    dev = {name: metrics(composite(legs[u], SETS[k]), mkt, *DEV) for name, (u, k) in configs.items()}
    choice = max(dev, key=lambda n: dev[n]['sharpe'])
    C.record_choice('track_g', choice, dev)
    hold = {name: metrics(composite(legs[u], SETS[k]), mkt, *HOLD) for name, (u, k) in configs.items()}
    sens = {f'cost_x{m}': metrics(composite(legs[configs[choice][0]], SETS[configs[choice][1]], m), mkt, *HOLD)['excess_pp'] for m in (0, 1, 2)}
    per_signal = {}
    for n in SETS['15']:
        per_signal[n] = {'dev_excess_pp': metrics(legs['ex_nyse_p20_me'][n], mkt, *DEV)['excess_pp'],
                         'hold_excess_pp': metrics(legs['ex_nyse_p20_me'][n], mkt, *HOLD)['excess_pp']}
    res = C.verdict(dev[choice], hold[choice])
    C.save('track_g', {'choice': choice, 'development': dev, 'holdout': hold, 'cost_sensitivity_holdout_excess_pp': sens,
                       'per_signal_long_leg_vs_market_ex_nyse_p20': per_signal, 'rules': res})
    C.show('G', choice, dev, hold, res)
    print('cost sensitivity', {k: round(v, 1) for k, v in sens.items()})
    print(pd.DataFrame(per_signal).T.round(1).to_string())


if __name__ == '__main__':
    main()
