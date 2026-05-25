"""Source collection for Aurel3."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote
from xml.etree import ElementTree as ET

import httpx

from openclaw_bridge import export_source_batch, load_fresh_interpreted_items
from scanner import scan_all_sources
from state import utc_now_iso

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
# News older than this is skipped at collection time — anything older is almost
# never actionable for momentum trading because the price move has usually
# already played out. See signals._news_age_hours for the downstream gate.
MAX_NEWS_AGE_DAYS = 2

NEWS_QUERIES = [
    ("romania_bvb", "BVB OR \"Bucharest Stock Exchange\" OR Romania IPO stocks"),
    ("eu_policy", "\"EU defense spending\" stocks OR Europe industrial policy stocks"),
    ("energy", "oil gas energy stocks geopolitical tensions"),
    ("ai", "AI investment stocks semiconductors data center"),
    ("healthcare", "pharma biotech drug approval commercialization stocks"),
    ("materials", "rare earth lithium nickel copper uranium battery materials stocks"),
    ("banking", "banking rates credit financial stocks"),
    ("agriculture", "agriculture fertilizer food supply stocks"),
    ("infrastructure", "infrastructure grid construction industrial capex stocks"),
    ("earnings", "earnings guidance stock market"),
    ("ma", "\"merger\" OR acquisition stocks"),
    ("ipo", "IPO stock market listing"),
]


def _parse_google_news_feed(xml_text: str, label: str) -> list[dict]:
    items: list[dict] = []
    root = ET.fromstring(xml_text)
    for item in root.findall(".//item")[:8]:
        title = item.findtext("title", default="").strip()
        link = item.findtext("link", default="").strip()
        pub_date = item.findtext("pubDate", default="").strip()
        source = item.findtext("source", default="Google News").strip() or "Google News"
        timestamp = utc_now_iso()
        if pub_date:
            try:
                timestamp = parsedate_to_datetime(pub_date).astimezone().isoformat()
            except Exception:
                pass
        items.append({
            "type": "news",
            "provider": "google_news_rss",
            "label": label,
            "timestamp": timestamp,
            "title": title,
            "url": link,
            "publisher": source,
        })
    return items


def collect_news_items() -> list[dict]:
    items: list[dict] = []
    now = datetime.now(timezone.utc)
    with httpx.Client(timeout=20, follow_redirects=True) as client:
        for label, query in NEWS_QUERIES:
            try:
                url = GOOGLE_NEWS_RSS.format(query=quote(query))
                resp = client.get(url)
                if resp.status_code != 200:
                    continue
                parsed_items = _parse_google_news_feed(resp.text, label)
                for item in parsed_items:
                    try:
                        ts = datetime.fromisoformat(item["timestamp"])
                    except Exception:
                        continue
                    if now - ts > timedelta(days=MAX_NEWS_AGE_DAYS):
                        continue
                    if ts > now + timedelta(days=1):
                        continue
                    items.append(item)
            except Exception:
                continue
    return items


def collect_source_items(*, export_batch: bool = False) -> dict:
    """Collect a normalized set of source items.

    MVP scope:
    - social: ApeWisdom / Reddit proxy
    - news: public RSS search feeds
    - events: empty placeholder
    """
    social_items = []
    raw_social = scan_all_sources()
    now = utc_now_iso()

    for item in raw_social:
        social_items.append({
            "type": "social",
            "provider": "apewisdom",
            "timestamp": now,
            "payload": item,
        })

    raw_news_items = collect_news_items()
    if export_batch:
        export_source_batch({
            "news": raw_news_items,
            "social": social_items,
        })
    interpreted_news_items = load_fresh_interpreted_items()
    news_items = interpreted_news_items

    payload = {
        "social": social_items,
        "news": news_items,
        "raw_news": raw_news_items,
        "events": [],
        "raw_social": raw_social,
    }
    return payload
