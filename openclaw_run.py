#!/usr/bin/env python3
"""Run OpenClaw interpretation through the local OpenClaw gateway/agent."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from openclaw_import import validate_payload
from state import save_openclaw_interpreted_items, utc_now_iso

ROOT = Path(__file__).parent
CONFIG_PATH = ROOT / "config.json"
TASK_PATH = ROOT / "data" / "openclaw_task_payload.json"


def load_runtime_config() -> dict:
    with open(CONFIG_PATH) as f:
        config = json.load(f)
    openclaw = config.setdefault("openclaw", {})
    return {
        "agent_id": openclaw.get("agent_id", "main"),
        "model": openclaw.get("model"),
        "thinking": openclaw.get("thinking", "medium"),
        "timeout_seconds": int(openclaw.get("timeout_seconds", 120)),
        "max_input_items": int(openclaw.get("max_input_items", 40)),
    }


def load_task_payload() -> dict:
    if not TASK_PATH.exists():
        raise FileNotFoundError(
            "OpenClaw task payload not found. Run `python3 run.py openclaw_prepare` first."
        )
    with open(TASK_PATH) as f:
        return json.load(f)


def trim_task_payload(payload: dict, max_input_items: int) -> dict:
    trimmed = dict(payload)
    source_batch = dict(payload.get("source_batch", {}))
    items = list(source_batch.get("items", []))
    source_batch["items"] = items[:max_input_items]
    trimmed["source_batch"] = source_batch
    return trimmed


def build_agent_message(task_payload: dict) -> str:
    return "\n\n".join([
        "You are the OpenClaw worker for Aurel3.",
        "Read the task payload below and return only valid JSON matching the required output schema.",
        "Do not wrap the JSON in markdown fences.",
        json.dumps(task_payload, ensure_ascii=True),
    ])


def extract_agent_text(payload: dict) -> str:
    result = payload.get("result", {})
    for item in result.get("payloads", []):
        text = item.get("text")
        if text:
            return text
    raise ValueError("OpenClaw agent response did not include a text payload.")


def _switch_model(model: str) -> str | None:
    """Temporarily switch OpenClaw default model. Returns previous model or None."""
    try:
        result = subprocess.run(
            ["openclaw", "models", "status"],
            capture_output=True, text=True,
        )
        prev = None
        for line in result.stdout.splitlines():
            if line.strip().startswith("Default"):
                prev = line.split(":", 1)[1].strip()
                break
        if prev and prev != model:
            subprocess.run(
                ["openclaw", "models", "set", model],
                capture_output=True, text=True,
            )
            return prev
    except Exception:
        pass
    return None


def call_openclaw_agent(runtime: dict, task_payload: dict) -> dict:
    # Temporarily switch to the interpretation model if configured
    interpretation_model = runtime.get("model")
    prev_model = None
    if interpretation_model:
        prev_model = _switch_model(interpretation_model)

    message = build_agent_message(task_payload)
    cmd = [
        "openclaw",
        "agent",
        "--agent",
        runtime["agent_id"],
        "--json",
        "--thinking",
        runtime["thinking"],
        "--timeout",
        str(runtime["timeout_seconds"]),
        "--message",
        message,
    ]
    try:
        result = subprocess.run(
            cmd,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
    finally:
        if prev_model:
            _switch_model(prev_model)
    if result.returncode != 0:
        details = result.stderr.strip() or result.stdout.strip() or "unknown error"
        raise RuntimeError(f"OpenClaw agent invocation failed: {details}")

    envelope = json.loads(result.stdout)
    text = extract_agent_text(envelope)
    # Strip markdown fences if present
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()
    # Extract the first complete JSON object (models sometimes append extra text)
    start = text.find("{")
    if start < 0:
        raise ValueError("No JSON object found in OpenClaw response.")
    depth = 0
    for i, ch in enumerate(text[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                fragment = text[start : i + 1]
                try:
                    return json.loads(fragment)
                except json.JSONDecodeError:
                    # Models sometimes emit control characters — try strict=False
                    return json.loads(fragment, strict=False)
    raise ValueError("Incomplete JSON object in OpenClaw response.")


def main() -> int:
    runtime = load_runtime_config()
    task_payload = load_task_payload()
    trimmed_payload = trim_task_payload(task_payload, runtime["max_input_items"])
    interpreted = call_openclaw_agent(runtime, trimmed_payload)

    interpreted["generated_at"] = utc_now_iso()
    interpreted["source_batch_generated_at"] = (
        trimmed_payload.get("source_batch", {}).get("generated_at")
    )

    # Filter to items that match the current source batch
    batch_ids = {item.get("id") for item in trimmed_payload.get("source_batch", {}).get("items", [])}
    if batch_ids:
        interpreted["items"] = [
            item for item in interpreted.get("items", [])
            if item.get("source_item_id") in batch_ids
        ]

    # Backfill missing optional fields with safe defaults
    for item in interpreted.get("items", []):
        item.setdefault("theme_id", None)
        item.setdefault("theme_label", "")
        item.setdefault("event_type", "unknown")
        item.setdefault("durability", "medium")
        item.setdefault("time_horizon", "1-2 weeks")
        item.setdefault("confidence", "medium")
        item.setdefault("actionability", "informational")
        item.setdefault("reasoning_notes", "")
        item.setdefault("beneficiary_sectors", [])
        item.setdefault("hurt_sectors", [])
        item.setdefault("direct_beneficiaries", [])
        item.setdefault("secondary_beneficiaries", [])

    errors = validate_payload(interpreted)
    if errors:
        print("OpenClaw output validation failed:")
        for error in errors:
            print(f"  - {error}")
        return 1

    save_openclaw_interpreted_items(interpreted)
    print(
        "OpenClaw run complete: "
        f"{len(interpreted.get('items', []))} interpreted items saved."
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"OpenClaw run failed: {exc}")
        raise
