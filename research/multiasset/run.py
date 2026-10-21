"""Run the frozen comparison and save every variant, including failures."""
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from research.multiasset.engine import DATA, HERE, PROTOCOL, load_market, features, ridge_forecast, targets, simulate, metrics, bootstrap_excess


def run():
    manifest = json.loads((DATA / "manifest.json").read_text())
    protocol_hash = hashlib.sha256((HERE / "protocol.json").read_bytes()).hexdigest()
    if manifest["protocol_sha256"] != protocol_hash:
        raise ValueError("Protocol changed after inputs were fingerprinted")
    for filename, metadata in manifest["files"].items():
        if hashlib.sha256((DATA / filename).read_bytes()).hexdigest() != metadata["sha256"]:
            raise ValueError(f"Input fingerprint mismatch: {filename}")
    market = load_market()
    panel, x = features(market)
    pred, audit = ridge_forecast(panel, x)
    output = DATA / "results"
    output.mkdir(exist_ok=True)
    pd.DataFrame(audit).to_csv(output / "model-training-audit.csv", index=False)
    panel.assign(prediction=pred).to_csv(output / "signals-and-labels.csv", index=False)
    variants = {}
    target_frames = {}
    for strategy in ["spy", "static", "spy_btc", "price", "economic", "ml"]:
        t = targets(panel, pred, strategy)
        target_frames[strategy] = t
        variants[strategy] = (t, {})
        if strategy in PROTOCOL["candidates"]:
            variants[strategy + "__double_cost"] = (t, {"cost_multiplier": 2})
            variants[strategy + "__delay3"] = (t, {"delay": 3})
            variants[strategy + "__skip20"] = (t, {"skip": True})
            for group in PROTOCOL["group_budget"]:
                variants[strategy + "__without_" + group] = (targets(panel, pred, strategy, exclude=group), {})
    for name, args in [("lag120", {"lag": 120}), ("shorter", {"horizons": (50, 100, 200)}),
                       ("longer", {"horizons": (75, 150, 300)})]:
        alternate_panel, alternate_x = features(market, **args)
        alternate_pred, alternate_audit = ridge_forecast(alternate_panel, alternate_x)
        pd.DataFrame(alternate_audit).to_csv(output / f"model-training-audit-{name}.csv", index=False)
        for strategy in PROTOCOL["candidates"]:
            if name == "lag120" and strategy == "price":
                continue
            variants[strategy + "__" + name] = (targets(alternate_panel, alternate_pred, strategy), {})
    frames = {}
    for name, (target, kwargs) in variants.items():
        frame, fills = simulate(market, target, **kwargs)
        frames[name] = frame
        frame.to_csv(output / f"{name}-daily.csv")
        fills.to_csv(output / f"{name}-fills.csv", index=False)
        print(name, round(metrics(frame, "2013-01-02")["cagr"] * 100, 2), flush=True)
    results = {name: {period: metrics(frame, start) for period, start in PROTOCOL["periods"].items()}
               for name, frame in frames.items()}
    for name in PROTOCOL["candidates"]:
        result = results[name]
        result["excess_uncertainty"] = bootstrap_excess(frames[name], frames["spy"], "2013-01-02")
        for period in PROTOCOL["periods"]:
            result[period]["excess_cagr"] = result[period]["cagr"] - results["spy"][period]["cagr"]
        checks = {}
        for period in ["walk_forward_comparison", "recent"]:
            checks[period + "_return"] = result[period]["excess_cagr"] >= .03
            checks[period + "_drawdown"] = result[period]["max_drawdown"] >= results["spy"][period]["max_drawdown"]
        for stress in ["double_cost", "delay3"]:
            checks[stress] = results[name + "__" + stress]["walk_forward_comparison"]["cagr"] - results["spy"]["walk_forward_comparison"]["cagr"] >= .03
        result["screen_checks"] = checks
        result["screen_verdict"] = "PASS_REQUIRES_FURTHER_AUDIT" if all(checks.values()) else "REJECT_THIS_SPECIFICATION"
    annual = pd.DataFrame({name: (1 + frame["return"]).resample("YE").prod() - 1 for name, frame in frames.items()})
    annual.index = annual.index.year
    annual.to_csv(output / "annual-returns.csv", index_label="year")
    rolling = []
    for year in range(2013, 2024):
        end = f"{year+2}-12-31"
        if pd.Timestamp(end) > market.close.index[-1]:
            continue
        for name in ["spy", *PROTOCOL["candidates"]]:
            item = metrics(frames[name].loc[:end], f"{year}-01-01")
            rolling.append({"strategy": name, "start_year": year, **item})
    pd.DataFrame(rolling).to_csv(output / "rolling-three-years.csv", index=False)
    # Reduce SPY's risk ex post for a diagnostic, never boost strategy leverage.
    risk_matched = {}
    for name in PROTOCOL["candidates"]:
        start = "2013-01-02"
        ratio = min(1, results[name]["walk_forward_comparison"]["volatility"] / results["spy"]["walk_forward_comparison"]["volatility"])
        spy = frames["spy"].loc[start:, "return"]
        cash = market.close.BIL.pct_change().reindex(spy.index).fillna(0)
        r = ratio * spy + (1-ratio) * cash
        years = ((r.index[-1] - r.index[0]).days+1)/365.25
        risk_matched[name] = {"spy_fraction": ratio, "benchmark_cagr": float(np.expm1(np.log1p(r).sum()/years)),
                              "note": "Ex-post volatility-matched daily blend; diagnostic only, no rebalancing costs."}
    summary = {"created_at": pd.Timestamp.now(tz="UTC").isoformat(), "last_price_date": str(market.close.index[-1].date()),
               "protocol_sha256": protocol_hash,
               "variant_count": len(variants), "metrics": results, "risk_matched_diagnostic": risk_matched,
               "qualification": "No live qualification from this rejection screen; tax, actual instruments and vintage timing remain unverified."}
    (output / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False))
    for name, t in target_frames.items():
        t.to_csv(output / f"{name}-targets.csv", index_label="signal_date")
    return summary


if __name__ == "__main__":
    run()
