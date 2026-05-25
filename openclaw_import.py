#!/usr/bin/env python3
"""Validate and import OpenClaw interpreted payloads into Aurel3 state."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from state import load_openclaw_source_batch, save_openclaw_interpreted_items

REQUIRED_TOP_LEVEL = {"generated_at", "source_batch_generated_at", "items"}
REQUIRED_ITEM_FIELDS = {
    "source_item_id",
    "market_relevant",
    "event_type",
    "theme_id",
    "theme_label",
    "summary",
    "beneficiary_sectors",
    "hurt_sectors",
    "direct_beneficiaries",
    "secondary_beneficiaries",
    "time_horizon",
    "durability",
    "confidence",
    "actionability",
    "reasoning_notes",
}


def _load_json(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


def validate_payload(payload: dict, batch: dict | None = None) -> list[str]:
    """Validate an interpreted payload against the source batch it came from.

    ``batch`` can be passed explicitly (e.g. from the task payload used to
    invoke the agent) to avoid a TOCTOU race against the on-disk batch file.
    When not provided, the current batch is loaded from disk — which is the
    right behavior for standalone imports via ``openclaw_import.py``.
    """
    errors: list[str] = []
    missing_top = REQUIRED_TOP_LEVEL - payload.keys()
    if missing_top:
        errors.append(f"Missing top-level fields: {sorted(missing_top)}")

    items = payload.get("items", [])
    if not isinstance(items, list):
        errors.append("Top-level 'items' must be a list.")
        return errors

    if batch is None:
        batch = load_openclaw_source_batch()
    batch_ids = {item.get("id") for item in batch.get("items", [])}
    batch_generated_at = batch.get("generated_at")
    payload_batch_generated_at = payload.get("source_batch_generated_at")
    if batch_generated_at and payload_batch_generated_at != batch_generated_at:
        errors.append(
            "Payload source_batch_generated_at does not match the current source batch: "
            f"{payload_batch_generated_at} != {batch_generated_at}"
        )

    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append(f"Item {idx} is not an object.")
            continue
        missing = REQUIRED_ITEM_FIELDS - item.keys()
        if missing:
            errors.append(f"Item {idx} missing fields: {sorted(missing)}")
        source_item_id = item.get("source_item_id")
        if batch_ids and source_item_id not in batch_ids:
            errors.append(f"Item {idx} source_item_id not found in current source batch: {source_item_id}")

    return errors


def main() -> int:
    if len(sys.argv) not in (2, 3):
        print("Usage: python3 openclaw_import.py PATH_TO_INTERPRETED_PAYLOAD.json [--force]")
        return 1

    path = Path(sys.argv[1])
    force = len(sys.argv) == 3 and sys.argv[2] == "--force"
    if not path.exists():
        print(f"File not found: {path}")
        return 1

    payload = _load_json(path)
    errors = [] if force else validate_payload(payload)
    if errors:
        print("Validation failed:")
        for error in errors:
            print(f"  - {error}")
        return 1

    save_openclaw_interpreted_items(payload)
    print(f"Imported interpreted payload with {len(payload.get('items', []))} items." + (" (forced)" if force else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
