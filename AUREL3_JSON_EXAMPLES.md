# Aurel3 JSON Examples

## Purpose

This document provides concrete example records for the main Aurel3 state objects.

It is not a strict schema definition. It is an implementation aid so that the target object shapes are unambiguous before coding.

## 1. Theme / Event Record Example

```json
{
  "id": "theme_2026_04_02_eu_defense_001",
  "timestamp": "2026-04-02T08:15:00Z",
  "theme_type": "geopolitics_policy",
  "theme_label": "EU defense spending acceleration",
  "event_summary": "Multiple EU policy and security developments are reinforcing a higher medium-term defense spending path.",
  "geography": "EU",
  "catalyst_strength": "high",
  "narrative_consensus": "high",
  "confirmation_state": "confirmed",
  "crowding_state": "medium",
  "expected_horizon": "1-3 months",
  "affected_sectors": [
    "defense",
    "aerospace",
    "industrial suppliers"
  ],
  "candidate_tickers": [
    "RHM.DE",
    "BAE.L",
    "LDO.MI"
  ],
  "source_refs": [
    {
      "type": "news",
      "title": "European governments expand defense commitments",
      "url": "https://example.com/eu-defense-news",
      "publisher": "Example News",
      "timestamp": "2026-04-02T07:30:00Z",
      "relevance_note": "Supports the durability of the defense-spending theme."
    },
    {
      "type": "market_data",
      "title": "EU defense basket relative strength",
      "url": "internal://market/defense-rs",
      "publisher": "Aurel3",
      "timestamp": "2026-04-02T08:10:00Z",
      "relevance_note": "Sector leaders are outperforming their market benchmarks."
    }
  ],
  "status": "active"
}
```

## 2. Recommendation Record Example

```json
{
  "id": "rec_2026_04_02_rhm_001",
  "timestamp": "2026-04-02T08:20:00Z",
  "ticker": "RHM.DE",
  "company": "Rheinmetall AG",
  "market_exchange": "XETRA",
  "action": "buy_now",
  "theme_driver": "EU defense spending acceleration",
  "why_now": "Defense policy momentum is strengthening, sector relative strength is positive, and the stock remains in a confirmed uptrend without extreme crowding.",
  "confirmation_state": "confirmed",
  "confidence": "high",
  "expected_horizon": "1-3 months",
  "invalidation": "Exit if defense-sector relative strength weakens materially or policy/news momentum fades.",
  "alternatives": [
    {
      "ticker": "BAE.L",
      "company": "BAE Systems plc",
      "market_exchange": "LSE",
      "reason": "Large-cap alternative with the same macro driver."
    },
    {
      "ticker": "LDO.MI",
      "company": "Leonardo S.p.A.",
      "market_exchange": "Borsa Italiana",
      "reason": "Secondary EU defense expression with positive trend confirmation."
    }
  ],
  "source_refs": [
    {
      "type": "theme",
      "title": "EU defense spending acceleration",
      "url": "internal://themes/theme_2026_04_02_eu_defense_001",
      "publisher": "Aurel3",
      "timestamp": "2026-04-02T08:15:00Z",
      "relevance_note": "Parent theme record driving this recommendation."
    }
  ],
  "status": "active"
}
```

## 3. Watchlist Thesis Record Example

```json
{
  "id": "wl_2026_04_02_rhm_001",
  "ticker": "RHM.DE",
  "company": "Rheinmetall AG",
  "market_exchange": "XETRA",
  "entry_date": "2026-04-02T09:05:00Z",
  "entry_price": 582.4,
  "shares_or_position_size": {
    "shares": 3,
    "notional": 1747.2,
    "currency": "EUR"
  },
  "original_theme_driver": "EU defense spending acceleration",
  "original_reason_for_entry": "Direct beneficiary of EU rearmament and defense budget repricing with confirmed trend and positive sector relative strength.",
  "expected_horizon": "1-3 months",
  "confirmation_at_entry": "confirmed",
  "current_thesis_state": "intact",
  "current_confirmation_state": "confirmed",
  "current_action": "hold",
  "exit_urgency": "low",
  "invalidation_conditions": [
    "Defense-sector relative strength turns negative versus EU industrial peers.",
    "Material policy or procurement de-escalation weakens the spending narrative.",
    "Price trend fails with weak volume follow-through."
  ],
  "next_relevant_catalyst": "EU defense procurement and budget headlines over the next two weeks.",
  "last_reviewed_at": "2026-04-03T10:30:00Z",
  "linked_recommendation_id": "rec_2026_04_02_rhm_001",
  "notes": "Good core expression of the theme. Not yet overconfirmed."
}
```

## 4. Closed-Position Review Record Example

```json
{
  "id": "review_2026_05_10_rhm_001",
  "ticker": "RHM.DE",
  "entry_date": "2026-04-02T09:05:00Z",
  "exit_date": "2026-05-10T14:40:00Z",
  "entry_price": 582.4,
  "exit_price": 641.8,
  "realized_pnl": {
    "pnl_pct": 0.102,
    "pnl_amount": 178.2,
    "currency": "EUR"
  },
  "holding_period": "38 days",
  "original_theme_driver": "EU defense spending acceleration",
  "original_reason_for_entry": "Direct beneficiary of EU rearmament and defense budget repricing with confirmed trend and positive sector relative strength.",
  "expected_horizon": "1-3 months",
  "thesis_outcome": "worked",
  "failure_point": "other",
  "what_changed": "The defense theme remained valid, but the position was exited after the move became crowded and short-term upside compressed.",
  "lesson": "Aurel3 correctly identified a durable theme and a strong direct beneficiary. Trim and exit logic should continue to prioritize crowding after strong confirmation phases.",
  "spec_change_candidate": false,
  "exceptional_case": false,
  "linked_watchlist_id": "wl_2026_04_02_rhm_001",
  "reviewed_at": "2026-05-10T18:00:00Z"
}
```

## 5. Recommendation Example For Romanian / BVB Context

```json
{
  "id": "rec_2026_04_15_bvb_ipo_001",
  "timestamp": "2026-04-15T07:45:00Z",
  "ticker": "H2O",
  "company": "Example Romanian Issuer",
  "market_exchange": "BVB",
  "action": "watch_for_confirmation",
  "theme_driver": "Romanian IPO attention build-up",
  "why_now": "Local news and listing attention are increasing, but market confirmation is still developing and liquidity behavior remains the key validation point.",
  "confirmation_state": "developing",
  "confidence": "medium",
  "expected_horizon": "1-2 weeks",
  "invalidation": "Do not upgrade to buy if post-listing volume is weak or price fails to hold above the opening range.",
  "alternatives": [],
  "source_refs": [
    {
      "type": "news",
      "title": "Romanian IPO attracts strong investor attention",
      "url": "https://example.com/romanian-ipo-news",
      "publisher": "Example Romania Business",
      "timestamp": "2026-04-15T06:50:00Z",
      "relevance_note": "Supports the existence of the local listing theme."
    }
  ],
  "status": "active"
}
```

## 6. Watchlist Review Example With Sell Outcome

```json
{
  "id": "wl_2026_04_18_nvo_001",
  "ticker": "NVO",
  "company": "Novo Nordisk A/S",
  "market_exchange": "NYSE",
  "entry_date": "2026-04-18T13:10:00Z",
  "entry_price": 132.6,
  "shares_or_position_size": {
    "shares": 5,
    "notional": 663.0,
    "currency": "USD"
  },
  "original_theme_driver": "Commercialization upside from new metabolic treatment momentum",
  "original_reason_for_entry": "The stock appeared to be an early beneficiary of a durable health-care commercialization theme with developing confirmation.",
  "expected_horizon": "1-3 months",
  "confirmation_at_entry": "developing",
  "current_thesis_state": "broken",
  "current_confirmation_state": "unconfirmed",
  "current_action": "sell",
  "exit_urgency": "high",
  "invalidation_conditions": [
    "If follow-through buying fails after the catalyst window.",
    "If health-care peer relative strength turns negative and the stock underperforms peers."
  ],
  "next_relevant_catalyst": "None. Thesis no longer active.",
  "last_reviewed_at": "2026-04-27T15:20:00Z",
  "linked_recommendation_id": "rec_2026_04_18_nvo_001",
  "notes": "Catalyst did not translate into durable price confirmation. The idea should be closed."
}
```

## 7. Recommended Implementation Notes

Recommended MVP choices:
- keep enum values stable
- prefer explicit strings over overloaded numeric codes
- keep timestamps in ISO 8601 UTC
- use arrays for `source_refs`, `alternatives`, and `invalidation_conditions`
- keep recommendation and review records immutable after creation where practical
- allow watchlist thesis records to be updated over time

Suggested future extensions:
- internal numeric component scores
- richer relative-strength metadata
- theme history snapshots
- recommendation lifecycle audit trail
