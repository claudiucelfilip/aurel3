# Aurel3 Session Handoff

Original: 2026-04-08 · Updated: 2026-07-21 (removed the legacy
`openclaw_cycle`/`openclaw_run` subprocess path; interpretation now runs in the
OpenClaw agent-turn).

## Current State

Aurel3 is wired to the real OpenClaw runtime for interpretation.

The live path is the OpenClaw cron agent-turn (`aurel3-signal-cycle`): the
agent interprets the source batch itself, then calls `openclaw_import` and
`signal_scan`. The old `run.py openclaw_cycle` subprocess path has been removed.

Important:
- OpenClaw provides the model/runtime/auth layer
- Current Aurel3 interpretation model: `openai-codex/gpt-5.5`
- Do not rewire back to a direct API flow — use OpenClaw for model routing
- Gemini is no longer part of the intended Aurel3 runtime path

## Current model policy

Aurel3 is the decision-quality layer, so its judgment jobs run on the strong
model — model quality directly affects recommendation, exit, and learning
quality. Lower-stakes ops/reporting jobs outside the Aurel3 judgment loop use a
cheaper model.

The authoritative, up-to-date model policy lives on Dumbo:
- `/root/.openclaw/workspace/MODEL-POLICY.md`
- `/root/.openclaw/workspace/AUREL3-OPERATIONS.md`

Consult those files rather than pinning a version here — model versions move,
and this handoff will go stale again if it hardcodes one.

## Current cron-related expectation

These Aurel3 jobs are part of the judgment loop and follow the judgment-layer
model policy above:
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
python3 run.py watchlist_review
python3 run.py review_signals
python3 run.py review_summary
python3 run.py status
```
