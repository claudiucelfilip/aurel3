# Aurel3 Session Handoff

Date: 2026-04-08

## Current State

Aurel3 is wired to the real OpenClaw runtime for interpretation.

The live path is:

```text
python3 run.py openclaw_cycle
  -> export source batch
  -> prepare OpenClaw task payload
  -> run OpenClaw agent
  -> save interpreted items
  -> run signal scan
```

Important:
- Aurel3 interpretation uses `openclaw agent --agent main --json`
- OpenClaw provides the model/runtime/auth layer
- Current Aurel3 interpretation model: `openai-codex/gpt-5.4`
- Do not rewire back to a direct API flow — use OpenClaw for model routing
- Gemini is no longer part of the intended Aurel3 runtime path

## Current model policy

### Keep on `openai-codex/gpt-5.4`
- Aurel3 signal interpretation
- Aurel3 event-driven analysis
- Aurel3 watchlist thesis review when model judgment matters
- Aurel3 weekly review / postmortem / learning loop

Reason:
Aurel3 is part of the decision-quality layer. Model quality can directly affect recommendation quality, exit quality, and learning quality.

### Use `openai-codex/gpt-5.1` only for lower-stakes ops/reporting jobs outside the Aurel3 judgment loop

Examples outside Aurel3 core judgment:
- `aurel2-daily-ops-check`
- `session-cleanup`
- `aurel2-crypto-daily-check`
- `aurel2-crypto-monday-rebalance-report`

## Current cron-related expectation

Aurel3 jobs that affect signal quality should stay on `openai-codex/gpt-5.4`:
- `aurel3-signal-cycle`
- `aurel3-watchlist-review`
- `aurel3-review-signals`
- `aurel3-weekly-review-summary`

## Notes

- Historical notes may mention Gemini because it was tested previously. Those references are now stale.
- Current authoritative policy lives in `/root/.openclaw/workspace/MODEL-POLICY.md`.
- Current Aurel3 operational guidance lives in `/root/.openclaw/workspace/AUREL3-OPERATIONS.md`.

## Useful commands

```bash
python3 run.py openclaw_cycle
python3 run.py watchlist_review
python3 run.py review_signals
python3 run.py review_summary
python3 run.py status
python3 interpretation_test.py
```
