# Aurel3

Aurel3 is a market signal engine and thesis manager. It is designed to turn noisy source inputs into structured candidate ideas, watchlist reviews, and exit/trim guidance without directly executing trades.

Where Aurel2 focuses on automated systematic execution, Aurel3 focuses on the earlier and messier part of the workflow: finding market-relevant themes, mapping them to tradable tickers, judging signal quality, and tracking whether an original investment thesis is strengthening or breaking.

This repository is a public portfolio snapshot. It demonstrates product thinking, source interpretation, signal design, and workflow orchestration. It is not financial advice.

## What It Does

- Scans news, social, event, and market inputs for market-relevant themes.
- Maps themes to candidate ticker expressions.
- Scores ideas by catalyst strength, narrative consensus, market confirmation, crowding risk, and durability.
- Emits recommendation labels such as `buy_now`, `watch_for_confirmation`, `trim_de_risk`, and `sell`.
- Maintains watchlist thesis records so exits are based on thesis quality, not only price movement.
- Uses OpenClaw-compatible worker prompts and schemas for interpretation-heavy steps.

## What It Does Not Do

- It does not place broker orders.
- It does not manage account balances.
- It does not rebalance a portfolio automatically.
- It should not be treated as a generic news summarizer; market validation is part of the point.

## Core Concepts

| Concept | Meaning |
|---|---|
| Theme | A market-relevant narrative or catalyst, such as earnings surprise, policy change, sector repricing, or local-market event. |
| Candidate | A ticker that expresses the theme in a realistic way. |
| Confirmation | Price, volume, and relative-strength support for the idea. |
| Crowding | Late-entry or attention-saturation risk. |
| Durability | Expected useful life of the catalyst: days, weeks, months, or structural. |
| Thesis state | Whether a held position's original rationale is strengthening, intact, weakening, or broken. |

## Recommendation Labels

- `buy_now`: high-quality signal with enough confirmation and acceptable crowding.
- `watch_for_confirmation`: interesting setup, but not actionable yet.
- `hold`: thesis is intact or strengthening.
- `hold_not_fresh_buy`: okay to keep, unattractive to add.
- `trim_de_risk`: thesis or confirmation is weakening.
- `sell`: thesis is broken, catalyst edge is spent, or confirmation materially failed.

## Repository Map

| Path | Purpose |
|---|---|
| `AUREL3_SPEC.md` | Product and signal-quality specification. |
| `AUREL3_WORKFLOWS.md` | Scheduled scans, event-driven scans, watchlist review, postmortem, and notification workflows. |
| `AUREL3_STATE_SCHEMA.md` | State model for themes, recommendations, watchlist records, and reviews. |
| `OPENCLAW_SCHEMA.md` | Structured input/output contract for interpretation jobs. |
| `OPENCLAW_WORKER.md` | Worker prompt and behavioral contract. |
| `signals.py` | Signal scoring and recommendation logic. |
| `scanner.py`, `sources.py`, `sentiment.py` | Source collection and signal preparation. |
| `watchlist.py`, `reviews.py`, `state.py` | Watchlist thesis tracking and persistence. |
| `run.py` | Command dispatcher for scans, reviews, status, and manual actions. |
| `interpretation_test.py` | Regression tests for interpretation behavior. |

## Quick Start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install requests
python3 interpretation_test.py
```

Create a local config from the example:

```bash
cp config.example.json config.json
```

Then run local commands:

```bash
python3 run.py status
python3 run.py openclaw_prepare
python3 run.py signal_scan
python3 run.py watchlist_review
```

Notification tokens and API credentials should be supplied through environment variables referenced by `config.example.json`.

## Operating Model

Aurel3 is intentionally conservative:

- `buy_now` is reserved for strong, confirmed, durable signals.
- `watch_for_confirmation` is useful output, not a failure.
- Held positions are reviewed against their original thesis.
- Sell quality matters as much as buy quality.
- Postmortems are part of the system, not an afterthought.

## Safety Note

Aurel3 is research and decision-support software. It can help organize market signals, but it does not remove the need for human judgment, independent validation, and risk management.
