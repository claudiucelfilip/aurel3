# Aurel3 Buy-Now Gate

## Purpose

This document defines the non-negotiable quality bar for a `buy_now` recommendation.

If a candidate fails any required condition, it must not be promoted to `buy_now`.

The goal is recommendation quality, not recommendation volume.

## Core Principle

`buy_now` should be rare.

If the system is unsure, or if a setup is interesting but not yet sufficiently validated, it should use:
- `watch_for_confirmation`
- `hold_not_fresh_buy`
- or no recommendation at all

## Required Conditions

A recommendation may become `buy_now` only if all of the following are true.

### 1. Real Catalyst Exists

There must be a concrete repricing reason.

Examples:
- policy shift
- earnings or guidance change
- contract award
- M&A process
- commercialization milestone
- commodity or supply shock
- IPO demand
- funding, licensing, or manufacturing progress after a technical breakthrough

Disallowed:
- vague hype
- generic optimism
- ticker attention with no clear event

### 2. Interpretation Is Coherent

The interpretation layer must clearly explain:
- what happened
- why it matters
- who benefits
- why the specific ticker is relevant
- whether the ticker is a direct or secondary beneficiary

If the interpretation is weak, fuzzy, or generic, the candidate must not be `buy_now`.

### 3. Theme Support Is Multi-Signal

The theme should not usually depend on one isolated article.

Support may come from:
- multiple related articles
- article plus social reaction
- article plus sector move
- article plus commodity move
- article plus filing or company confirmation

An isolated signal should remain below `buy_now` unless it is unusually direct and strong.

### 4. Ticker Mapping Is Strong

The chosen ticker must be:
- a direct beneficiary
or
- a very clean secondary beneficiary

It must not be:
- a weak proxy
- a sympathy meme
- an unrelated broad-market beneficiary

Weak mapping disqualifies `buy_now`.

### 5. Market Confirmation Exists

Market confirmation is mandatory.

At minimum:
- price trend is supportive
- volume participation is supportive
- relative strength is not weak

If the market is not validating the thesis, the setup must not be `buy_now`.

### 6. Crowding Is Acceptable

Even a correct thesis should not become `buy_now` when:
- the move is too extended
- attention is already saturated
- the easy move appears gone

Those cases belong in:
- `hold_not_fresh_buy`
or
- `watch_for_confirmation`

### 7. Durability Is Sufficient

The move should be investable, not just interesting.

Avoid `buy_now` for:
- one-headline pops
- rumor spikes
- low-durability retail bursts

Unless:
- the horizon is explicitly short
and
- confirmation is unusually strong

### 8. Invalidation Is Explicit

Every `buy_now` must include a concrete invalidation path.

The system must be able to state:
- what would make this wrong
- what would invalidate the thesis

If it cannot do that, the recommendation is not good enough.

## Category Guardrails

The replay evidence suggests several categories require stricter or more specific handling.

### Commodities / resource shock

`buy_now` should require:
- a direct commodity-linked transmission path
- stronger market confirmation than the generic minimum
- a short and explicit invalidation tied to price reversal or supply normalization

Broad commodity enthusiasm alone is not sufficient.

### Energy / geopolitical supply risk

`buy_now` should prefer:
- direct majors or clean first-order beneficiaries
- repeated evidence, not one isolated headline

Short-horizon energy beta names should clear a higher bar than integrated majors.

### Infrastructure / industrial capex

`buy_now` should require:
- company-specific support, not only broad macro optimism
- evidence that the chosen ticker is a direct beneficiary rather than a vague industrial proxy

### Healthcare / commercialization

`buy_now` should require:
- company-specific commercialization, approval, launch, demand, or guidance evidence

Sector halo is not enough.

### Speculative battery / EV names

These should default to `watch_for_confirmation` unless:
- commercialization evidence is concrete
- ticker mapping is direct
- market confirmation is unusually clean

### High-crowding AI leaders

Crowded AI leaders can still be valid `buy_now` names if:
- the beneficiary mapping is direct
- confirmation is strong
- extension remains acceptable

Do not downgrade a clean AI leader purely because social attention is high.

## Label Guidance

### `buy_now`

Use only when all required conditions are met.

### `watch_for_confirmation`

Use when:
- the catalyst is real
- interpretation is plausible
- mapping is decent
- but confirmation, durability, or confidence is not yet strong enough

### `hold`

Use when:
- the thesis remains valid
- confirmation remains supportive

### `hold_not_fresh_buy`

Use when:
- the thesis is still valid
- but timing is worse now
- usually because of extension or crowding

### `trim_de_risk`

Use when:
- the thesis is weakening
- confirmation is slipping
- or crowding is too high after gains

### `sell`

Use when:
- thesis breaks
- confirmation fails materially
- invalidation is hit
- or the catalyst edge is clearly spent

## Operational Consequence

If the implementation cannot demonstrate these standards consistently, the recommendation engine is not good enough for serious live use.
