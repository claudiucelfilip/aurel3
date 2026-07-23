# OpenClaw Worker

## Purpose

This document defines how an external OpenClaw worker should interpret Aurel3 source batches.

The loop is:
1. Aurel3 writes [openclaw_source_batch.json](/root/aurel3/data/openclaw_source_batch.json)
2. Aurel3 prepares [openclaw_task_payload.json](/root/aurel3/data/openclaw_task_payload.json)
3. OpenClaw reads that task payload
4. OpenClaw interprets each item with the prompt in this document
5. OpenClaw writes [openclaw_interpreted_items.json](/root/aurel3/data/openclaw_interpreted_items.json)
6. Aurel3 consumes those interpreted items on the next scan

## Batch-Synchronization Rule

The interpreted payload must match the current exported source batch exactly.

Required sequence:
1. Run `python3 run.py openclaw_export`
2. Run `python3 run.py openclaw_prepare`
3. Read `/root/aurel3/data/openclaw_task_payload.json`
4. Write `/root/aurel3/data/openclaw_interpreted_items.json`
5. Validate/import it with `python3 run.py openclaw_import /root/aurel3/data/openclaw_interpreted_items.json`
6. Only then run `python3 run.py signal_scan`

Do not run export and prepare in parallel.
Do not reuse an older interpreted payload.
The top-level `source_batch_generated_at` you write must exactly equal the current batch timestamp in `/root/aurel3/data/openclaw_source_batch.json`.
If the timestamps do not match, fail rather than continuing.

## Worker Objective

For each source item:
- decide whether it is market-relevant
- classify the event
- map it to a controlled Aurel3 theme
- identify beneficiary and hurt sectors
- identify direct and secondary beneficiary tickers when justified
- classify the ticker-specific impact as bullish, bearish, mixed, or neutral
- estimate durability, horizon, confidence, and actionability

Do not produce generic summaries. Produce structured market interpretation.

## Theme Guidance

Prefer these theme ids when appropriate:
- `eu_defense_rearmament`
- `energy_geopolitical_supply_risk`
- `ai_compute_infrastructure`
- `commodities_resource_supply_shock`
- `critical_materials_battery_inputs`
- `battery_storage_commercialization`
- `healthcare_commercialization`
- `banking_rates_credit`
- `agriculture_food_supply`
- `infrastructure_industrial_capex`
- `earnings_guidance_momentum`
- `m_and_a_corporate_action`
- `ipo_listing_momentum`
- `romanian_bvb_local_catalyst`

If none fits clearly, use:
- `null` for `theme_id`

## Market-Confirmation Step (required)

After mapping an item's direct beneficiaries, fetch their current market state:

```bash
python3 run.py market_context TICKER [TICKER...]
```

Batch all direct-beneficiary tickers from the whole batch into ONE call. Use the
returned trend / volume_ratio / EMA position to set confirmation-aware fields:

- Market confirms the thesis (uptrend, elevated volume in the thesis direction):
  confidence and actionability may stand at what the catalyst merits.
- Market does not confirm (downtrend/weak trend, no volume): cap actionability at
  `potentially_actionable` and reduce confidence one level below what the
  narrative alone suggests.
- No data returned for a ticker: judge on the narrative alone, as before.

Why: benchmarked on 64 resolved cases (BAKEOFF_FINDINGS.md), narrative-only
confidence is anti-calibrated; adding the asset's own market state fixed
calibration for every model tested and roughly doubled correct buy signals.

## Interpretation Rules

1. Ignore items that are not investable or market-relevant.
2. Focus on causality, not sentiment words alone.
3. Distinguish direct beneficiaries from weak proxies (see beneficiary rules below).
4. Be conservative with ticker suggestions.
5. Prefer sectors over tickers if the article is too broad for ticker-level mapping.
6. Treat patents or scientific news as actionable only if commercialization is plausible.
7. Treat geopolitics as probabilistic market impact, not certainty.
8. For commodities, energy shocks, infrastructure, and healthcare, prefer company-specific transmission paths over broad sector optimism.
9. For speculative EV or battery names, default to caution unless commercialization and beneficiary mapping are unusually clear.
10. For crowded AI leaders, do not downgrade purely due to attention if the item clearly supports a direct beneficiary and durable demand path.

## Confidence Rubric

Confidence measures the strength of the **investment thesis**, not your certainty about the interpretation. An article you fully understand but that has no actionable catalyst should be `low` confidence, not `high`.

Use these criteria to assign confidence. Do not default to `medium` — apply the rubric.

### `high`

The causal mechanism is direct AND the source is authoritative.

Examples:
- Company filing, earnings release, or official guidance update
- Confirmed contract award, regulatory approval, or policy announcement
- Named-party M&A report from a credible financial outlet
- Commodity price move with a clear, observable supply/demand driver

### `medium`

The causal path is plausible and the source is credible, but the thesis depends on interpretation or the transmission path is not fully direct.

Examples:
- Analyst commentary linking a macro event to sector beneficiaries
- Geopolitical risk that plausibly affects supply chains but hasn't yet
- A credible rumor without official confirmation
- Earnings from a peer company implying read-through to a related name

### `low`

The thesis is speculative, rumor-based, depends on multiple contingencies, or the item has no actionable thesis at all.

Examples:
- Social media speculation without corroborating sources
- Generic "sector poised to benefit" commentary with no specific catalyst
- Scientific or patent news with no near-term commercial path
- A connection that requires 3+ logical hops to reach a beneficiary
- Listicles, best-of lists, portfolio guides, or editorial opinion with no new event
- Items rated `informational` should almost always have `low` confidence

## Actionability Decision Tree

Assign actionability based on these criteria. The downstream signal engine uses this field to gate recommendations — accurate ratings matter more than conservative defaults.

### `actionable`

All three conditions are met:
1. A specific, identifiable catalyst exists (not just a trend or narrative)
2. At least one ticker has a direct, primary-revenue-exposure link to the catalyst
3. The source is credible and the information is fresh (not a rehash)

Examples:
- "Amazon reportedly acquiring Globalstar" → GSAT is actionable
- "NFLX beats earnings, raises full-year guidance" → NFLX is actionable
- "EU approves €100B defense procurement package" → RHM.DE, BAESY are actionable

### `potentially_actionable`

A real catalyst exists and ticker mapping is reasonable, but one condition weakens it:
- The catalyst needs further confirmation, OR
- The ticker benefits through a clear but not primary path, OR
- The durability is uncertain

Examples:
- "Oil prices surge on shipping disruption" → XOM, OXY are potentially_actionable (clear path, but the disruption duration is uncertain)
- "Copper prices rising on China stimulus hopes" → FCX is potentially_actionable (direct exposure, but stimulus is not confirmed)
- "Defense spending expected to increase" → RTX is potentially_actionable (real theme, but no specific contract)

### `interesting_but_early`

The driver is real but too early or speculative for positioning:
- No specific catalyst yet (just a thematic trend)
- Commercialization is plausible but unproven
- The article is forward-looking analysis, not a new event

Examples:
- "Solid-state battery breakthrough in lab" → QS is interesting_but_early
- "Analysts see upside in uranium if nuclear policy shifts" → no specific policy event yet
- "EV adoption trends suggest long-term upside for lithium" → thematic, not catalyzed

### `informational`

No trading relevance or purely backward-looking:
- Historical analysis, educational content, opinion pieces
- Market recaps without new information
- Generic "best stocks to buy" listicles

Do not assign `informational` to items that have a real catalyst just because you are uncertain. If a catalyst exists, choose `interesting_but_early` at minimum.

## Durability Guidance

### `high`

The driver is structural and expected to persist 3+ months:
- Policy regime changes (defense budgets, trade policy, regulatory shifts)
- Multi-year capex cycles (AI infrastructure, energy transition)
- Secular demand shifts with confirmed funding or orders

### `medium`

The driver is expected to persist 2-6 weeks:
- Supply disruptions with uncertain resolution
- Earnings momentum that may carry for a quarter
- Commodity price moves driven by temporary supply/demand imbalance

### `low`

The driver is likely to fade within days:
- One-off news events (M&A rumors without follow-up, single analyst note)
- Retail attention spikes without fundamental support
- Event-day reactions (earnings day, FDA decision day)

## Beneficiary Classification

### Direct beneficiary

The company meets at least one condition:
- It is **named in the catalyst** (target of M&A, company reporting earnings, contract recipient)
- It has **primary revenue exposure** to the specific driver (oil major during crude supply shock, fertilizer producer during ag input disruption)
- The catalyst **directly changes the company's earnings, orders, or regulatory status**

Direct beneficiary means directly affected, not necessarily positively affected.
For negative or mixed company-specific catalysts, still list the named company as
direct so downstream review can learn from both bullish and bearish outcomes.

For every ticker in `direct_beneficiaries` or `secondary_beneficiaries`, also
emit one `ticker_impacts` object with:

- `ticker`: the same ticker symbol
- `direction`: `bullish`, `bearish`, `mixed`, or `neutral`
- `rationale`: one concise causal sentence

Directness and direction are independent. Never label a ticker bullish merely
because it is named or directly affected. A lawsuit seeking to block a merger
is bearish for the target's deal-completion thesis; a sector selloff caused by
rates or oil is bearish for the falling companies; a guidance change with no
known direction is mixed or neutral until the direction is established.

### Secondary beneficiary

The company benefits but through an indirect path:
- Supply chain adjacency (chip equipment maker benefits from AI capex, but the capex goes to data center operators)
- Competitive read-through (peer's strong earnings imply sector strength)
- Portfolio overlap (company has some but not primary exposure to the driver)

### Do not list as beneficiary

- The connection requires 3+ logical hops
- The company is in the same sector but has no specific exposure to this catalyst
- The benefit is purely speculative ("if X happens, then maybe Y benefits")

When in doubt between direct and secondary, ask: "Does this catalyst directly change this company's near-term revenue or cost structure?" If yes → direct. If "it depends" → secondary. If "maybe eventually" → do not list.

## Theme-Specific Interpretation Rules

### Energy / geopolitical supply risk

- Oil majors (XOM, CVX, OXY, SHEL) are **direct** beneficiaries of crude supply disruption — they have primary upstream revenue exposure. Do not relegate them to secondary.
- Oil services (SLB, HAL) are **secondary** unless the catalyst specifically involves drilling/service demand.
- Rate as `actionable` when the supply disruption is confirmed and observable (shipping blockage, sanctions enforcement, pipeline incident). Rate as `potentially_actionable` when it is geopolitical risk that may or may not materialize.

### Earnings / guidance momentum

- The reporting company is always a **direct** beneficiary, even when the
  earnings update is mixed or negative. Example: "Intel reports revenue in-line,
  cuts full-year capex guidance" must include `INTC` as a direct beneficiary.
- Rate as `actionable` when the company beat expectations AND raised guidance. Rate as `potentially_actionable` for a beat without guidance raise, or mixed results.
- Peers with read-through are **secondary** and at most `potentially_actionable`.

### M&A / corporate action

- Named target is **direct**, `actionable`.
- Named acquirer is usually **secondary**, not direct. Only mark the acquirer direct if the catalyst clearly and immediately changes its near-term earnings, orders, or regulatory status. In most cases, keep the acquirer `potentially_actionable` at best.
- Competitors or sector peers are **secondary**, `interesting_but_early` unless the deal creates clear competitive dynamics.
- Confidence is `high` only if the report cites named parties and a credible outlet. Unconfirmed rumors = `medium`.
- Default downstream bias: the target is the primary tradable expression of M&A news. The acquirer should not auto-promote to `buy_now` from deal news alone.
- Deal approval, a higher bid, or improved completion probability is normally
  bullish for the target. A lawsuit, antitrust challenge, blocked vote, or
  other reduction in completion probability is bearish for the target even
  though the target remains a direct affected ticker.

### Healthcare / commercialization

- Rate as `actionable` only for company-specific catalysts: FDA approval, clinical trial results, commercial launch data, or guidance update.
- Sector-level analysis ("biotech poised for recovery") is `informational` unless tied to a specific policy or event.
- Be careful not to create false positives — a positive article about a drug class does not make every company in that class a direct beneficiary.

### AI / compute infrastructure

- Direct beneficiaries must have specific exposure: GPU suppliers, data center builders, power/cooling infrastructure with confirmed AI-linked contracts.
- Do not downgrade confidence or actionability purely because the AI narrative is crowded. If the catalyst is real and the beneficiary mapping is direct, rate it accurately.
- Software companies that "use AI" are not direct beneficiaries of AI infrastructure spending.

### Commodities / critical materials

- Mining and extraction companies with primary exposure to the specific commodity are **direct**.
- Rate copper miners as **direct** beneficiaries of copper supply shocks — this is primary revenue exposure, not a weak proxy.
- Downstream users who benefit from lower input costs are **secondary** at most.

### Speculative / early-stage names (EV, battery, pre-revenue biotech)

- Default actionability is `interesting_but_early` unless there is concrete commercialization evidence: contracted orders, funded production facility, regulatory milestone achieved.
- Do not rate as `actionable` based on technology announcements alone.
- Durability is `low` unless backed by multi-quarter commercial milestones.

## Required Output Shape

Return JSON only.

Top-level:

```json
{
  "generated_at": "ISO8601",
  "source_batch_generated_at": "ISO8601",
  "items": []
}
```

Per item:

```json
{
  "source_item_id": "string",
  "market_relevant": true,
  "event_type": "string",
  "theme_id": "string or null",
  "theme_label": "string",
  "summary": "short market interpretation",
  "beneficiary_sectors": ["sector"],
  "hurt_sectors": ["sector"],
  "direct_beneficiaries": ["ticker"],
  "secondary_beneficiaries": ["ticker"],
  "time_horizon": "1-3 days | 1-2 weeks | 1-3 months | 3+ months / structural",
  "durability": "low | medium | high",
  "confidence": "low | medium | high",
  "actionability": "informational | interesting_but_early | potentially_actionable | actionable",
  "reasoning_notes": "short explanation"
}
```

## Prompt Template

System instruction:

```text
You are interpreting market-relevant source items for Aurel3, a signal-detection engine.
Your task is to convert raw source items into structured market-event interpretations.
Be conservative, specific, and causal.
Do not write prose outside the requested JSON output.
```

User payload:

```text
Interpret the following source batch for Aurel3.

Rules:
- Output JSON only.
- Use the required schema exactly.
- Use only controlled confidence, durability, actionability, and time_horizon values.
- Prefer the provided Aurel3 theme ids where applicable.
- If an item is not market-relevant, still include it with market_relevant=false and low actionability.

Source batch:
<contents of openclaw_source_batch.json>
```
