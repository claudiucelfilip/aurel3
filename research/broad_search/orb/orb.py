"""Track K: long-only, unleveraged intraday opening-range breakout on QQQ (protocol.json track_K_intraday_orb).

Usage: python orb.py [data_dir]  -- expects QQQ_1min_YYYY.csv (Alpaca IEX) + BIL_1D.csv in data_dir,
and ../flows/SPY.csv for the SPY benchmark. Prints every grid cell; nothing is dropped.
"""
import glob, sys
from pathlib import Path
import numpy as np
import pandas as pd

DATA = Path(sys.argv[1] if len(sys.argv) > 1 else "data/broad_search/orb")
DEV_END = pd.Timestamp("2022-12-31")
HOLD_START, SPLIT, END = pd.Timestamp("2023-01-01"), pd.Timestamp("2024-12-31"), pd.Timestamp("2026-10-23")
COSTS_BP = [0, 1, 2, 5]


def load_minutes():
    frames = [pd.read_csv(f) for f in sorted(glob.glob(str(DATA / "QQQ_1min_*.csv")))]
    m = pd.concat(frames, ignore_index=True)
    ts = pd.to_datetime(m["timestamp"], utc=True).dt.tz_convert("America/New_York")
    m["ts"] = ts
    m["date"] = ts.dt.date
    m["mins"] = ts.dt.hour * 60 + ts.dt.minute  # minutes since midnight ET
    m = m[(m.mins >= 570) & (m.mins < 960)].sort_values("ts")  # 09:30-16:00
    # drop days with too few bars (holidays / half days / IEX gaps)
    n = m.groupby("date").size()
    m = m[m.date.isin(n[n >= 300].index)]
    return m.reset_index(drop=True)


def daily_from_minutes(m):
    d = m.groupby("date").agg(open=("open", "first"), close=("close", "last"))
    d.index = pd.to_datetime(d.index)
    d["sma20"] = d.close.rolling(20).mean().shift(1)
    return d


def orb_trades(m, R, gate=None):
    """One trade per day at most. Returns DataFrame[date, entry, exit, reason]."""
    out = []
    for date, g in m.groupby("date", sort=True):
        if gate is not None:
            day = pd.Timestamp(date)
            if day not in gate.index or not gate.loc[day]:
                continue
        rng = g[g.mins < 570 + R]
        if len(rng) < max(1, R // 2):
            continue
        hi, lo = rng.high.max(), rng.low.min()
        after = g[(g.mins >= 570 + R)]
        trig = after[(after.high > hi) & (after.mins < 720)]
        if trig.empty:
            continue
        i = trig.index[0]
        bar = after.loc[i]
        entry = max(bar.open, hi)  # gap-through fills at open, else at the stop level
        rest = after.loc[i:].iloc[1:]
        stopped = rest[rest.low <= lo]
        if not stopped.empty:
            sbar = stopped.iloc[0]
            exit_px, reason = min(sbar.open, lo), "stop"
        else:
            eod = rest[rest.mins <= 955]
            exit_px, reason = (eod.iloc[-1].close if len(eod) else rest.iloc[-1].close), "close"
        out.append((pd.Timestamp(date), entry, exit_px, reason))
    return pd.DataFrame(out, columns=["date", "entry", "exit", "reason"]).set_index("date")


def session_momentum_trades(m, trail):
    """First 5-min candle closes above EMA12 of 5-min closes -> buy at 09:35; trailing stop = trail x candle range."""
    five = m.set_index("ts").groupby(pd.Grouper(freq="5min", label="left", closed="left")).agg(
        open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last")).dropna()
    five["ema12"] = five.close.ewm(span=12, adjust=False).mean()
    first = five[(five.index.hour == 9) & (five.index.minute == 30)]
    out = []
    for ts, c in first.iterrows():
        if not c.close > c.ema12:
            continue
        date = ts.date()
        g = m[(m.date == date) & (m.mins >= 575)]
        if g.empty:
            continue
        entry = c.close
        rng = c.high - c.low
        if rng <= 0:
            continue
        run_hi, exit_px, reason = entry, None, None
        for _, b in g.iterrows():
            stop = run_hi - trail * rng
            if b.low <= stop:
                exit_px, reason = min(b.open, stop), "stop"
                break
            run_hi = max(run_hi, b.high)
            if b.mins >= 955:
                exit_px, reason = b.close, "close"
                break
        if exit_px is None:
            exit_px, reason = g.iloc[-1].close, "close"
        out.append((pd.Timestamp(date), entry, exit_px, reason))
    return pd.DataFrame(out, columns=["date", "entry", "exit", "reason"]).set_index("date")


def equity(trades, all_days, cost_bp, cash_ret=None):
    r = pd.Series(0.0, index=all_days)
    if len(trades):
        tr = trades.exit / trades.entry - 1 - 2 * cost_bp / 1e4
        r.loc[tr.index] = tr.values
    if cash_ret is not None:
        r = r + cash_ret.reindex(all_days).fillna(0.0)
    return r


def stats(r):
    r = r.dropna()
    if len(r) < 20:
        return dict(cagr=np.nan, dd=np.nan, sharpe=np.nan)
    eq = (1 + r).cumprod()
    yrs = (r.index[-1] - r.index[0]).days / 365.25
    cagr = eq.iloc[-1] ** (1 / yrs) - 1
    dd = (eq / eq.cummax() - 1).min()
    sharpe = r.mean() / r.std() * np.sqrt(252) if r.std() > 0 else np.nan
    return dict(cagr=cagr, dd=dd, sharpe=sharpe)


def fmt(s):
    return f"{s['cagr']*100:6.1f}% {s['dd']*100:6.1f}% {s['sharpe']:5.2f}"


def main():
    m = load_minutes()
    d = daily_from_minutes(m)
    all_days = d.index
    print(f"QQQ minute data: {all_days[0].date()} -> {all_days[-1].date()}, {len(all_days)} sessions")
    spy = pd.read_csv(Path("data/broad_search/flows/SPY.csv"), index_col=0, parse_dates=True)
    spy_r = spy.iloc[:, 0].pct_change().reindex(all_days).fillna(0.0)  # adjusted close, ends 2026-10-16
    qqq_r = d.close.pct_change().fillna(0.0)
    bil = pd.read_csv(DATA / "BIL_1D.csv")
    bil.index = pd.to_datetime(bil.timestamp, utc=True).dt.tz_convert("America/New_York").dt.normalize().dt.tz_localize(None)
    bil_r = bil.close.pct_change()
    # BIL price return excludes its monthly dividend; approximate yield from 3m T-bill is better. Use price return + 4%/yr floor proxy? No: stay honest,
    # use FRED-free proxy = BIL price return, which understates cash yield. Reported as a lower bound.

    periods = {
        "dev": (all_days[0], DEV_END), "holdout": (HOLD_START, END),
        "H1 23-24": (HOLD_START, SPLIT), "H2 25-26": (SPLIT + pd.Timedelta(days=1), END),
    }
    gate = d.open > d.sma20
    cells = {}
    for R in (5, 15, 30):
        cells[f"K1 ORB R{R}"] = orb_trades(m, R)
        cells[f"K3 ORB R{R} +trend"] = orb_trades(m, R, gate=gate)
    for t in (1, 2):
        cells[f"K2 SessMom trail{t}"] = session_momentum_trades(m, t)

    print("\nBenchmarks (CAGR  maxDD  Sharpe):")
    for pname, (a, b) in periods.items():
        sl = slice(a, b)
        print(f"  {pname:9s} SPY {fmt(stats(spy_r[sl]))} | QQQ(px) {fmt(stats(qqq_r[sl]))}")

    for name, tr in cells.items():
        print(f"\n== {name}: {len(tr)} trades, win {np.mean(tr.exit > tr.entry)*100:.0f}%, "
              f"avg {((tr.exit/tr.entry-1).mean())*1e4:.1f}bp gross/trade, stops {np.mean(tr.reason=='stop')*100:.0f}%")
        for cost in COSTS_BP:
            r = equity(tr, all_days, cost)
            line = f"  {cost}bp/side: "
            for pname, (a, b) in periods.items():
                s = stats(r[a:b]); n = len(tr[a:b])
                line += f"{pname} {fmt(s)} (n={n}) | "
            print(line)
        r = equity(tr, all_days, 1)
        hs = stats(r[HOLD_START:END]); ss = stats(spy_r[HOLD_START:END])
        print(f"  holdout @1bp vs SPY: {(hs['cagr']-ss['cagr'])*100:+.1f}pp/yr  hurdle +3.0pp -> {'PASS' if hs['cagr']-ss['cagr']>=0.03 and hs['dd']>=ss['dd'] else 'FAIL'}")


if __name__ == "__main__":
    main()
