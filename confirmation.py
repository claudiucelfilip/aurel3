"""Shared market-confirmation logic.

Single source of truth for both entry scoring (signals.py) and watchlist
reviews (watchlist.py) so a position cannot flip confirmation states just
because two code paths judged the same market data differently.
"""

from __future__ import annotations


def confirmation_state(data: dict) -> str:
    trend = data.get("trend")
    change_pct = data.get("change_pct", 0)
    volume_ratio = data.get("volume_ratio", 0)
    ema20 = data.get("ema_20")
    price = data.get("price")
    avg_daily_move = data.get("avg_daily_move")

    if trend in ("down", "weak", "unknown"):
        # Allow "developing" if price is only slightly below EMA20 relative
        # to the stock's normal daily volatility — catches temporary dips
        # on catalyst days rather than structural downtrends.
        if (
            trend != "unknown"
            and ema20 and price and avg_daily_move and avg_daily_move > 0
            and volume_ratio >= 1.2
        ):
            ema20_gap = (ema20 - price) / ema20
            if ema20_gap <= avg_daily_move * 2.5:
                return "developing"
        return "unconfirmed"

    is_extended = bool(ema20 and price and price >= ema20 * 1.10)
    if trend == "strong_up" and change_pct > 0 and volume_ratio >= 1.5:
        return "overconfirmed" if is_extended or change_pct >= 0.09 else "confirmed"

    if trend in ("strong_up", "up") and change_pct >= -0.01 and volume_ratio >= 1.0:
        return "confirmed" if trend == "strong_up" and change_pct >= 0.01 else "developing"

    if trend in ("strong_up", "up") and change_pct >= -0.02 and volume_ratio >= 0.85:
        return "developing"

    # Allow developing for strong uptrend with quiet volume if the daily
    # move is within normal range — catches steady accumulation days.
    if (
        trend == "strong_up"
        and change_pct >= 0
        and volume_ratio >= 0.6
        and avg_daily_move and avg_daily_move > 0
        and change_pct <= avg_daily_move * 1.5
    ):
        return "developing"

    return "unconfirmed"
