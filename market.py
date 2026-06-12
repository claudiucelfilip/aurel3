"""Market data — price, volume, trend, and quality filters via Yahoo Finance."""

import yfinance as yf


def _yahoo_symbol(ticker: str) -> str:
    """Convert ApeWisdom ticker to Yahoo Finance symbol."""
    if ticker.endswith(".X"):
        return ticker.replace(".X", "-USD")  # BTC.X → BTC-USD
    return ticker


# Hard quality thresholds
MIN_PRICE = 5.0              # no penny stocks
MIN_AVG_VOLUME = 500_000     # shares/day (relaxed from 1M for mid-caps)
MIN_DOLLAR_VOLUME = 10_000_000  # $10M avg daily dollar volume
MIN_MARKET_CAP = 1_000_000_000  # $1B (relaxed from $2B to catch mid-cap momentum)
MAX_DAILY_CHANGE = 0.25      # reject >25% single-day moves (likely pump)

# Crypto uses different thresholds (no market cap filter, lower volume)
CRYPTO_MIN_AVG_VOLUME = 50_000_000  # $50M daily dollar volume for crypto


def get_stock_data(ticker: str) -> dict | None:
    """Get price, volume, trend, and quality data for a ticker.

    Returns dict with all fields needed for filtering and display,
    or None if data unavailable.
    """
    try:
        yahoo_sym = _yahoo_symbol(ticker)
        stock = yf.Ticker(yahoo_sym)
        info = stock.fast_info
        is_crypto = ticker.endswith(".X")

        current_price = getattr(info, "last_price", None)
        if not current_price or current_price <= 0:
            return None

        prev_close = getattr(info, "previous_close", current_price)
        change_pct = (current_price / prev_close) - 1 if prev_close > 0 else 0

        today_volume = getattr(info, "last_volume", 0) or 0
        avg_volume = getattr(info, "three_month_average_volume", 0) or 0
        volume_ratio = round(today_volume / avg_volume, 2) if avg_volume > 0 else 0
        market_cap = getattr(info, "market_cap", None) or 0

        # Calculate EMAs and volatility from recent history
        ema_20 = None
        ema_50 = None
        avg_daily_move = None
        change_5d = None
        try:
            hist = stock.history(period="3mo", auto_adjust=True)
            if hist is not None and len(hist) >= 20:
                ema_20 = float(hist["Close"].ewm(span=20).mean().iloc[-1])
                # Average daily move (absolute % change) over last 20 days
                daily_returns = hist["Close"].pct_change().dropna().tail(20).abs()
                avg_daily_move = round(float(daily_returns.mean()), 4)
            if hist is not None and len(hist) >= 50:
                ema_50 = float(hist["Close"].ewm(span=50).mean().iloc[-1])
            if hist is not None and len(hist) >= 6:
                close_5d_ago = float(hist["Close"].iloc[-6])
                if close_5d_ago > 0:
                    change_5d = round((current_price / close_5d_ago) - 1, 4)
        except Exception:
            pass

        # Trend assessment
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
            "market_cap": market_cap,
            "dollar_volume": round(avg_volume * current_price, 0) if avg_volume else 0,
            "ema_20": round(ema_20, 2) if ema_20 else None,
            "ema_50": round(ema_50, 2) if ema_50 else None,
            "avg_daily_move": avg_daily_move,
            "change_5d": change_5d,
            "trend": trend,
            "sector": None,  # populated lazily by get_sector()
            "is_crypto": is_crypto,
        }

    except Exception as e:
        print(f"  Warning: failed to get market data for {ticker}: {e}")
        return None


def get_sector(ticker: str) -> str | None:
    """Get the sector for a ticker from Yahoo Finance."""
    try:
        yahoo_sym = ticker.replace(".X", "-USD") if ticker.endswith(".X") else ticker
        stock = yf.Ticker(yahoo_sym)
        info = stock.info
        return info.get("sector") or info.get("category") or None
    except Exception:
        return None


def quality_check(ticker: str, data: dict) -> str | None:
    """Run hard quality filters. Returns rejection reason or None if passes."""
    is_crypto = data.get("is_crypto", False)

    if not is_crypto:
        # Stock filters
        if data["price"] < MIN_PRICE:
            return f"price ${data['price']:.2f} < ${MIN_PRICE}"

        if data["avg_volume"] < MIN_AVG_VOLUME:
            return f"avg volume {data['avg_volume']:,} < {MIN_AVG_VOLUME:,}"

        if data["dollar_volume"] < MIN_DOLLAR_VOLUME:
            return f"dollar volume ${data['dollar_volume']:,.0f} < ${MIN_DOLLAR_VOLUME:,.0f}"

        if data["market_cap"] and data["market_cap"] < MIN_MARKET_CAP:
            cap_m = data["market_cap"] / 1e6
            return f"market cap ${cap_m:.0f}M < ${MIN_MARKET_CAP/1e9:.0f}B"
    else:
        # Crypto filters (use dollar volume only)
        if data["dollar_volume"] < CRYPTO_MIN_AVG_VOLUME:
            return f"crypto dollar volume ${data['dollar_volume']:,.0f} < ${CRYPTO_MIN_AVG_VOLUME:,.0f}"

    # Reject wild single-day moves (likely pump or crash)
    if abs(data["change_pct"]) > MAX_DAILY_CHANGE:
        return f"daily move {data['change_pct']:+.1%} exceeds ±{MAX_DAILY_CHANGE:.0%}"

    # Reject downtrends
    if data["trend"] in ("down", "weak"):
        return f"trend is {data['trend']} (below key EMAs)"

    return None  # passes


def enrich_opportunities(opportunities: list[dict], min_volume_ratio: float = 1.5) -> list[dict]:
    """Add market data, run quality filters, return survivors with rejection log."""
    enriched = []
    rejected = []

    for opp in opportunities:
        ticker = opp["ticker"]
        data = get_stock_data(ticker)

        if data is None:
            rejected.append({"ticker": ticker, "reason": "no market data"})
            continue

        # Attach all market data
        opp["price"] = data["price"]
        opp["change_pct"] = data["change_pct"]
        opp["volume"] = data["volume"]
        opp["avg_volume"] = data["avg_volume"]
        opp["volume_ratio"] = data["volume_ratio"]
        opp["market_cap"] = data["market_cap"]
        opp["dollar_volume"] = data["dollar_volume"]
        opp["ema_20"] = data["ema_20"]
        opp["ema_50"] = data["ema_50"]
        opp["trend"] = data["trend"]

        # Volume ratio check
        if data["volume_ratio"] < min_volume_ratio:
            rejected.append({"ticker": ticker, "reason": f"volume ratio {data['volume_ratio']:.1f}x < {min_volume_ratio}x"})
            continue

        # Hard quality filters
        rejection = quality_check(ticker, data)
        if rejection:
            rejected.append({"ticker": ticker, "reason": rejection})
            continue

        enriched.append(opp)

    # Log rejections
    if rejected:
        print(f"  Rejected {len(rejected)} candidates:")
        for r in rejected[:10]:  # show top 10
            print(f"    {r['ticker']:8s} — {r['reason']}")
        if len(rejected) > 10:
            print(f"    ... and {len(rejected) - 10} more")

    return enriched
