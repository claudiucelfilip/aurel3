"""Signal generation for Aurel3 MVP."""

from __future__ import annotations

import re

from markets import infer_market_profile
from market import get_sector, get_stock_data
from sentiment import analyze_mention_sentiment
from state import make_id, utc_now_iso
from taxonomy import infer_theme_taxonomy

BENEFICIARY_SYMBOL_NORMALIZATION = {
    "RHM": "RHM.DE",
    "BAE.L": "BAESY",
    "BVB": "BVB.RO",
}


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def _news_candidate_score(news: dict, direct: bool, beneficiary_index: int = 0) -> float:
    actionability_rank = {
        "informational": 0,
        "interesting_but_early": 1,
        "potentially_actionable": 2,
        "actionable": 3,
    }.get(news.get("actionability", ""), 0)
    confidence_rank = {"low": 0, "medium": 1, "high": 2}.get(news.get("confidence", ""), 0)
    durability_rank = {"low": 0, "medium": 1, "high": 2}.get(news.get("durability", ""), 0)
    direct_bonus = 3 if direct else 1
    beneficiary_bonus = max(0, 2 - beneficiary_index)
    return float(actionability_rank * 4 + confidence_rank * 2 + durability_rank + direct_bonus + beneficiary_bonus)


def _build_news_candidate(ticker: str, news: dict, direct: bool, beneficiary_index: int = 0) -> dict:
    normalized_ticker = BENEFICIARY_SYMBOL_NORMALIZATION.get(ticker.upper(), ticker.upper())
    return {
        "ticker": normalized_ticker,
        "name": normalized_ticker,
        "sector_hint": "",
        "score": _news_candidate_score(news, direct, beneficiary_index),
        "mention_change": 0.0,
        "sources": [news.get("source_item_id", "interpreted_news")],
        "signal_origin": "interpreted_news",
        "signal_direct": direct,
        "signal_theme_id": news.get("theme_id"),
        "signal_summary": news.get("summary", ""),
        "beneficiary_rank": max(0, 3 - beneficiary_index),
    }


def _candidate_universe(source_items: dict) -> list[dict]:
    social_items = sorted(
        source_items.get("raw_social", []),
        key=lambda item: item.get("score", 0),
        reverse=True,
    )[:12]

    merged: dict[str, dict] = {item["ticker"].upper(): dict(item) for item in social_items}

    for news in source_items.get("news", []):
        if not news.get("market_relevant"):
            continue
        actionability_rank = _actionability_rank(news)
        if actionability_rank < 1:
            continue

        for index, ticker in enumerate(news.get("direct_beneficiaries", [])):
            key = ticker.upper()
            candidate = _build_news_candidate(key, news, direct=True, beneficiary_index=index)
            existing = merged.get(key)
            if (
                not existing
                or candidate["score"] > existing.get("score", 0)
                or (
                    candidate["score"] == existing.get("score", 0)
                    and candidate.get("beneficiary_rank", 0) > existing.get("beneficiary_rank", 0)
                )
            ):
                merged[key] = candidate

        if actionability_rank < 2:
            continue

        for index, ticker in enumerate(news.get("secondary_beneficiaries", [])):
            key = ticker.upper()
            candidate = _build_news_candidate(key, news, direct=False, beneficiary_index=index)
            existing = merged.get(key)
            if (
                not existing
                or candidate["score"] > existing.get("score", 0)
                or (
                    candidate["score"] == existing.get("score", 0)
                    and candidate.get("beneficiary_rank", 0) > existing.get("beneficiary_rank", 0)
                )
            ):
                merged[key] = candidate

    return sorted(merged.values(), key=lambda item: item.get("score", 0), reverse=True)[:20]


def _related_news_items(item: dict, news_items: list[dict]) -> list[dict]:
    ticker = item["ticker"].lower()
    company = _normalize_text(item.get("name", ""))
    company_tokens = [token for token in re.split(r"[^a-z0-9]+", company) if len(token) >= 4]
    sector_hint = (item.get("sector_hint") or "").lower()

    sector_label_map = {
        "energy": {"energy"},
        "technology": {"ai"},
        "industrials": {"eu_policy", "infrastructure"},
        "utilities": {"energy"},
        "healthcare": {"healthcare"},
        "basic materials": {"materials", "agriculture", "infrastructure"},
        "financial services": {"banking"},
        "consumer defensive": {"agriculture"},
    }
    relevant_labels = sector_label_map.get(sector_hint, set())
    scored = []

    for news in news_items:
        title = _normalize_text(news.get("title", ""))
        summary = _normalize_text(news.get("summary", ""))
        theme_label = _normalize_text(news.get("theme_label", ""))
        reasoning_notes = _normalize_text(news.get("reasoning_notes", ""))
        label = news.get("label", "")
        beneficiary_sectors = {s.lower() for s in news.get("beneficiary_sectors", [])}
        direct_beneficiaries = {b.lower() for b in news.get("direct_beneficiaries", [])}
        secondary_beneficiaries = {b.lower() for b in news.get("secondary_beneficiaries", [])}
        score = 0
        haystacks = [title, summary, theme_label, reasoning_notes]

        if ticker in direct_beneficiaries:
            score += 6
        elif ticker in secondary_beneficiaries:
            score += 4
        elif any(token and any(token in text for text in haystacks) for token in company_tokens[:2]):
            score += 3
        elif any(re.search(rf"\b{re.escape(ticker)}\b", text) for text in haystacks if text):
            score += 3

        if sector_hint and sector_hint in beneficiary_sectors:
            score += 2
        if sector_hint and any(sector_hint in text for text in haystacks):
            score += 1
        if label in relevant_labels:
            score += 1
        if label == "romania_bvb" and ".ro" in ticker:
            score += 1

        if score > 0:
            scored.append((score, news))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [news for _, news in scored[:4]]


def _actionability_rank(news: dict) -> int:
    return {
        "informational": 0,
        "interesting_but_early": 1,
        "potentially_actionable": 2,
        "actionable": 3,
    }.get(news.get("actionability", ""), 0)


def _support_profile(ticker: str, related_news: list[dict]) -> dict:
    ticker_key = ticker.lower()
    profile = {
        "count": len(related_news),
        "direct_hits": 0,
        "secondary_hits": 0,
        "actionable_count": 0,
        "potentially_actionable_count": 0,
        "high_confidence_count": 0,
        "medium_confidence_count": 0,
        "high_durability_count": 0,
    }
    for news in related_news:
        directs = {b.lower() for b in news.get("direct_beneficiaries", [])}
        secondaries = {b.lower() for b in news.get("secondary_beneficiaries", [])}
        if ticker_key in directs:
            profile["direct_hits"] += 1
        if ticker_key in secondaries:
            profile["secondary_hits"] += 1
        actionability_rank = _actionability_rank(news)
        if actionability_rank >= 3:
            profile["actionable_count"] += 1
        if actionability_rank >= 2:
            profile["potentially_actionable_count"] += 1
        if news.get("confidence") == "high":
            profile["high_confidence_count"] += 1
        elif news.get("confidence") == "medium":
            profile["medium_confidence_count"] += 1
        if news.get("durability") == "high":
            profile["high_durability_count"] += 1
    return profile


def _crowding_state(data: dict, mention_change: float, bullish_points: int) -> str:
    ema20 = data.get("ema_20")
    price = data.get("price")
    extended_hard = False
    extended_soft = False
    if ema20 and price:
        extended_hard = price >= ema20 * 1.10
        extended_soft = price >= ema20 * 1.05
    hot_day = data.get("change_pct", 0) >= 0.09
    extreme_social = mention_change >= 6.0
    social_heat = mention_change >= 1.2
    multi_day_runup = (data.get("change_5d") or 0) >= 0.08

    if extended_hard or hot_day or extreme_social or (social_heat and extended_soft):
        return "high"
    if extended_soft or multi_day_runup:
        return "high" if multi_day_runup and extended_soft else "medium"
    if data.get("change_pct", 0) >= 0.05 or social_heat or bullish_points >= 5:
        return "medium"
    return "low"


def _expected_horizon(theme_meta: dict, sentiment: dict, data: dict) -> str:
    default_horizon = theme_meta.get("default_horizon")
    if default_horizon:
        return default_horizon
    if sentiment.get("momentum") == "surging":
        return "1-2 weeks"
    if data.get("trend") == "strong_up":
        return "1-3 months"
    return "1-2 weeks"


def _confidence_label(sentiment: dict, confirmation_state: str, crowding: str) -> str:
    bullish_points = sentiment.get("bullish_points", 0)
    if confirmation_state == "confirmed" and bullish_points >= 2 and crowding != "high":
        return "high"
    if confirmation_state in ("developing", "overconfirmed") or bullish_points >= 2:
        return "medium"
    return "low"


def _merged_confidence_label(
    sentiment: dict,
    confirmation_state: str,
    crowding: str,
    support: dict,
) -> str:
    baseline = _confidence_label(sentiment, confirmation_state, crowding)
    if (
        support["direct_hits"] >= 1
        and support["potentially_actionable_count"] >= 1
        and support["high_confidence_count"] >= 1
        and confirmation_state == "confirmed"
        and crowding != "high"
    ):
        return "high"
    if support["potentially_actionable_count"] >= 1 and baseline == "low":
        return "medium"
    return baseline


def _confirmation_state(data: dict) -> str:
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


def _allow_unconfirmed_watch(data: dict, support: dict, theme_id: str | None = None) -> bool:
    if theme_id == "earnings_guidance_momentum":
        return (
            support["direct_hits"] >= 1
            and support["actionable_count"] >= 1
            and support["high_confidence_count"] >= 1
            and data.get("volume_ratio", 0) >= 1.75
            and data.get("change_pct", 0) >= -0.10
        )

    if theme_id == "m_and_a_corporate_action":
        return (
            support["direct_hits"] >= 2
            and support["actionable_count"] >= 2
            and data.get("dollar_volume", 0) >= 5_000_000
            and (data.get("volume_ratio", 0) >= 0.5 or abs(data.get("change_pct", 0)) >= 0.06)
        )

    if theme_id == "healthcare_commercialization":
        return (
            support["direct_hits"] >= 1
            and support["potentially_actionable_count"] >= 1
            and data.get("volume_ratio", 0) >= 1.2
            and data.get("change_pct", 0) >= -0.015
        )

    if data.get("trend") not in ("up", "strong_up"):
        return False
    if support["potentially_actionable_count"] < 2:
        strong_direct_setup = (
            data.get("trend") == "strong_up"
            and data.get("change_pct", 0) >= -0.01
            and data.get("volume_ratio", 0) >= 0.75
            and support["direct_hits"] >= 1
            and (
                support["potentially_actionable_count"] >= 1
                or support["high_confidence_count"] >= 1
                or support["medium_confidence_count"] >= 2
            )
        )
        if not strong_direct_setup:
            return False
    if support["direct_hits"] >= 1:
        return True
    if support["secondary_hits"] >= 2:
        return True
    return False


def _recommendation_action(
    theme_id: str | None,
    confirmation: str,
    crowding: str,
    confidence: str,
    data: dict,
    sentiment: dict,
    support: dict,
) -> str:
    direct_news_candidate = support["direct_hits"] >= 1
    volume_floor = 1.15
    if direct_news_candidate:
        volume_floor = 0.6
        if theme_id in ("energy_geopolitical_supply_risk", "commodities_resource_supply_shock"):
            volume_floor = 0.75
        elif theme_id in ("ai_compute_infrastructure", "eu_defense_rearmament", "infrastructure_industrial_capex"):
            volume_floor = 0.5

    base_buy = (
        confirmation == "confirmed"
        and crowding != "high"
        and confidence in ("medium", "high")
        and data.get("volume_ratio", 0) >= volume_floor
        and data.get("change_pct", 0) >= -0.01
        and sentiment.get("bullish_points", 0) >= 2
        and support["potentially_actionable_count"] >= 1
        and (support["direct_hits"] >= 1 or support["secondary_hits"] >= 1)
    )

    if theme_id == "commodities_resource_supply_shock":
        if (
            base_buy
            and support["direct_hits"] >= 1
            and support["high_confidence_count"] >= 1
            and data.get("volume_ratio", 0) >= max(volume_floor, 0.9)
            and data.get("change_pct", 0) >= 0
        ):
            return "buy_now"
        return "watch_for_confirmation"

    if theme_id == "energy_geopolitical_supply_risk":
        if (
            base_buy
            and support["actionable_count"] >= 1
            and support["potentially_actionable_count"] >= 2
            and (support["direct_hits"] >= 1 or support["high_confidence_count"] >= 1)
        ):
            return "buy_now"
        return "watch_for_confirmation"

    if theme_id == "eu_defense_rearmament":
        if (
            confirmation in ("developing", "confirmed", "overconfirmed")
            and confidence in ("medium", "high")
            and data.get("volume_ratio", 0) >= max(volume_floor, 0.85)
            and data.get("change_pct", 0) >= 0
            and support["potentially_actionable_count"] >= 2
            and support["direct_hits"] >= 2
            and support["high_durability_count"] >= 1
            and data.get("change_pct", 0) <= 0.15
        ):
            return "buy_now"
        if confirmation == "overconfirmed" or crowding == "high":
            return "hold_not_fresh_buy"
        return "watch_for_confirmation"

    if theme_id == "infrastructure_industrial_capex":
        if (
            base_buy
            and support["direct_hits"] >= 1
            and support["high_durability_count"] >= 1
        ):
            return "buy_now"
        return "watch_for_confirmation"

    if theme_id == "agriculture_food_supply":
        if (
            base_buy
            and support["direct_hits"] >= 1
            and support["actionable_count"] >= 1
            and support["high_confidence_count"] >= 1
        ):
            return "buy_now"
        return "watch_for_confirmation"

    if theme_id == "healthcare_commercialization":
        if (
            (
                base_buy
                and support["direct_hits"] >= 1
                and support["actionable_count"] >= 1
            )
            or (
                confirmation in ("developing", "confirmed")
                and crowding != "high"
                and confidence in ("medium", "high")
                and support["direct_hits"] >= 1
                and support["potentially_actionable_count"] >= 1
                and data.get("volume_ratio", 0) >= 1.18
                and data.get("change_pct", 0) >= 0.008
            )
        ):
            return "buy_now"
        return "watch_for_confirmation"

    if theme_id == "battery_storage_commercialization":
        if (
            base_buy
            and support["direct_hits"] >= 1
            and support["actionable_count"] >= 1
            and support["high_confidence_count"] >= 1
            and data.get("volume_ratio", 0) >= max(volume_floor, 0.9)
        ):
            return "buy_now"
        return "watch_for_confirmation"

    if theme_id == "ai_compute_infrastructure":
        if (
            confirmation in ("developing", "confirmed", "overconfirmed")
            and confidence in ("medium", "high")
            and data.get("volume_ratio", 0) >= max(volume_floor, 0.85)
            and data.get("change_pct", 0) >= 0
            and support["potentially_actionable_count"] >= 1
            and support["direct_hits"] >= 2
            and support["high_durability_count"] >= 1
            and data.get("change_pct", 0) <= 0.08
            and (crowding != "high" or data.get("change_pct", 0) <= 0.065)
        ):
            return "buy_now"
        if confirmation == "overconfirmed" or crowding == "high":
            return "hold_not_fresh_buy"
        return "watch_for_confirmation"

    if theme_id == "earnings_guidance_momentum":
        if (
            confirmation in ("developing", "confirmed")
            and crowding != "high"
            and confidence in ("medium", "high")
            and support["direct_hits"] >= 1
            and support["actionable_count"] >= 1
            and support["high_confidence_count"] >= 1
            and data.get("volume_ratio", 0) >= 1.5
            and data.get("change_pct", 0) >= -0.01
        ):
            return "buy_now"
        # Post-earnings dip path: strong support + massive volume + moderate dip.
        # Catches cases like NFLX where earnings are strong but the day's
        # reaction overshoots before recovering.
        if (
            confirmation in ("developing", "confirmed", "unconfirmed")
            and crowding != "high"
            and confidence in ("medium", "high")
            and support["direct_hits"] >= 1
            and support["actionable_count"] >= 1
            and support["high_confidence_count"] >= 1
            and data.get("volume_ratio", 0) >= 3.0
            and data.get("change_pct", 0) >= -0.12
        ):
            return "buy_now"
        if (
            confirmation == "overconfirmed"
            and support["direct_hits"] >= 1
            and support["actionable_count"] >= 1
            and data.get("change_pct", 0) <= 0.12
        ):
            return "buy_now"
        if confirmation == "overconfirmed":
            return "hold_not_fresh_buy"
        return "watch_for_confirmation"

    if theme_id == "m_and_a_corporate_action":
        if (
            confirmation in ("developing", "confirmed")
            and confidence in ("medium", "high")
            and support["direct_hits"] >= 2
            and support["actionable_count"] >= 2
            and data.get("dollar_volume", 0) >= 10_000_000
            and data.get("volume_ratio", 0) >= 0.8
            and data.get("change_pct", 0) >= -0.02
        ):
            return "buy_now"
        return "watch_for_confirmation"

    # Fallback: unknown themes must not get an easier path than named themes.
    # Default to watch until a theme proves itself and gets its own gate.
    if confirmation == "overconfirmed":
        return "hold_not_fresh_buy"
    return "watch_for_confirmation"


def generate_signal_scan(source_items: dict) -> tuple[list[dict], list[dict]]:
    """Return theme records and recommendation records for the MVP."""
    theme_records: list[dict] = []
    candidate_records: list[dict] = []

    news_items = source_items.get("news", [])
    candidates = _candidate_universe(source_items)

    for item in candidates:
        ticker = item["ticker"]
        if item.get("signal_origin") == "interpreted_news":
            sentiment = {
                "sentiment": "bullish",
                "confidence": 0.7 if item.get("signal_direct") else 0.5,
                "reason": item.get("signal_summary") or "Interpreted market catalyst",
                "momentum": "steady",
                "bullish_points": 3 if item.get("signal_direct") else 2,
                "bearish_points": 0,
            }
        else:
            sentiment = analyze_mention_sentiment(item)
            if sentiment["sentiment"] != "bullish":
                continue

        data = get_stock_data(ticker)
        if not data:
            continue

        sector = get_sector(ticker)
        item["sector_hint"] = sector or ""
        related_news = _related_news_items(item, news_items)
        support = _support_profile(ticker, related_news)
        if news_items and support["count"] == 0:
            continue
        if (
            news_items
            and item.get("signal_origin") != "interpreted_news"
            and support["direct_hits"] == 0
            and support["secondary_hits"] == 0
        ):
            continue
        confirmation = _confirmation_state(data)
        if confirmation == "unconfirmed" and not _allow_unconfirmed_watch(data, support, item.get("signal_theme_id")):
            continue

        is_crypto = data.get("is_crypto", False)
        if is_crypto:
            theme_meta = {
                "theme_id": "crypto_momentum",
                "theme_type": "structural_sector_narrative",
                "label": f"Crypto momentum in {ticker.replace('.X', '')}",
                "default_horizon": "1-2 weeks",
            }
        else:
            theme_meta = infer_theme_taxonomy(sector, related_news)
        market_profile = infer_market_profile(ticker)
        theme_type = theme_meta["theme_type"]
        theme_label = theme_meta["label"]
        crowding = _crowding_state(data, item.get("mention_change", 0), sentiment.get("bullish_points", 0))
        expected_horizon = _expected_horizon(theme_meta, sentiment, data)
        confidence = _merged_confidence_label(sentiment, confirmation, crowding, support)
        action = _recommendation_action(
            theme_meta.get("theme_id"),
            confirmation,
            crowding,
            confidence,
            data,
            sentiment,
            support,
        )

        why_now = (
            f"{ticker} is seeing bullish social momentum, {data['trend']} price confirmation, "
            f"and volume at {data['volume_ratio']:.1f}x average."
        )
        if related_news:
            catalyst_text = related_news[0].get("summary") or related_news[0].get("title") or theme_label
            why_now += f" Related catalyst: {catalyst_text}."
        invalidation = (
            "Exit if price/volume confirmation weakens materially or the ticker starts lagging its peer group."
        )

        theme_id = make_id("theme", ticker)
        rec_id = make_id("rec", ticker)

        theme_record = {
            "id": theme_id,
            "timestamp": utc_now_iso(),
            "theme_type": theme_type,
            "theme_label": theme_label,
            "event_summary": why_now,
            "geography": market_profile["region"],
            "catalyst_strength": "high" if related_news else ("medium" if sentiment.get("bullish_points", 0) < 5 else "high"),
            "interpreted_support": support,
            "narrative_consensus": confidence,
            "confirmation_state": confirmation,
            "crowding_state": crowding,
            "expected_horizon": expected_horizon,
            "affected_sectors": [sector] if sector else [],
            "candidate_tickers": [ticker],
            "source_refs": [{
                "type": "social",
                "title": f"ApeWisdom momentum for {ticker}",
                "url": "internal://source/apewisdom",
                "publisher": "Aurel3",
                "timestamp": utc_now_iso(),
                "relevance_note": sentiment.get("reason", "Bullish momentum"),
            }] + [
                {
                    "type": "news",
                    "title": news.get("title") or news.get("theme_label") or news.get("summary", "Interpreted news item"),
                    "url": news.get("url", "internal://source/interpreted"),
                    "publisher": news.get("publisher", "OpenClaw"),
                    "timestamp": news.get("timestamp", utc_now_iso()),
                    "relevance_note": news.get("reasoning_notes") or f"Theme: {news.get('theme_id', 'unknown')}",
                }
                for news in related_news
            ],
            "status": "active" if action == "buy_now" else "developing",
        }
        theme_records.append(theme_record)

        candidate_record = {
            "id": rec_id,
            "timestamp": utc_now_iso(),
            "ticker": ticker,
            "company": item.get("name", ticker),
            "market_exchange": market_profile["exchange"],
            "market_region": market_profile["region"],
            "market_accessible": market_profile["accessible"],
            "action": action,
            "theme_driver": theme_label,
            "why_now": why_now,
            "confirmation_state": confirmation,
            "confidence": confidence,
            "interpreted_support": support,
            "expected_horizon": expected_horizon,
            "reference_price": data.get("price"),
            "invalidation": invalidation,
            "alternatives": [],
            "source_refs": [{
                "type": "theme",
                "title": theme_label,
                "url": f"internal://themes/{theme_id}",
                "publisher": "Aurel3",
                "timestamp": utc_now_iso(),
                "relevance_note": "Parent theme for this recommendation.",
            }] + [
                {
                    "type": "news",
                    "title": news.get("title") or news.get("theme_label") or news.get("summary", "Interpreted news item"),
                    "url": news.get("url", "internal://source/interpreted"),
                    "publisher": news.get("publisher", "OpenClaw"),
                    "timestamp": news.get("timestamp", utc_now_iso()),
                    "relevance_note": news.get("reasoning_notes") or f"Theme: {news.get('theme_id', 'unknown')}",
                }
                for news in related_news
            ],
            "status": "active",
            "theme_id": theme_meta.get("theme_id"),
            "raw_score": item.get("score", 0),
            "beneficiary_rank": item.get("beneficiary_rank", 0),
            "theme_record_id": theme_id,
        }
        candidate_records.append(candidate_record)

    grouped: dict[str, list[dict]] = {}
    latest_theme_record: dict[str, dict] = {}
    for rec, theme in zip(candidate_records, theme_records):
        grouped.setdefault(rec["theme_driver"], []).append(rec)
        latest_theme_record[rec["theme_driver"]] = theme

    recommendations: list[dict] = []
    final_theme_records: list[dict] = []

    def ranking_key(rec: dict) -> tuple:
        action_rank = {
            "buy_now": 4,
            "hold_not_fresh_buy": 3,
            "watch_for_confirmation": 2,
            "hold": 0,
        }.get(rec["action"], 0)
        support = rec.get("interpreted_support", {})
        direct_rank = 2 if support.get("direct_hits", 0) >= 1 else 1 if support.get("secondary_hits", 0) >= 1 else 0
        durability_rank = 1 if support.get("high_durability_count", 0) >= 1 else 0
        conf_rank = {
            "confirmed": 3,
            "developing": 2,
            "overconfirmed": 1,
            "unconfirmed": 0,
        }.get(rec["confirmation_state"], 0)
        conf_label = {"high": 2, "medium": 1, "low": 0}.get(rec["confidence"], 0)
        market_pref = 1 if rec.get("market_accessible") else 0
        return (
            action_rank,
            direct_rank,
            rec.get("beneficiary_rank", 0),
            durability_rank,
            conf_rank,
            conf_label,
            rec.get("raw_score", 0),
            market_pref,
        )

    for theme_label, recs in grouped.items():
        recs.sort(key=ranking_key, reverse=True)
        top = recs[0]
        alternatives = []
        for alt in recs[1:]:
            if len(alternatives) >= 1:
                break
            if alt["action"] not in ("buy_now", "watch_for_confirmation", "hold_not_fresh_buy"):
                continue
            alternatives.append({
                "ticker": alt["ticker"],
                "company": alt["company"],
                "market_exchange": alt["market_exchange"],
                "action": alt["action"],
                "confirmation_state": alt["confirmation_state"],
                "confidence": alt["confidence"],
                "reason": f"Alternative expression of {theme_label}.",
            })

        top["alternatives"] = alternatives
        recommendations.append(top)
        final_theme_records.append(latest_theme_record[theme_label])

    recommendations.sort(key=ranking_key, reverse=True)
    final_theme_records.sort(key=lambda theme: theme["theme_label"])
    return final_theme_records, recommendations
