# Replay 64 Findings

Date: 2026-04-02

## Scope

Expanded historical replay with 64 curated representative cases across:
- AI / compute infrastructure
- EU defense / rearmament
- Energy / geopolitical supply risk
- Banking / rates / credit
- Healthcare / commercialization
- Battery / storage commercialization
- Commodities / resource supply shock
- Critical materials / battery inputs
- Agriculture / food supply
- Infrastructure / industrial capex
- Earnings / guidance momentum
- M&A / corporate action
- IPO / listing momentum

## Headline Result

- Cases reviewed: `64`
- Outcomes:
  - `worked = 39`
  - `partial = 13`
  - `failed = 1`
  - `late = 11`

## Engine Behavior

- Actions:
  - `buy_now = 8`
  - `watch_for_confirmation = 15`
  - `hold_not_fresh_buy = 3`
  - `no_signal = 38`
- Exact action matches vs benchmark labels: `14 / 64`
- Missed opportunities while not `buy_now`:
  - `>=10% = 8`
  - `>=20% = 4`

## What Still Looks Good

- AI and direct EU defense leaders remain the strongest recurring `buy_now` bucket.
- Energy, agriculture, and commodities are conservative but mostly avoid bad aggressive entries.
- Banking remains selective rather than noisy.
- The engine still avoids obvious false positives better than the earlier looser versions.

## Weak Spots Exposed

### Earnings / guidance is underpowered

The new earnings cases were the clearest gap:
- `NFLX` late
- `TSM` late
- `ADBE` late
- `COST` only partial on `watch_for_confirmation`

This theme is too reluctant to upgrade strong company-specific earnings resets into `buy_now`.

### M&A is too conservative

All three M&A cases stayed below `buy_now`.
That was acceptable for `GSAT` and `EL`, but `RVYL` matured into a late miss.

### Healthcare still misses direct company-specific winners

`VRTX` was a late miss.
That suggests the healthcare gate is still too cautious even when the company-specific setup is relatively clean.

### Battery / speculative names remain difficult

`QS` and `RIVN` both became late.
This is a real blind spot, but also a dangerous one because the same bucket produces many false positives.
It should be handled with better watch coverage before relaxing `buy_now`.

### Infrastructure remains conservative

Most infrastructure cases were filtered to `no_signal` or `watch_for_confirmation`.
That avoided damage in weak cases like `ETN` and `PWR`, but may still be overly strict in stronger contractor and electrification names.

## Theme Notes

- `AI / compute infrastructure`: generally good, but `PLTR` was still missed and `VRT` was the one outright failed `buy_now`
- `EU defense / rearmament`: strong on direct leaders, still conservative on secondary names like `GD`
- `Energy / geopolitical supply risk`: all five cases stayed at `watch_for_confirmation`, which looks safe but a bit too restrained
- `Critical materials / battery inputs`: all four cases stayed below `buy_now`; `FCX` became a late miss
- `IPO / listing momentum`: all four stayed at `no_signal`; mostly acceptable, but `ARM` still matured into a miss

## Honest Conclusion

The 64-case replay validates that the engine is directionally useful and not random, but it is still conservative in several high-value areas.

The next tuning pass should focus on:
- stronger earnings / guidance upgrade logic
- less timid M&A handling for direct event-driven setups
- slightly better healthcare direct-beneficiary recognition
- better coverage of speculative names through alternatives and watch logic, not blindly more `buy_now`
