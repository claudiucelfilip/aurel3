"""Persistent state helpers for Aurel3."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
THEMES_PATH = DATA_DIR / "theme_events.json"
RECOMMENDATIONS_PATH = DATA_DIR / "recommendations.json"
RECOMMENDATION_HISTORY_PATH = DATA_DIR / "recommendation_history.json"
CLOSED_REVIEWS_PATH = DATA_DIR / "closed_reviews.json"
RECOMMENDATION_REVIEWS_PATH = DATA_DIR / "recommendation_reviews.json"
OPENCLAW_SOURCE_BATCH_PATH = DATA_DIR / "openclaw_source_batch.json"
OPENCLAW_INTERPRETED_ITEMS_PATH = DATA_DIR / "openclaw_interpreted_items.json"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_id(prefix: str, suffix: str = "") -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    clean_suffix = suffix.lower().replace(" ", "_") if suffix else ""
    return f"{prefix}_{ts}" + (f"_{clean_suffix}" if clean_suffix else "")


def _load_json(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path) as f:
        return json.load(f)


def _save_json(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(records, f, indent=2)


def load_theme_events() -> list[dict]:
    return _load_json(THEMES_PATH)


def save_theme_events(records: list[dict]) -> None:
    _save_json(THEMES_PATH, records)


def append_theme_event(record: dict) -> None:
    records = load_theme_events()
    records.append(record)
    save_theme_events(records)


def load_recommendations() -> list[dict]:
    return _load_json(RECOMMENDATIONS_PATH)


def save_recommendations(records: list[dict]) -> None:
    _save_json(RECOMMENDATIONS_PATH, records)


def load_recommendation_history() -> list[dict]:
    return _load_json(RECOMMENDATION_HISTORY_PATH)


def append_recommendation_snapshot(records: list[dict], metadata: dict | None = None) -> dict:
    snapshot = {
        "id": make_id("recsnap"),
        "generated_at": utc_now_iso(),
        "metadata": metadata or {},
        "recommendations": records,
    }
    history = load_recommendation_history()
    history.append(snapshot)
    _save_json(RECOMMENDATION_HISTORY_PATH, history)
    return snapshot


def append_recommendation(record: dict) -> None:
    records = load_recommendations()
    records.append(record)
    save_recommendations(records)


def load_closed_reviews() -> list[dict]:
    return _load_json(CLOSED_REVIEWS_PATH)


def save_closed_reviews(records: list[dict]) -> None:
    _save_json(CLOSED_REVIEWS_PATH, records)


def append_closed_review(record: dict) -> None:
    records = load_closed_reviews()
    records.append(record)
    save_closed_reviews(records)


def load_recommendation_reviews() -> list[dict]:
    return _load_json(RECOMMENDATION_REVIEWS_PATH)


def save_recommendation_reviews(records: list[dict]) -> None:
    _save_json(RECOMMENDATION_REVIEWS_PATH, records)


def append_recommendation_review(record: dict) -> None:
    records = load_recommendation_reviews()
    records.append(record)
    save_recommendation_reviews(records)


def load_openclaw_source_batch() -> dict:
    if not OPENCLAW_SOURCE_BATCH_PATH.exists():
        return {"generated_at": None, "items": []}
    with open(OPENCLAW_SOURCE_BATCH_PATH) as f:
        return json.load(f)


def save_openclaw_source_batch(batch: dict) -> None:
    OPENCLAW_SOURCE_BATCH_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OPENCLAW_SOURCE_BATCH_PATH, "w") as f:
        json.dump(batch, f, indent=2)


def load_openclaw_interpreted_items() -> dict:
    if not OPENCLAW_INTERPRETED_ITEMS_PATH.exists():
        return {"generated_at": None, "items": []}
    with open(OPENCLAW_INTERPRETED_ITEMS_PATH) as f:
        return json.load(f)


def save_openclaw_interpreted_items(payload: dict) -> None:
    OPENCLAW_INTERPRETED_ITEMS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OPENCLAW_INTERPRETED_ITEMS_PATH, "w") as f:
        json.dump(payload, f, indent=2)


def find_latest_active_recommendation(ticker: str) -> dict | None:
    ticker = ticker.upper()
    for rec in reversed(load_recommendations()):
        if rec.get("ticker") == ticker and rec.get("status") == "active":
            return rec
    return None


def mark_recommendation_promoted(rec_id: str) -> None:
    records = load_recommendations()
    changed = False
    for rec in records:
        if rec.get("id") == rec_id:
            rec["status"] = "promoted_to_watchlist"
            changed = True
            break
    if changed:
        save_recommendations(records)
