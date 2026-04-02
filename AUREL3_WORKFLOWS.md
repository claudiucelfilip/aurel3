# Aurel3 Workflows

## Overview

OpenClaw should orchestrate Aurel3 through a small set of explicit jobs.

Core jobs:
1. `scheduled_signal_scan`
2. `event_driven_signal_scan`
3. `watchlist_thesis_review`
4. `closed_position_postmortem`
5. `notification_dispatch`

OpenClaw should execute these jobs against the Aurel3 policy defined in `AUREL3_SPEC.md` and the record types defined in `AUREL3_STATE_SCHEMA.md`.

## 1. scheduled_signal_scan

Purpose:
- find new actionable opportunities on a fixed cadence

Reads:
- source inputs from news, market data, calendars, and social
- current theme and event state
- current recommendations
- current watchlist

Steps:
1. collect fresh source items
2. detect new themes or update active themes
3. map themes to candidate tickers
4. score candidates using Aurel3 signal logic
5. create or update recommendation records
6. expire stale recommendations when appropriate

Writes:
- theme and event records
- recommendation records

Notification triggers:
- new `buy_now`
- unusually strong `watch_for_confirmation`

Never notify for:
- no-op scans
- unchanged active recommendations
- purely informational findings

## 2. event_driven_signal_scan

Purpose:
- react quickly to important developments

Example triggers:
- geopolitical or policy shock
- earnings surprise
- M&A or corporate action news
- IPO pricing or listing
- Romanian or BVB issuer or market-moving local event

Reads:
- fresh event source items
- market reaction data
- current watchlist
- current recommendations

Steps:
1. detect the event
2. classify affected theme families
3. identify likely beneficiary and loser sectors
4. map sectors and themes to candidate tickers
5. validate the idea with confirmation logic
6. create or update theme and recommendation records
7. reassess affected watchlist positions

Writes:
- theme and event records
- recommendation records
- updated watchlist thesis records when needed

Notification triggers:
- strong new actionable signal
- material thesis change on a held position
- urgent `trim_de_risk`
- `sell`

## 3. watchlist_thesis_review

Purpose:
- protect capital and manage exits

Cadence:
- more frequent than entry scans

Reads:
- current watchlist thesis records
- fresh source inputs
- fresh market data
- relevant event and calendar data
- linked recommendation and theme records where useful

Steps for each held position:
1. load the original thesis and invalidation conditions
2. gather fresh evidence
3. reassess:
   - current thesis state
   - current confirmation state
   - exit urgency
4. determine current action:
   - `hold`
   - `hold_not_fresh_buy`
   - `trim_de_risk`
   - `sell`
5. update the watchlist thesis record

Writes:
- updated watchlist thesis records

Notify only when:
- action becomes `trim_de_risk`
- action becomes `sell`
- thesis changes materially with operational significance

Never notify for:
- routine `hold`
- unchanged `hold`
- "no new info"

## 4. closed_position_postmortem

Purpose:
- learn from outcomes and improve the system carefully

Trigger:
- when a watchlist position is closed

Reads:
- watchlist thesis record
- linked recommendation record
- linked theme and event record
- realized trade outcome

Steps:
1. compare original thesis to actual outcome
2. classify thesis outcome:
   - `worked`
   - `partial`
   - `failed`
3. identify the main failure point when applicable
4. determine whether the case was:
   - normal miss
   - exceptional case
   - recurring or structural issue
5. create a closed-position review record
6. optionally flag a spec change candidate when justified

Writes:
- closed-position review record

Notification policy:
- do not send immediate push notifications
- send batched or on-demand summaries to Slack only

## 5. notification_dispatch

Purpose:
- decide what should reach Slack and what should reach ntfy

Reads:
- newly created or updated recommendation records
- updated watchlist thesis records
- newly created postmortem records

Slack should receive:
- new `buy_now`
- strong `watch_for_confirmation`
- `trim_de_risk`
- `sell`
- important event-driven market shifts
- batched postmortem summaries

ntfy should receive only:
- strongest `buy_now`
- `sell`
- high-urgency `trim_de_risk`
- major watchlist thesis breaks

Never notify for:
- no new info
- unchanged thesis
- routine hold
- routine scan completion

## Scheduling Model

Scheduled jobs:
- `scheduled_signal_scan`
  - pre-market
  - mid-session
  - near close

- `watchlist_thesis_review`
  - more frequent during active market periods
  - plus post-event checks when relevant

Event-driven jobs:
- `event_driven_signal_scan`
  - whenever a major trigger is detected

Post-trade jobs:
- `closed_position_postmortem`
  - after a position is sold or otherwise closed

## Record Lifecycle

Recommended lifecycle:
1. theme or event detected
2. recommendation created
3. recommendation promoted into watchlist thesis after buy
4. watchlist thesis reviewed repeatedly
5. position closed
6. closed-position review created

This provides traceability from idea to outcome and supports disciplined learning.

## Architecture Split

Aurel3 should own:
- policy logic
- scoring
- state transitions
- output generation

OpenClaw should own:
- scheduling
- source collection orchestration
- job execution
- notification dispatch orchestration

Slack and ntfy should remain the operator-facing interfaces, with Slack carrying richer analysis and ntfy reserved for urgent or very high-value pings.
