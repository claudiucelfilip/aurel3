"""Shared loaders and a weights-to-equity engine for track F."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import common as C  # noqa: E402

STOCKS = C.ROOT / 'data' / 'broad_search' / 'insider' / 'prices'
WILD = C.ROOT / 'data' / 'broad_search' / 'wild'
SIDE = .001


def load_stocks():
    """Wide adjusted-close and raw-close frames for every cached stock, cached as parquet after the first load."""
    cache = WILD / 'stocks_wide.parquet'
    if cache.exists():
        adj = pd.read_parquet(cache)
        close = pd.read_parquet(WILD / 'stocks_close.parquet')
        return adj, close
    adj, close = {}, {}
    for p in STOCKS.glob('*.csv'):
        if p.stem.startswith('^'):
            continue
        d = pd.read_csv(p, index_col='Date', parse_dates=True)
        if len(d) > 250:
            adj[p.stem], close[p.stem] = d['adj'], d['close']
    adj, close = pd.DataFrame(adj).sort_index(), pd.DataFrame(close).sort_index()
    spy = adj['SPY'].dropna()
    adj, close = adj.loc[spy.index], close.loc[spy.index]
    WILD.mkdir(parents=True, exist_ok=True)
    adj.to_parquet(cache)
    close.to_parquet(WILD / 'stocks_close.parquet')
    return adj, close


def clean_stocks(adj, close):
    """Yahoo leaves some reverse splits unadjusted (ALP: 100 -> 8,500 in a day). Drop any ticker with a >100% daily move
    and cap the rest at +/-50% a day. Returns the cleaned frames and the dropped tickers."""
    r = adj.pct_change(fill_method=None)
    bad = list(r.columns[(r.abs() > 1).any()])
    r = r.drop(columns=bad).clip(-.5, .5)
    adj2 = (1 + r.fillna(0)).cumprod().where(adj.drop(columns=bad).notna())
    return adj2, close.drop(columns=bad), bad


def run_weights(adj, w, start, end, side=SIDE):
    """w: target weights indexed by the entry close date. Held until the next entry; unallocated weight sits in SPY."""
    w = w.reindex(columns=adj.columns, fill_value=0.0)
    w['SPY'] = w['SPY'] + (1 - w.sum(axis=1)).clip(lower=0)
    daily = adj.pct_change(fill_method=None).loc[start:end].fillna(0)
    held = w.reindex(adj.index).ffill().shift(1).loc[start:end].fillna(0)
    held.loc[held.sum(axis=1) == 0, 'SPY'] = 1.0
    turnover = held.diff().abs().sum(axis=1).fillna(0)
    r = (held * daily).sum(axis=1) - turnover * side
    return (1 + r).cumprod()


def evaluate(track, configs, adj, dev_start='2008-01-01', extra=None):
    """configs: name -> weights frame. Picks by development Sharpe, then scores the holdout. Saves via common."""
    spy = adj['SPY']
    dev, hold = {}, {}
    for name, w in configs.items():
        eq = run_weights(adj, w, dev_start, '2018-12-31')
        dev[name] = C.metrics(eq, spy.loc[eq.index[0]:eq.index[-1]])
    choice = max(dev, key=lambda k: dev[k]['sharpe'])
    C.record_choice(track, choice, dev)
    for name, w in configs.items():
        eq = run_weights(adj, w, '2018-12-31', C.END)
        hold[name] = C.metrics(eq, spy.loc[eq.index[0]:eq.index[-1]])
    res = C.verdict(dev[choice], hold[choice])
    C.save(track, {'choice': choice, 'development': dev, 'holdout': hold, 'rules': res, **(extra or {})})
    C.show(track.upper(), choice, dev, hold, res)
    return choice, dev, hold, res


def next_close(index, dates):
    """Map signal dates to the following trading day (one-day execution delay)."""
    pos = np.minimum(index.searchsorted(dates, side='right'), len(index) - 1)
    return index[pos]
