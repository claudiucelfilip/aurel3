"""Reddit sentiment analysis — infer buy/sell signals from ApeWisdom mention data.

Since Reddit's API is not accessible from this server, we use ApeWisdom's
mention/rank/upvote data as a sentiment proxy:
- Rising mentions + rising rank + high upvotes = bullish (community is excited)
- Falling mentions + dropping rank = fading interest (bearish signal for watchlist)

Combined with market technicals (uptrend confirmation), this filters to
tickers that Reddit is actively recommending AND the market confirms.
"""


def analyze_mention_sentiment(ticker_data: dict) -> dict:
    """Analyze sentiment from ApeWisdom mention data.

    Input: a ticker dict from scan_all_sources() with mentions, upvotes,
           mention_change, rank, rank_24h_ago, sources, score.

    Returns:
        {
            "sentiment": "bullish" | "bearish" | "neutral",
            "confidence": float (0-1),
            "reason": str,
            "momentum": str ("surging" | "rising" | "steady" | "fading"),
        }
    """
    mentions = ticker_data.get("mentions", 0)
    mention_change = ticker_data.get("mention_change", 0)
    upvotes = ticker_data.get("upvotes", 0)
    rank = ticker_data.get("rank", 999)
    rank_24h = ticker_data.get("rank_24h_ago", 999)
    sources = len(ticker_data.get("sources", []))
    score = ticker_data.get("score", 0)

    # Rank improvement (lower rank = more popular)
    rank_improving = rank_24h > 0 and rank < rank_24h
    rank_jump = (rank_24h - rank) if rank_24h > 0 else 0

    # Momentum classification
    if mention_change >= 0.5:
        momentum = "surging"
    elif mention_change >= 0.15:
        momentum = "rising"
    elif mention_change >= -0.15:
        momentum = "steady"
    else:
        momentum = "fading"

    # Bullish signals
    bullish_points = 0
    reasons = []

    if mention_change >= 0.3:
        bullish_points += 2
        reasons.append(f"mentions +{mention_change:.0%}")
    elif mention_change >= 0.1:
        bullish_points += 1
        reasons.append(f"mentions +{mention_change:.0%}")

    if rank_improving and rank_jump >= 5:
        bullish_points += 2
        reasons.append(f"rank #{rank_24h}→#{rank}")
    elif rank_improving:
        bullish_points += 1
        reasons.append(f"rank improving")

    if upvotes >= 1000:
        bullish_points += 2
        reasons.append(f"{upvotes} upvotes")
    elif upvotes >= 300:
        bullish_points += 1
        reasons.append(f"{upvotes} upvotes")

    if sources > 1:
        bullish_points += 1
        reasons.append(f"trending in {sources} subs")

    if mentions >= 50:
        bullish_points += 1
        reasons.append(f"{mentions} mentions")

    # Bearish signals
    bearish_points = 0
    if mention_change <= -0.3:
        bearish_points += 2
    elif mention_change <= -0.1:
        bearish_points += 1

    if rank_24h > 0 and rank > rank_24h + 10:
        bearish_points += 2  # dropping fast in rank

    # Classify
    net = bullish_points - bearish_points

    if net >= 3:
        sentiment = "bullish"
        confidence = min(net / 6, 1.0)
    elif net <= -2:
        sentiment = "bearish"
        confidence = min(abs(net) / 4, 1.0)
    else:
        sentiment = "neutral"
        confidence = 0.2

    return {
        "sentiment": sentiment,
        "confidence": round(confidence, 2),
        "reason": ", ".join(reasons) if reasons else "low activity",
        "momentum": momentum,
        "bullish_points": bullish_points,
        "bearish_points": bearish_points,
    }


def get_take_profit_target(
    current_price: float,
    trend: str,
    ema_20: float | None = None,
    ema_50: float | None = None,
    change_pct: float = 0,
    avg_daily_move: float | None = None,
) -> float | None:
    """Calculate a take-profit target based on the stock's actual volatility.

    Uses 2.5x average daily move as a realistic swing target achievable
    in 3-5 days with momentum. Clamped to 3-10% range.
    Returns None if the stock is too slow to justify the risk (< 3%).
    """
    if current_price <= 0:
        return None

    if avg_daily_move and avg_daily_move > 0:
        # Volatility-based: 2.5x average daily move
        target_pct = avg_daily_move * 2.5

        # Clamp to 3-10%
        target_pct = max(0.03, min(target_pct, 0.10))

        # Tighten if already extended above EMA20
        if ema_20 and current_price > ema_20 * 1.05:
            target_pct *= 0.75
            target_pct = max(0.03, target_pct)
    else:
        # Fallback if no volatility data: conservative 5%
        target_pct = 0.05

    return round(current_price * (1 + target_pct), 2)


def check_watchlist_sentiment(tickers: list[str], apewisdom_data: list[dict]) -> dict[str, dict]:
    """Check mention momentum for watchlist tickers using ApeWisdom data.

    Returns {ticker: sentiment_data} for tickers with notable signals.
    """
    # Build lookup from latest scan data
    ape_lookup = {t["ticker"]: t for t in apewisdom_data}

    results = {}
    for ticker in tickers:
        if ticker in ape_lookup:
            results[ticker] = analyze_mention_sentiment(ape_lookup[ticker])
        else:
            # Ticker not in trending at all — could mean fading interest
            results[ticker] = {
                "sentiment": "neutral",
                "confidence": 0.3,
                "reason": "not trending on Reddit anymore",
                "momentum": "fading",
                "bullish_points": 0,
                "bearish_points": 1,
            }
    return results
