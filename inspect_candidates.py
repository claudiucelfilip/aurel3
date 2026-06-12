#!/usr/bin/env python3
"""Inspect live signal candidates for threshold tuning."""

from sources import collect_source_items
from sentiment import analyze_mention_sentiment
from market import get_stock_data, get_sector
from signals import _confirmation_state, _crowding_state, _confidence_label


def main() -> None:
    source_items = collect_source_items()
    raw = sorted(source_items["raw_social"], key=lambda x: x.get("score", 0), reverse=True)[:12]

    for item in raw:
        ticker = item["ticker"]
        sentiment = analyze_mention_sentiment(item)
        if sentiment["sentiment"] != "bullish":
            continue

        data = get_stock_data(ticker)
        if not data:
            continue

        confirmation = _confirmation_state(data)
        crowding = _crowding_state(data, item.get("mention_change", 0), sentiment.get("bullish_points", 0))
        confidence = _confidence_label(sentiment, confirmation, crowding)

        print({
            "ticker": ticker,
            "score": item.get("score"),
            "mentions": item.get("mentions"),
            "mention_change": item.get("mention_change"),
            "bullish_points": sentiment.get("bullish_points"),
            "momentum": sentiment.get("momentum"),
            "trend": data.get("trend"),
            "change_pct": data.get("change_pct"),
            "volume_ratio": data.get("volume_ratio"),
            "price": data.get("price"),
            "ema_20": data.get("ema_20"),
            "confirmation": confirmation,
            "crowding": crowding,
            "confidence": confidence,
            "sector": get_sector(ticker),
        })


if __name__ == "__main__":
    main()
