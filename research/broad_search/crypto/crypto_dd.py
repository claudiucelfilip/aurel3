"""Track J: crypto with drawdown control. J1 BTC trend; J2 aurel2-crypto rules on BTC/ETH; J3 BTC vol targeting. See protocol.json track_J_crypto_drawdown_control."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import common as C  # noqa: E402

D = C.DATA / 'crypto'
COST = {'BTC': .0025, 'ETH': .0025, 'BIL': .001}


def load():
    px = pd.concat([pd.read_csv(D / f'{s}.csv', index_col=0, parse_dates=True).iloc[:, 0].rename(n)
                    for s, n in [('BTC-USD', 'BTC'), ('ETH-USD', 'ETH'), ('BIL', 'BIL')]], axis=1)
    px = px.loc['2014-09-17':C.END]
    px['BIL'] = px['BIL'].ffill()           # crypto trades 7 days; BIL marks flat on weekends
    spy = pd.read_csv(C.DATA / 'flows' / 'SPY.csv', index_col=0, parse_dates=True).iloc[:, 0]
    return px, spy


def equity(px, w, start, end):
    """w: weights decided at each close, applied from the next close; remainder in BIL."""
    idx = px.loc[start:end].index
    w = w.reindex(index=idx, columns=['BTC', 'ETH']).fillna(0).clip(0, 1)
    w['BIL'] = (1 - w.sum(axis=1)).clip(lower=0)
    held = w.shift(1).fillna(0)
    r = px.pct_change(fill_method=None).reindex(idx).fillna(0)
    cost = sum(held[c].diff().abs().fillna(0) * COST[c] for c in held.columns)
    return (1 + (held * r).sum(axis=1) - cost).cumprod()


def btc_trend(px, n):
    on = px['BTC'] > px['BTC'].rolling(n).mean()
    return pd.DataFrame({'BTC': on.astype(float)})


def a2c_rules(px, L, stop=.10):
    """Weekly pick of the stronger coin if its L-day return > 0; daily exit if all negative; 10% trailing stop to cash until next weekly signal."""
    mom = px[['BTC', 'ETH']].pct_change(L)
    weekly = px.index.dayofweek == 0
    hold, hwm, out = None, 0.0, []
    for i, d in enumerate(px.index):
        m = mom.loc[d]
        if hold is not None:
            p = px.at[d, hold]
            hwm = max(hwm, p)
            if p < hwm * (1 - stop) or (m.dropna() <= 0).all():
                hold = None
        if weekly[i]:
            best = m.dropna().idxmax() if m.notna().any() else None
            if best is not None and m[best] > 0:
                if best != hold:
                    hold, hwm = best, px.at[d, best]
            else:
                hold = None
        out.append({'BTC': float(hold == 'BTC'), 'ETH': float(hold == 'ETH')})
    return pd.DataFrame(out, index=px.index)


def vol_target(px, target, trend):
    vol = px['BTC'].pct_change().rolling(30).std() * np.sqrt(365)
    w = (target / vol).clip(upper=1)
    if trend:
        w = w.where(px['BTC'] > px['BTC'].rolling(200).mean(), 0)
    w = w.where(px.index.dayofweek == 0).ffill().fillna(0)   # weekly rebalance
    return pd.DataFrame({'BTC': w})


def run_family(tag, cfgs, px, spy):
    dev = {k: C.metrics(e := equity(px, w, '2015-01-01', '2018-12-31'), spy.reindex(e.index).ffill().bfill()) for k, w in cfgs.items()}
    choice = max(dev, key=lambda k: dev[k]['sharpe'])
    C.record_choice(f'track_j_{tag}', choice, dev)
    hold = {k: C.metrics(e := equity(px, w, '2018-12-31', C.END), spy.reindex(e.index).ffill().bfill()) for k, w in cfgs.items()}
    res = C.verdict(dev[choice], hold[choice])
    C.show(f'J {tag}', choice, dev, hold, res)
    tim = {k: float(w.reindex(px.loc['2019':].index).fillna(0).sum(axis=1).gt(0).mean()) for k, w in cfgs.items()}
    print('   time in crypto 2019+', {k: round(v, 2) for k, v in tim.items()})
    return {'choice': choice, 'development': dev, 'holdout': hold, 'rules': res, 'time_in_crypto_holdout': tim}


def main():
    px, spy = load()
    out = {}
    # benchmarks for context
    for name, w in [('btc_buy_hold', pd.DataFrame({'BTC': 1.0}, index=px.index))]:
        m = C.metrics(e := equity(px, w, '2018-12-31', C.END), spy.reindex(e.index).ffill().bfill())
        print(f'context {name}: hold cagr {100*m["cagr"]:.1f} vs SPY {100*m["spy_cagr"]:.1f} dd {100*m["dd"]:.0f} halves {m.get("first_half"):+.1f}/{m.get("second_half"):+.1f}')
        out[name] = m
    out['J1_btc_trend'] = run_family('trend', {f'N{n}': btc_trend(px, n) for n in (100, 200, 140)}, px, spy)
    out['J2_a2c_rules'] = run_family('a2c', {f'L{L}': a2c_rules(px, L) for L in (28, 56, 90)}, px, spy)
    out['J3_vol_target'] = run_family('vol', {f'target{int(t*100)}{"_trend" if tr else ""}': vol_target(px, t, tr) for t in (.3, .5) for tr in (False, True)}, px, spy)
    C.save('track_j', out)


if __name__ == '__main__':
    main()
