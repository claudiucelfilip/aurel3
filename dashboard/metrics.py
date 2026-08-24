"""Read-only performance aggregation for the Aurel3 dashboard.

Never writes to data/ — the signal cycle owns those files. Price lookups go
through market.py and are cached in-process, so a page load stays cheap even
though the equity curve walks every buy-lane recommendation.
"""

from __future__ import annotations

import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from state import (  # noqa: E402
    load_closed_reviews,
    load_recommendation_history,
    load_recommendation_reviews,
    load_theme_events,
)

BUY_LANE = ("buy_now", "early_accumulation")

# The tightened entry gate + managed exits (take-profit / time stop) went live
# on this date; everything before it is the old fire-and-forget regime and is
# scored separately. See REPLAY_LIVE_BUYS_2026_08.md.
MANAGED_EXIT_START = "2026-08-18"

DEFAULT_TAKE_PROFIT_PCT = 0.04
DEFAULT_MAX_HOLD_DAYS = 10

DESK_ORDERS_PATH = REPO_ROOT / "data" / "desk" / "orders.json"

ACTIVE_CANDIDATE_STATUSES = {"open", "queued", "awaiting_approval"}


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _mean(values: List[float]) -> Optional[float]:
    return sum(values) / len(values) if values else None


def load_desk_orders() -> List[dict]:
    import json

    if not DESK_ORDERS_PATH.exists():
        return []
    try:
        with open(DESK_ORDERS_PATH) as handle:
            return json.load(handle)
    except Exception:
        return []


def load_unique_recommendations() -> List[dict]:
    """Flatten the batch history into one record per recommendation id.

    Each cycle re-emits still-active recommendations, so the same id appears in
    many batches; the newest copy wins because it carries the latest status.
    """
    by_id: Dict[str, dict] = {}
    for batch in load_recommendation_history():
        for rec in batch.get("recommendations") or []:
            rec_id = rec.get("id")
            if rec_id:
                by_id[rec_id] = rec
    return sorted(
        by_id.values(),
        key=lambda rec: rec.get("timestamp") or "",
        reverse=True,
    )


def latest_batch() -> Optional[dict]:
    history = load_recommendation_history()
    return history[-1] if history else None


def reviews_by_recommendation() -> Dict[str, dict]:
    """Newest review per recommendation id."""
    latest: Dict[str, dict] = {}
    for review in load_recommendation_reviews():
        rec_id = review.get("recommendation_id")
        if not rec_id:
            continue
        current = latest.get(rec_id)
        if current is None or (review.get("reviewed_at") or "") > (current.get("reviewed_at") or ""):
            latest[rec_id] = review
    return latest


# --- price cache -----------------------------------------------------------

_PRICE_LOCK = threading.Lock()
_PRICE_CACHE: Dict[Tuple, Tuple[float, Any]] = {}
_PRICE_TTL_SECONDS = 900


def _cached(key: Tuple, producer) -> Any:
    now = time.time()
    with _PRICE_LOCK:
        hit = _PRICE_CACHE.get(key)
        if hit and now - hit[0] < _PRICE_TTL_SECONDS:
            return hit[1]
    try:
        value = producer()
    except Exception:
        value = None
    with _PRICE_LOCK:
        _PRICE_CACHE[key] = (now, value)
    return value


def benchmark_return(start_iso: Optional[str], end_iso: Optional[str] = None) -> Optional[float]:
    from market import get_benchmark_return

    return _cached(("bench", start_iso, end_iso), lambda: get_benchmark_return(start_iso, end_iso=end_iso))


def take_profit_hit(
    ticker: str,
    start_iso: Optional[str],
    reference_price: Optional[float],
    take_profit_pct: float,
    max_hold_days: int,
) -> Optional[dict]:
    from market import get_take_profit_hit

    key = ("tp", ticker, start_iso, reference_price, take_profit_pct, max_hold_days)
    return _cached(
        key,
        lambda: get_take_profit_hit(ticker, start_iso, reference_price, take_profit_pct, max_hold_days),
    )


# --- scoreboard ------------------------------------------------------------


def _exit_plan_of(rec: dict) -> Tuple[float, int]:
    plan = rec.get("exit_plan") or {}
    tp = plan.get("take_profit_pct") or DEFAULT_TAKE_PROFIT_PCT
    hold = plan.get("max_hold_trading_days") or DEFAULT_MAX_HOLD_DAYS
    return float(tp), int(hold)


def build_scoreboard(recs: List[dict], reviews: Dict[str, dict]) -> dict:
    """Headline counts plus the pre/post managed-exit split.

    The post-Aug-18 cohort is the decision the whole dashboard exists to serve:
    it should fill up until mid-October, when the user judges whether managed
    exits actually earn the +1.6%/trade the replays suggested.
    """
    buy_lane = [r for r in recs if r.get("action") in BUY_LANE]
    action_counts: Dict[str, int] = {}
    for rec in recs:
        action = rec.get("action") or "unknown"
        action_counts[action] = action_counts.get(action, 0) + 1

    buy_excess = [
        reviews[r["id"]]["excess_return_pct"]
        for r in buy_lane
        if r.get("id") in reviews and isinstance(reviews[r["id"]].get("excess_return_pct"), (int, float))
    ]

    cohort = build_managed_cohort(buy_lane, reviews)

    return {
        "total_recommendations": len(recs),
        "action_counts": action_counts,
        "buy_lane_count": len(buy_lane),
        "buy_lane_reviewed": len(buy_excess),
        "buy_lane_mean_excess": _mean(buy_excess),
        "buy_lane_win_rate": (
            sum(1 for value in buy_excess if value > 0) / len(buy_excess) if buy_excess else None
        ),
        "total_reviews": len(load_recommendation_reviews()),
        "cohort": cohort,
    }


def build_managed_cohort(buy_lane: List[dict], reviews: Dict[str, dict]) -> dict:
    """Post-Aug-18 buys carrying an exit plan — the managed-exit experiment.

    Take-profit status is resolved live from prices rather than waiting on the
    nightly review, so a fresh buy shows its outcome the day it hits.
    """
    members = [
        rec
        for rec in buy_lane
        if (rec.get("timestamp") or "") >= MANAGED_EXIT_START and rec.get("exit_plan")
    ]
    members.sort(key=lambda rec: rec.get("timestamp") or "")

    rows: List[dict] = []
    banked: List[float] = []
    excess: List[float] = []
    tp_hits = 0
    open_trades = 0

    for rec in members:
        tp_pct, hold_days = _exit_plan_of(rec)
        reference = rec.get("reference_price")
        result = take_profit_hit(rec.get("ticker") or "", rec.get("timestamp"), reference, tp_pct, hold_days)
        review = reviews.get(rec.get("id") or "")

        hit = bool(result and result.get("hit"))
        window_complete = bool(result and result.get("window_complete"))
        if hit:
            tp_hits += 1
        if not window_complete:
            open_trades += 1

        trade_return: Optional[float] = None
        if hit:
            trade_return = tp_pct
        elif review and isinstance(review.get("forward_return_pct"), (int, float)):
            trade_return = review["forward_return_pct"]

        end_iso = None
        if hit and result.get("hit_date"):
            end_iso = result["hit_date"]
        bench = benchmark_return(rec.get("timestamp"), end_iso)

        if trade_return is not None:
            banked.append(trade_return)
            if bench is not None:
                excess.append(trade_return - bench)

        rows.append(
            {
                "id": rec.get("id"),
                "ticker": rec.get("ticker"),
                "action": rec.get("action"),
                "timestamp": rec.get("timestamp"),
                "reference_price": reference,
                "take_profit_pct": tp_pct,
                "max_hold_trading_days": hold_days,
                "take_profit_hit": hit,
                "take_profit_hit_date": result.get("hit_date") if result else None,
                "sessions_to_hit": result.get("sessions_to_hit") if result else None,
                "window_complete": window_complete,
                "trade_return": trade_return,
                "benchmark_return": bench,
                "excess_return": (trade_return - bench) if trade_return is not None and bench is not None else None,
                "theme_driver": rec.get("theme_driver"),
                "status": "take-profit hit" if hit else ("time-stopped" if window_complete else "open"),
            }
        )

    rows.reverse()
    return {
        "n": len(members),
        "rows": rows,
        "tp_hits": tp_hits,
        "tp_hit_rate": (tp_hits / len(members)) if members else None,
        "open_trades": open_trades,
        "resolved": len(members) - open_trades,
        "mean_banked_return": _mean(banked),
        "mean_excess": _mean(excess),
        "start_date": MANAGED_EXIT_START,
    }


# --- equity curve ----------------------------------------------------------


def build_equity_curve(recs: List[dict], reviews: Dict[str, dict], start_capital: float = 100.0) -> dict:
    """$100 following the managed-exit policy vs SPY buy-and-hold.

    One trade at a time, full capital: enter at reference_price, exit at the
    take-profit if the window reached it, otherwise at the reviewed return
    after the time stop. Capital sits in SPY between signals, which is what the
    exit plan's parking guidance actually prescribes.
    """
    buy_lane = [
        rec
        for rec in recs
        if rec.get("action") in BUY_LANE and rec.get("reference_price") and rec.get("timestamp")
    ]
    buy_lane.sort(key=lambda rec: rec.get("timestamp") or "")
    if not buy_lane:
        return {"points": [], "trades": [], "final_equity": start_capital, "spy_final": start_capital}

    equity = start_capital
    points: List[dict] = []
    trades: List[dict] = []
    busy_until: Optional[datetime] = None

    first_ts = buy_lane[0].get("timestamp")
    points.append({"date": (_parse_iso(first_ts) or datetime.now(timezone.utc)).date().isoformat(), "equity": round(equity, 2)})

    for rec in buy_lane:
        entered = _parse_iso(rec.get("timestamp"))
        if entered is None:
            continue
        # One position at a time: a signal arriving mid-trade is skipped rather
        # than pretending capital was available for both.
        if busy_until is not None and entered < busy_until:
            continue

        tp_pct, hold_days = _exit_plan_of(rec)
        reference = rec.get("reference_price")
        result = take_profit_hit(rec.get("ticker") or "", rec.get("timestamp"), reference, tp_pct, hold_days)
        review = reviews.get(rec.get("id") or "")

        hit = bool(result and result.get("hit"))
        window_complete = bool(result and result.get("window_complete"))
        if not hit and not window_complete:
            # Trade still open — do not book an unrealized result into the curve.
            continue

        if hit:
            trade_return = tp_pct
            exit_date = result.get("hit_date")
            sessions = result.get("sessions_to_hit") or hold_days
        else:
            if review and isinstance(review.get("forward_return_pct"), (int, float)):
                trade_return = float(review["forward_return_pct"])
            else:
                continue
            sessions = hold_days
            exit_date = (entered + timedelta(days=int(hold_days * 1.45))).date().isoformat()

        equity *= 1 + trade_return
        busy_until = _parse_iso(exit_date) or (entered + timedelta(days=hold_days))
        points.append({"date": exit_date, "equity": round(equity, 2)})
        trades.append(
            {
                "ticker": rec.get("ticker"),
                "entry_date": entered.date().isoformat(),
                "exit_date": exit_date,
                "trade_return": trade_return,
                "take_profit_hit": hit,
                "sessions_held": sessions,
                "equity_after": round(equity, 2),
            }
        )

    spy_return = benchmark_return(first_ts)
    spy_final = start_capital * (1 + spy_return) if spy_return is not None else None

    return {
        "points": points,
        "trades": list(reversed(trades)),
        "trade_count": len(trades),
        "final_equity": round(equity, 2),
        "total_return": (equity / start_capital) - 1,
        "spy_final": round(spy_final, 2) if spy_final is not None else None,
        "spy_return": spy_return,
        "start_capital": start_capital,
        "start_date": (_parse_iso(first_ts) or datetime.now(timezone.utc)).date().isoformat(),
    }


# --- theme scorecard -------------------------------------------------------


def build_theme_scorecard() -> List[dict]:
    """Per-theme n / mean excess / outcome mix, mirroring run.py review_summary."""
    stats: Dict[str, dict] = {}
    for review in load_recommendation_reviews():
        theme = review.get("theme_driver") or "unknown"
        entry = stats.setdefault(theme, {"theme": theme, "n": 0, "outcomes": {}, "excess": []})
        entry["n"] += 1
        outcome = review.get("outcome") or "unknown"
        entry["outcomes"][outcome] = entry["outcomes"].get(outcome, 0) + 1
        excess = review.get("excess_return_pct", review.get("forward_return_pct"))
        if isinstance(excess, (int, float)):
            entry["excess"].append(excess)

    rows = []
    for entry in stats.values():
        rows.append(
            {
                "theme": entry["theme"],
                "n": entry["n"],
                "mean_excess": _mean(entry["excess"]),
                "outcomes": entry["outcomes"],
                "worked": entry["outcomes"].get("worked", 0),
                "partial": entry["outcomes"].get("partial", 0),
                "failed": entry["outcomes"].get("failed", 0),
                "late": entry["outcomes"].get("late", 0),
            }
        )
    rows.sort(key=lambda row: -row["n"])
    return rows


def build_outcome_counts() -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for review in load_recommendation_reviews():
        outcome = review.get("outcome") or "unknown"
        counts[outcome] = counts.get(outcome, 0) + 1
    return counts


# --- ops -------------------------------------------------------------------


def build_ops() -> dict:
    batch = latest_batch()
    generated_at = batch.get("generated_at") if batch else None
    generated_dt = _parse_iso(generated_at)
    age_hours = None
    if generated_dt:
        age_hours = (datetime.now(timezone.utc) - generated_dt).total_seconds() / 3600

    # The scan runs on a weekday cron, so a Monday morning legitimately sits a
    # weekend behind; only flag beyond that.
    if age_hours is None:
        staleness = "unknown"
    elif age_hours < 26:
        staleness = "fresh"
    elif age_hours < 74:
        staleness = "aging"
    else:
        staleness = "stale"

    reviews = load_recommendation_reviews()
    open_candidates = [
        review
        for review in reviews
        if review.get("spec_change_candidate")
        and review.get("candidate_status") in ACTIVE_CANDIDATE_STATUSES
    ]

    orders = load_desk_orders()
    pending_orders = [order for order in orders if order.get("status") in ("proposed", "pending", "notified")]

    themes = load_theme_events()

    return {
        "last_batch_at": generated_at,
        "last_batch_age_hours": age_hours,
        "staleness": staleness,
        "last_batch_metadata": (batch or {}).get("metadata") or {},
        "active_themes": [
            {
                "label": theme.get("theme_label"),
                "type": theme.get("theme_type"),
                "strength": theme.get("catalyst_strength"),
                "timestamp": theme.get("timestamp"),
            }
            for theme in themes
        ],
        "open_spec_candidates": len(open_candidates),
        "spec_candidate_details": [
            {
                "ticker": review.get("ticker"),
                "theme": review.get("theme_driver"),
                "outcome": review.get("outcome"),
                "reason": review.get("candidate_decision_reason"),
            }
            for review in open_candidates
        ][:8],
        "desk_orders_total": len(orders),
        "desk_orders_pending": len(pending_orders),
        "closed_trade_reviews": len(load_closed_reviews()),
    }


def build_recommendation_rows(recs: List[dict], reviews: Dict[str, dict], limit: int = 120) -> List[dict]:
    rows = []
    for rec in recs[:limit]:
        review = reviews.get(rec.get("id") or "")
        plan = rec.get("exit_plan") or {}
        rows.append(
            {
                "id": rec.get("id"),
                "ticker": rec.get("ticker"),
                "company": rec.get("company"),
                "action": rec.get("action"),
                "timestamp": rec.get("timestamp"),
                "date": (rec.get("timestamp") or "")[:10],
                "reference_price": rec.get("reference_price"),
                "confidence": rec.get("confidence"),
                "confirmation_state": rec.get("confirmation_state"),
                "theme_driver": rec.get("theme_driver"),
                "expected_horizon": rec.get("expected_horizon"),
                "gate_reasons": rec.get("gate_reasons") or [],
                "why_now": rec.get("why_now"),
                "status": rec.get("status"),
                "is_buy_lane": rec.get("action") in BUY_LANE,
                "exit_plan": (
                    "+{:.0%} / {}td".format(plan["take_profit_pct"], plan.get("max_hold_trading_days", "?"))
                    if plan.get("take_profit_pct")
                    else None
                ),
                "outcome": review.get("outcome") if review else None,
                "excess_return_pct": review.get("excess_return_pct") if review else None,
                "forward_return_pct": review.get("forward_return_pct") if review else None,
                "take_profit_hit": review.get("take_profit_hit") if review else None,
                "review_summary": review.get("summary") if review else None,
            }
        )
    return rows


def build_dashboard_data() -> dict:
    recs = load_unique_recommendations()
    reviews = reviews_by_recommendation()
    return {
        "scoreboard": build_scoreboard(recs, reviews),
        "equity": build_equity_curve(recs, reviews),
        "themes": build_theme_scorecard(),
        "outcomes": build_outcome_counts(),
        "ops": build_ops(),
        "recommendations": build_recommendation_rows(recs, reviews),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
