#!/usr/bin/env python3
"""Historical signal replay for the current Aurel3 engine.

This is not a fully archived news replay. It is a curated scenario replay that:
- uses historical price/volume snapshots from Yahoo Finance
- constructs theme-consistent interpreted source items
- runs the current Aurel3 signal engine against those inputs
- grades the generated action against forward returns

It is intentionally closer to the live engine than the old static-label proxy.
"""

from __future__ import annotations

import argparse
import json
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import yfinance as yf

import signals as signals_mod
from market import get_sector as live_get_sector
from reviews import build_recommendation_review
from taxonomy import THEME_TAXONOMY

CASES_PATH = Path(__file__).parent / "data" / "historical_replay_cases.json"
HOLDOUT_IDS_PATH = Path(__file__).parent / "data" / "historical_replay_holdout_ids.json"
RESULTS_PATH = Path(__file__).parent / "data" / "historical_replay_engine_results.json"

THEME_LABEL_TO_ID = {
    meta["label"]: theme_id
    for theme_id, meta in THEME_TAXONOMY.items()
}

THEME_DEFAULTS: dict[str, dict[str, Any]] = {
    "ai_compute_infrastructure": {
        "event_type": "ai_infrastructure_demand",
        "confidence": "medium",
        "actionability": "potentially_actionable",
        "durability": "high",
        "support_items": 2,
        "beneficiary_sectors": ["semiconductors", "data centers", "power electronics"],
        "hurt_sectors": [],
        "summary": "AI compute and data-center demand support direct infrastructure beneficiaries.",
        "reasoning_notes": "Durable capex theme, but fresh company-specific follow-through still matters.",
        "peer_tickers": ["NVDA", "AVGO", "ANET", "SMCI", "INTC"],
    },
    "eu_defense_rearmament": {
        "event_type": "defense_spending_policy",
        "confidence": "medium",
        "actionability": "potentially_actionable",
        "durability": "high",
        "support_items": 2,
        "beneficiary_sectors": ["defense", "aerospace", "munitions"],
        "hurt_sectors": [],
        "summary": "Defense rearmament policy and procurement support direct European defense beneficiaries.",
        "reasoning_notes": "Structural theme, but buy timing still depends on clean market confirmation.",
        "peer_tickers": ["RHM.DE", "BAESY", "RTX", "LDO.MI"],
    },
    "energy_geopolitical_supply_risk": {
        "event_type": "energy_supply_risk",
        "confidence": "medium",
        "actionability": "potentially_actionable",
        "durability": "medium",
        "support_items": 2,
        "beneficiary_sectors": ["energy", "oil services"],
        "hurt_sectors": ["airlines", "transportation", "chemicals"],
        "summary": "Geopolitical tension and shipping disruption support direct upstream energy beneficiaries.",
        "reasoning_notes": "Clear transmission path, but commentary-heavy setups should stay below buy-now without strong confirmation.",
        "peer_tickers": ["XOM", "CVX", "OXY", "SLB", "HAL", "SHEL"],
    },
    "banking_rates_credit": {
        "event_type": "banking_rates_credit",
        "confidence": "high",
        "actionability": "actionable",
        "durability": "medium",
        "support_items": 1,
        "beneficiary_sectors": ["banks", "consumer finance"],
        "hurt_sectors": [],
        "summary": "Rates and credit setup creates a direct repricing opportunity in lenders with clean sensitivity.",
        "reasoning_notes": "This theme is most investable when company sensitivity is direct and price confirms.",
        "peer_tickers": ["JPM"],
    },
    "healthcare_commercialization": {
        "event_type": "healthcare_regulatory_commercialization",
        "confidence": "medium",
        "actionability": "potentially_actionable",
        "durability": "medium",
        "support_items": 1,
        "beneficiary_sectors": ["biotech", "pharmaceuticals"],
        "hurt_sectors": [],
        "summary": "Commercialization or regulatory progress creates a company-specific healthcare catalyst.",
        "reasoning_notes": "Healthcare should only reach buy-now when the company-specific transmission path is clear.",
        "peer_tickers": ["LLY", "NVO", "PFE", "MRNA"],
    },
    "battery_storage_commercialization": {
        "event_type": "battery_storage_commercialization",
        "confidence": "medium",
        "actionability": "interesting_but_early",
        "durability": "medium",
        "support_items": 1,
        "beneficiary_sectors": ["batteries", "EV supply chain"],
        "hurt_sectors": [],
        "summary": "Battery and storage commercialization can reprice direct technology beneficiaries.",
        "reasoning_notes": "Speculative battery names need unusually clean commercialization and market confirmation.",
        "peer_tickers": ["QS", "LCID", "NIO"],
    },
    "commodities_resource_supply_shock": {
        "event_type": "resource_supply_shock",
        "confidence": "medium",
        "actionability": "actionable",
        "durability": "medium",
        "support_items": 2,
        "beneficiary_sectors": ["mining", "energy", "materials"],
        "hurt_sectors": ["manufacturing"],
        "summary": "Resource supply shock supports direct commodity and extraction beneficiaries.",
        "reasoning_notes": "Broad commodity enthusiasm should not be enough without direct transmission and confirmation.",
        "peer_tickers": ["CCJ", "UUUU"],
    },
    "critical_materials_battery_inputs": {
        "event_type": "critical_materials_supply_chain",
        "confidence": "medium",
        "actionability": "potentially_actionable",
        "durability": "medium",
        "support_items": 2,
        "beneficiary_sectors": ["critical minerals", "materials"],
        "hurt_sectors": [],
        "summary": "Critical materials bottlenecks support select mining and battery-input beneficiaries.",
        "reasoning_notes": "Directness matters more than broad thematic scarcity.",
        "peer_tickers": ["FCX", "ALB", "MP"],
    },
    "agriculture_food_supply": {
        "event_type": "agriculture_input_supply_shock",
        "confidence": "medium",
        "actionability": "potentially_actionable",
        "durability": "medium",
        "support_items": 2,
        "beneficiary_sectors": ["fertilizers", "agricultural inputs"],
        "hurt_sectors": ["food producers", "transportation"],
        "summary": "Agricultural input disruption supports fertilizer producers and raises food supply concerns.",
        "reasoning_notes": "Useful only when the supply-shock transmission path is clear.",
        "peer_tickers": ["MOS", "CF", "NTR", "DE"],
    },
    "infrastructure_industrial_capex": {
        "event_type": "industrial_capex_support",
        "confidence": "medium",
        "actionability": "interesting_but_early",
        "durability": "high",
        "support_items": 1,
        "beneficiary_sectors": ["industrial capex", "construction", "utilities infrastructure"],
        "hurt_sectors": [],
        "summary": "Infrastructure and industrial capex support direct contractors and equipment suppliers.",
        "reasoning_notes": "Broad capex optimism should stay below buy-now unless the company linkage is specific.",
        "peer_tickers": ["GEV", "CAT", "NUE", "BA"],
    },
    "ipo_listing_momentum": {
        "event_type": "ipo_listing_momentum",
        "confidence": "high",
        "actionability": "interesting_but_early",
        "durability": "medium",
        "support_items": 2,
        "beneficiary_sectors": ["ipo market", "growth listings"],
        "hurt_sectors": [],
        "summary": "Major IPO activity supports listing momentum and adjacent comparables.",
        "reasoning_notes": "Usually indirect and should remain below buy-now unless the listed beneficiary is exceptionally clean.",
        "peer_tickers": ["ARM", "RKLB"],
    },
    "earnings_guidance_momentum": {
        "event_type": "earnings_guidance_update",
        "confidence": "high",
        "actionability": "actionable",
        "durability": "medium",
        "support_items": 1,
        "beneficiary_sectors": ["earnings-driven single names"],
        "hurt_sectors": [],
        "summary": "Fresh earnings or guidance reset is a direct company-specific catalyst.",
        "reasoning_notes": "The sign of guidance matters; generic earnings commentary should not qualify.",
        "peer_tickers": [],
    },
    "m_and_a_corporate_action": {
        "event_type": "m_and_a_deal_speculation",
        "confidence": "medium",
        "actionability": "actionable",
        "durability": "low",
        "support_items": 2,
        "beneficiary_sectors": ["event-driven equities"],
        "hurt_sectors": [],
        "summary": "Deal reports or closing milestones create event-driven repricing in named parties.",
        "reasoning_notes": "High actionability but low durability until confirmed.",
        "peer_tickers": ["GSAT", "AMZN", "EL", "RVYL"],
    },
}

CASE_OVERRIDES: dict[str, dict[str, Any]] = {
    "case_intc_ai_2025_03_18": {"role": "secondary", "confidence": "medium"},
    "case_panw_ai_2025_05_12": {"role": "secondary", "confidence": "medium"},
    "case_rtx_defense_2025_03_10": {"role": "secondary"},
    "case_arm_ipo_2025_03_05": {"role": "direct", "actionability": "interesting_but_early"},
    "case_ba_infra_2025_04_01": {"role": "secondary"},
    "case_nue_infra_2025_06_01": {"role": "secondary"},
    "case_de_agri_2025_03_22": {"role": "secondary"},
    "case_lcid_battery_2025_04_07": {"role": "direct", "actionability": "interesting_but_early"},
    "case_qs_battery_2025_03_14": {"role": "direct", "actionability": "interesting_but_early"},
    "case_nio_battery_2025_02_20": {"role": "direct", "actionability": "interesting_but_early"},
    "case_pfe_health_2025_05_05": {"role": "secondary"},
    "case_mrna_health_2025_03_26": {"role": "secondary"},
    "case_regn_healthcare_2024_06_03": {"actionability": "actionable", "confidence": "high"},
    "case_vrtx_healthcare_2024_04_30": {"actionability": "actionable", "confidence": "high"},
}


def _load_holdout_ids() -> set[str]:
    with open(HOLDOUT_IDS_PATH) as f:
        return set(json.load(f))


def _load_cases(split: str = "full") -> list[dict]:
    with open(CASES_PATH) as f:
        cases = json.load(f)

    if split == "full":
        return cases

    holdout_ids = _load_holdout_ids()
    if split == "holdout":
        return [case for case in cases if case["id"] in holdout_ids]
    if split == "tuning":
        return [case for case in cases if case["id"] not in holdout_ids]
    raise ValueError(f"Unsupported split: {split}")


def _horizon_days(expected_horizon: str) -> int:
    return {
        "1-3 days": 3,
        "1-2 weeks": 14,
        "1-3 months": 45,
        "3+ months / structural": 90,
    }.get(expected_horizon, 14)


def _first_valid_close(ticker: str, start: datetime, end: datetime) -> tuple[float, float] | None:
    history = yf.Ticker(ticker).history(
        start=start.date().isoformat(),
        end=end.date().isoformat(),
        auto_adjust=True,
    )
    if history is None or history.empty:
        return None
    return float(history["Close"].iloc[0]), float(history["Close"].iloc[-1])


def _historical_market_snapshot(ticker: str, as_of: datetime) -> dict | None:
    start = (as_of - timedelta(days=120)).date().isoformat()
    end = (as_of + timedelta(days=7)).date().isoformat()
    hist = yf.Ticker(ticker).history(start=start, end=end, auto_adjust=True)
    if hist is None or hist.empty:
        return None

    hist = hist.sort_index()
    eligible = hist[hist.index.tz_localize(None) >= as_of]
    if eligible.empty:
        return None
    anchor_idx = eligible.index[0]
    anchor_pos = hist.index.get_loc(anchor_idx)
    prior = hist.iloc[: anchor_pos + 1]
    if prior.empty:
        return None

    current = prior.iloc[-1]
    prev_close = float(prior["Close"].iloc[-2]) if len(prior) >= 2 else float(current["Close"])
    avg_volume = float(prior["Volume"].tail(60).mean()) if len(prior) >= 5 else float(current["Volume"])
    ema_20 = float(prior["Close"].ewm(span=20).mean().iloc[-1]) if len(prior) >= 20 else None
    ema_50 = float(prior["Close"].ewm(span=50).mean().iloc[-1]) if len(prior) >= 50 else None
    avg_daily_move = round(float(prior["Close"].pct_change().dropna().tail(20).abs().mean()), 4) if len(prior) >= 20 else None
    current_price = float(current["Close"])
    today_volume = float(current["Volume"])
    volume_ratio = round(today_volume / avg_volume, 2) if avg_volume > 0 else 0
    change_pct = (current_price / prev_close) - 1 if prev_close > 0 else 0

    above_ema20 = current_price > ema_20 if ema_20 else None
    above_ema50 = current_price > ema_50 if ema_50 else None
    if above_ema20 and above_ema50:
        trend = "strong_up"
    elif above_ema20:
        trend = "up"
    elif above_ema20 is False and above_ema50 is False:
        trend = "down"
    elif above_ema50 is False:
        trend = "weak"
    else:
        trend = "unknown"

    return {
        "price": round(current_price, 2),
        "change_pct": round(change_pct, 4),
        "volume": int(today_volume),
        "avg_volume": int(avg_volume),
        "volume_ratio": volume_ratio,
        "market_cap": 0,
        "dollar_volume": round(avg_volume * current_price, 0) if avg_volume else 0,
        "ema_20": round(ema_20, 2) if ema_20 else None,
        "ema_50": round(ema_50, 2) if ema_50 else None,
        "avg_daily_move": avg_daily_move,
        "trend": trend,
        "sector": None,
        "is_crypto": False,
    }


def _case_profile(case: dict) -> dict[str, Any]:
    theme_id = THEME_LABEL_TO_ID[case["theme_driver"]]
    base = dict(THEME_DEFAULTS[theme_id])
    base.update(case.get("replay_profile", {}))
    base.update(CASE_OVERRIDES.get(case["id"], {}))
    base.setdefault("role", "direct")
    base["theme_id"] = theme_id
    base["theme_label"] = case["theme_driver"]
    return base


def _candidate_tickers(case: dict, profile: dict[str, Any]) -> list[str]:
    tickers = [case["ticker"]]
    for peer in profile.get("peer_tickers", []):
        if peer not in tickers:
            tickers.append(peer)
    return tickers


def _build_interpreted_items(case: dict, profile: dict[str, Any]) -> list[dict]:
    tickers = _candidate_tickers(case, profile)
    target = case["ticker"]
    role = profile.get("role", "direct")
    directs: list[str]
    secondaries: list[str]
    peers = [t for t in tickers if t != target]
    if role == "secondary":
        directs = peers[:2]
        secondaries = [target] + peers[2:4]
    else:
        directs = [target] + peers[:2]
        secondaries = peers[2:4]

    count = int(profile.get("support_items", 1))
    items = []
    event_date = datetime.fromisoformat(case["date"]).replace(hour=12)
    for idx in range(count):
        ts = (event_date + timedelta(hours=idx)).isoformat()
        confidence = profile.get("confidence", "medium")
        if idx > 0 and confidence == "high":
            confidence = "medium"
        # Distinct summaries per support item: these model independent
        # articles, and identical summaries would (correctly) be collapsed
        # by the engine's syndication dedup.
        summary = profile["summary"] if idx == 0 else f"{profile['summary']} (independent source {idx+1})"
        items.append({
            "source_item_id": f"replay::{case['id']}::{idx+1}",
            "market_relevant": True,
            "event_type": profile["event_type"],
            "theme_id": profile["theme_id"],
            "theme_label": profile["theme_label"],
            "summary": summary,
            "beneficiary_sectors": profile["beneficiary_sectors"],
            "hurt_sectors": profile["hurt_sectors"],
            "direct_beneficiaries": directs,
            "secondary_beneficiaries": secondaries,
            "time_horizon": case["expected_horizon"],
            "durability": profile["durability"],
            "confidence": confidence,
            "actionability": profile["actionability"],
            "reasoning_notes": profile["reasoning_notes"],
            "title": f"{profile['theme_label']} replay item {idx+1}",
            "timestamp": ts,
            "publisher": "Aurel3 replay",
            "url": f"internal://replay/{case['id']}/{idx+1}",
            "label": next(
                (lbl for lbl in THEME_TAXONOMY[profile["theme_id"]].get("match_labels", set())),
                "",
            ),
        })
    return items


@contextmanager
def _patched_engine(market_snapshots: dict[str, dict], sector_map: dict[str, str | None]):
    old_get_stock_data = signals_mod.get_stock_data
    old_get_sector = signals_mod.get_sector
    signals_mod.get_stock_data = lambda ticker: market_snapshots.get(ticker)
    signals_mod.get_sector = lambda ticker: sector_map.get(ticker)
    try:
        yield
    finally:
        signals_mod.get_stock_data = old_get_stock_data
        signals_mod.get_sector = old_get_sector


def _engine_case_result(case: dict) -> dict:
    as_of = datetime.fromisoformat(case["date"])
    profile = _case_profile(case)
    interpreted_items = _build_interpreted_items(case, profile)
    candidate_tickers = _candidate_tickers(case, profile)

    market_snapshots = {
        ticker: _historical_market_snapshot(ticker, as_of)
        for ticker in candidate_tickers
    }
    market_snapshots = {k: v for k, v in market_snapshots.items() if v}
    if case["ticker"] not in market_snapshots:
        return {**case, "status": "skipped", "reason": "No historical market snapshot available"}

    sector_map = {
        ticker: live_get_sector(ticker)
        for ticker in market_snapshots
    }
    source_items = {
        "social": [],
        "raw_social": [],
        "news": interpreted_items,
        "raw_news": interpreted_items,
        "events": [],
    }

    with _patched_engine(market_snapshots, sector_map):
        _themes, recommendations = signals_mod.generate_signal_scan(source_items)

    ticker = case["ticker"]
    target_rec = next((rec for rec in recommendations if rec["ticker"] == ticker), None)
    theme_top = next((rec for rec in recommendations if rec["theme_driver"] == case["theme_driver"]), None)

    if target_rec:
        generated_action = target_rec["action"]
        generated_conf = target_rec["confirmation_state"]
        generated_confidence = target_rec["confidence"]
        reference_price = target_rec.get("reference_price") or market_snapshots[ticker]["price"]
        why_now = target_rec.get("why_now")
    else:
        generated_action = "no_signal"
        generated_conf = "none"
        generated_confidence = "low"
        reference_price = market_snapshots[ticker]["price"]
        why_now = None

    review_end = as_of + timedelta(days=_horizon_days(case["expected_horizon"]) + 7)
    prices = _first_valid_close(ticker, as_of - timedelta(days=3), review_end)
    if not prices:
        return {**case, "status": "skipped", "reason": "No forward price history available"}
    _, review_price = prices

    review_recommendation = {
        "id": case["id"],
        "ticker": ticker,
        "theme_driver": case["theme_driver"],
        "action": "watch_for_confirmation" if generated_action == "no_signal" else generated_action,
        "confirmation_state": generated_conf,
        "confidence": generated_confidence,
        "expected_horizon": case["expected_horizon"],
        "reference_price": reference_price,
    }
    review = build_recommendation_review(
        review_recommendation,
        review_price,
        avg_daily_move=market_snapshots[ticker].get("avg_daily_move"),
    )

    top_ticker = theme_top["ticker"] if theme_top else None
    top_review = None
    if theme_top:
        top_prices = _first_valid_close(top_ticker, as_of - timedelta(days=3), review_end)
        if top_prices:
            top_reference_price, top_review_price = top_prices
            top_recommendation = {
                "id": f"{case['id']}::{top_ticker}",
                "ticker": top_ticker,
                "theme_driver": case["theme_driver"],
                "action": theme_top["action"],
                "confirmation_state": theme_top["confirmation_state"],
                "confidence": theme_top["confidence"],
                "expected_horizon": case["expected_horizon"],
                "reference_price": top_reference_price,
            }
            top_review = build_recommendation_review(
                top_recommendation,
                top_review_price,
                avg_daily_move=market_snapshots.get(top_ticker, {}).get("avg_daily_move"),
            )

    return {
        **case,
        "status": "reviewed",
        "engine_action": generated_action,
        "engine_confirmation_state": generated_conf,
        "engine_confidence": generated_confidence,
        "engine_why_now": why_now,
        "theme_top_ticker": theme_top["ticker"] if theme_top else None,
        "target_survived": bool(target_rec),
        "reference_price": round(reference_price, 2),
        "review_price": round(review_price, 2),
        "forward_return_pct": review["forward_return_pct"],
        "outcome": review["outcome"],
        "summary": review["summary"],
        "theme_top_action": theme_top["action"] if theme_top else None,
        "theme_top_confirmation_state": theme_top["confirmation_state"] if theme_top else None,
        "theme_top_confidence": theme_top["confidence"] if theme_top else None,
        "theme_top_forward_return_pct": top_review["forward_return_pct"] if top_review else None,
        "theme_top_outcome": top_review["outcome"] if top_review else None,
    }


def diagnose_cases(split: str, tickers: list[str]) -> list[dict]:
    wanted = {ticker.upper() for ticker in tickers}
    diagnostics: list[dict] = []

    for case in _load_cases(split):
        if case["ticker"].upper() not in wanted:
            continue

        as_of = datetime.fromisoformat(case["date"])
        profile = _case_profile(case)
        interpreted_items = _build_interpreted_items(case, profile)
        candidate_tickers = _candidate_tickers(case, profile)
        market_snapshots = {
            ticker: _historical_market_snapshot(ticker, as_of)
            for ticker in candidate_tickers
        }
        market_snapshots = {k: v for k, v in market_snapshots.items() if v}
        sector_map = {
            ticker: live_get_sector(ticker)
            for ticker in market_snapshots
        }
        source_items = {
            "social": [],
            "raw_social": [],
            "news": interpreted_items,
            "raw_news": interpreted_items,
            "events": [],
        }

        with _patched_engine(market_snapshots, sector_map):
            candidates = signals_mod._candidate_universe(source_items)

        target = next((item for item in candidates if item["ticker"] == case["ticker"]), None)
        if not target:
            diagnostics.append({
                "ticker": case["ticker"],
                "theme_driver": case["theme_driver"],
                "date": case["date"],
                "diagnostic": "not_in_candidate_universe",
            })
            continue

        data = market_snapshots.get(case["ticker"])
        if not data:
            diagnostics.append({
                "ticker": case["ticker"],
                "theme_driver": case["theme_driver"],
                "date": case["date"],
                "diagnostic": "missing_market_snapshot",
            })
            continue

        target["sector_hint"] = sector_map.get(case["ticker"]) or ""
        related_news = signals_mod._related_news_items(target, source_items["news"])
        support = signals_mod._support_profile(case["ticker"], related_news)
        confirmation = signals_mod._confirmation_state(data)
        sentiment = {
            "sentiment": "bullish",
            "confidence": 0.7 if target.get("signal_direct") else 0.5,
            "reason": target.get("signal_summary") or "Interpreted market catalyst",
            "momentum": "steady",
            "bullish_points": 3 if target.get("signal_direct") else 2,
            "bearish_points": 0,
        }
        crowding = signals_mod._crowding_state(
            data,
            target.get("mention_change", 0),
            sentiment.get("bullish_points", 0),
        )
        confidence = signals_mod._merged_confidence_label(sentiment, confirmation, crowding, support)
        action = signals_mod._recommendation_action(
            profile["theme_id"],
            confirmation,
            crowding,
            confidence,
            data,
            sentiment,
            support,
        )

        diagnostics.append({
            "ticker": case["ticker"],
            "theme_driver": case["theme_driver"],
            "date": case["date"],
            "benchmark_action": case["action"],
            "computed_action": action,
            "confirmation": confirmation,
            "crowding": crowding,
            "confidence": confidence,
            "data": {
                "trend": data.get("trend"),
                "change_pct": data.get("change_pct"),
                "volume_ratio": data.get("volume_ratio"),
                "dollar_volume": data.get("dollar_volume"),
                "price": data.get("price"),
            },
            "support": support,
        })

    return diagnostics


def _results_path(split: str) -> Path:
    if split == "full":
        return RESULTS_PATH
    suffix = f"_{split}"
    return RESULTS_PATH.with_name(f"{RESULTS_PATH.stem}{suffix}{RESULTS_PATH.suffix}")


def run_engine_replay(split: str = "full") -> tuple[list[dict], dict]:
    results = []
    summary = {
        "total_cases": 0,
        "skipped": 0,
        "worked": 0,
        "partial": 0,
        "failed": 0,
        "late": 0,
        "buy_now": 0,
        "watch_for_confirmation": 0,
        "hold_not_fresh_buy": 0,
        "no_signal": 0,
        "exact_action_matches": 0,
        "missed_10pct": 0,
        "missed_20pct": 0,
        "theme_top_reviewed": 0,
        "theme_top_worked": 0,
        "theme_top_partial": 0,
        "theme_top_failed": 0,
        "theme_top_late": 0,
    }

    for case in _load_cases(split):
        result = _engine_case_result(case)
        results.append(result)
        if result["status"] == "skipped":
            summary["skipped"] += 1
            continue
        summary["total_cases"] += 1
        summary[result["outcome"]] += 1
        summary[result["engine_action"]] = summary.get(result["engine_action"], 0) + 1
        if result["engine_action"] == case["action"]:
            summary["exact_action_matches"] += 1
        if result["engine_action"] in ("no_signal", "watch_for_confirmation", "hold_not_fresh_buy"):
            if result["forward_return_pct"] >= 0.10:
                summary["missed_10pct"] += 1
            if result["forward_return_pct"] >= 0.20:
                summary["missed_20pct"] += 1
        if result.get("theme_top_outcome"):
            summary["theme_top_reviewed"] += 1
            summary[f"theme_top_{result['theme_top_outcome']}"] += 1

    _results_path(split).write_text(json.dumps(results, indent=2))
    return results, summary


def _print_engine(results: list[dict], summary: dict, split: str) -> None:
    print(f"Historical Signal Replay (engine, split={split})")
    print(f"  Cases reviewed: {summary['total_cases']} | skipped: {summary['skipped']}")
    print(
        "  Outcomes: "
        f"worked={summary.get('worked', 0)}, "
        f"partial={summary.get('partial', 0)}, "
        f"failed={summary.get('failed', 0)}, "
        f"late={summary.get('late', 0)}"
    )
    print(
        "  Engine actions: "
        f"buy_now={summary.get('buy_now', 0)}, "
        f"watch_for_confirmation={summary.get('watch_for_confirmation', 0)}, "
        f"hold_not_fresh_buy={summary.get('hold_not_fresh_buy', 0)}, "
        f"no_signal={summary.get('no_signal', 0)}"
    )
    print(f"  Exact action matches vs benchmark labels: {summary['exact_action_matches']}/{summary['total_cases']}")
    print(
        "  Missed opportunities: "
        f">=10% move while not buy_now = {summary['missed_10pct']}, "
        f">=20% move while not buy_now = {summary['missed_20pct']}"
    )
    print(
        "  Theme-top outcomes: "
        f"reviewed={summary['theme_top_reviewed']}, "
        f"worked={summary['theme_top_worked']}, "
        f"partial={summary['theme_top_partial']}, "
        f"failed={summary['theme_top_failed']}, "
        f"late={summary['theme_top_late']}"
    )
    print("")
    for result in results:
        if result["status"] == "skipped":
            print(f"  {result['ticker']} | skipped | {result['reason']}")
            continue
        print(
            f"  {result['ticker']} | engine={result['engine_action']} | benchmark={result['action']} | "
            f"{result['forward_return_pct']:+.1%} | {result['outcome']}"
        )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Aurel3 historical replay.")
    parser.add_argument(
        "--split",
        choices=("full", "tuning", "holdout"),
        default="full",
        help="Which curated replay split to run.",
    )
    parser.add_argument(
        "--diagnose",
        nargs="*",
        default=[],
        help="Optional list of tickers to inspect instead of running the full replay.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    if args.diagnose:
        diagnostics = diagnose_cases(args.split, args.diagnose)
        print(json.dumps(diagnostics, indent=2))
        return
    results, summary = run_engine_replay(args.split)
    _print_engine(results, summary, args.split)


if __name__ == "__main__":
    main()
