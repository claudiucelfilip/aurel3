#!/usr/bin/env python3
"""Run OpenClaw interpretation through the local OpenClaw gateway/agent."""

from __future__ import annotations

import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from openclaw_import import validate_payload
from state import save_openclaw_interpreted_items, utc_now_iso

ROOT = Path(__file__).parent
CONFIG_PATH = ROOT / "config.json"
TASK_PATH = ROOT / "data" / "openclaw_task_payload.json"
INTERPRETED_PATH = ROOT / "data" / "openclaw_interpreted_items.json"
FRESH_FALLBACK_SECONDS = 45 * 60


def load_runtime_config() -> dict:
    with open(CONFIG_PATH) as f:
        config = json.load(f)
    openclaw = config.setdefault("openclaw", {})
    return {
        "agent_id": openclaw.get("agent_id", "main"),
        "session_id": openclaw.get("session_id"),
        "use_isolated_run": bool(openclaw.get("use_isolated_run", True)),
        "model": openclaw.get("model"),
        "thinking": openclaw.get("thinking", "low"),
        "timeout_seconds": int(openclaw.get("timeout_seconds", 120)),
        "max_input_items": int(openclaw.get("max_input_items", 40)),
        "chunk_size": int(openclaw.get("chunk_size", 5)),
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


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def load_existing_interpreted_payload(task_payload: dict) -> dict | None:
    """Return a fresh valid interpreted payload when OpenClaw has a transient failure."""
    if not INTERPRETED_PATH.exists():
        return None

    try:
        with open(INTERPRETED_PATH) as f:
            existing = json.load(f)
    except Exception as exc:
        print(f"Existing interpreted payload could not be read: {exc}")
        return None

    items = existing.get("items", [])
    if not isinstance(items, list) or not items:
        return None

    errors = validate_payload(existing, batch=task_payload.get("source_batch"))
    batch_generated_at = task_payload.get("source_batch", {}).get("generated_at")
    if not errors and existing.get("source_batch_generated_at") == batch_generated_at:
        return existing

    generated_at = _parse_iso_datetime(existing.get("generated_at"))
    if generated_at is None:
        return None

    age_seconds = (datetime.now(timezone.utc) - generated_at).total_seconds()
    if 0 <= age_seconds <= FRESH_FALLBACK_SECONDS:
        print(
            "Existing interpreted payload is fresh but not an exact batch match; "
            f"preserving it after provider failure (age_seconds={age_seconds:.0f})."
        )
        return existing

    return None


def trim_task_payload(payload: dict, max_input_items: int) -> dict:
    trimmed = dict(payload)
    source_batch = dict(payload.get("source_batch", {}))
    items = list(source_batch.get("items", []))
    source_batch["items"] = items[:max_input_items]
    trimmed["source_batch"] = source_batch
    return trimmed


def build_agent_message(task_payload: dict) -> str:
    return "\n".join([
        "You are the OpenClaw worker for Aurel3.",
        "Return JSON only. No markdown. No explanation.",
        "Output exactly one JSON object with keys: generated_at, source_batch_generated_at, items.",
        "For each input item, output one item with these keys only:",
        "source_item_id, market_relevant, event_type, theme_id, theme_label, summary, beneficiary_sectors, hurt_sectors, direct_beneficiaries, secondary_beneficiaries, time_horizon, durability, confidence, actionability, reasoning_notes",
        "Allowed time_horizon: 1-3 days | 1-2 weeks | 1-3 months | 3+ months / structural",
        "Allowed durability: low | medium | high",
        "Allowed confidence: low | medium | high",
        "Allowed actionability: informational | interesting_but_early | potentially_actionable | actionable",
        "Include every source item exactly once, even if market_relevant=false.",
        "Keep summary and reasoning_notes brief.",
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
    ]
    # OpenClaw 5.x: omit --session-id for isolated runs (the 4.x "-" placeholder
    # is no longer accepted; the new convention is no flag = new isolated session).
    if not runtime.get("use_isolated_run", True):
        session_id = runtime.get("session_id") or "aurel3-openclaw-worker"
        if session_id:
            cmd.extend(["--session-id", session_id])
    cmd.extend([
        "--message",
        message,
    ])
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
    chunk_size = max(1, int(runtime.get("chunk_size", 5)))
    source_batch = dict(task_payload.get("source_batch", {}))
    items = list(source_batch.get("items", []))
    merged_items: list[dict] = []

    try:
        for chunk_index in range(0, len(items), chunk_size):
            chunk_items = items[chunk_index : chunk_index + chunk_size]
            chunk_payload = dict(task_payload)
            chunk_source_batch = dict(source_batch)
            chunk_source_batch["items"] = chunk_items
            chunk_payload["source_batch"] = chunk_source_batch

            last_error: Exception | None = None
            for attempt in range(1, max_retries + 1):
                try:
                    chunk_result = _invoke_openclaw_once(runtime, chunk_payload)
                    merged_items.extend(chunk_result.get("items", []))
                    print(
                        "OpenClaw chunk complete: "
                        f"{len(chunk_items)} input items -> {len(chunk_result.get('items', []))} interpreted items."
                    )
                    break
                except Exception as exc:
                    last_error = exc
                    print(f"OpenClaw chunk attempt {attempt}/{max_retries} failed: {exc}")
                    if attempt >= max_retries:
                        raise RuntimeError(
                            f"OpenClaw agent failed for chunk starting at index {chunk_index} "
                            f"after {max_retries} attempts: {last_error}"
                        )
                    if retry_delay_seconds > 0:
                        time.sleep(retry_delay_seconds)
    finally:
        if prev_model:
            _switch_model(prev_model)

    return {
        "generated_at": task_payload.get("generated_at"),
        "source_batch_generated_at": source_batch.get("generated_at"),
        "items": merged_items,
    }


def main() -> int:
    runtime = load_runtime_config()
    task_payload = load_task_payload()
    trimmed_payload = trim_task_payload(task_payload, runtime["max_input_items"])
    try:
        interpreted = call_openclaw_agent(runtime, trimmed_payload)
    except Exception as exc:
        existing = load_existing_interpreted_payload(trimmed_payload)
        if existing is not None:
            print(
                "OpenClaw provider failed, but a fresh valid interpreted payload "
                f"already exists; preserving current recommendations. Error: {exc}"
            )
            return 0
        raise

    interpreted["generated_at"] = utc_now_iso()

    # Filter to items that match the batch actually sent to OpenClaw.
    batch_ids = {item.get("id") for item in trimmed_payload.get("source_batch", {}).get("items", [])}
    if batch_ids:
        interpreted["items"] = [
            item for item in interpreted.get("items", [])
            if item.get("source_item_id") in batch_ids
        ]

    # Stamp the interpreted payload to the exact prepared subset if the worker
    # drifted or echoed a stale batch timestamp.
    interpreted["source_batch_generated_at"] = (
        trimmed_payload.get("source_batch", {}).get("generated_at")
    )

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
