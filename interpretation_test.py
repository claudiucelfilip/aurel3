#!/usr/bin/env python3
"""Test interpretation quality by sending known source items through OpenClaw
and comparing output ratings against expected values."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from state import utc_now_iso

CASES_PATH = Path(__file__).parent / "data" / "interpretation_test_cases.json"
WORKER_PATH = Path(__file__).parent / "OPENCLAW_WORKER.md"
CONFIG_PATH = Path(__file__).parent / "config.json"

ACTIONABILITY_RANK = {
    "informational": 0,
    "interesting_but_early": 1,
    "potentially_actionable": 2,
    "actionable": 3,
}

CONFIDENCE_RANK = {"low": 0, "medium": 1, "high": 2}
DURABILITY_RANK = {"low": 0, "medium": 1, "high": 2}


def _run_openclaw(source_items: list[dict]) -> list[dict]:
    """Send source items through OpenClaw using the same approach as openclaw_run.py."""
    from openclaw_run import load_runtime_config, call_openclaw_agent

    runtime = load_runtime_config()
    prompt_text = WORKER_PATH.read_text()
    now = utc_now_iso()

    batch = {
        "generated_at": now,
        "items": source_items,
    }
    payload = {
        "prepared_at": now,
        "instructions_ref": "OPENCLAW_WORKER.md",
        "task": "Interpret the attached source batch for Aurel3 and return only JSON matching the schema in OPENCLAW_WORKER.md.",
        "source_batch": batch,
        "prompt_markdown": prompt_text,
    }

    try:
        result = call_openclaw_agent(runtime, payload)
        return result.get("items", [])
    except json.JSONDecodeError:
        # The agent may return JSON wrapped in markdown fences — try to extract it
        from openclaw_run import extract_agent_text
        import subprocess as sp

        message = "\n\n".join([
            "You are the OpenClaw worker for Aurel3.",
            "Read the task payload below and return only valid JSON matching the required output schema.",
            "Do not wrap the JSON in markdown fences.",
            json.dumps(payload, ensure_ascii=True),
        ])
        cmd = [
            "openclaw", "agent",
            "--agent", runtime["agent_id"],
            "--json",
            "--thinking", runtime["thinking"],
            "--timeout", str(runtime["timeout_seconds"]),
            "--message", message,
        ]
        proc = sp.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            print(f"OpenClaw error: {proc.stderr[:500]}")
            return []
        envelope = json.loads(proc.stdout)
        text = extract_agent_text(envelope)
        # Strip markdown fences if present
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            parsed = json.loads(text[start:end])
            return parsed.get("items", [])
        print(f"Could not parse response: {text[:300]}")
        return []
    except Exception as e:
        print(f"OpenClaw error: {e}")
        return []


def _score_case(case: dict, interpreted: dict | None) -> dict:
    expected = case["expected"]
    case_id = case["id"]
    result = {"id": case_id, "pass": True, "errors": [], "warnings": []}

    if interpreted is None:
        result["pass"] = False
        result["errors"].append("no interpretation returned")
        return result

    # market_relevant
    if expected.get("market_relevant") is not None:
        if interpreted.get("market_relevant") != expected["market_relevant"]:
            result["errors"].append(
                f"market_relevant: got {interpreted.get('market_relevant')}, expected {expected['market_relevant']}"
            )

    # actionability — exact match or within 1 rank
    if "actionability" in expected:
        got = interpreted.get("actionability", "")
        exp = expected["actionability"]
        got_rank = ACTIONABILITY_RANK.get(got, -1)
        exp_rank = ACTIONABILITY_RANK.get(exp, -1)
        if got != exp:
            if abs(got_rank - exp_rank) <= 1:
                result["warnings"].append(f"actionability: got {got}, expected {exp} (within 1 rank)")
            else:
                result["errors"].append(f"actionability: got {got}, expected {exp}")

    # confidence — exact match or within 1 rank
    if "confidence" in expected:
        got = interpreted.get("confidence", "")
        exp = expected["confidence"]
        got_rank = CONFIDENCE_RANK.get(got, -1)
        exp_rank = CONFIDENCE_RANK.get(exp, -1)
        if got != exp:
            if abs(got_rank - exp_rank) <= 1:
                result["warnings"].append(f"confidence: got {got}, expected {exp} (within 1 rank)")
            else:
                result["errors"].append(f"confidence: got {got}, expected {exp}")

    # durability — exact match or within 1 rank
    if "durability" in expected:
        got = interpreted.get("durability", "")
        exp = expected["durability"]
        got_rank = DURABILITY_RANK.get(got, -1)
        exp_rank = DURABILITY_RANK.get(exp, -1)
        if got != exp:
            if abs(got_rank - exp_rank) <= 1:
                result["warnings"].append(f"durability: got {got}, expected {exp} (within 1 rank)")
            else:
                result["errors"].append(f"durability: got {got}, expected {exp}")

    # theme_id
    if "theme_id" in expected:
        got = interpreted.get("theme_id")
        if got != expected["theme_id"]:
            result["errors"].append(f"theme_id: got {got}, expected {expected['theme_id']}")

    # direct beneficiaries — must include
    if "direct_beneficiaries_must_include" in expected:
        got = {t.upper() for t in interpreted.get("direct_beneficiaries", [])}
        for ticker in expected["direct_beneficiaries_must_include"]:
            if ticker.upper() not in got:
                result["errors"].append(f"direct_beneficiaries missing {ticker}")

    # direct beneficiaries — must not include
    if "direct_beneficiaries_must_not_include" in expected:
        got = {t.upper() for t in interpreted.get("direct_beneficiaries", [])}
        for ticker in expected["direct_beneficiaries_must_not_include"]:
            if ticker.upper() in got:
                result["warnings"].append(f"direct_beneficiaries should not include {ticker}")

    if result["errors"]:
        result["pass"] = False

    return result


def main() -> int:
    with open(CASES_PATH) as f:
        data = json.load(f)
    cases = data["cases"]

    print(f"Interpretation Test: {len(cases)} cases")
    print(f"Sending to OpenClaw...\n")

    source_items = [c["source_item"] for c in cases]
    interpreted_items = _run_openclaw(source_items)

    if not interpreted_items:
        print("ERROR: No interpreted items returned from OpenClaw.")
        return 1

    # Match by source_item_id
    interpreted_map = {item["source_item_id"]: item for item in interpreted_items}

    passed = 0
    failed = 0
    warnings = 0
    results = []

    for case in cases:
        source_id = case["source_item"]["id"]
        interpreted = interpreted_map.get(source_id)
        result = _score_case(case, interpreted)
        results.append(result)

        status = "PASS" if result["pass"] else "FAIL"
        if result["pass"]:
            passed += 1
        else:
            failed += 1

        warn_count = len(result.get("warnings", []))
        warnings += warn_count
        warn_str = f" ({warn_count} warnings)" if warn_count else ""

        print(f"  {status}{warn_str}  {case['id']}")
        for err in result["errors"]:
            print(f"         ERROR: {err}")
        for warn in result["warnings"]:
            print(f"         WARN:  {warn}")

    print(f"\nSummary: {passed} passed, {failed} failed, {warnings} warnings out of {len(cases)} cases")

    # Save results
    results_path = Path(__file__).parent / "data" / "interpretation_test_results.json"
    with open(results_path, "w") as f:
        json.dump({"results": results, "interpreted_items": interpreted_items}, f, indent=2)
    print(f"Results saved to {results_path}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
