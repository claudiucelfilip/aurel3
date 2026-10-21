"""Causal signals and a cash-constrained, delayed-fill research simulator."""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
DATA = HERE.parents[1] / "data" / "multiasset"
PROTOCOL = json.loads((HERE / "protocol.json").read_text())


@dataclass
class Market:
    close: pd.DataFrame
    opening: pd.DataFrame
    signal_close: pd.DataFrame
    sessions: pd.DatetimeIndex
    groups: dict


def load_market(data=DATA):
    groups = {**PROTOCOL["assets"], "BIL": "cash"}
    frames = {}
    for ticker in groups:
        f = pd.read_csv(data / f"{ticker}.csv", index_col=0, parse_dates=True)
        if f.index.has_duplicates or not f.index.is_monotonic_increasing:
            raise ValueError(f"Invalid dates: {ticker}")
        f = f.loc[f["Close"].notna() & f["Adj Close"].notna()]
        if (f[["Open", "Close", "Adj Close"]] <= 0).any().any():
            raise ValueError(f"Nonpositive price: {ticker}")
        frames[ticker] = f
    sessions = frames["SPY"].index
    calendar = pd.date_range(sessions[0], sessions[-1], freq="D")
    opening, close, signal_close = {}, {}, {}
    for ticker, frame in frames.items():
        close[ticker] = frame["Adj Close"].reindex(calendar).ffill()
        opening[ticker] = (frame["Open"] * frame["Adj Close"] / frame["Close"]).reindex(calendar)
        # A UTC crypto close labelled Friday is not known at Friday's US close.
        signal_close[ticker] = close[ticker].shift(1) if groups[ticker] == "crypto" else close[ticker]
    return Market(pd.DataFrame(close), pd.DataFrame(opening),
                  pd.DataFrame(signal_close).loc[sessions], sessions, groups)


def macro_series(data=DATA, lag=90):
    result = {}
    for name, label, scale in [("pcpi", "inflation", 5), ("employ_level", "growth", 200)]:
        rows = json.loads((data / f"{name}-rows.json").read_text())
        records = {}
        for row in rows:
            date = row.get("A", "")
            if re.fullmatch(r"\d{4}:\d{2}", date):
                value = pd.to_numeric(row.get("B"), errors="coerce")
                records[pd.Period(date.replace(":", "-"), freq="M")] = value
        s = pd.Series(records).sort_index()
        s = s.reindex(pd.period_range(s.index.min(), s.index.max(), freq="M"))
        change = (s.rolling(3).mean() - s.shift(3).rolling(3).mean()) / scale
        change.index = change.index.to_timestamp(how="end").normalize() + pd.Timedelta(days=lag)
        result[label] = change.clip(-3, 3)
    return pd.DataFrame(result)


def features(market, lag=90, horizons=(63, 126, 252)):
    p = market.signal_close
    ret = p.pct_change(fill_method=None)
    vol = ret.rolling(63, min_periods=63).std() * np.sqrt(252)
    excess = {n: p.pct_change(n, fill_method=None).sub(p.BIL.pct_change(n, fill_method=None), axis=0)
              for n in horizons}
    macro = macro_series(lag=lag)
    union = macro.index.union(p.index)
    macro = macro.reindex(union).ffill().reindex(p.index).fillna(0)
    # Stale or incomplete six-month input windows produce neutral signals.
    source = macro_series(lag=lag)
    for col in macro:
        dates = pd.Series(source.index.where(source[col].notna()), index=source.index)
        last = dates.reindex(union).ffill().reindex(p.index)
        stale = (pd.Series(p.index, index=p.index) - last).dt.days > 150
        macro.loc[stale.fillna(True), col] = 0
    weekly = pd.Series(p.index, index=p.index).groupby(p.index.to_period("W-FRI")).last()
    rows = []
    groups = list(PROTOCOL["group_budget"])
    for ticker, group in PROTOCOL["assets"].items():
        frame = pd.DataFrame({f"r{k}": excess[n][ticker] / vol[ticker] for k, n in enumerate(horizons)})
        frame["vol"] = vol[ticker]
        frame["drawdown"] = p[ticker] / p[ticker].rolling(max(horizons)).max() - 1
        frame["growth"] = macro.growth
        frame["inflation"] = macro.inflation
        frame["trend"] = sum((excess[n][ticker] > 0).astype(float) for n in horizons) / len(horizons)
        frame["valid"] = p[ticker].shift(max(horizons)).notna() & vol[ticker].notna()
        frame["label"] = (p[ticker].shift(-21) / p[ticker] - p.BIL.shift(-21) / p.BIL) / vol[ticker]
        frame["label_end"] = pd.Series(p.index, index=p.index).shift(-21)
        frame = frame.reindex(pd.DatetimeIndex(weekly.values))
        frame = frame.loc[frame.valid].copy()
        frame["ticker"] = ticker
        frame["group"] = group
        frame["date"] = frame.index
        rows.append(frame)
    panel = pd.concat(rows).sort_values(["date", "ticker"]).reset_index(drop=True)
    base = panel[["r0", "r1", "r2", "vol", "drawdown", "growth", "inflation"]].clip(-5, 5)
    x = pd.concat([base, base.pow(2).add_suffix("_squared")], axis=1)
    x["growth_inflation"] = base.growth * base.inflation
    x["trend_growth"] = base.r1 * base.growth
    x["trend_inflation"] = base.r1 * base.inflation
    for group in groups:
        x[group] = (panel.group == group).astype(float)
    return panel, x.fillna(0)


def ridge_forecast(panel, x):
    predictions = pd.Series(np.nan, index=panel.index)
    audit = []
    for year in sorted(panel.date.dt.year.unique()):
        current = panel.date.dt.year == year
        fit_date = panel.loc[current, "date"].min()
        train = (panel.label_end < fit_date) & panel.label.notna()
        first = panel.loc[train, "date"].min()
        if train.sum() < 500 or pd.isna(first) or (fit_date - first).days < 365.25 * 5:
            continue
        xt = x.loc[train].to_numpy()
        mean, scale = xt.mean(axis=0), xt.std(axis=0)
        scale = np.where(scale > 1e-8, scale, 1)
        z = np.column_stack([np.ones(len(xt)), np.clip((xt - mean) / scale, -5, 5)])
        y = panel.loc[train, "label"].clip(-3, 3).to_numpy()
        penalty = np.eye(z.shape[1]) * 10
        penalty[0, 0] = 0
        coef = np.linalg.solve(z.T @ z + penalty, z.T @ y)
        test = np.column_stack([np.ones(current.sum()), np.clip((x.loc[current].to_numpy() - mean) / scale, -5, 5)])
        predictions.loc[current] = test @ coef
        audit.append({"fit_date": str(fit_date.date()), "last_label_end": str(panel.loc[train, "label_end"].max().date()),
                      "training_rows": int(train.sum()), "prediction_rows": int(current.sum())})
    return predictions, audit


def targets(panel, predictions, strategy, exclude=None):
    targets_by_date = {}
    for date, rows in panel.groupby("date"):
        weights = {s: 0.0 for s in [*PROTOCOL["assets"], "BIL"]}
        if strategy in ("spy", "spy_btc"):
            weights["SPY"] = 1.0 if strategy == "spy" else 0.9
            if strategy == "spy_btc" and "BTC-USD" in set(rows.ticker):
                weights["BTC-USD"] = 0.1
        else:
            for group, budget in PROTOCOL["group_budget"].items():
                subset = rows.loc[rows.group == group]
                if subset.empty or group == exclude:
                    continue
                inv_vol = 1 / subset.vol.clip(lower=0.03)
                base = budget * inv_vol / inv_vol.sum()
                for i, row in subset.iterrows():
                    g, inf = np.sign(row.growth), np.sign(row.inflation)
                    econ = {"equity": (g-inf)/2, "crypto": (g-inf)/2,
                            "bond": (-g-inf)/2, "commodity": (g+inf)/2, "currency": 0}[group]
                    score = row.trend
                    if strategy in ("economic", "ml"):
                        score = np.clip(score * (1 + 0.25 * econ), 0, 1)
                    if strategy == "ml" and pd.notna(predictions.loc[i]):
                        score = 0.5 * score + 0.5 * np.clip(0.5 + 2 * predictions.loc[i], 0, 1)
                    if strategy == "static":
                        score = 1
                    weights[row.ticker] = float(base.loc[i] * score)
        weights["BIL"] = max(0, 1 - sum(weights.values()))
        targets_by_date[date] = weights
    return pd.DataFrame.from_dict(targets_by_date, orient="index").sort_index()


def execute_batch(units, cash, prices, target, selected, cost_bps, minimum_fee, threshold):
    nav = cash + float(np.nansum(units * prices))
    desired = target * nav
    delta = desired - np.nan_to_num(units * prices)
    traded, fees, count = 0.0, 0.0, 0
    events = []
    for sell in [True, False]:
        for j in selected:
            if not np.isfinite(prices[j]) or prices[j] <= 0:
                continue
            value = delta[j]
            if abs(value) < threshold or (value < 0) != sell:
                continue
            rate = cost_bps[j] / 10000
            if sell:
                amount = min(-value, units[j] * prices[j])
                fee = max(minimum_fee, amount * rate)
                if amount <= fee:
                    continue
                units[j] -= amount / prices[j]
                cash += amount - fee
            else:
                amount = min(value, max(0, cash - minimum_fee), max(0, cash / (1 + rate)))
                if amount < threshold:
                    continue
                fee = max(minimum_fee, amount * rate)
                units[j] += amount / prices[j]
                cash -= amount + fee
            traded += amount
            fees += fee
            count += 1
            events.append((j, "sell" if sell else "buy", amount, fee))
    if cash < -1e-7 or (units < -1e-8).any():
        raise AssertionError("Negative cash or unintended short")
    return units, max(0, cash), traded, fees, count, events


def simulate(market, target, delay=1, cost_multiplier=1, skip=False, start=None):
    start = pd.Timestamp(start or PROTOCOL["start"])
    cols = list(market.close.columns)
    dates = market.close.index[market.close.index >= start]
    opening = market.opening.loc[dates].to_numpy()
    close = market.close.loc[dates].to_numpy()
    prev_close = market.close.shift(1).loc[dates].to_numpy()
    calendar_positions = {d: i for i, d in enumerate(dates)}
    session_positions = {d: i for i, d in enumerate(market.sessions)}
    crypto = [j for j, s in enumerate(cols) if market.groups[s] == "crypto"]
    traditional = [j for j in range(len(cols)) if j not in crypto]
    schedule = {}
    for signal_date, row in target.iterrows():
        if signal_date < start:
            continue
        if skip and int(hashlib.sha256(str(signal_date.date()).encode()).hexdigest()[:8], 16) % 5 == 0:
            continue
        pos = session_positions[signal_date] + delay
        if pos >= len(market.sessions):
            continue
        trade_date = market.sessions[pos]
        for date, indices in [(trade_date, traditional), (trade_date + pd.Timedelta(days=1), crypto)]:
            if date in calendar_positions:
                schedule.setdefault(calendar_positions[date], []).append((row.reindex(cols).to_numpy(), indices, signal_date))
    rates = np.array([PROTOCOL["costs"]["crypto_one_way_bps" if j in crypto else "etf_one_way_bps"] for j in range(len(cols))]) * cost_multiplier
    units = np.zeros(len(cols))
    cash = float(PROTOCOL["initial_usd"])
    rows, fills = [], []
    for i, date in enumerate(dates):
        turnover, fees, count = 0.0, 0.0, 0
        # Opening marks never use the same day's closing prices.
        marks = np.where(np.isfinite(opening[i]), opening[i], prev_close[i])
        for wanted, indices, signal_date in schedule.get(i, []):
            batch_marks = marks.copy()
            if indices == crypto:
                batch_marks[traditional] = prev_close[i, traditional]
            nav = cash + float(np.nansum(units * batch_marks))
            tradable = [j for j in indices if np.isfinite(opening[i, j])]
            units, cash, amount, fee, n, events = execute_batch(
                units, cash, batch_marks, wanted, tradable, rates,
                PROTOCOL["costs"]["minimum_per_order_usd"] * cost_multiplier, max(100, nav * 0.01))
            turnover += amount / nav
            fees += fee
            count += n
            for j, side, notional, charge in events:
                fills.append({"signal_date": str(signal_date.date()), "fill_date": str(date.date()),
                              "ticker": cols[j], "side": side, "notional_usd": notional, "fee_usd": charge})
        nav = cash + float(np.nansum(units * close[i]))
        cash_weight = (cash + units[cols.index("BIL")] * close[i, cols.index("BIL")]) / nav
        rows.append((date, nav, turnover, fees, count, cash_weight))
    result = pd.DataFrame(rows, columns=["date", "nav", "turnover", "fees", "orders", "cash_weight"]).set_index("date")
    result["return"] = result.nav.pct_change().fillna(result.nav.iloc[0] / PROTOCOL["initial_usd"] - 1)
    return result, pd.DataFrame(fills)


def metrics(frame, start):
    f = frame.loc[start:]
    r = f["return"]
    wealth = (1 + r).cumprod()
    years = ((f.index[-1] - f.index[0]).days + 1) / 365.25
    peak = wealth.cummax().clip(lower=1)
    return {"cagr": float(wealth.iloc[-1] ** (1 / years) - 1),
            "max_drawdown": float((wealth / peak - 1).min()),
            "volatility": float(r.std() * np.sqrt(365.25)),
            "turnover_per_year": float(f.turnover.sum() / years),
            "orders_per_month": float(f.orders.sum() / (years * 12)),
            "mean_cash_weight": float(f.cash_weight.mean()),
            "total_return": float(wealth.iloc[-1] - 1)}


def bootstrap_excess(strategy, benchmark, start, draws=2000):
    a = strategy.loc[start:, "return"]
    b = benchmark.loc[start:, "return"]
    monthly = pd.concat([np.log1p(a), np.log1p(b)], axis=1).resample("ME").sum().to_numpy()
    rng = np.random.default_rng(20261021)
    out = []
    n = len(monthly)
    for _ in range(draws):
        starts = rng.integers(0, n, size=(n + 5) // 6)
        indices = np.concatenate([(x + np.arange(6)) % n for x in starts])[:n]
        annual = np.expm1(monthly[indices].mean(axis=0) * 12)
        out.append(annual[0] - annual[1])
    return {"lower_95": float(np.quantile(out, .025)), "upper_95": float(np.quantile(out, .975)),
            "note": "Paired circular six-month block bootstrap; descriptive, not corrected for strategy selection."}
