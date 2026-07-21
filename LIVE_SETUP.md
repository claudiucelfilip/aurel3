# Aurel3 Live Setup

## Purpose

This document is the minimum setup needed to run Aurel3 live in a controlled trial.

The current recommendation is:
- small-size live trial only
- act only on `buy_now`
- keep first position sizes small, for example around 30 EUR equivalent
- continue using thesis-aware review for existing holdings such as `NIO`

## Current Runtime Shape

The live interpretation path runs inside the OpenClaw cron agent-turn
(`aurel3-signal-cycle`): the agent interprets the source batch itself, then
calls `openclaw_import` and `signal_scan`.

That means:
- Aurel3 does not need a direct `OPENAI_API_KEY` for interpretation anymore
- OpenClaw handles the interpretation step through its own configured runtime
- The old `run.py openclaw_cycle` subprocess entrypoint has been removed

## Environment Variables

Set these in the live runtime environment:

```bash
export AUREL3_SLACK_BOT_TOKEN="..."
export AUREL3_SLACK_USER_ID="..."
export AUREL3_NTFY_TOPIC="aurel3"
export AUREL3_NTFY_SERVER="https://ntfy.sh"
```

Notes:
- Slack and ntfy already degrade safely if these are not set, but live alerts require them.
- The old Slack token that previously appeared in config should be treated as exposed and rotated.
- Interpretation is handled by the local OpenClaw runtime, so do not wire Aurel3 back to a direct OpenAI API client.

## Commands

Main runtime commands (entry-scan interpretation runs in the OpenClaw
agent-turn, not a `run.py` command):

```bash
python3 run.py watchlist_review
python3 run.py review_signals
python3 run.py review_summary
```

Useful manual commands:

```bash
python3 run.py status
python3 run.py buy TICKER [PRICE] [SHARES]
python3 run.py sell TICKER [PRICE]
python3 run.py postmortem [TICKER]
```

## Recommended Live Cadence

Recommended schedule:
- entry-scan cycle (OpenClaw agent-turn `aurel3-signal-cycle`)
  - 09:30 UTC
  - 13:30 UTC
  - 17:30 UTC
- `watchlist_review`
  - 10:30 UTC
  - 14:30 UTC
  - 18:30 UTC
  - 20:30 UTC
- `review_signals`
  - 21:00 UTC on weekdays
- `review_summary`
  - 09:00 UTC on Sunday

This is intentionally simple. Adjust later if live behavior suggests a better cadence.

## Cron Wrapper

Use `cron.sh` as the wrapper:

```bash
bash /root/aurel3/cron.sh watchlist_review
bash /root/aurel3/cron.sh review_signals
bash /root/aurel3/cron.sh review_summary
```

## First-Trial Operating Rules

Recommended first live rules:
- only consider `buy_now`
- ignore `watch_for_confirmation` for actual trades at first
- keep size very small
- do not open too many new positions at once
- let Aurel3 accumulate review history before trusting it more aggressively

## Interpretation

Live behavior should be interpreted like this:
- `buy_now`
  - eligible for tiny-size trial entries
- `watch_for_confirmation`
  - monitor only
- `hold`
  - no alert needed
- `trim / de-risk`
  - action required for an existing position
- `sell`
  - high-priority action required

## Logs

`cron.sh` writes to:

```bash
/root/aurel3/data/runtime.log
```

Check this if a scheduled job appears quiet or fails.
