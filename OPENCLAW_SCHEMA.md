# OpenClaw Interpreted Payload Schema

## Purpose

This document defines the file contract for OpenClaw to hand interpreted source items back to Aurel3.

Aurel3 writes:
- [openclaw_source_batch.json](/root/aurel3/data/openclaw_source_batch.json)

OpenClaw should read that file, interpret the items, then write:
- [openclaw_interpreted_items.json](/root/aurel3/data/openclaw_interpreted_items.json)

## Top-Level Payload

```json
{
  "generated_at": "2026-04-02T13:50:00+00:00",
  "source_batch_generated_at": "2026-04-02T13:48:46+00:00",
  "items": [
    {
      "source_item_id": "news::energy::2026-04-02T13:00:00+00:00::Oil Prices Jump...",
      "market_relevant": true,
      "event_type": "energy_supply_risk",
      "theme_id": "energy_geopolitical_supply_risk",
      "theme_label": "Energy / geopolitical supply risk",
      "summary": "Shipping disruption and geopolitical tension are increasing the probability of higher near-term energy prices.",
      "beneficiary_sectors": ["energy", "utilities"],
      "hurt_sectors": ["airlines", "transportation"],
      "direct_beneficiaries": ["XOM", "CVX", "SHEL"],
      "secondary_beneficiaries": ["SLB", "HAL"],
      "time_horizon": "1-2 weeks",
      "durability": "medium",
      "confidence": "high",
      "actionability": "actionable",
      "reasoning_notes": "The article directly links geopolitical tension to higher energy pricing risk and cites supply disruption."
    }
  ]
}
```

## Required Top-Level Fields

- `generated_at`
- `source_batch_generated_at`
- `items`

## Required Item Fields

- `source_item_id`
- `market_relevant`
- `event_type`
- `theme_id`
- `theme_label`
- `summary`
- `beneficiary_sectors`
- `hurt_sectors`
- `direct_beneficiaries`
- `secondary_beneficiaries`
- `time_horizon`
- `durability`
- `confidence`
- `actionability`
- `reasoning_notes`

## Allowed Value Guidelines

### `market_relevant`
- `true`
- `false`

### `confidence`
- `low`
- `medium`
- `high`

### `actionability`
- `informational`
- `interesting_but_early`
- `potentially_actionable`
- `actionable`

### `durability`
- `low`
- `medium`
- `high`

### `time_horizon`
- `1-3 days`
- `1-2 weeks`
- `1-3 months`
- `3+ months / structural`

## Notes

- `source_item_id` must match an item in the exported source batch.
- `source_batch_generated_at` must exactly match the current `/root/aurel3/data/openclaw_source_batch.json` `generated_at` value.
- `theme_id` should align with Aurel3 taxonomy where possible.
- `direct_beneficiaries` and `secondary_beneficiaries` may be empty arrays when the source is market-relevant but not ticker-specific.
- `beneficiary_sectors` and `hurt_sectors` should use plain lowercase sector strings where possible.
- `reasoning_notes` should remain concise and decision-oriented.

## Current Aurel3 Usage

Aurel3 currently uses interpreted items mainly for:
- `theme_id`
- `beneficiary_sectors`
- `durability`

Future versions should make deeper use of:
- direct beneficiaries
- secondary beneficiaries
- hurt sectors
- actionability
- reasoning notes
