# Aurel3 Spec

## Purpose

Aurel3 is a signal engine plus watchlist thesis manager.

It should:
- detect market-relevant themes and catalysts
- identify the best ticker expressions of those themes
- recommend entries only when signal quality is strong enough
- track the original thesis behind each held position
- issue thesis-aware hold, trim, and sell guidance
- prioritize sell quality at least as much as buy quality

It should not:
- execute trades
- manage broker accounts
- rebalance a portfolio automatically
- act as a generic news summarizer without market validation

Aurel2 handles auto-trading and execution.

## Geographic Focus

Actionable focus:
- Romania and BVB
- EU
- Global as context and fallback for superior signals

Ranking rule:
- signal quality is always first
- recommendations must be realistically tradable
- Romania, BVB, Tradeville, and EU get a modest preference boost
- tax and platform convenience never override a materially better signal

## Source Universe

Core source classes:
- market data
- news
- event calendars
- social

Source trust priority:
1. market data
2. news
3. event calendars
4. social

Broker and platform trend feeds are optional enrichment, not core evidence.

## Theme Taxonomy

Aurel3 should classify opportunities under these families:
- geopolitics and policy
- earnings and guidance
- M&A and corporate action
- IPO and listing
- structural sector narratives
- Romanian and BVB local catalysts

Example themes:
- AI investment rush
- EU defense spending increase
- energy repricing after geopolitical escalation
- pre-earnings optimism
- merger speculation
- Romanian IPO momentum

## Signal Quality Framework

Core signal dimensions:
- catalyst strength
- narrative consensus
- market confirmation
- crowding and late-entry risk
- durability and horizon

Definitions:
- catalyst strength: how real and meaningful the repricing reason is
- narrative consensus: how strongly credible sources converge on the same implication
- market confirmation: price, volume, and relative strength support the thesis
- crowding: attention saturation and late-entry risk
- durability: how long the driver is likely to matter

## Market Confirmation

Market confirmation should be based on:
- price behavior
- volume behavior
- relative strength

Relative strength should be judged against:
- relevant sector peers
- relevant market or index
- relevant local or regional benchmark

Confirmation states:
- unconfirmed
- developing
- confirmed
- overconfirmed

Meaning:
- unconfirmed: narrative exists, market does not support it yet
- developing: early support exists, but not enough for strong conviction
- confirmed: market clearly supports the thesis
- overconfirmed: thesis is strongly validated, but may be crowded or stretched

## Durability

Horizon buckets:
- 1-3 days
- 1-2 weeks
- 1-3 months
- 3+ months / structural

Durability guidance:
- low durability: one-off hype, rumor, single shock
- medium durability: earnings drift, short policy cycle, contract or news impulse
- high durability: structural capex, defense re-rating, product ramp, commercialization trend

## Recommendation Labels

Aurel3 may issue these actions:
- buy now
- watch for confirmation
- hold
- hold, not a fresh buy
- trim / de-risk
- sell

Interpretation:
- buy now: high-quality signal, usually confirmed, not too crowded, durable enough
- watch for confirmation: interesting thesis without enough validation
- hold: thesis strengthening or intact
- hold, not a fresh buy: thesis valid, but timing unattractive
- trim / de-risk: thesis weakening, confirmation slipping, or move too extended or crowded
- sell: thesis broken, confirmation materially failed, invalidation hit, or catalyst edge spent

## Watchlist Thesis Model

Each held position should remember:
- original theme and driver
- original reason for entry
- expected horizon
- confirmation state at entry
- current thesis state
- current confirmation state
- invalidation conditions
- next relevant catalyst or event

Watchlist thesis states:
- strengthening
- intact
- weakening
- broken

Exit urgency:
- low
- medium
- high

## Sell Philosophy

Exits are thesis-first with price confirmation.

Aurel3 should sell because:
- the thesis is no longer true
- the market is materially rejecting the thesis
- the catalyst passed and follow-through failed
- risk and reward are no longer favorable after crowding or deterioration

It should not sell only because of random price noise.

## Invalidation Framework

Every idea should define invalidation conditions from these buckets:
- thesis invalidation
- confirmation invalidation
- crowding invalidation
- event invalidation

Examples:
- thesis invalidation: policy fades, merger fails, demand narrative weakens
- confirmation invalidation: failed breakout, weak volume, sector-relative underperformance
- crowding invalidation: move too extended, attention too saturated
- event invalidation: catalyst passes with weak or no follow-through

## Output Format

Each recommendation should include:
- ticker
- company and market
- action
- theme and driver
- why now
- confirmation state
- confidence: low, medium, or high
- expected horizon
- invalidation or main risk
- optional alternatives

Output style:
- one top ticker
- one to three alternatives when useful

Each watchlist review should include:
- ticker
- original thesis
- current thesis state
- current confirmation state
- action
- exit urgency
- why
- next catalyst

## Notification Policy

Default behavior is silent unless actionable.

Slack should be used for:
- new buy now recommendations
- strong watch for confirmation setups
- trim / de-risk
- sell
- important event-driven market shifts
- batched postmortem summaries

ntfy should be used only for:
- strongest buy now recommendations
- sell
- high-urgency trim / de-risk
- major watchlist thesis breaks

Never notify for:
- no new info
- unchanged thesis
- routine hold
- routine scan completion

## Runtime Model

Aurel3 should run on:
- a fixed schedule for entry scans
- a tighter cadence for watchlist reviews
- event-driven triggers for major developments

Examples of event-driven triggers:
- geopolitical escalation
- major earnings surprise
- IPO pricing or listing
- M&A announcement or credible rumor
- Romanian or BVB issuer and market-moving local news

## Learning Loop

Aurel3 should review closed positions and learn carefully from outcomes.

It should run postmortems that answer:
- what was the original thesis
- what actually happened
- which component failed
- whether this was a normal miss, an exceptional case, or a recurring issue
- whether the spec should be refined

It should not rewrite the spec from one bad trade. It should only propose rule changes when failures are clearly structural or repeated.

## Guiding Principle

Every Aurel3 judgment should answer:
- is the story true?
- is the market confirming it?
- is the timing still good?

Buy quality depends on all three.
Sell quality depends on noticing when one of them stops being true.
