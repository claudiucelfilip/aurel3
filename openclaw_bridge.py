"""OpenClaw file-bridge helpers for Aurel3."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from state import (
    load_openclaw_interpreted_items,
    load_openclaw_source_batch,
    save_openclaw_source_batch,
    utc_now_iso,
)


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts)
    except Exception:
        return None


def export_source_batch(source_items: dict) -> dict:
    items = []
    for item in source_items.get("news", []):
        items.append({
            "id": f"news::{item.get('label', 'news')}::{item.get('timestamp', utc_now_iso())}::{item.get('title', '')[:40]}",
            "type": "news",
            "source": item.get("provider", "unknown"),
            "label": item.get("label"),
            "title": item.get("title"),
            "snippet": item.get("title"),
            "url": item.get("url"),
            "timestamp": item.get("timestamp"),
            "publisher": item.get("publisher"),
        })

    payload = {
        "generated_at": utc_now_iso(),
        "instructions": (
            "Interpret each source item into a structured market event with fields: "
            "market_relevant, event_type, theme_id, theme_label, summary, beneficiary_sectors, "
            "hurt_sectors, direct_beneficiaries, secondary_beneficiaries, time_horizon, durability, "
            "confidence, actionability, reasoning_notes."
        ),
        "items": items,
    }
    save_openclaw_source_batch(payload)
    return payload


def load_fresh_interpreted_items(max_age_hours: int = 12) -> list[dict]:
    payload = load_openclaw_interpreted_items()
    generated_at = _parse_iso(payload.get("generated_at"))
    if not generated_at:
        return []
    current_batch = load_openclaw_source_batch()
    current_batch_generated_at = current_batch.get("generated_at")
    payload_batch_generated_at = payload.get("source_batch_generated_at")
    if not current_batch_generated_at or payload_batch_generated_at != current_batch_generated_at:
        return []
    now = datetime.now(timezone.utc)
    if now - generated_at > timedelta(hours=max_age_hours):
        return []
    return payload.get("items", [])
