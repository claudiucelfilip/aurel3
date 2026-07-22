#!/usr/bin/env python3
"""Interpreter calibration bake-off: compare LLM backends on Aurel3's judgment step.

This is a STANDALONE analysis tool. It does not touch the live Aurel3 engine,
cron path, or any state files. It exists to answer one question:

    Does a given model produce better-CALIBRATED confidence / actionability on
    Aurel3's own historical cases than another model?

Motivating comparison: Thinking Machines' Inkling (RL-trained for calibration)
vs. the frontier general model Aurel3's judgment layer runs on (Fable 5 / GPT-5.5).

--------------------------------------------------------------------------------
HONEST LIMITATION — read before trusting results
--------------------------------------------------------------------------------
The ground-truth file (data/historical_replay_cases.json) has NO archived
article text — only {ticker, date, theme_driver, benchmark action, horizon,
notes}. A fully faithful interpreter test would replay real headlines as they
appeared. We don't have those here.

So this harness SYNTHESIZES a plausible source item per case from its metadata
(same information historical_replay.py's THEME_DEFAULTS already uses, just as
prose) and feeds THAT through the real OPENCLAW_WORKER.md prompt. It therefore
measures: "given a fair, theme-consistent description of the catalyst, how well-
calibrated is each model's confidence/actionability vs. the real forward move?"

It does NOT measure headline comprehension or source-quality discrimination.
Treat a win here as necessary-but-not-sufficient evidence, then confirm on real
archived items before acting. This caveat is printed with every result.
--------------------------------------------------------------------------------

Backends (select with --models):
  - fable   : FLAT-RATE. Calls the Claude Code CLI (`claude -p --model claude-fable-5`),
              using your existing subscription auth. No per-token API billing.
  - gpt5    : FLAT-RATE. Calls the Codex CLI (`codex exec -m gpt-5.6-sol`), using
              your existing subscription auth. No per-token API billing.
  - inkling : TOKEN-BILLED (Tinker/Thinking Machines). This is the ONLY backend that
              costs money per call. It is gated behind --allow-tinker-billing so it
              can never run by accident. Needs TINKER_API_KEY in the environment.

Usage:
  python3 scripts/interpreter_bakeoff.py --models fable gpt5            # flat-rate only
  python3 scripts/interpreter_bakeoff.py --models fable --limit 8       # quick smoke run
  python3 scripts/interpreter_bakeoff.py --models fable --probe-only    # connectivity check
  # Inkling only if you explicitly accept spending against the Tinker balance:
  TINKER_API_KEY=... python3 scripts/interpreter_bakeoff.py \
      --models fable inkling --allow-tinker-billing
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

import yfinance as yf

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from reviews import build_recommendation_review  # engine's own outcome grading

CASES_PATH = REPO / "data" / "historical_replay_cases.json"
WORKER_MD = REPO / "OPENCLAW_WORKER.md"
OUT_PATH = REPO / "data" / "interpreter_bakeoff_results.json"

# Confidence label -> numeric probability, for calibration scoring. These are
# the implied "this thesis works" probabilities a well-calibrated interpreter
# should be expressing when it stamps a confidence label.
CONFIDENCE_P = {"low": 0.25, "medium": 0.50, "high": 0.75}
# actionability -> whether the model is asserting a tradable catalyst now
ACTIONABLE_LABELS = {"actionable"}


# --------------------------------------------------------------------------- #
# Prompt construction — reuse the REAL worker contract
# --------------------------------------------------------------------------- #
def _worker_system_prompt() -> str:
    """Extract the system instruction from OPENCLAW_WORKER.md verbatim."""
    text = WORKER_MD.read_text()
    # The doc's "Prompt Template" section holds the canonical system instruction.
    m = re.search(r"System instruction:\s*```text\s*(.*?)```", text, re.DOTALL)
    if not m:
        raise SystemExit("Could not find system instruction in OPENCLAW_WORKER.md")
    return m.group(1).strip()


_CATALYSTS_PATH = REPO / "data" / "bakeoff_catalysts.json"
try:
    _CATALYSTS = json.loads(_CATALYSTS_PATH.read_text())
except FileNotFoundError:
    _CATALYSTS = {}


def _synthesized_source_item(case: dict) -> dict:
    """Build a fair, SPECIFIC source item from the pre-authored catalyst file.

    The catalyst text is authored blind to the case outcome (see
    build_bakeoff_catalysts.py) and carries a realistic confirmation strength,
    so models have room to differ in confidence. Falls back to a neutral stub
    only if no catalyst was authored for the case.
    """
    entry = _CATALYSTS.get(case["id"])
    if entry:
        body = entry["catalyst"]
    else:
        body = (
            f"A development in the '{case['theme_driver']}' theme is reported "
            f"around {case['ticker']}."
        )
    return {
        "source_item_id": f"bakeoff::{case['id']}",
        "title": f"{case['theme_driver']} — {case['ticker']}",
        "published": case["date"],
        "body": body,
        "primary_ticker_hint": case["ticker"],
    }


# Toggled by --enrich. When on, each prompt also carries the ticker's real
# market state AS OF the case date (never forward data) — price trend, volume
# ratio, relative strength. This tests whether models calibrate better once they
# have the market-confirmation signal, not just the catalyst text.
ENRICH = False


def _at_date_market_context(ticker: str, as_of: datetime) -> dict | None:
    """Market snapshot computed from data UP TO as_of only — no lookahead.

    Mirrors historical_replay.py's _historical_market_snapshot: trend from EMAs,
    volume ratio vs 60d avg, all from bars at or before the decision date.
    """
    start = (as_of - timedelta(days=120)).date().isoformat()
    end = (as_of + timedelta(days=2)).date().isoformat()  # +2d only to include as_of bar
    try:
        hist = yf.Ticker(ticker).history(start=start, end=end, auto_adjust=True)
    except Exception:
        return None
    if hist is None or hist.empty:
        return None
    hist = hist.sort_index()
    eligible = hist[hist.index.tz_localize(None) <= as_of + timedelta(days=1)]
    if eligible.empty or len(eligible) < 5:
        return None
    prior = eligible
    current = float(prior["Close"].iloc[-1])
    prev = float(prior["Close"].iloc[-2]) if len(prior) >= 2 else current
    avg_vol = float(prior["Volume"].tail(60).mean())
    today_vol = float(prior["Volume"].iloc[-1])
    ema20 = float(prior["Close"].ewm(span=20).mean().iloc[-1]) if len(prior) >= 20 else None
    ema50 = float(prior["Close"].ewm(span=50).mean().iloc[-1]) if len(prior) >= 50 else None
    above20 = current > ema20 if ema20 else None
    above50 = current > ema50 if ema50 else None
    if above20 and above50:
        trend = "strong_uptrend"
    elif above20:
        trend = "uptrend"
    elif above20 is False and above50 is False:
        trend = "downtrend"
    elif above50 is False:
        trend = "weak"
    else:
        trend = "unclear"
    return {
        "trend": trend,
        "day_change_pct": round((current / prev - 1) * 100, 2) if prev else None,
        "volume_vs_60d_avg": round(today_vol / avg_vol, 2) if avg_vol else None,
        "above_20d_ema": above20,
        "above_50d_ema": above50,
    }


def _user_payload(case: dict) -> str:
    item = _synthesized_source_item(case)
    context_block = ""
    if ENRICH:
        as_of = datetime.fromisoformat(case["date"])
        ctx = _at_date_market_context(case["ticker"], as_of)
        if ctx:
            context_block = (
                "\n\nMarket state as of the item date (price/volume confirmation — "
                "use this to judge whether the market is confirming the thesis):\n"
                f"{json.dumps(ctx, indent=2)}"
            )
    return (
        "Interpret the following source item for Aurel3.\n\n"
        "Rules:\n"
        "- Output JSON only, a single object (not an array).\n"
        "- Use only controlled confidence (low|medium|high), durability "
        "(low|medium|high), and actionability (informational|interesting_but_early|"
        "potentially_actionable|actionable) values.\n"
        "- Assess confidence as the strength of the INVESTMENT THESIS, not your "
        "certainty about the interpretation. Do not default to medium.\n"
        "- Required fields: theme_id, theme_label, summary, direct_beneficiaries, "
        "secondary_beneficiaries, time_horizon, durability, confidence, "
        "actionability, reasoning_notes.\n\n"
        f"Source item:\n{json.dumps(item, indent=2)}"
        f"{context_block}"
    )


def _parse_model_json(text: str) -> dict | None:
    """Pull the LAST balanced JSON object out of a model response.

    Last, not first: the Codex CLI prints a transcript that echoes the prompt
    (which itself contains JSON), so the model's actual answer is the trailing
    object. Taking the last balanced object also works for clean single-object
    replies (claude -p) and fenced blocks.
    """
    text = text.strip()
    fence = re.findall(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence[-1].strip()
    # Scan for all top-level balanced {...} objects; return the last valid one.
    found: list[dict] = []
    depth = 0
    start = -1
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start >= 0:
                    try:
                        found.append(json.loads(text[start : i + 1]))
                    except json.JSONDecodeError:
                        pass
                    start = -1
    return found[-1] if found else None


# --------------------------------------------------------------------------- #
# Model backends — each is (system, user) -> raw text.
#
# fable/gpt5 shell out to the subscription CLIs (flat-rate, no per-token
# billing). inkling is the only token-billed path and is gated at run() time.
# --------------------------------------------------------------------------- #
import subprocess


def _run_cli(cmd: list[str], stdin_text: str, timeout: int = 180) -> str:
    p = subprocess.run(
        cmd, input=stdin_text, capture_output=True, text=True, timeout=timeout
    )
    if p.returncode != 0:
        raise RuntimeError(f"{cmd[0]} exited {p.returncode}: {p.stderr.strip()[:300]}")
    return p.stdout


def _backend_fable() -> Callable[[str, str], str]:
    """Claude Code CLI, subscription auth. System+user folded into one -p prompt."""
    model = os.getenv("FABLE_MODEL", "claude-fable-5")

    def call(system: str, user: str) -> str:
        prompt = f"{system}\n\n{user}"
        # -p prints and exits; default text output is the model's reply verbatim.
        return _run_cli(["claude", "-p", prompt, "--model", model], stdin_text="")

    return call


def _backend_gpt5() -> Callable[[str, str], str]:
    """Codex CLI (`codex exec`), subscription auth. Prints a transcript; the
    model reply is the trailing text — _parse_model_json takes the last object.
    Defaults to gpt-5.6-sol (the model actually configured in Codex); override
    with GPT5_MODEL."""
    model = os.getenv("GPT5_MODEL", "gpt-5.6-sol")

    def call(system: str, user: str) -> str:
        prompt = f"{system}\n\n{user}"
        return _run_cli(["codex", "exec", "-m", model, prompt], stdin_text="")

    return call


def _backend_inkling() -> Callable[[str, str], str]:
    """TOKEN-BILLED. Tinker OpenAI-compatible API. Only constructed when the
    caller has passed --allow-tinker-billing (enforced in run())."""
    from openai import OpenAI

    key = os.getenv("TINKER_API_KEY")
    if not key:
        raise SystemExit("inkling backend needs TINKER_API_KEY in the environment.")
    client = OpenAI(
        base_url="https://tinker.thinkingmachines.dev/services/tinker-prod/oai/api/v1",
        api_key=key,
        timeout=120.0,   # hard per-request cap so a hanging call can't stall the run
        max_retries=1,
    )
    model = os.getenv("INKLING_MODEL", "thinkingmachines/Inkling")

    # Inkling is a reasoning model: it thinks in prose before the JSON, so it
    # needs headroom for both. 800 tokens truncated it mid-thought. _parse_model_json
    # takes the LAST object, so trailing reasoning before the JSON is harmless.
    def call(system: str, user: str) -> str:
        sys_json = system + "\n\nReturn ONLY the final JSON object as your last output."
        try:
            r = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": sys_json},
                    {"role": "user", "content": user},
                ],
                temperature=0.2,
                max_tokens=2000,
            )
            return r.choices[0].message.content or ""
        except Exception:
            r = client.completions.create(
                model=model,
                prompt=f"{sys_json}\n\n{user}\n\nJSON:",
                temperature=0.2,
                max_tokens=2000,
            )
            return r.choices[0].text or ""

    return call


BACKENDS = {"fable": _backend_fable, "gpt5": _backend_gpt5, "inkling": _backend_inkling}
FLAT_RATE = {"fable", "gpt5"}
TOKEN_BILLED = {"inkling"}


# --------------------------------------------------------------------------- #
# Forward-return grading — reuse yfinance + the engine's review outcome
# --------------------------------------------------------------------------- #
def _horizon_days(h: str) -> int:
    return {"1-3 days": 3, "1-2 weeks": 14, "1-3 months": 45, "3+ months / structural": 90}.get(h, 14)


def _forward_return(ticker: str, as_of: datetime, horizon: str) -> tuple[float, float] | None:
    end = as_of + timedelta(days=_horizon_days(horizon) + 7)
    try:
        hist = yf.Ticker(ticker).history(
            start=(as_of - timedelta(days=3)).date().isoformat(),
            end=end.date().isoformat(),
            auto_adjust=True,
        )
    except Exception:
        return None
    if hist is None or hist.empty:
        return None
    return float(hist["Close"].iloc[0]), float(hist["Close"].iloc[-1])


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #
def _brier(prob: float, worked: bool) -> float:
    return (prob - (1.0 if worked else 0.0)) ** 2


def _score_model(rows: list[dict]) -> dict:
    """Calibration + actionability metrics over graded rows for one model."""
    graded = [r for r in rows if r.get("outcome") and r.get("confidence") in CONFIDENCE_P]
    n = len(graded)
    if not n:
        return {"cases_scored": 0}

    # A case "worked" if forward excess return was meaningfully positive.
    def worked(r: dict) -> bool:
        return r["outcome"] in ("worked", "late")  # positive forward move either way

    brier = sum(_brier(CONFIDENCE_P[r["confidence"]], worked(r)) for r in graded) / n

    # Calibration table: for each confidence label, realized hit-rate.
    calib = {}
    for label in ("low", "medium", "high"):
        bucket = [r for r in graded if r["confidence"] == label]
        if bucket:
            calib[label] = {
                "implied_p": CONFIDENCE_P[label],
                "realized_hit_rate": round(sum(worked(r) for r in bucket) / len(bucket), 3),
                "n": len(bucket),
            }

    # Actionability precision: of items the model called `actionable`, how many
    # actually delivered a meaningful forward move.
    actionable = [r for r in graded if r.get("actionability") in ACTIONABLE_LABELS]
    action_precision = (
        round(sum(worked(r) for r in actionable) / len(actionable), 3) if actionable else None
    )

    # Late-miss recovery: cases whose benchmark label was buy_now — did the model
    # express high confidence + actionable (i.e. would it have caught them)?
    buy_cases = [r for r in graded if r.get("benchmark_action") == "buy_now"]
    caught = [
        r for r in buy_cases
        if r.get("confidence") == "high" and r.get("actionability") in ACTIONABLE_LABELS
    ]
    buy_recall = round(len(caught) / len(buy_cases), 3) if buy_cases else None

    return {
        "cases_scored": n,
        "brier_score": round(brier, 4),  # lower is better-calibrated
        "calibration_by_label": calib,
        "actionable_precision": action_precision,
        "buy_now_recall_high_actionable": buy_recall,
        "buy_now_case_count": len(buy_cases),
    }


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #
def _probe(name: str, call: Callable[[str, str], str]) -> bool:
    print(f"[probe] {name}: sending 1 request...", flush=True)
    try:
        out = call("You are a JSON API. Reply with a single JSON object.", 'Return {"ok": true}')
    except Exception as e:
        print(f"[probe] {name}: FAILED — {type(e).__name__}: {e}", flush=True)
        return False
    parsed = _parse_model_json(out)
    ok = bool(parsed)
    print(f"[probe] {name}: {'OK' if ok else 'reachable but no JSON'} — raw: {out[:120]!r}", flush=True)
    return ok


def run(models: list[str], limit: int | None, probe_only: bool, allow_tinker: bool,
        enrich: bool = False) -> None:
    global ENRICH, OUT_PATH
    ENRICH = enrich
    # Separate output file so enriched results don't clobber the thin baseline.
    OUT_PATH = REPO / "data" / (
        "interpreter_bakeoff_results_enriched.json" if enrich
        else "interpreter_bakeoff_results.json"
    )
    if enrich:
        print("[enrich] at-date market context (no lookahead) ADDED to each prompt.\n")

    # Cost guard: token-billed backends refuse to run unless explicitly allowed.
    billed = [m for m in models if m in TOKEN_BILLED]
    if billed and not allow_tinker:
        raise SystemExit(
            f"Refusing to run token-billed backend(s) {billed} without "
            f"--allow-tinker-billing. The flat-rate backends are {sorted(FLAT_RATE)}."
        )
    if billed:
        print(f"[cost] token-billed backend(s) ENABLED: {billed} — this spends real money.\n")

    system = _worker_system_prompt()
    backends = {}
    for name in models:
        if name not in BACKENDS:
            raise SystemExit(f"Unknown model '{name}'. Choose from {list(BACKENDS)}.")
        backends[name] = BACKENDS[name]()  # constructs client / checks prerequisites

    # Connectivity probe first — fail fast before a 64-case run.
    reachable = {name: _probe(name, call) for name, call in backends.items()}
    backends = {n: c for n, c in backends.items() if reachable.get(n)}
    if probe_only or not backends:
        print("\nProbe-only or no reachable backends — stopping.")
        return

    cases = json.loads(CASES_PATH.read_text())
    if limit:
        cases = cases[:limit]

    all_rows: dict[str, list[dict]] = {name: [] for name in backends}
    for idx, case in enumerate(cases, 1):
        as_of = datetime.fromisoformat(case["date"])
        fwd = _forward_return(case["ticker"], as_of, case["expected_horizon"])
        if not fwd:
            print(f"  [{idx}/{len(cases)}] {case['ticker']}: no price history — skipped", flush=True)
            continue
        ref_price, review_price = fwd
        user = _user_payload(case)

        for name, call in backends.items():
            try:
                raw = call(system, user)
            except Exception as e:
                print(f"  [{idx}] {case['ticker']} {name}: call error {type(e).__name__}", flush=True)
                continue
            parsed = _parse_model_json(raw) or {}
            conf = str(parsed.get("confidence", "")).lower().strip()
            action = str(parsed.get("actionability", "")).lower().strip()

            review = build_recommendation_review(
                {
                    "id": case["id"],
                    "ticker": case["ticker"],
                    "theme_driver": case["theme_driver"],
                    # Map the model's own read to a buy/watch action for grading:
                    "action": "buy_now" if action in ACTIONABLE_LABELS else "watch_for_confirmation",
                    "confidence": conf,
                    "expected_horizon": case["expected_horizon"],
                    "reference_price": ref_price,
                },
                review_price,
            )
            all_rows[name].append({
                "id": case["id"],
                "ticker": case["ticker"],
                "benchmark_action": case["action"],
                "confidence": conf if conf in CONFIDENCE_P else None,
                "actionability": action,
                "forward_return_pct": review["forward_return_pct"],
                "outcome": review["outcome"],
                "model_summary": parsed.get("summary", ""),
            })
        # Checkpoint after every case so a mid-run failure never loses progress
        # (and the token spend so far is never wasted).
        interim = {n: _score_model(r) for n, r in all_rows.items()}
        OUT_PATH.write_text(json.dumps({"scores": interim, "rows": all_rows}, indent=2))
        print(f"  [{idx}/{len(cases)}] {case['ticker']} done "
              f"(checkpointed {sum(len(r) for r in all_rows.values())} rows)", flush=True)

    scores = {name: _score_model(rows) for name, rows in all_rows.items()}
    OUT_PATH.write_text(json.dumps({"scores": scores, "rows": all_rows}, indent=2))

    print("\n" + "=" * 70)
    print("INTERPRETER CALIBRATION BAKE-OFF")
    print("=" * 70)
    print("CAVEAT: inputs are AUTHORED catalysts (blind to outcome, varied")
    print("confirmation strength), not real archived headlines. Fair across")
    print("models, but confirm a decisive winner on real news before acting.\n")
    for name, s in scores.items():
        print(f"[{name}] cases={s.get('cases_scored', 0)}  "
              f"Brier={s.get('brier_score', 'n/a')} (lower=better calibrated)")
        for label, c in (s.get("calibration_by_label") or {}).items():
            print(f"    {label:>6}: implied {c['implied_p']:.2f} vs realized "
                  f"{c['realized_hit_rate']:.2f}  (n={c['n']})")
        print(f"    actionable precision: {s.get('actionable_precision')}  "
              f"buy_now recall (high+actionable): {s.get('buy_now_recall_high_actionable')} "
              f"of {s.get('buy_now_case_count')} buy cases")
    print(f"\nFull rows written to {OUT_PATH}")


def _args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Aurel3 interpreter calibration bake-off (standalone).")
    p.add_argument("--models", nargs="+", default=["fable", "gpt5"],
                   help="Backends to compare: fable, gpt5 (flat-rate), inkling (token-billed)")
    p.add_argument("--limit", type=int, default=None, help="Only run the first N cases (smoke test).")
    p.add_argument("--probe-only", action="store_true", help="Only test connectivity, don't run cases.")
    p.add_argument("--allow-tinker-billing", action="store_true",
                   help="Required to run the token-billed 'inkling' backend. Off by default.")
    p.add_argument("--enrich", action="store_true",
                   help="Add at-date market context (trend/volume/RS, no lookahead) to each prompt. "
                        "Writes to a separate _enriched results file.")
    return p.parse_args()


if __name__ == "__main__":
    a = _args()
    run(a.models, a.limit, a.probe_only, a.allow_tinker_billing, a.enrich)
