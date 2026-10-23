"""Track I: predictable-flow tests. I1 turn-of-month on SPY; I2 S&P 500 additions; I3 S&P 500 deletions. See protocol.json track_I_predictable_flows."""
import re
import sys
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import common as C  # noqa: E402

D = C.DATA / 'flows'
SIDE = .001
EXCLUDE = re.compile(r'acqui|merg|bankrupt|spun|spin|taken private|chapter 11|delist|liquidat', re.I)


def load_cash_daily(idx):
    """Daily cash return: SHY where it exists, else 3-month T-bill yield accrued daily."""
    shy = pd.read_csv(D / 'SHY.csv', index_col=0, parse_dates=True).iloc[:, 0]
    tb = pd.read_csv(D / 'dtb3.csv', index_col=0, parse_dates=True).iloc[:, 0]
    tb = pd.to_numeric(tb, errors='coerce').reindex(idx).ffill() / 100 / 252
    r = shy.reindex(idx).pct_change(fill_method=None)
    return r.where(r.notna(), tb).fillna(0)


def equity(spy, cash_r, w_stock, stock_r, start, end):
    """w_stock: DataFrame of weights per stock decided at the close of each date (applied from the next close).
    Remaining weight is SPY unless w_stock sums to 0 and the row is flagged cash via column '__cash__'."""
    idx = spy.loc[start:end].index
    spy_r = spy.pct_change(fill_method=None).reindex(idx).fillna(0)
    w = w_stock.reindex(idx).fillna(0)
    cash = w.pop('__cash__') if '__cash__' in w else pd.Series(0.0, index=idx)
    held = w.shift(1).fillna(0)
    cash_h = cash.shift(1).fillna(0)
    spy_w = (1 - held.sum(axis=1) - cash_h).clip(lower=0)
    sr = stock_r.reindex(index=idx, columns=held.columns).fillna(0)
    r = (held * sr).sum(axis=1) + spy_w * spy_r + cash_h * cash_r.reindex(idx).fillna(0)
    turnover = held.diff().abs().sum(axis=1).fillna(0) + spy_w.diff().abs().fillna(0) + cash_h.diff().abs().fillna(0)
    return (1 + r - turnover * SIDE).cumprod()


def tom_weights(idx, L, F):
    """1 = hold SPY on the last L and first F trading days of each month; otherwise cash."""
    s = pd.Series(idx, index=idx)
    pos_from_start = s.groupby(idx.to_period('M')).cumcount()
    n_in_month = s.groupby(idx.to_period('M')).transform('size')
    pos_from_end = n_in_month - 1 - pos_from_start
    hold = (pos_from_start < F) | (pos_from_end < L)
    # Decide at the previous close: weight for day t is set on t-1, so shift the signal back one day.
    hold = hold.shift(-1).fillna(False).astype(float)
    return pd.DataFrame({'__cash__': 1 - hold}, index=idx)


def load_stocks(tickers):
    out = {}
    for t in tickers:
        f = D / 'prices' / f'{t}.csv'
        if f.exists():
            s = pd.read_csv(f, index_col=0, parse_dates=True).iloc[:, 0]
            if len(s) > 20:
                out[t] = s
    px = pd.DataFrame(out)
    r = px.pct_change(fill_method=None).clip(-.5, .5)  # the known reverse-split glitch guard
    return px, r


def event_weights(idx, events, entry_offset, exit_offset):
    """events: list of (effective_date, ticker). Enter at close of effective+entry_offset trading days,
    exit at close of effective+exit_offset. Weight is equal split among active events (so SPY weight is 0 while any is active)."""
    w = pd.DataFrame(0.0, index=idx, columns=sorted({t for _, t in events}))
    pos = {d: i for i, d in enumerate(idx)}
    for eff, t in events:
        eff = pd.Timestamp(eff)
        loc = idx.searchsorted(eff)
        if loc >= len(idx):
            continue
        a, b = loc + entry_offset, loc + exit_offset
        if a < 0 or b <= a or b > len(idx):
            continue
        w.iloc[a:b, w.columns.get_loc(t)] = 1.0
    n = w.sum(axis=1).replace(0, np.nan)
    return w.div(n, axis=0).fillna(0)


def run_family(tag, cfgs, spy, cash_r, stock_r, dev, hold_, upper=None):
    dev_m = {k: C.metrics(e := equity(spy, cash_r, w, stock_r, *dev), spy.loc[e.index[0]:e.index[-1]]) for k, w in cfgs.items()}
    choice = max(dev_m, key=lambda k: dev_m[k]['sharpe'])
    C.record_choice(f'track_i_{tag}', choice, dev_m)
    hold_m = {k: C.metrics(e := equity(spy, cash_r, w, stock_r, *hold_), spy.loc[e.index[0]:e.index[-1]]) for k, w in cfgs.items()}
    res = C.verdict(dev_m[choice], hold_m[choice])
    C.show(f'I {tag}', choice, dev_m, hold_m, res)
    out = {'choice': choice, 'development': dev_m, 'holdout': hold_m, 'rules': res}
    if upper:
        out['upper_bound_not_eligible'] = {k: C.metrics(e := equity(spy, cash_r, w, stock_r, *hold_), spy.loc[e.index[0]:e.index[-1]]) for k, w in upper.items()}
        for k, m in out['upper_bound_not_eligible'].items():
            print(f'   upper bound {k}: hold ex {m["excess_pp"]:+.1f} t {m["t_nw6"]:+.2f}')
    return out


def main(parts=('I1', 'I2', 'I3')):
    spy = pd.read_csv(D / 'SPY.csv', index_col=0, parse_dates=True).iloc[:, 0]
    idx = spy.index
    cash_r = load_cash_daily(idx)
    out = {}
    if 'I1' in parts:
        cfgs = {f'L{L}F{F}': tom_weights(idx, L, F) for L, F in [(1, 3), (3, 3), (4, 5), (2, 2)]}
        empty = pd.DataFrame(index=idx)
        out['I1_turn_of_month'] = run_family('tom', cfgs, spy, cash_r, empty, ('1994-01-01', '2018-12-31'), ('2018-12-31', C.END))
        tim = {k: float(1 - w['__cash__'].loc['2019':].mean()) for k, w in cfgs.items()}
        out['I1_turn_of_month']['time_in_market_holdout'] = tim
        print('   time in market', {k: round(v, 2) for k, v in tim.items()})
    if 'I2' in parts or 'I3' in parts:
        ch = pd.read_csv(D / 'sp500_changes_wiki.csv').fillna('')
        ch = ch[ch.effective >= '2010-06-01']
        adds = [(r.effective, r.added) for r in ch.itertuples() if r.added]
        dels = [(r.effective, r.removed) for r in ch.itertuples() if r.removed and not EXCLUDE.search(r.reason)]
        px, stock_r = load_stocks(sorted({t for _, t in adds + dels}))
        have = set(px.columns)
        adds = [(d, t) for d, t in adds if t in have and px[t].loc[:d].notna().sum() > 10]
        dels = [(d, t) for d, t in dels if t in have and px[t].loc[d:].notna().sum() > 10]
        print(f'additions with pre-event prices {len(adds)}, deletions (non-corporate-action) with post-event prices {len(dels)}')
        dev, hold_ = ('2011-01-01', '2018-12-31'), ('2018-12-31', C.END)
        if 'I2' in parts:
            cfgs = {f'k{k}_exit{h}': event_weights(idx, adds, -k, h + 1) for k in (1, 2) for h in (0, 5)}
            upper = {f'k{k}_exit0': event_weights(idx, adds, -k, 1) for k in (3, 5)}
            out['I2_sp500_additions'] = run_family('adds', cfgs, spy, cash_r, stock_r, dev, hold_, upper)
            out['I2_sp500_additions']['n_events'] = {'development': sum(dev[0] <= d <= dev[1] for d, _ in adds), 'holdout': sum(d > dev[1] for d, _ in adds)}
        if 'I3' in parts:
            cfgs = {f'N{n}': event_weights(idx, dels, 0, n + 1) for n in (20, 60, 120)}
            out['I3_sp500_deletions'] = run_family('dels', cfgs, spy, cash_r, stock_r, dev, hold_)
            out['I3_sp500_deletions']['n_events'] = {'development': sum(dev[0] <= d <= dev[1] for d, _ in dels), 'holdout': sum(d > dev[1] for d, _ in dels)}
    C.save('track_i', out)


if __name__ == '__main__':
    main(tuple(sys.argv[1:]) or ('I1', 'I2', 'I3'))
