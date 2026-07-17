"""Backtest: short aurel3's declined candidates (hype-fade hypothesis).

Universe comes from data/recommendation_history.json (append-only record of
every scan's recommendations). Price paths from yfinance daily OHLC.

Rules (short leg):
- signal: action == watch_for_confirmation AND confirmation_state in
  (unconfirmed, developing)
- entry: next trading day's OPEN after the recommendation timestamp
- stop: +15% above entry, checked against daily HIGH (fill at stop price —
  pessimistic; a squeeze through the stop fills worse, not better)
- exit: close of the 10th trading day after entry, if the stop never hit
- one open position per ticker; later signals for a held ticker are ignored
- sanity: skip if entry open differs from reference_price by >40% (bad data)

Control legs run the same rules on cohorts the hypothesis says should NOT
fall (overconfirmed watch, hold_not_fresh_buy) and on SPY itself.
"""

import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import pandas as pd
import yfinance as yf

HIST_PATH = "data/recommendation_history.json"
STOP_PCT = 0.15
HOLD_DAYS = 10  # trading days
ROUND_TRIP_COST = 0.01  # spread + ~2wk borrow on liquid names, rough


def load_signals():
    with open(HIST_PATH) as f:
        batches = json.load(f)
    rows = []
    for batch in batches:
        for r in batch.get("recommendations", []):
            ts = r.get("timestamp") or batch.get("generated_at")
            if not ts or not r.get("ticker") or not r.get("reference_price"):
                continue
            rows.append({
                "ticker": r["ticker"].upper(),
                "ts": datetime.fromisoformat(ts),
                "action": r.get("action"),
                "confirmation": r.get("confirmation_state"),
                "theme": r.get("theme_driver"),
                "reference_price": r["reference_price"],
            })
    rows.sort(key=lambda x: x["ts"])
    return rows


def yahoo_symbol(ticker):
    return {"BRK.B": "BRK-B", "BF.B": "BF-B"}.get(ticker, ticker)


def fetch_history(tickers, start, end):
    out = {}
    for t in sorted(tickers):
        try:
            df = yf.download(yahoo_symbol(t), start=start, end=end,
                             progress=False, auto_adjust=False)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            df = df.dropna(subset=["Open", "High", "Close"])
            if len(df) > 0:
                out[t] = df
        except Exception as e:
            print(f"  data fail {t}: {e}", file=sys.stderr)
    return out


def simulate_leg(name, signals, prices):
    open_until = defaultdict(lambda: None)  # ticker -> exit date while held
    trades = []
    skipped = {"no_data": 0, "bad_price": 0, "still_held": 0, "no_future_bars": 0}

    for sig in signals:
        t = sig["ticker"]
        df = prices.get(t)
        if df is None:
            skipped["no_data"] += 1
            continue
        sig_date = sig["ts"].date()
        future = df[df.index.date > sig_date]
        if len(future) < 2:
            skipped["no_future_bars"] += 1
            continue
        entry_date = future.index[0].date()
        held_until = open_until[t]
        if held_until is not None and entry_date <= held_until:
            skipped["still_held"] += 1
            continue
        entry = float(future.iloc[0]["Open"])
        if pd.isna(entry) or entry <= 0 or abs(entry / sig["reference_price"] - 1) > 0.40:
            skipped["bad_price"] += 1
            continue

        stop_price = entry * (1 + STOP_PCT)
        window = future.iloc[:HOLD_DAYS + 1]
        exit_price, exit_date, stopped = None, None, False
        mae = 0.0  # max adverse excursion for a short = max high vs entry
        for i, (idx, bar) in enumerate(window.iterrows()):
            high = float(bar["High"])
            mae = max(mae, high / entry - 1)
            if high >= stop_price:
                exit_price, exit_date, stopped = stop_price, idx.date(), True
                break
            if i == len(window) - 1 or i == HOLD_DAYS:
                exit_price, exit_date = float(bar["Close"]), idx.date()
        if exit_price is None:
            skipped["no_future_bars"] += 1
            continue

        short_ret = (entry - exit_price) / entry  # positive = short made money
        open_until[t] = exit_date
        trades.append({
            "ticker": t, "signal_date": str(sig_date), "entry_date": str(entry_date),
            "exit_date": str(exit_date), "entry": round(entry, 2),
            "exit": round(exit_price, 2), "stopped": stopped,
            "short_ret_gross": round(short_ret, 4),
            "short_ret_net": round(short_ret - ROUND_TRIP_COST, 4),
            "mae": round(mae, 4), "theme": sig["theme"],
            "confirmation": sig["confirmation"],
        })

    return {"leg": name, "trades": trades, "skipped": skipped}


def summarize(result):
    trades = result["trades"]
    print(f"\n=== {result['leg']} ===")
    print(f"signals skipped: {result['skipped']}")
    if not trades:
        print("no trades")
        return
    g = [t["short_ret_gross"] for t in trades]
    n = [t["short_ret_net"] for t in trades]
    mae = [t["mae"] for t in trades]
    stops = sum(1 for t in trades if t["stopped"])
    win = sum(1 for x in n if x > 0) / len(n)
    print(f"trades={len(trades)} stopped={stops} win_rate_net={win:.2f}")
    print(f"gross: mean={sum(g)/len(g):+.4f} total={sum(g):+.3f}")
    print(f"net  : mean={sum(n)/len(n):+.4f} total={sum(n):+.3f}")
    print(f"MAE  : mean={sum(mae)/len(mae):.3f} max={max(mae):.3f}")
    worst = sorted(trades, key=lambda t: t["short_ret_net"])[:3]
    best = sorted(trades, key=lambda t: t["short_ret_net"], reverse=True)[:3]
    print("worst:", [(t["ticker"], t["entry_date"], t["short_ret_net"]) for t in worst])
    print("best :", [(t["ticker"], t["entry_date"], t["short_ret_net"]) for t in best])
    by_theme = defaultdict(list)
    for t in trades:
        by_theme[t["theme"]].append(t["short_ret_net"])
    for th, v in sorted(by_theme.items(), key=lambda kv: -sum(kv[1])):
        print(f"  theme {th}: n={len(v)} total_net={sum(v):+.3f}")


def main():
    signals = load_signals()
    print(f"signals loaded: {len(signals)}, "
          f"{signals[0]['ts'].date()} -> {signals[-1]['ts'].date()}")

    legs = {
        "SHORT unconfirmed/developing watch": [
            s for s in signals
            if s["action"] == "watch_for_confirmation"
            and s["confirmation"] in ("unconfirmed", "developing")],
        "CONTROL overconfirmed watch": [
            s for s in signals
            if s["action"] == "watch_for_confirmation"
            and s["confirmation"] == "overconfirmed"],
        "CONTROL hold_not_fresh_buy": [
            s for s in signals if s["action"] == "hold_not_fresh_buy"],
    }
    tickers = {s["ticker"] for leg in legs.values() for s in leg}
    start = (signals[0]["ts"] - timedelta(days=5)).date()
    end = (datetime.now(timezone.utc) + timedelta(days=1)).date()
    print(f"fetching {len(tickers)} tickers {start} -> {end}")
    prices = fetch_history(tickers, str(start), str(end))
    print(f"got data for {len(prices)}/{len(tickers)}")

    results = {}
    for name, leg_signals in legs.items():
        res = simulate_leg(name, leg_signals, prices)
        summarize(res)
        results[name] = res

    spy = fetch_history({"SPY"}, str(start), str(end)).get("SPY")
    if spy is not None:
        spy_ret = float(spy.iloc[-1]["Close"] / spy.iloc[0]["Open"] - 1)
        print(f"\nSPY over full window: {spy_ret:+.3f}")

    with open("data/backtest_short_fade_results.json", "w") as f:
        json.dump({k: v["trades"] for k, v in results.items()}, f, indent=1)
    print("\ntrade log -> data/backtest_short_fade_results.json")


if __name__ == "__main__":
    main()
