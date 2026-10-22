"""Track H: four timing rules claimed on Reddit, tested on ETFs. See protocol.json track_H_reddit_claims."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import common as C  # noqa: E402
import pairs as P  # noqa: E402

SIDE, CASH = .001, 'SHY'
SECTORS = ['XLB', 'XLE', 'XLF', 'XLI', 'XLK', 'XLP', 'XLU', 'XLV', 'XLY']


def run(px, w, start, end):
    """w: target weights decided at the close of each index date; applied from the next close. Rest in cash."""
    w = w.reindex(index=px.index, columns=px.columns).ffill().fillna(0)
    w[CASH] = w[CASH] + (1 - w.drop(columns=CASH).sum(axis=1)).clip(lower=0)
    daily = px.pct_change(fill_method=None).fillna(0)
    held = w.shift(1).loc[start:end].fillna(0)
    turnover = held.diff().abs().sum(axis=1).fillna(0)
    r = (held * daily.loc[held.index]).sum(axis=1) - turnover * SIDE
    return (1 + r).cumprod()


def rsi(s, n=2):
    d = s.diff()
    up, dn = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean(), (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def qqq_trend(px, mode):
    q = px['QQQ']
    if mode == 'daily200':
        on = q > q.rolling(200).mean()
    else:
        m = q.groupby(q.index.to_period('M')).tail(1)
        sig = m > (m.rolling(10).mean() if mode == 'monthly10m' else q.rolling(200).mean().reindex(m.index))
        on = sig.reindex(q.index).ffill().fillna(False)
    return pd.DataFrame({'QQQ': on.astype(float)}, index=px.index)


def rsi2(px, tickers):
    w = pd.DataFrame(0.0, index=px.index, columns=tickers)
    for t in tickers:
        s = px[t]
        r2, sma, ema5 = rsi(s), s.rolling(200).mean(), s.ewm(span=5, adjust=False).mean()
        pos, out = False, []
        for i in range(len(s)):
            if pos and (r2.iloc[i] > 70 or s.iloc[i] > ema5.iloc[i]):
                pos = False
            elif not pos and r2.iloc[i] < 10 and s.iloc[i] > sma.iloc[i]:
                pos = True
            out.append(pos)
        w[t] = np.array(out, float)
    n = w.sum(axis=1).replace(0, np.nan)
    return w.div(n, axis=0).fillna(0)


def two_down(px, hold):
    s = px['SPY']
    down = (s.diff() < 0)
    trig = down & down.shift(1).fillna(False)
    pos, left, out = False, 0, []
    for t in trig:
        if left > 0:
            left -= 1
        if t and left == 0:
            left = hold
        out.append(1.0 if left > 0 else 0.0)
    return pd.DataFrame({'SPY': out}, index=px.index)


def fx_filter(px, weeks):
    wk = px.groupby(px.index.to_period('W-FRI')).tail(1)
    on = wk['FXE'].pct_change(weeks) > wk['UUP'].pct_change(weeks)
    return pd.DataFrame({'SPY': on.reindex(px.index).ffill().fillna(False).astype(float)}, index=px.index)


def main():
    px = P.load()
    spy = px['SPY']
    families = {
        'qqq_trend': {m: qqq_trend(px, m) for m in ('daily200', 'monthly200', 'monthly10m')},
        'rsi2_pullback': {'SPY': rsi2(px, ['SPY']), 'QQQ': rsi2(px, ['QQQ']), 'sectors': rsi2(px, SECTORS)},
        'two_down_closes': {f'hold{h}': two_down(px, h) for h in (5, 3, 10)},
        'fxe_uup_filter': {f'{k}w': fx_filter(px, k) for k in (4, 8, 13)},
    }
    out = {}
    for fam, cfgs in families.items():
        dev = {k: C.metrics(e := run(px, w, '2008-01-01', '2018-12-31'), spy.loc[e.index[0]:e.index[-1]]) for k, w in cfgs.items()}
        choice = max(dev, key=lambda k: dev[k]['sharpe'])
        C.record_choice(f'track_h_{fam}', choice, dev)
        hold = {k: C.metrics(e := run(px, w, '2018-12-31', C.END), spy.loc[e.index[0]:e.index[-1]]) for k, w in cfgs.items()}
        tim = {k: float(w.sum(axis=1).loc['2019':].gt(0).mean()) for k, w in cfgs.items()}
        res = C.verdict(dev[choice], hold[choice])
        out[fam] = {'choice': choice, 'development': dev, 'holdout': hold, 'time_in_market_holdout': tim, 'rules': res}
        C.show(f'H {fam}', choice, dev, hold, res)
        print('   time in market 2019+', {k: round(v, 2) for k, v in tim.items()})
    C.save('track_h', out)


if __name__ == '__main__':
    main()
