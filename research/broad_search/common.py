"""Shared metrics and holdout rules (H1-H5 in protocol.json) for tracks B and C."""
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / 'data' / 'broad_search'
OUT = ROOT / 'data' / 'gold_grid' / 'results' / 'broad_search'
END = '2026-10-16'
SPLIT = '2022-12-31'


def nw_t(x, lags=6):
    x = np.asarray(x, float)
    e = x - x.mean()
    s = e @ e / len(x)
    for l in range(1, lags + 1):
        s += 2 * (1 - l / (lags + 1)) * (e[l:] @ e[:-l]) / len(x)
    return float(x.mean() / np.sqrt(s / len(x)))


def cagr(eq):
    eq = eq.dropna()
    return float((eq.iloc[-1] / eq.iloc[0]) ** (365.25 / (eq.index[-1] - eq.index[0]).days) - 1)


def metrics(eq, spy):
    """eq and spy are value series on the same daily index."""
    spy = spy.reindex(eq.index).ffill()
    d = eq.pct_change().dropna()
    m = eq.resample('ME').last().pct_change().dropna() - spy.resample('ME').last().pct_change().dropna()
    halves = {}
    for label, a, b in [('first_half', None, SPLIT), ('second_half', SPLIT, None)]:
        e, s = eq.loc[a:b], spy.loc[a:b]
        if len(e) > 60:
            halves[label] = 100 * (cagr(e) - cagr(s))
    return {'from': str(eq.index[0].date()), 'to': str(eq.index[-1].date()),
            'cagr': cagr(eq), 'spy_cagr': cagr(spy), 'excess_pp': 100 * (cagr(eq) - cagr(spy)),
            't_nw6': nw_t(m.dropna()), 'sharpe': float(d.mean() / d.std() * np.sqrt(252)),
            'dd': float(1 - (eq / eq.cummax()).min()), 'spy_dd': float(1 - (spy / spy.cummax()).min()),
            **halves}


def verdict(dev, hold):
    r = {'H1': hold['excess_pp'] >= 3, 'H2': hold['t_nw6'] >= 2.2,
         'H3': hold.get('first_half', -1) > 0 and hold.get('second_half', -1) > 0,
         'H4': hold['dd'] <= hold['spy_dd'] + .10, 'H5': dev['excess_pp'] >= 3}
    r['passed'] = all(r.values())
    return r


def record_choice(track, choice, dev):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f'{track}_choice.json').write_text(json.dumps({'choice': choice, 'development': dev}, indent=2))


def save(track, out):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f'{track}_results.json').write_text(json.dumps(out, indent=2, default=float))
    (Path(__file__).resolve().parent / f'{track}_snapshot.json').write_text(json.dumps(out, indent=2, default=float))


def show(tag, choice, dev, hold, res):
    for k in dev:
        d, h = dev[k], hold[k]
        print(f"{tag} {k:14s}{'*' if k == choice else ' '} dev ex {d['excess_pp']:+6.1f} sh {d['sharpe']:.2f} | "
              f"hold cagr {100 * h['cagr']:5.1f} vs SPY {100 * h['spy_cagr']:5.1f} ex {h['excess_pp']:+5.1f} t {h['t_nw6']:+.2f} "
              f"halves {h.get('first_half', float('nan')):+.1f}/{h.get('second_half', float('nan')):+.1f} dd {100 * h['dd']:.0f}/{100 * h['spy_dd']:.0f}")
    print(tag, 'rules', res)
