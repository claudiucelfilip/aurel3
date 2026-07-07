"""Postmortem review helpers for Aurel3."""

from __future__ import annotations

import math
from datetime import datetime, timezone

from state import make_id, utc_now_iso


def build_closed_position_review(position: dict) -> dict:
    pnl_pct = position.get("pnl_pct", 0)
    outcome = "worked" if pnl_pct > 0.03 else "partial" if pnl_pct >= 0 else "failed"
    if outcome == "worked":
        failure_point = "other"
        lesson = "The original thesis held and the exit captured a favorable move."
    elif outcome == "partial":
        failure_point = "late_exit"
        lesson = "The thesis was not fully wrong, but the realized edge was limited."
    else:
        failure_point = "market_confirmation"
        lesson = "The thesis did not produce durable confirmation or the exit lagged deterioration."

    return {
        "id": make_id("review", position.get("ticker", "position")),
        "ticker": position.get("ticker"),
        "entry_date": position.get("entry_date"),
        "exit_date": position.get("closed_date"),
        "entry_price": position.get("entry_price"),
        "exit_price": position.get("sell_price"),
        "realized_pnl": {
            "pnl_pct": pnl_pct,
            "pnl_amount": position.get("pnl_dollar", 0),
            "currency": position.get("currency", "USD"),
        },
        "holding_period": f"{position.get('days_held', 0)} days",
        "original_theme_driver": position.get("original_theme_driver"),
        "original_reason_for_entry": position.get("original_reason_for_entry"),
        "expected_horizon": position.get("expected_horizon"),
        "thesis_outcome": outcome,
        "failure_point": failure_point,
        "what_changed": (
            position.get("close_reason")
            or position.get("current_action_reason")
            or "Position was closed after thesis review or manual exit."
        ),
        "lesson": lesson,
        "spec_change_candidate": False,
        "exceptional_case": False,
        "linked_watchlist_id": position.get("id"),
        "reviewed_at": utc_now_iso(),
    }


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts)
    except Exception:
        return None


def _required_age_days(expected_horizon: str | None) -> int:
    mapping = {
        "1-3 days": 3,
        "1-2 weeks": 14,
        "1-3 months": 30,
        "3+ months / structural": 90,
    }
    return mapping.get(expected_horizon or "", 14)


def recommendation_is_mature(recommendation: dict, now: datetime | None = None) -> bool:
    now = now or datetime.now(timezone.utc)
    created = _parse_iso(recommendation.get("timestamp"))
    if not created:
        return False
    age_days = (now - created).total_seconds() / 86400
    return age_days >= _required_age_days(recommendation.get("expected_horizon"))


def build_recommendation_review(
    recommendation: dict,
    current_price: float,
    benchmark_return: float | None = None,
    avg_daily_move: float | None = None,
) -> dict:
    reference_price = recommendation.get("reference_price") or 0
    pnl_pct = ((current_price / reference_price) - 1) if reference_price else 0
    original_action = recommendation.get("action")

    # Judge excess return over the benchmark, scaled to the name's own
    # volatility and the stated horizon — raw fixed thresholds called every
    # buy a win in a rising tape and ignored horizon entirely.
    excess_pct = pnl_pct - benchmark_return if benchmark_return is not None else pnl_pct
    horizon_days = _required_age_days(recommendation.get("expected_horizon"))
    adm = avg_daily_move or 0.02
    meaningful_move = max(0.03, adm * math.sqrt(horizon_days))

    if original_action in ("buy_now", "early_accumulation"):
        if excess_pct >= meaningful_move:
            outcome = "worked"
            note = "The buy recommendation beat the benchmark by a meaningful margin for this name and horizon."
        elif excess_pct >= 0:
            outcome = "partial"
            note = "The signal edged out the benchmark but the move was weaker than intended."
        else:
            outcome = "failed"
            note = "The buy recommendation did not beat the benchmark over the intended horizon."
    else:
        if excess_pct >= meaningful_move * 1.5:
            outcome = "late"
            note = "The signal outran the benchmark strongly later, suggesting the action was too conservative."
        elif excess_pct >= 0:
            outcome = "partial"
            note = "The watch-style signal was directionally fine but not strong enough to justify upgrading with confidence."
        else:
            outcome = "worked"
            note = "Keeping the signal below buy-now was reasonable given the later weak outcome."

    return {
        "id": make_id("sigreview", recommendation.get("ticker", "signal")),
        "recommendation_id": recommendation.get("id"),
        "ticker": recommendation.get("ticker"),
        "theme_driver": recommendation.get("theme_driver"),
        "original_action": original_action,
        "original_confirmation_state": recommendation.get("confirmation_state"),
        "original_confidence": recommendation.get("confidence"),
        "expected_horizon": recommendation.get("expected_horizon"),
        "reference_price": reference_price,
        "review_price": current_price,
        "forward_return_pct": round(pnl_pct, 4),
        "benchmark_return_pct": round(benchmark_return, 4) if benchmark_return is not None else None,
        "excess_return_pct": round(excess_pct, 4),
        "meaningful_move_threshold": round(meaningful_move, 4),
        "outcome": outcome,
        "summary": note,
        "spec_change_candidate": outcome in ("failed", "late"),
        "reviewed_at": utc_now_iso(),
    }
