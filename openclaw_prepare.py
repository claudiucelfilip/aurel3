#!/usr/bin/env python3
"""Prepare an OpenClaw interpretation task payload from the latest source batch."""

from __future__ import annotations

import json
from pathlib import Path

from state import load_openclaw_source_batch


EXCLUDE_TITLE_MARKERS = [
    "which ",
    "top-ranked",
    "top ranked",
    "top ",
    "best ",
    "stocks to buy",
    "should you buy",
    "motley fool",
    "zacks",
    "vs.",
    "versus",
]


def _keep_item(item: dict) -> bool:
    title = (item.get("title") or "").strip().lower()
    if not title:
        return False
    return not any(marker in title for marker in EXCLUDE_TITLE_MARKERS)

PROMPT_PATH = Path(__file__).parent / "OPENCLAW_WORKER.md"
TASK_PATH = Path(__file__).parent / "data" / "openclaw_task_payload.json"


def main() -> int:
    batch = load_openclaw_source_batch()
    if not batch.get("items"):
        print("No source batch items available. Run signal_scan or openclaw_export first.")
        return 1

    prompt_text = PROMPT_PATH.read_text()
    filtered_batch = dict(batch)
    filtered_batch["items"] = [item for item in batch.get("items", []) if _keep_item(item)]

    payload = {
        "prepared_at": batch.get("generated_at"),
        "instructions_ref": str(PROMPT_PATH.name),
        "task": (
            "Interpret the attached source batch for Aurel3 and return only JSON "
            "matching the schema in OPENCLAW_WORKER.md."
        ),
        "source_batch": filtered_batch,
        "prompt_markdown": prompt_text,
    }

    with open(TASK_PATH, "w") as f:
        json.dump(payload, f, indent=2)

    print(
        f"Prepared OpenClaw task payload with {len(filtered_batch.get('items', []))} items "
        f"(from {len(batch.get('items', []))}) at {TASK_PATH}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
