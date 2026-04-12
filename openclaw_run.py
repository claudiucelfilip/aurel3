#!/usr/bin/env python3
"""Run OpenClaw interpretation through the local OpenClaw gateway/agent."""

from __future__ import annotations

import json
import subprocess
import time
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
        "max_retries": int(openclaw.get("max_retries", 3)),
        "retry_delay_seconds": int(openclaw.get("retry_delay_seconds", 8)),
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


def _describe_provider(envelope: dict) -> str:
    """Best-effort human-readable provider/model label for error messages."""
    agent_meta = envelope.get("result", {}).get("meta", {}).get("agentMeta", {})
    provider = agent_meta.get("provider") or "?"
    model = agent_meta.get("model") or "?"
    return f"{provider}/{model}"


def check_envelope_for_errors(envelope: dict) -> None:
    """Raise a descriptive error if the CLI envelope indicates a failure.

    The OpenClaw envelope reports top-level ``status`` and a
    ``result.meta`` block with ``stopReason`` and ``aborted`` flags.
    When a provider (e.g. Gemini) returns an error like a 429 quota
    exhausted, the envelope still comes back with status=ok but empty
    payloads and stopReason=error. We surface that explicitly instead
    of failing downstream with a cryptic JSON-parse error.
    """
    if envelope.get("status") and envelope.get("status") != "ok":
        raise RuntimeError(
            "OpenClaw agent returned non-ok status: "
            f"{envelope.get('status')} (summary={envelope.get('summary')!r}, "
            f"model={_describe_provider(envelope)})"
        )
    result = envelope.get("result", {})
    meta = result.get("meta", {})
    if meta.get("aborted"):
        raise RuntimeError(
            f"OpenClaw agent run was aborted (model={_describe_provider(envelope)})."
        )
    stop_reason = meta.get("stopReason")
    if stop_reason and stop_reason not in ("stop", "end_turn", "tool_use"):
        raise RuntimeError(
            f"OpenClaw agent returned stopReason={stop_reason!r} "
            f"(model={_describe_provider(envelope)}). "
            "This typically indicates a provider-side error (rate limit, "
            "auth, content filter, etc.)."
        )


def extract_agent_text(payload: dict) -> str:
    result = payload.get("result", {})
    payloads = result.get("payloads", [])
    if not payloads:
        raise ValueError(
            "OpenClaw agent returned zero payloads "
            f"(model={_describe_provider(payload)}). Likely a provider error."
        )
    for item in payloads:
        text = item.get("text")
        if text:
            return text
    raise ValueError(
        "OpenClaw agent response had payloads but no text content "
        f"(model={_describe_provider(payload)})."
    )


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


def _extract_json_object(text: str, envelope: dict) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    start = text.find("{")
    if start < 0:
        excerpt = text[:400].replace("\n", " ")
        raise ValueError(
            "No JSON object found in OpenClaw response "
            f"(model={_describe_provider(envelope)}, text_len={len(text)}). "
            f"First 400 chars: {excerpt!r}"
        )

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
                    return json.loads(fragment, strict=False)

    excerpt = text[start : start + 400].replace("\n", " ")
    raise ValueError(
        "Incomplete JSON object in OpenClaw response "
        f"(model={_describe_provider(envelope)}). Excerpt: {excerpt!r}"
    )


def _invoke_openclaw_once(runtime: dict, task_payload: dict) -> dict:
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
    result = subprocess.run(
        cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        details = result.stderr.strip() or result.stdout.strip() or "unknown error"
        raise RuntimeError(f"OpenClaw agent invocation failed: {details}")
    if not result.stdout.strip():
        raise RuntimeError("OpenClaw agent invocation returned empty stdout.")

    try:
        envelope = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        excerpt = result.stdout[:400].replace("\n", " ")
        raise ValueError(
            f"OpenClaw agent returned invalid CLI JSON envelope: {exc}. First 400 chars: {excerpt!r}"
        ) from exc

    check_envelope_for_errors(envelope)
    text = extract_agent_text(envelope)
    return _extract_json_object(text, envelope)


def call_openclaw_agent(runtime: dict, task_payload: dict) -> dict:
    interpretation_model = runtime.get("model")
    prev_model = None
    if interpretation_model:
        prev_model = _switch_model(interpretation_model)

    max_retries = max(1, int(runtime.get("max_retries", 3)))
    retry_delay_seconds = max(0, int(runtime.get("retry_delay_seconds", 8)))
    last_error: Exception | None = None

    try:
        for attempt in range(1, max_retries + 1):
            try:
                return _invoke_openclaw_once(runtime, task_payload)
            except Exception as exc:
                last_error = exc
                print(f"OpenClaw run attempt {attempt}/{max_retries} failed: {exc}")
                if attempt >= max_retries:
                    break
                if retry_delay_seconds > 0:
                    time.sleep(retry_delay_seconds)
    finally:
        if prev_model:
            _switch_model(prev_model)

    raise RuntimeError(
        f"OpenClaw agent failed after {max_retries} attempts: {last_error}"
    )


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

    # Validate against the batch we actually used, not whatever is on disk
    # right now. Re-reading the batch here would race with a concurrent
    # openclaw_export (seen 2026-04-08 13:30 & 17:30 in runtime.log where
    # the on-disk batch ended up ~5s ahead of the one that drove the task).
    errors = validate_payload(interpreted, batch=trimmed_payload.get("source_batch"))
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
