"""Reddit sentiment scanner — uses ApeWisdom API for Reddit mention data.

ApeWisdom aggregates Reddit mentions across WSB, stocks, investing, etc.
Free, no API key needed, updated in near real-time.
"""

try:
    import httpx
except ImportError:
    httpx = None
    import requests


def _get(url: str, *, timeout: int = 15):
    if httpx is not None:
        return httpx.get(url, timeout=timeout)
    return requests.get(url, timeout=timeout)

APEWISDOM_BASE = "https://apewisdom.io/api/v1.0"

# ETFs, indices, commodity funds, and leveraged products to skip.
# We want individual stocks tradeable on major retail brokers, not funds.
SKIP_TICKERS = {
    # Major indices & broad ETFs
    "SPY", "QQQ", "IWM", "DIA", "VOO", "VTI", "VXX", "UVXY", "SQQQ",
    "TQQQ", "SPXU", "SPXS", "SH", "SPX", "NDX", "DJI",
    # Commodity/bond ETFs (often not on major retail brokers)
    "USO", "GLD", "SLV", "TLT", "HYG", "BNO", "UNG", "DBA", "DBC",
    "PDBC", "GSG", "CORN", "WEAT", "SOYB", "CPER", "PPLT", "PALL",
    "BIL", "SHV", "SHY", "IEF", "TIP", "LQD", "JNK", "EMB", "AGG",
    "BND", "BNDX", "SGOV", "TBIL",
    # Sector/thematic ETFs
    "XLF", "XLE", "XLK", "XLV", "XBI", "ARKK", "ARKG", "ARKW",
    "XLP", "XLY", "XLI", "XLB", "XLC", "XLRE", "XME", "XOP",
    "SMH", "SOXX", "IGV", "HACK", "BOTZ", "ROBO", "DRIV",
    "VNQ", "VNQI", "SCHD", "VIG", "DVY", "HDV",
    # International/EM ETFs
    "EFA", "EEM", "VEA", "VWO", "IEMG", "FXI", "EWZ", "EWJ",
    # Leveraged/inverse
    "SOXL", "SOXS", "LABU", "LABD", "FNGU", "FNGD", "JNUG", "JDST",
    "UPRO", "SPXL", "TNA", "TZA", "UDOW", "SDOW", "NUGT", "DUST",
    # Not real tickers in Reddit context
    "EU", "AM", "RE", "IT", "DD", "ALL", "ON", "AN", "ARE", "NOW",
    "GO", "SO", "AI", "BE", "DO", "HAS", "CEO", "IMO", "RH",
}

# Only allow top-cap crypto (no shitcoins). ApeWisdom uses .X suffix.
CRYPTO_WHITELIST = {
    "BTC.X", "ETH.X", "SOL.X", "BNB.X", "XRP.X", "ADA.X", "AVAX.X",
    "DOT.X", "MATIC.X", "LINK.X", "UNI.X", "ATOM.X", "LTC.X", "NEAR.X",
    "APT.X", "OP.X", "ARB.X", "FIL.X", "RENDER.X", "INJ.X", "SUI.X",
    "DOGE.X", "SHIB.X",  # meme coins but high cap
    "AAVE.X", "MKR.X", "CRV.X",  # DeFi blue chips
    "STX.X", "IMX.X", "ALGO.X", "XMR.X", "BCH.X",
}


def fetch_trending_tickers(
    subreddit: str = "all-stocks",
    pages: int = 1,
) -> list[dict]:
    """Fetch trending tickers from ApeWisdom.

    subreddit: "all-stocks", "wallstreetbets", "stocks", "investing", etc.
    Returns list of {ticker, name, mentions, upvotes, rank, mention_change}.
    """
    results = []

    for page in range(1, pages + 1):
        try:
            resp = _get(
                f"{APEWISDOM_BASE}/filter/{subreddit}/page/{page}",
                timeout=15,
            )
            if resp.status_code != 200:
                print(f"  Warning: ApeWisdom returned {resp.status_code}")
                break

            data = resp.json()
            for item in data.get("results", []):
                ticker = item["ticker"]
                if ticker in SKIP_TICKERS:
                    continue

                mentions_now = item.get("mentions") or 0
                mentions_24h_ago = item.get("mentions_24h_ago") or 0

                # Calculate mention momentum (% change in 24h)
                if mentions_24h_ago > 0:
                    mention_change = (mentions_now / mentions_24h_ago) - 1
                elif mentions_now > 0:
                    mention_change = 1.0  # new entrant
                else:
                    mention_change = 0

                results.append({
                    "ticker": ticker,
                    "name": item.get("name", "").replace("&amp;", "&"),
                    "mentions": mentions_now,
                    "upvotes": item.get("upvotes", 0),
                    "rank": item.get("rank", 0),
                    "rank_24h_ago": item.get("rank_24h_ago", 0),
                    "mentions_24h_ago": mentions_24h_ago,
                    "mention_change": round(mention_change, 2),
                })

        except Exception as e:
            print(f"  Warning: ApeWisdom fetch failed: {e}")
            break

    return results


def scan_all_sources() -> list[dict]:
    """Scan multiple Reddit sources and merge results.

    Returns deduplicated, scored list of opportunities.
    """
    # Fetch from WSB and general stocks
    print("    ApeWisdom all-stocks...", end="", flush=True)
    all_stocks = fetch_trending_tickers("all-stocks", pages=1)
    print(f" {len(all_stocks)} tickers")

    print("    ApeWisdom wallstreetbets...", end="", flush=True)
    wsb = fetch_trending_tickers("wallstreetbets", pages=1)
    print(f" {len(wsb)} tickers")

    # Fetch crypto
    print("    ApeWisdom crypto...", end="", flush=True)
    all_crypto = fetch_trending_tickers("all-crypto", pages=1)
    # Only keep whitelisted top-cap coins
    crypto = [t for t in all_crypto if t["ticker"] in CRYPTO_WHITELIST]
    # Tag as crypto for display
    for c in crypto:
        c["asset_type"] = "crypto"
        c["ticker_display"] = c["ticker"].replace(".X", "")  # BTC.X → BTC
    print(f" {len(crypto)} whitelisted (of {len(all_crypto)})")

    # Merge: combine mentions from different sources
    merged: dict[str, dict] = {}
    for source_name, tickers in [("all", all_stocks), ("wsb", wsb), ("crypto", crypto)]:
        for t in tickers:
            ticker = t["ticker"]
            if ticker in merged:
                merged[ticker]["mentions"] += t["mentions"]
                merged[ticker]["upvotes"] += t["upvotes"]
                merged[ticker]["sources"].append(source_name)
                # Keep the higher mention change
                if t["mention_change"] > merged[ticker]["mention_change"]:
                    merged[ticker]["mention_change"] = t["mention_change"]
            else:
                merged[ticker] = {
                    **t,
                    "sources": [source_name],
                }

    # Score and sort
    results = list(merged.values())
    for r in results:
        r["score"] = _calc_opportunity_score(r)

    results.sort(key=lambda r: r["score"], reverse=True)
    return results


def _calc_opportunity_score(item: dict) -> float:
    """Calculate an opportunity score based on mentions, momentum, and upvotes.

    Higher = more interesting opportunity.
    """
    mentions = item.get("mentions", 0)
    mention_change = item.get("mention_change", 0)
    upvotes = item.get("upvotes", 0)
    sources = len(item.get("sources", []))

    # Mention volume (log scale, capped)
    mention_score = min(mentions / 50, 5.0)

    # Mention momentum (new attention is more interesting than steady)
    momentum_score = min(max(mention_change, 0), 3.0) * 2

    # Upvote engagement
    upvote_score = min(upvotes / 500, 3.0)

    # Multi-source bonus
    source_bonus = 1.5 if sources > 1 else 1.0

    return (mention_score + momentum_score + upvote_score) * source_bonus


def filter_opportunities(
    tickers: list[dict],
    min_mentions: int = 3,
    min_score: float = 2.0,
    max_results: int = 10,
) -> list[dict]:
    """Filter to actionable opportunities."""
    filtered = [
        t for t in tickers
        if t["mentions"] >= min_mentions
        and t["score"] >= min_score
        and t["mention_change"] > -0.3  # not fading
    ]
    return filtered[:max_results]
