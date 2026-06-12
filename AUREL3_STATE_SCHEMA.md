# Aurel3 State Schema

## Overview

Aurel3 should persist four core record types:
- theme and event records
- recommendation records
- watchlist thesis records
- closed-position review records

These records should support a clean lifecycle:
1. theme or event detected
2. recommendation created
3. recommendation promoted to watchlist after buy
4. watchlist thesis reviewed over time
5. position closed
6. postmortem review created

Suggested storage files:
- `data/theme_events.json`
- `data/recommendations.json`
- `data/watchlist.json`
- `data/closed_reviews.json`

## Shared Enums

Recommendation actions:
- `buy_now`
- `watch_for_confirmation`
- `hold`
- `hold_not_fresh_buy`
- `trim_de_risk`
- `sell`

Confirmation states:
- `unconfirmed`
- `developing`
- `confirmed`
- `overconfirmed`

Watchlist thesis states:
- `strengthening`
- `intact`
- `weakening`
- `broken`

Exit urgency:
- `low`
- `medium`
- `high`

Confidence:
- `low`
- `medium`
- `high`

Recommendation status:
- `active`
- `expired`
- `promoted_to_watchlist`
- `dismissed`

Theme status:
- `active`
- `developing`
- `fading`
- `expired`

Thesis outcome:
- `worked`
- `partial`
- `failed`

Failure point:
- `catalyst_strength`
- `narrative_consensus`
- `market_confirmation`
- `crowding`
- `durability`
- `late_exit`
- `exceptional_event`
- `other`

## Theme / Event Record

Purpose:
- capture a detected narrative or event and its impact context

Fields:
- `id`
- `timestamp`
- `theme_type`
- `theme_label`
- `event_summary`
- `geography`
- `catalyst_strength`
- `narrative_consensus`
- `confirmation_state`
- `crowding_state`
- `expected_horizon`
- `affected_sectors`
- `candidate_tickers`
- `source_refs`
- `status`

Notes:
- this should remain lightweight in the MVP
- it provides traceability from source evidence to recommendations

## Recommendation Record

Purpose:
- capture a surfaced idea and its current lifecycle status

Fields:
- `id`
- `timestamp`
- `ticker`
- `company`
- `market_exchange`
- `action`
- `theme_driver`
- `why_now`
- `confirmation_state`
- `confidence`
- `expected_horizon`
- `invalidation`
- `alternatives`
- `source_refs`
- `status`

Recommended notes:
- `alternatives` should be a short array, not a full basket
- `status` should track whether the recommendation is still actionable

## Watchlist Thesis Record

Purpose:
- track the original reason for owning a position and its current health

Fields:
- `id`
- `ticker`
- `company`
- `market_exchange`
- `entry_date`
- `entry_price`
- `shares_or_position_size`
- `original_theme_driver`
- `original_reason_for_entry`
- `expected_horizon`
- `confirmation_at_entry`
- `current_thesis_state`
- `current_confirmation_state`
- `current_action`
- `exit_urgency`
- `invalidation_conditions`
- `next_relevant_catalyst`
- `last_reviewed_at`
- `linked_recommendation_id`
- `notes`

Notes:
- this replaces a purely price-driven watchlist model
- it is the backbone of thesis-aware sell logic

## Closed-Position Review Record

Purpose:
- analyze completed positions and support postmortem learning

Fields:
- `id`
- `ticker`
- `entry_date`
- `exit_date`
- `entry_price`
- `exit_price`
- `realized_pnl`
- `holding_period`
- `original_theme_driver`
- `original_reason_for_entry`
- `expected_horizon`
- `thesis_outcome`
- `failure_point`
- `what_changed`
- `lesson`
- `spec_change_candidate`
- `exceptional_case`
- `linked_watchlist_id`
- `reviewed_at`

Notes:
- use this for disciplined learning, not impulsive rule changes
- spec changes should only be proposed when a pattern is structural or repeated

## Source Reference Shape

Purpose:
- attach lightweight evidence to themes and recommendations

Fields:
- `type`
- `title`
- `url`
- `publisher`
- `timestamp`
- `relevance_note`

Notes:
- keep this lightweight
- the MVP does not need a full document store

## Alternatives Shape

Purpose:
- preserve nearby candidate tickers without diluting the main recommendation

Fields:
- `ticker`
- `company`
- `market_exchange`
- `reason`

Notes:
- one top ticker should remain primary
- alternatives should remain short and specific

## State Linkage

Recommended linkage:
- one `theme/event` may produce many `recommendations`
- one `recommendation` may become one `watchlist thesis record`
- one `watchlist thesis record` may produce one `closed-position review`

This gives Aurel3 a clear idea-to-outcome chain suitable for reviews and future refinements.
