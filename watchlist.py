"""Watchlist manager — thesis-aware position tracking for Aurel3."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from confirmation import confirmation_state

WATCHLIST_PATH = Path(__file__).parent / "data" / "watchlist.json"
HISTORY_PATH = Path(__file__).parent / "data" / "trade_history.json"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_iso() -> str:
    return _utc_now().isoformat()


def _make_watchlist_id(ticker: str) -> str:
    ts = _utc_now().strftime("%Y%m%d%H%M%S")
    return f"wl_{ts}_{ticker.lower()}"


def _migrate_position(pos: dict) -> dict:
    """Ensure legacy records expose the thesis-aware shape."""
    shares = pos.get("shares", 0)
    invested = pos.get("invested")
    if invested is None:
        invested = round(pos.get("entry_price", 0) * shares, 2) if shares else 0

    pos.setdefault("id", _make_watchlist_id(pos.get("ticker", "unknown")))
    pos.setdefault("company", pos.get("ticker"))
    pos.setdefault("market_exchange", "UNKNOWN")
    pos.setdefault("shares_or_position_size", {
        "shares": shares,
        "notional": invested,
        "currency": pos.get("currency", "USD"),
    })
    pos.setdefault("original_theme_driver", pos.get("notes") or "Manual thesis")
    pos.setdefault(
        "original_reason_for_entry",
        pos.get("notes") or "Legacy watchlist entry migrated into thesis-aware format.",
    )
    pos.setdefault("expected_horizon", "1-2 weeks")
    pos.setdefault("confirmation_at_entry", "developing")
    pos.setdefault("current_thesis_state", "intact")
    pos.setdefault("current_confirmation_state", "developing")
    pos.setdefault("current_action", "hold")
    pos.setdefault("exit_urgency", "low")
    pos.setdefault("invalidation_conditions", [])
    pos.setdefault("next_relevant_catalyst", None)
    pos.setdefault("last_reviewed_at", None)
    pos.setdefault("linked_recommendation_id", None)
    pos.setdefault("close_reason", None)
    pos.setdefault("current_action_reason", None)
    pos.setdefault("notes", "")
    pos.setdefault("status", "open")
    pos.setdefault("high_water_mark", pos.get("entry_price"))
    pos.setdefault("trailing_stop", None)
    pos.setdefault("last_alert", None)
    pos.setdefault("alert_count", 0)
    pos.setdefault("acknowledged", False)
    return pos


def load_watchlist() -> list[dict]:
    if not WATCHLIST_PATH.exists():
        return []
    with open(WATCHLIST_PATH) as f:
        watchlist = json.load(f)
    return [_migrate_position(pos) for pos in watchlist]


def save_watchlist(watchlist: list[dict]) -> None:
    WATCHLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(WATCHLIST_PATH, "w") as f:
        json.dump(watchlist, f, indent=2)


def load_history() -> list[dict]:
    if not HISTORY_PATH.exists():
        return []
    with open(HISTORY_PATH) as f:
        return json.load(f)


def save_history(history: list[dict]) -> None:
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(HISTORY_PATH, "w") as f:
        json.dump(history, f, indent=2)


def add_position(
    ticker: str,
    entry_price: float,
    shares: float = 0,
    notes: str = "",
    recommendation: dict | None = None,
) -> dict:
    watchlist = load_watchlist()
    ticker = ticker.upper()

    for pos in watchlist:
        if pos["ticker"] == ticker and pos["status"] == "open":
            return pos

    recommendation = recommendation or {}
    market_exchange = recommendation.get("market_exchange", "UNKNOWN")
    company = recommendation.get("company", ticker)
    currency = "USD"
    if market_exchange in ("BVB", "Bucharest Stock Exchange"):
        currency = "RON"
    elif market_exchange in ("XETRA", "LSE", "Borsa Italiana", "EURONEXT"):
        currency = "EUR"

    position = {
        "id": _make_watchlist_id(ticker),
        "ticker": ticker,
        "company": company,
        "market_exchange": market_exchange,
        "entry_price": entry_price,
        "shares": shares,
        "invested": round(entry_price * shares, 2) if shares > 0 else 0,
        "shares_or_position_size": {
            "shares": shares,
            "notional": round(entry_price * shares, 2) if shares > 0 else 0,
            "currency": currency,
        },
        "entry_date": _utc_now_iso(),
        "status": "open",
        "original_theme_driver": recommendation.get("theme_driver", "Manual thesis"),
        "original_reason_for_entry": recommendation.get(
            "why_now",
            notes or "Manually added to the watchlist.",
        ),
        "expected_horizon": recommendation.get("expected_horizon", "1-2 weeks"),
        "confirmation_at_entry": recommendation.get("confirmation_state", "developing"),
        "current_thesis_state": "intact",
        "current_confirmation_state": recommendation.get("confirmation_state", "developing"),
        "current_action": "hold",
        "exit_urgency": "low",
        "invalidation_conditions": (
            recommendation.get("invalidation_conditions")
            or ([recommendation.get("invalidation")] if recommendation.get("invalidation") else [])
        ),
        "next_relevant_catalyst": None,
        "last_reviewed_at": None,
        "linked_recommendation_id": recommendation.get("id"),
        "notes": notes,
        "high_water_mark": entry_price,
        "trailing_stop": None,
        "last_alert": None,
        "alert_count": 0,
        "acknowledged": False,
        "close_reason": None,
        "current_action_reason": None,
        "currency": currency,
    }
    watchlist.append(position)
    save_watchlist(watchlist)
    return position


def close_position(ticker: str, sell_price: float | None = None, close_reason: str | None = None) -> dict | None:
    watchlist = load_watchlist()
    closed = None

    for pos in watchlist:
        if pos["ticker"] == ticker.upper() and pos["status"] == "open":
            pos["status"] = "closed"
            pos["closed_date"] = _utc_now_iso()
            pos["sell_price"] = sell_price
            pos["close_reason"] = close_reason or pos.get("current_action_reason")

            entry_price = pos["entry_price"]
            shares = pos.get("shares", 0)
            pos["shares_sold"] = shares
            pos["shares_remaining"] = 0

            if sell_price and entry_price > 0:
                pos["pnl_pct"] = round((sell_price / entry_price) - 1, 4)
                pos["pnl_dollar"] = round((sell_price - entry_price) * shares, 2) if shares > 0 else 0
            else:
                pos["pnl_pct"] = 0
                pos["pnl_dollar"] = 0

            entry_date = datetime.fromisoformat(pos["entry_date"])
            pos["days_held"] = (_utc_now() - entry_date).days
            closed = pos.copy()
            break

    if closed:
        save_watchlist(watchlist)
        _record_trade(closed)

    return closed


def _record_trade(position: dict) -> None:
    history = load_history()
    history.append({
        "ticker": position["ticker"],
        "entry_price": position["entry_price"],
        "sell_price": position.get("sell_price"),
        "shares": position.get("shares_sold", position.get("shares", 0)),
        "pnl_pct": position.get("pnl_pct", 0),
        "pnl_dollar": position.get("pnl_dollar", 0),
        "days_held": position.get("days_held", 0),
        "entry_date": position["entry_date"],
        "closed_date": position.get("closed_date"),
        "close_reason": position.get("close_reason"),
    })
    save_history(history)


def ignore_position(ticker: str) -> bool:
    watchlist = load_watchlist()
    for pos in watchlist:
        if pos["ticker"] == ticker.upper() and pos["status"] == "open":
            pos["status"] = "ignored"
            save_watchlist(watchlist)
            return True
    return False


def acknowledge_position(ticker: str, action: str = "hold", sell_price: float | None = None) -> dict | bool:
    if action == "sell":
        return close_position(ticker, sell_price=sell_price)
    if action == "ignore":
        return ignore_position(ticker)

    watchlist = load_watchlist()
    for pos in watchlist:
        if pos["ticker"] == ticker.upper() and pos["status"] == "open":
            pos["acknowledged"] = True
            pos["acknowledged_at"] = _utc_now_iso()
            pos["alert_count"] = 0
            save_watchlist(watchlist)
            return True
    return False


def get_open_positions() -> list[dict]:
    return [p for p in load_watchlist() if p["status"] == "open"]


def get_closed_positions() -> list[dict]:
    return [p for p in load_watchlist() if p["status"] == "closed"]


def find_position(ticker: str, status: str = "open") -> dict | None:
    for pos in load_watchlist():
        if pos["ticker"] == ticker.upper() and pos["status"] == status:
            return pos
    return None


def get_performance_summary() -> dict:
    # Records marked excluded (e.g. corrupted fills) must not skew stats.
    history = [t for t in load_history() if not t.get("excluded")]
    if not history:
        return {"total_trades": 0}

    wins = [t for t in history if t["pnl_pct"] > 0]
    losses = [t for t in history if t["pnl_pct"] < 0]
    total_pnl = sum(t.get("pnl_dollar", 0) for t in history)
    avg_pnl_pct = sum(t["pnl_pct"] for t in history) / len(history) if history else 0
    avg_days = sum(t.get("days_held", 0) for t in history) / len(history) if history else 0

    return {
        "total_trades": len(history),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": len(wins) / len(history) if history else 0,
        "total_pnl_dollar": round(total_pnl, 2),
        "avg_pnl_pct": round(avg_pnl_pct, 4),
        "best_trade": max(history, key=lambda t: t["pnl_pct"]) if history else None,
        "worst_trade": min(history, key=lambda t: t["pnl_pct"]) if history else None,
        "avg_hold_days": round(avg_days, 1),
    }


def review_position(position: dict, market_data: dict, social_lookup: dict | None = None) -> dict:
    """Return updated position state and whether the change is actionable."""
    social_lookup = social_lookup or {}
    updated = position.copy()
    price = market_data["price"]
    change_pct = market_data.get("change_pct", 0)
    volume_ratio = market_data.get("volume_ratio", 0)
    trend = market_data.get("trend", "unknown")
    ema20 = market_data.get("ema_20")

    if price > updated.get("high_water_mark", position["entry_price"]):
        updated["high_water_mark"] = price

    # Same judgment as entry scoring — a position must not flip states just
    # because the review path graded identical market data differently.
    confirmation = confirmation_state(market_data)

    sentiment = social_lookup.get(position["ticker"])
    sentiment_label = sentiment.get("sentiment") if sentiment else None
    sentiment_confidence = sentiment.get("confidence", 0) if sentiment else 0

    thesis_state = "intact"
    action = "hold"
    exit_urgency = "low"
    reason = "Original thesis remains valid."

    pnl_pct = (price / position["entry_price"]) - 1 if position["entry_price"] > 0 else 0
    entry_confirmation = position.get("confirmation_at_entry", "developing")

    # Exit drawdown scales with the name's own volatility — a fixed -3% was a
    # single ordinary red day for higher-vol names, against the thesis-first
    # sell philosophy.
    adm = market_data.get("avg_daily_move") or 0.02
    drawdown_limit = max(0.04, adm * 3)

    invalidations = position.get("invalidation_conditions", [])
    hit_conditions: list[str] = []
    for item in invalidations:
        if isinstance(item, dict):
            kind = item.get("type")
            if kind == "confirmation_loss" and confirmation == "unconfirmed":
                hit_conditions.append(kind)
            elif kind == "trend_break" and trend in ("down", "weak"):
                hit_conditions.append(kind)
            elif kind == "adaptive_drawdown" and pnl_pct < -(item.get("threshold_pct") or drawdown_limit):
                hit_conditions.append(kind)
            continue
        # Legacy prose conditions from older positions.
        text = str(item).lower()
        if "relative strength" in text and confirmation == "unconfirmed":
            hit_conditions.append("legacy_relative_strength")
        if "price trend fails" in text and trend in ("down", "weak"):
            hit_conditions.append("legacy_trend")
    # Thesis-first with price confirmation: two independent hits invalidate,
    # or one *material* hit (trend break / drawdown) with confirmation broken.
    # confirmation_loss alone never sells — a soft day is not a broken thesis.
    distinct_hits = set(hit_conditions)
    material_hits = distinct_hits - {"confirmation_loss"}
    invalidation_hit = len(distinct_hits) >= 2 or (
        bool(material_hits) and confirmation == "unconfirmed"
    )

    if invalidation_hit:
        thesis_state = "broken"
        action = "sell"
        exit_urgency = "high"
        reason = (
            "Stated invalidation conditions were hit ("
            + ", ".join(sorted(set(hit_conditions)))
            + ") and market confirmation no longer supports the thesis."
        )
    elif confirmation == "unconfirmed" and pnl_pct < -drawdown_limit:
        thesis_state = "broken"
        action = "sell"
        exit_urgency = "high"
        reason = "Market confirmation failed and the drawdown exceeds the position's normal volatility."
    elif sentiment_label == "bearish" and sentiment_confidence >= 0.4 and pnl_pct <= 0:
        thesis_state = "broken"
        action = "sell"
        exit_urgency = "high"
        reason = "Social consensus turned bearish while price confirmation weakened."
    elif trend in ("down", "weak") and pnl_pct > 0:
        thesis_state = "weakening"
        action = "trim_de_risk"
        exit_urgency = "high" if pnl_pct >= 0.08 else "medium"
        reason = "The position is still up, but the price trend has rolled over against the original thesis."
    elif confirmation == "unconfirmed" and sentiment_label == "bearish":
        thesis_state = "broken"
        action = "sell"
        exit_urgency = "high"
        reason = "Both market confirmation and social sentiment have broken against the thesis."
    elif confirmation == "developing" and entry_confirmation in ("confirmed", "overconfirmed") and pnl_pct > 0.03:
        thesis_state = "weakening"
        action = "trim_de_risk"
        exit_urgency = "medium"
        reason = "The thesis still works, but confirmation has faded from its entry quality."
    elif confirmation == "overconfirmed":
        thesis_state = "intact"
        action = "hold_not_fresh_buy"
        exit_urgency = "low"
        reason = "The thesis still works, but the move looks crowded or extended."
    elif confirmation == "developing" and pnl_pct > 0.08 and volume_ratio < 1.0:
        thesis_state = "weakening"
        action = "trim_de_risk"
        exit_urgency = "medium"
        reason = "The move is profitable but participation is fading and confirmation is no longer strong."
    elif confirmation == "confirmed":
        thesis_state = "strengthening" if pnl_pct > 0 else "intact"
        action = "hold"
        exit_urgency = "low"
        reason = "Price, volume, and trend continue to support the thesis."
    elif confirmation == "developing":
        thesis_state = "intact" if sentiment_label != "bearish" else "weakening"
        action = "hold" if sentiment_label != "bearish" else "hold_not_fresh_buy"
        exit_urgency = "low"
        reason = (
            "The thesis remains live, but confirmation is still only developing."
            if sentiment_label != "bearish"
            else "The thesis remains live, but sentiment has softened and no fresh buying is justified."
        )
    else:
        thesis_state = "weakening"
        if pnl_pct > 0:
            action = "trim_de_risk"
            exit_urgency = "medium"
            reason = "Confirmation has faded while the position is still up — protect gains."
        elif pnl_pct < -drawdown_limit:
            action = "sell"
            exit_urgency = "high"
            reason = "Confirmation has failed and the drawdown exceeds normal volatility."
        else:
            # Down, but within the name's normal volatility: no fresh buying,
            # watch closely — don't sell on noise per the thesis-first policy.
            action = "hold_not_fresh_buy"
            exit_urgency = "medium"
            reason = "Confirmation has faded but the drawdown is within normal volatility; watching closely."

    updated["current_confirmation_state"] = confirmation
    updated["current_thesis_state"] = thesis_state
    updated["current_action"] = action
    updated["exit_urgency"] = exit_urgency
    updated["current_action_reason"] = reason
    updated["last_reviewed_at"] = _utc_now_iso()
    return updated


def save_reviewed_positions(reviewed_positions: list[dict]) -> None:
    current = load_watchlist()
    reviewed_map = {pos["id"]: pos for pos in reviewed_positions}
    for idx, pos in enumerate(current):
        if pos["id"] in reviewed_map:
            current[idx] = reviewed_map[pos["id"]]
    save_watchlist(current)


def should_send_action_alert(old_pos: dict, new_pos: dict) -> bool:
    old_action = old_pos.get("current_action", "hold")
    new_action = new_pos.get("current_action", "hold")
    if new_action in ("sell", "trim_de_risk") and new_action != old_action:
        return True
    if old_pos.get("exit_urgency") != new_pos.get("exit_urgency") and new_action in ("sell", "trim_de_risk"):
        return True
    return False
