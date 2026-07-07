"""Market data — price, volume, trend, and quality filters via Yahoo Finance."""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

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


def _info_get(info, *keys):
    """Read a value from either yfinance's mapping-style info or object attrs."""
    if info is None:
        return None
    if isinstance(info, dict):
        for key in keys:
            if key in info and info[key] is not None:
                return info[key]
        return None
    for key in keys:
        value = getattr(info, key, None)
        if value is not None:
            return value
    return None


def _session_elapsed_fraction(info) -> float:
    """Fraction of the trading session elapsed, for projecting partial-day
    volume to a full-day figure. Returns 1.0 when the session is over,
    unknown, or the instrument trades around the clock."""
    tz_name = _info_get(info, "timezone")
    if not tz_name:
        return 1.0
    tz_name = str(tz_name)
    try:
        now_local = datetime.now(ZoneInfo(tz_name))
    except Exception:
        return 1.0
    # Rough session bounds by region; exact minutes matter less than not
    # comparing a 10:00 volume against a full-day average.
    if tz_name.startswith("America"):
        open_min, close_min = 9 * 60 + 30, 16 * 60
    elif tz_name.startswith("Europe"):
        open_min, close_min = 9 * 60, 17 * 60 + 30
    elif tz_name.startswith(("Asia", "Australia")):
        open_min, close_min = 9 * 60, 15 * 60
    else:
        return 1.0
    if now_local.weekday() >= 5:
        return 1.0
    minutes = now_local.hour * 60 + now_local.minute
    if minutes <= open_min or minutes >= close_min:
        return 1.0
    elapsed = (minutes - open_min) / (close_min - open_min)
    # Floor early-session projection: the first minutes are volume-heavy
    # and would otherwise inflate the projected ratio wildly.
    return max(0.25, elapsed)


def get_stock_data(ticker: str) -> dict | None:
    """Get price, volume, trend, and quality data for a ticker.

    Returns dict with all fields needed for filtering and display,
    or None if data unavailable.
    """
    try:
        yahoo_sym = _yahoo_symbol(ticker)
        stock = yf.Ticker(yahoo_sym)
        is_crypto = ticker.endswith(".X")
        info = getattr(stock, "fast_info", None)
        info_fallback = None
        hist = None

        if info is None:
            try:
                info_fallback = stock.info
            except Exception:
                info_fallback = {}

        current_price = _info_get(info, "last_price", "regularMarketPrice", "currentPrice", "navPrice")
        today_volume = _info_get(info, "last_volume", "regularMarketVolume", "volume")
        avg_volume = _info_get(info, "three_month_average_volume", "averageVolume", "averageDailyVolume3Month")
        market_cap = _info_get(info, "market_cap", "marketCap")
        prev_close = _info_get(info, "previous_close", "previousClose", "regularMarketPreviousClose")

        if current_price is None or today_volume is None or avg_volume is None or prev_close is None:
            try:
                hist = stock.history(period="3mo", auto_adjust=True)
            except Exception:
                hist = None

        if current_price is None:
            current_price = _info_get(info_fallback, "regularMarketPrice", "currentPrice", "navPrice")
        if current_price is None and hist is not None and len(hist) >= 1:
            current_price = float(hist["Close"].iloc[-1])
        if not current_price or current_price <= 0:
            return None

        if prev_close is None:
            prev_close = _info_get(info_fallback, "previousClose", "regularMarketPreviousClose")
        if prev_close is None and hist is not None and len(hist) >= 2:
            prev_close = float(hist["Close"].iloc[-2])
        prev_close = prev_close or current_price
        change_pct = (current_price / prev_close) - 1 if prev_close > 0 else 0

        if today_volume is None and hist is not None and len(hist) >= 1 and "Volume" in hist:
            today_volume = float(hist["Volume"].iloc[-1])
        if avg_volume is None and hist is not None and len(hist) >= 20 and "Volume" in hist:
            avg_volume = float(hist["Volume"].tail(20).mean())
        if market_cap is None:
            market_cap = _info_get(info_fallback, "marketCap")

        today_volume = today_volume or 0
        avg_volume = avg_volume or 0
        volume_ratio = round(today_volume / avg_volume, 2) if avg_volume > 0 else 0
        volume_ratio_raw = volume_ratio
        # Mid-session, partial-day volume vs a full-day average structurally
        # fails volume gates on morning scans — project to full-day instead.
        if not is_crypto and avg_volume > 0 and today_volume > 0:
            fraction = _session_elapsed_fraction(info)
            if fraction < 1.0:
                volume_ratio = round((today_volume / fraction) / avg_volume, 2)
        market_cap = market_cap or 0

        # Calculate EMAs and volatility from recent history
        ema_20 = None
        ema_50 = None
        avg_daily_move = None
        change_5d = None
        try:
            if hist is None:
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
            "volume_ratio_raw": volume_ratio_raw,
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


_BENCHMARK_CACHE: dict[str, object] = {}


def get_benchmark_return(start_iso: str | None, benchmark: str = "SPY") -> float | None:
    """Benchmark return from start_iso to the latest close.

    Used by signal reviews to judge excess return instead of raw return —
    in a rising tape every buy 'works' otherwise.
    """
    if not start_iso:
        return None
    try:
        start = datetime.fromisoformat(start_iso)
    except Exception:
        return None
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    try:
        hist = _BENCHMARK_CACHE.get(benchmark)
        if hist is None:
            hist = yf.Ticker(benchmark).history(period="6mo", auto_adjust=True)
            _BENCHMARK_CACHE[benchmark] = hist
        if hist is None or len(hist) == 0:
            return None
        closes = hist["Close"]
        sub = closes[closes.index >= start]
        if len(sub) == 0:
            return None
        base = float(sub.iloc[0])
        last = float(closes.iloc[-1])
        if base <= 0:
            return None
        return round(last / base - 1, 4)
    except Exception:
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
