"""Signal generation for Aurel3 MVP."""

from __future__ import annotations

import math
import re
from datetime import datetime, timezone

from confirmation import confirmation_state
from markets import infer_market_profile
from market import get_sector, get_stock_data
from sentiment import analyze_mention_sentiment
from state import make_id, utc_now_iso
from taxonomy import infer_theme_taxonomy

BENEFICIARY_SYMBOL_NORMALIZATION = {
    "RHM": "RHM.DE",
    "BAE.L": "BAESY",
    "BVB": "BVB.RO",
    "HXSCF": "SKHY",
}


class MarketDataCoverageError(RuntimeError):
    pass

# Freshness thresholds (hours). News older than STALE_REJECT_HOURS cannot
# drive a candidate at all. News older than FRESH_BUY_HOURS cannot drive a
# buy_now action — only watch_for_confirmation / hold_not_fresh_buy. These
# values exist because in practice, a momentum setup driven by news that is
# already a day or two old is almost always late — the move has played out.
FRESH_BUY_HOURS = 24.0
STALE_REJECT_HOURS = 48.0
REDDIT_STALE_HOURS = 12.0
MIN_SOCIAL_BUY_POINTS = 3


def _news_age_hours(news: dict) -> float | None:
    """Return age of an interpreted news item in hours, or None if unknown.

    The original publication timestamp is preserved inside ``source_item_id``
    as ``news::{label}::{iso_timestamp}::{title_prefix}``.
    """
    source_id = news.get("source_item_id", "")
    if not source_id:
        return None
    parts = source_id.split("::", 3)
    if len(parts) < 3:
        return None
    try:
        ts = datetime.fromisoformat(parts[2])
    except ValueError:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - ts).total_seconds() / 3600.0
    return max(0.0, age)


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


IMPACT_DIRECTIONS = {"bullish", "bearish", "mixed", "neutral"}
BEARISH_CATALYST_PATTERNS = (
    r"\bsued?\b.*\bblock",
    r"\blawsuit\b.*\bblock",
    r"\bantitrust\b",
    r"\bcompletion risk\b",
    r"\bregulatory (?:and |or )?(?:timing )?risk\b",
    r"\bheadline risk\b",
    r"\bheadwind\b",
    r"\bpressur(?:e|es|ed|ing)\b",
    r"\bstocks? fall",
    r"\bshares? fall",
    r"\bdeclin(?:e|es|ed|ing)\b",
    r"\bcuts? (?:full-year )?(?:guidance|forecast|outlook)\b",
    r"\bweak (?:guidance|revenue|demand)\b",
    r"\bmiss(?:es|ed)?\b",
    r"\bdowngrades?\b",
    r"\binvestigation\b",
    r"\brecall\b",
    r"\bbankrupt(?:cy)?\b",
    r"\bfraud\b",
)


def _ticker_impact_direction(news: dict, ticker: str) -> str:
    """Return ticker-specific catalyst direction, independent of directness."""
    ticker_key = ticker.upper()
    for impact in news.get("ticker_impacts", []):
        if not isinstance(impact, dict):
            continue
        if str(impact.get("ticker", "")).upper() != ticker_key:
            continue
        direction = str(impact.get("direction", "")).lower()
        if direction in IMPACT_DIRECTIONS:
            return direction

    # Backward-compatible safety for interpreted payloads created before
    # ticker_impacts existed. Negative language must never default to bullish.
    text = _normalize_text(
        " ".join(
            str(news.get(field, ""))
            for field in ("summary", "reasoning_notes", "title", "event_type")
        )
    )
    if any(re.search(pattern, text) for pattern in BEARISH_CATALYST_PATTERNS):
        return "bearish"

    directs = {str(value).upper() for value in news.get("direct_beneficiaries", [])}
    secondaries = {str(value).upper() for value in news.get("secondary_beneficiaries", [])}
    if ticker_key in directs or ticker_key in secondaries:
        return "bullish"
    return "neutral"


def _dedup_news_items(news_items: list[dict]) -> list[dict]:
    """Collapse syndicated duplicates of the same story.

    The same headline often arrives via several outlets and gets interpreted
    into near-identical items; counting each copy would fake the multi-signal
    support that the buy-now gate requires. Keeps the freshest copy.
    """
    best: dict[tuple, dict] = {}
    for news in news_items:
        directs = ",".join(sorted(b.upper() for b in news.get("direct_beneficiaries", [])))
        summary_key = _normalize_text(news.get("summary", ""))
        key = (news.get("theme_id"), directs, summary_key)
        existing = best.get(key)
        if existing is None:
            best[key] = news
            continue
        age_new = _news_age_hours(news)
        age_old = _news_age_hours(existing)
        if age_new is not None and (age_old is None or age_new < age_old):
            best[key] = news
    return list(best.values())


def _social_evidence(item: dict, sentiment: dict) -> dict:
    mentions = item.get("mentions", 0)
    mentions_24h = item.get("mentions_24h_ago", 0)
    return {
        "mentions": mentions,
        "mentions_24h_ago": mentions_24h,
        "mention_change": item.get("mention_change", 0),
        "rank": item.get("rank"),
        "rank_24h_ago": item.get("rank_24h_ago"),
        "upvotes": item.get("upvotes", 0),
        "sources": list(item.get("sources", [])),
        "score": item.get("score", 0),
        "momentum": sentiment.get("momentum"),
        "sentiment": sentiment.get("sentiment"),
        "sentiment_confidence": sentiment.get("confidence", 0),
        "bullish_points": sentiment.get("bullish_points", 0),
        "bearish_points": sentiment.get("bearish_points", 0),
        "reason": sentiment.get("reason", "low activity"),
        "is_trending": mentions > 0 or len(item.get("sources", [])) > 0,
    }


def _format_social_summary(evidence: dict) -> str:
    if not evidence.get("is_trending"):
        return "not trending on tracked Reddit sources"

    mention_change = evidence.get("mention_change", 0)
    rank = evidence.get("rank")
    rank_24h = evidence.get("rank_24h_ago")
    rank_text = "rank n/a"
    if rank and rank_24h:
        rank_text = f"rank #{rank_24h}→#{rank}"
    elif rank:
        rank_text = f"rank #{rank}"

    return (
        f"mentions {evidence.get('mentions', 0)} ({mention_change:+.0%} vs 24h), "
        f"{rank_text}, upvotes {evidence.get('upvotes', 0)}, "
        f"sources {len(evidence.get('sources', []))}, momentum {evidence.get('momentum', 'unknown')}"
    )


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
        "signal_direction": _ticker_impact_direction(news, ticker),
        "beneficiary_rank": max(0, 3 - beneficiary_index),
    }


def _candidate_universe(source_items: dict) -> list[dict]:
    social_items = sorted(
        source_items.get("raw_social", []),
        key=lambda item: item.get("score", 0),
        reverse=True,
    )[:12]

    merged: dict[str, dict] = {item["ticker"].upper(): dict(item) for item in social_items}

    for news in _dedup_news_items(source_items.get("news", [])):
        if not news.get("market_relevant"):
            continue
        actionability_rank = _actionability_rank(news)
        if actionability_rank < 1:
            continue
        # Stale news (> 48h) cannot seed new candidates. It may still appear
        # as supporting context via _related_news_items for existing
        # candidates, but it won't create fresh buy candidates.
        age_hours = _news_age_hours(news)
        if age_hours is not None and age_hours > STALE_REJECT_HOURS:
            continue

        for index, ticker in enumerate(news.get("direct_beneficiaries", [])):
            key = ticker.upper()
            candidate = _build_news_candidate(key, news, direct=True, beneficiary_index=index)
            if candidate["signal_direction"] in {"bearish", "neutral"}:
                continue
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
            if candidate["signal_direction"] in {"bearish", "neutral"}:
                continue
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
        "bearish_hits": 0,
        "mixed_hits": 0,
        "freshest_direct_hours": None,
        "freshest_any_hours": None,
    }
    freshest_direct = math.inf
    freshest_any = math.inf
    for news in related_news:
        directs = {b.lower() for b in news.get("direct_beneficiaries", [])}
        secondaries = {b.lower() for b in news.get("secondary_beneficiaries", [])}
        is_direct = ticker_key in directs
        is_secondary = ticker_key in secondaries
        direction = _ticker_impact_direction(news, ticker)
        is_bullish = direction == "bullish"
        if is_direct and is_bullish:
            profile["direct_hits"] += 1
        if is_secondary and is_bullish:
            profile["secondary_hits"] += 1
        if (is_direct or is_secondary) and direction == "bearish":
            profile["bearish_hits"] += 1
        if (is_direct or is_secondary) and direction == "mixed":
            profile["mixed_hits"] += 1
        actionability_rank = _actionability_rank(news)
        if is_bullish and actionability_rank >= 3:
            profile["actionable_count"] += 1
        if is_bullish and actionability_rank >= 2:
            profile["potentially_actionable_count"] += 1
        if is_bullish and news.get("confidence") == "high":
            profile["high_confidence_count"] += 1
        elif is_bullish and news.get("confidence") == "medium":
            profile["medium_confidence_count"] += 1
        if is_bullish and news.get("durability") == "high":
            profile["high_durability_count"] += 1

        age_hours = _news_age_hours(news)
        if age_hours is not None:
            if age_hours < freshest_any:
                freshest_any = age_hours
            if is_direct and is_bullish and age_hours < freshest_direct:
                freshest_direct = age_hours

    if freshest_direct != math.inf:
        profile["freshest_direct_hours"] = round(freshest_direct, 2)
    if freshest_any != math.inf:
        profile["freshest_any_hours"] = round(freshest_any, 2)
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


# Shared with watchlist reviews — see confirmation.py. Alias kept because the
# replay harness diagnose path references signals._confirmation_state.
_confirmation_state = confirmation_state


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


def _social_is_actionable(evidence: dict) -> bool:
    if not evidence.get("is_trending"):
        return False
    if evidence.get("bearish_points", 0) > 0 and evidence.get("bullish_points", 0) < MIN_SOCIAL_BUY_POINTS + 1:
        return False
    if evidence.get("bullish_points", 0) < MIN_SOCIAL_BUY_POINTS:
        return False
    if evidence.get("momentum") == "fading":
        return False
    return True


def _has_recent_reddit_confirmation(item: dict) -> bool:
    mentions = item.get("mentions", 0)
    mentions_24h = item.get("mentions_24h_ago", 0)
    if mentions <= 0 and mentions_24h <= 0:
        return False
    return True


def _freshness_gate_action(action: str, confirmation: str, support: dict) -> str:
    """Downgrade buy_now actions whose driving news is too stale.

    A fresh buy requires a news catalyst within FRESH_BUY_HOURS. Without
    that, even a textbook setup is almost always late — the move has
    already played out by the time we're looking at it. In that case
    degrade to hold_not_fresh_buy (if already confirmed) or
    watch_for_confirmation (still developing).

    When no age info is available at all (e.g. historical replay items
    that use synthetic source_item_ids) the gate is a no-op — we fall
    back to the legacy rule-driven behavior.
    """
    if action != "buy_now":
        return action

    freshest_direct = support.get("freshest_direct_hours")
    freshest_any = support.get("freshest_any_hours")

    if freshest_direct is None and freshest_any is None:
        # No age signal — trust the upstream rules (replay, missing ids, etc.)
        return action

    if freshest_direct is not None and freshest_direct <= FRESH_BUY_HOURS:
        return action
    if support.get("direct_hits", 0) == 0 and freshest_any is not None and freshest_any <= FRESH_BUY_HOURS:
        return action

    if confirmation in ("confirmed", "overconfirmed"):
        return "hold_not_fresh_buy"
    return "watch_for_confirmation"


def _early_setup_state(
    theme_id: str | None,
    confirmation: str,
    crowding: str,
    confidence: str,
    data: dict,
    sentiment: dict,
    support: dict,
    direct_news_candidate: bool,
) -> str | None:
    """Flag fresh, low-extension setups that look early rather than late."""
    if not direct_news_candidate:
        return None
    if confidence not in ("medium", "high"):
        return None
    if support.get("potentially_actionable_count", 0) < 1:
        return None
    if support.get("high_confidence_count", 0) < 1 and support.get("direct_hits", 0) < 2:
        return None

    freshest_direct = support.get("freshest_direct_hours")
    if freshest_direct is None or freshest_direct > FRESH_BUY_HOURS:
        return None

    change_pct = data.get("change_pct", 0)
    change_5d = data.get("change_5d", 0) or 0
    volume_ratio = data.get("volume_ratio", 0)
    trend = data.get("trend")

    if crowding == "high":
        return None
    if change_pct >= 0.05 or change_5d >= 0.10:
        return None
    if trend not in ("up", "strong_up"):
        return None
    if volume_ratio < 0.7 or volume_ratio > 1.6:
        return None
    if confirmation not in ("developing", "confirmed"):
        return None

    speculative_themes = {
        "battery_storage_commercialization",
        "healthcare_commercialization",
    }
    if theme_id in speculative_themes and support.get("actionable_count", 0) < 1:
        return None

    if sentiment.get("bullish_points", 0) < 2:
        return None

    return "early_accumulation"


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
    action = _recommendation_action_raw(
        theme_id,
        confirmation,
        crowding,
        confidence,
        data,
        sentiment,
        support,
        direct_news_candidate,
    )
    return _freshness_gate_action(action, confirmation, support)


def _recommendation_action_raw(
    theme_id: str | None,
    confirmation: str,
    crowding: str,
    confidence: str,
    data: dict,
    sentiment: dict,
    support: dict,
    direct_news_candidate: bool,
) -> str:
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
        # M&A should favor the named target. Acquirers or broad sympathy moves
        # are too noisy for automatic buy_now promotion.
        if (
            direct_news_candidate
            and confirmation in ("developing", "confirmed")
            and confidence in ("medium", "high")
            and support["direct_hits"] >= 2
            and support["actionable_count"] >= 2
            and data.get("dollar_volume", 0) >= 10_000_000
            and data.get("volume_ratio", 0) >= 0.8
            and data.get("change_pct", 0) >= -0.02
            and support["high_confidence_count"] >= 1
            and data.get("change_pct", 0) <= 0.12
            and sentiment.get("bullish_points", 0) >= 3
            and support["secondary_hits"] == 0
        ):
            return "buy_now"
        return "watch_for_confirmation"

    # Fallback: unknown themes must not get an easier path than named themes.
    # Default to watch until a theme proves itself and gets its own gate.
    if confirmation == "overconfirmed":
        return "hold_not_fresh_buy"
    return "watch_for_confirmation"


def _non_buy_gate_reasons(
    action: str,
    signal_origin: str | None,
    confirmation: str,
    crowding: str,
    confidence: str,
    data: dict,
    sentiment: dict,
    support: dict,
    social_evidence: dict,
    contradictory_catalyst: bool,
    market_accessible: bool,
) -> list[str]:
    if action == "buy_now":
        return []

    reasons: list[str] = []
    if not market_accessible:
        reasons.append("market_not_accessible")
    if contradictory_catalyst:
        reasons.append("contradictory_catalyst")
    if confirmation not in ("developing", "confirmed", "overconfirmed"):
        reasons.append(f"confirmation_{confirmation}")
    if confirmation == "overconfirmed":
        reasons.append("overconfirmed")
    if crowding == "high":
        reasons.append("crowding_high")
    if confidence == "low":
        reasons.append("confidence_low")
    if support.get("potentially_actionable_count", 0) < 1:
        reasons.append("insufficient_actionable_news")
    if support.get("direct_hits", 0) == 0 and support.get("secondary_hits", 0) == 0:
        reasons.append("no_direct_or_secondary_news_hit")
    if support.get("freshest_direct_hours") is not None and support["freshest_direct_hours"] > FRESH_BUY_HOURS:
        reasons.append("direct_catalyst_stale")
    if data.get("volume_ratio", 0) < 0.75:
        reasons.append("volume_too_low")
    if data.get("change_pct", 0) < -0.02:
        reasons.append("price_reaction_negative")
    if signal_origin != "interpreted_news" and not _social_is_actionable(social_evidence):
        reasons.append("social_not_actionable")
    if not reasons:
        reasons.append("theme_specific_buy_gate_not_met")
    return reasons


def generate_signal_scan(source_items: dict) -> tuple[list[dict], list[dict]]:
    """Return theme records and recommendation records for the MVP."""
    theme_records: list[dict] = []
    candidate_records: list[dict] = []

    news_items = _dedup_news_items(source_items.get("news", []))
    candidates = _candidate_universe(source_items)
    market_data_attempts = 0
    market_data_failures: list[str] = []

    for item in candidates:
        ticker = item["ticker"]
        if item.get("signal_origin") == "interpreted_news":
            direction = item.get("signal_direction", "neutral")
            bullish_points = 0
            if direction == "bullish":
                bullish_points = 3 if item.get("signal_direct") else 2
            elif direction == "mixed":
                bullish_points = 1
            sentiment = {
                "sentiment": direction,
                "confidence": 0.7 if item.get("signal_direct") else 0.5,
                "reason": item.get("signal_summary") or "Interpreted market catalyst",
                "momentum": "steady",
                "bullish_points": bullish_points,
                "bearish_points": 3 if direction == "bearish" else 1 if direction == "mixed" else 0,
            }
        else:
            sentiment = analyze_mention_sentiment(item)
            if sentiment["sentiment"] != "bullish":
                continue

        social_evidence = _social_evidence(item, sentiment)

        market_data_attempts += 1
        data = get_stock_data(ticker)
        if not data:
            market_data_failures.append(ticker)
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
        direct_news_candidate = support["direct_hits"] >= 1
        action = _recommendation_action(
            theme_meta.get("theme_id"),
            confirmation,
            crowding,
            confidence,
            data,
            sentiment,
            support,
        )
        early_setup = _early_setup_state(
            theme_meta.get("theme_id"),
            confirmation,
            crowding,
            confidence,
            data,
            sentiment,
            support,
            direct_news_candidate,
        )
        if action == "watch_for_confirmation" and early_setup:
            action = early_setup
        if not market_profile["accessible"] and action in ("buy_now", "early_accumulation"):
            action = "watch_for_confirmation"

        contradictory_catalyst = support.get("bearish_hits", 0) > 0 or support.get("mixed_hits", 0) > 0
        if related_news:
            first_news = related_news[0]
            summary_blob = " ".join(
                str(first_news.get(k, "")).lower() for k in ("summary", "title", "reasoning_notes")
            )
            # Word-boundary patterns: bare substring "miss" used to match
            # "missile"/"commission" and falsely block defense buys.
            contradiction_patterns = (
                r"weak guidance",
                r"weak revenue",
                r"cuts guidance",
                r"\bmiss(?:es|ed)?\b",
                r"\bdowngrades?\b",
                r"lower demand",
                r"pressure in diagnostics demand",
            )
            contradictory_catalyst = contradictory_catalyst or any(
                re.search(p, summary_blob) for p in contradiction_patterns
            )

        if action == "buy_now":
            if contradictory_catalyst:
                action = "watch_for_confirmation"
            elif item.get("signal_origin") != "interpreted_news" and not _social_is_actionable(social_evidence):
                action = "watch_for_confirmation"

        gate_reasons = _non_buy_gate_reasons(
            action,
            item.get("signal_origin"),
            confirmation,
            crowding,
            confidence,
            data,
            sentiment,
            support,
            social_evidence,
            contradictory_catalyst,
            market_profile["accessible"],
        )

        social_summary = _format_social_summary(social_evidence)
        why_now = (
            f"Social: {social_summary}. Market: {data['trend']} trend, volume at {data['volume_ratio']:.1f}x average"
        )
        if related_news:
            catalyst_text = related_news[0].get("summary") or related_news[0].get("title") or theme_label
            why_now += f". Catalyst: {catalyst_text}"
        if contradictory_catalyst:
            why_now += ". Warning: catalyst text reads bearish/contradictory, so this is not a clean fresh buy"
        else:
            why_now += "."
        # Machine-checkable invalidation conditions: watchlist reviews evaluate
        # these structurally instead of substring-matching prose (which never
        # matched the old boilerplate and left invalidation dead).
        adm = data.get("avg_daily_move") or 0.02
        drawdown_limit = round(max(0.04, adm * 3), 4)
        invalidation_conditions = [
            {
                "type": "confirmation_loss",
                "detail": "market confirmation drops back to unconfirmed",
            },
            {
                "type": "trend_break",
                "detail": "price loses both key EMAs (trend turns down/weak)",
            },
            {
                "type": "adaptive_drawdown",
                "threshold_pct": drawdown_limit,
                "detail": f"position falls more than {drawdown_limit:.1%} from entry (~3x normal daily move)",
            },
        ]
        invalidation = "; ".join(c["detail"] for c in invalidation_conditions)

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
                "relevance_note": _format_social_summary(social_evidence),
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
            "social_evidence": social_evidence,
            "reference_price": data.get("price"),
            "invalidation": invalidation,
            "invalidation_conditions": invalidation_conditions,
            "alternatives": [],
            "gate_reasons": gate_reasons,
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
        if candidate_record["market_accessible"]:
            # Pair rec with its own theme record; a positional zip drifted
            # whenever an inaccessible candidate was skipped.
            candidate_records.append((candidate_record, theme_record))

    if market_data_attempts >= 3 and len(market_data_failures) / market_data_attempts >= 0.75:
        failed = ", ".join(sorted(set(market_data_failures)))
        raise MarketDataCoverageError(
            f"Market data unavailable for {len(market_data_failures)}/{market_data_attempts} candidates: {failed}"
        )

    grouped: dict[str, list[dict]] = {}
    latest_theme_record: dict[str, dict] = {}
    for rec, theme in candidate_records:
        grouped.setdefault(rec["theme_driver"], []).append(rec)
        latest_theme_record[rec["theme_driver"]] = theme

    recommendations: list[dict] = []
    final_theme_records: list[dict] = []

    def ranking_key(rec: dict) -> tuple:
        action_rank = {
            "buy_now": 5,
            "early_accumulation": 4,
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
            if alt["action"] not in ("buy_now", "early_accumulation", "watch_for_confirmation", "hold_not_fresh_buy"):
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
