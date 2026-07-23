#!/usr/bin/env python3
"""Engine-level before/after: run A3's historical replay with real model judgments.

The interpreter bake-off saved each model's per-case confidence/actionability under
two conditions (thin = catalyst text only, enriched = + at-date market context).
This script feeds those judgments into the actual A3 signal engine replay
(historical_replay.py) in place of the canned THEME_DEFAULTS values, so we can see
whether enriched judgment changes REAL engine outcomes (buy_now/watch/miss), not
just calibration scores.

No LLM calls — pure replay over saved judgments + yfinance history.

Usage:
  python3 scripts/replay_with_model_judgments.py --model fable
  python3 scripts/replay_with_model_judgments.py --model fable --limit 10
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import historical_replay as hr

THIN_PATH = REPO / "data" / "interpreter_bakeoff_results_thin_gpt56.json"
ENRICHED_PATH = REPO / "data" / "interpreter_bakeoff_results_enriched.json"

VALID_CONF = {"low", "medium", "high"}
VALID_ACT = {"informational", "interesting_but_early", "potentially_actionable", "actionable"}


def _judgments(path: Path, model: str) -> dict[str, dict]:
    rows = json.loads(path.read_text())["rows"][model]
    out = {}
    for r in rows:
        j = {}
        if r.get("confidence") in VALID_CONF:
            j["confidence"] = r["confidence"]
        if r.get("actionability") in VALID_ACT:
            j["actionability"] = r["actionability"]
        if j:
            out[r["id"]] = j
    return out


def _run_arm(judgments: dict[str, dict], limit: int | None) -> dict:
    """Run the engine replay with per-case confidence/actionability overridden."""
    orig_profile = hr._case_profile
    orig_load = hr._load_cases

    def patched_profile(case: dict):
        profile = orig_profile(case)
        profile.update(judgments.get(case["id"], {}))
        return profile

    def patched_load(split: str = "full"):
        cases = orig_load(split)
        return cases[:limit] if limit else cases

    hr._case_profile = patched_profile
    hr._load_cases = patched_load
    try:
        _results, summary = hr.run_engine_replay("full")
    finally:
        hr._case_profile = orig_profile
        hr._load_cases = orig_load
    return summary


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--model", default="fable", choices=("fable", "gpt5", "inkling"))
    p.add_argument("--limit", type=int, default=None)
    args = p.parse_args()

    thin = _judgments(THIN_PATH, args.model)
    enriched = _judgments(ENRICHED_PATH, args.model)
    print(f"model={args.model}: {len(thin)} thin judgments, {len(enriched)} enriched")

    print("\n--- ARM A: thin judgments (catalyst text only) ---")
    a = _run_arm(thin, args.limit)
    print("\n--- ARM B: enriched judgments (+ at-date market context) ---")
    b = _run_arm(enriched, args.limit)

    keys = [
        "total_cases", "worked", "partial", "failed", "late",
        "buy_now", "watch_for_confirmation", "no_signal",
        "exact_action_matches", "missed_10pct", "missed_20pct",
    ]
    print(f"\n{'metric':28} {'thin':>8} {'enriched':>9}")
    for k in keys:
        print(f"{k:28} {a.get(k, 0):>8} {b.get(k, 0):>9}")

    out = REPO / "data" / f"engine_replay_before_after_{args.model}.json"
    out.write_text(json.dumps({"model": args.model, "thin": a, "enriched": b}, indent=2))
    print(f"\nSaved to {out}")


if __name__ == "__main__":
    main()
