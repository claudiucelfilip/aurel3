# Live Buy-Recommendation Replay — Jul 23 → Aug 14, 2026

Date: 2026-08-17

## Scope

Replay of every buy-flavored recommendation (`buy_now`, `early_accumulation`)
issued by the live engine since the current code went live (commit `49fe87a`,
2026-07-23), against actual market prices. Entry = recorded `reference_price`
(verified inside that day's trading range for all 13 names). Returns measured
at +5 and +10 trading days and to 2026-08-14, vs SPY over the same windows.

## Headline Result

Following the buys with $100:

| Policy | Result |
|---|---|
| Equal split across the 10 `buy_now` names, hold to date | **$100.84 (+0.8%)** |
| Chronological, 1/3-of-cash per signal, exit at stated horizon | **$104.85 (+4.9%)** |
| SPY buy-and-hold over the same window | **+5.2%** |

The buys underperformed the index. 11 of 13 unique buys came from a single
theme (`earnings_guidance_momentum`); its confirmed-path buys averaged
**−2.9% excess vs SPY at +10td (1 of 6 positive)**.

## Per-Recommendation Outcomes

| Ticker | Action | Date | Day-of run-up | +10td | Excess vs SPY |
|---|---|---|---:|---:|---:|
| WEX | buy_now | Jul 23 | +9.9% | +10.8% | +6.7 |
| VZ | buy_now | Jul 24 | +3.5% | +3.8% | −0.9 |
| TECK | buy_now | Jul 24 | +2.2% | +8.7% | +4.0 |
| CLF | buy_now | Jul 24 | +9.3% | +2.3% | −2.3 |
| KO | buy_now | Jul 28 | +4.3% | −1.4% | −5.4 |
| IDXX | buy_now | Aug 4 | +5.2% | −7.8% | −8.4 |
| TFX | buy_now | Aug 6 | +1.6% | −1.1% | −2.1 |
| TTWO | buy_now | Aug 7 | +3.9% | +2.3% | +1.9 |
| EAT | buy_now | Aug 12 | +12.0% | −4.4% | −4.9 |
| NOMD | buy_now | Aug 13 | +5.9% | −2.8% | −2.6 |
| FAN.L | early_accum | Jul 23 | −0.2% | +8.0% | +3.9 |
| BMY | early_accum | Aug 4 | +0.6% | −3.1% | −3.8 |
| HWM | early_accum | Aug 6 | +1.2% | −1.9% | −2.9 |

## What Goes Wrong

1. **Chasing extended earnings pops.** Buys entered >4% into the day's move
   averaged −0.5% at +10td; entries ≤4% averaged +2.4%. KO, IDXX, NOMD, EAT
   all bought the top of a guidance gap and mean-reverted. The
   `earnings_guidance_momentum` overconfirmed path issued `buy_now` with **no
   crowding check** and a day-of cap of 12% — violating BUY_NOW_GATE §6
   (Crowding Is Acceptable). This path produced WEX (+), CLF (−), EAT (−).
2. **Confidence is inversely calibrated.** `high`-confidence buys averaged
   +0.2% at +10td vs +2.0% for `medium` — "high" selects confirmed+moved
   names, i.e. later entries.
3. **No exit management.** Zero `sell`/`trim_de_risk` recommendations in the
   entire recorded history; the watchlist has been empty since April. Buys are
   fire-and-forget, so the "sell quality first" half of the spec never runs.
4. **Learning loop flags but nothing acts.** VZ/CLF/KO failures were promoted
   to open spec-change candidates ("Repeated independent misses in the same
   gate cohort") and stayed open. This change is the action on that cohort.

## Change Made

`signals.py` — `EARNINGS_FRESH_BUY_MAX_CHANGE = 0.04`:

- Main confirmed path: day-of `change_pct` capped at +4% (was uncapped above).
- Post-earnings dip path: capped at +4% so it stays a dip lane (was uncapped).
- Overconfirmed path: now requires `crowding != "high"` and the same +4% cap
  (was: no crowding check, cap 12%).
- Overconfirmed or high-crowding setups fall through to `hold_not_fresh_buy`.

Counterfactual on this window: surviving buy_nows are VZ, TECK, TFX, TTWO —
equal-split $100 → **$102.98** (vs $100.84), per-trade mean excess vs SPY
−1.1% → +0.7%. Cost: WEX (+10.8%) would have been demoted to
`hold_not_fresh_buy`; it was the only >4% entry that worked (1 of 6).

## Validation

- `python3 -m pytest` — 17 passed (includes new `test_earnings_buy_gate.py`;
  also fixed a time-bomb date in `test_wbd_safety.py`).
- `historical_replay.py --split full` — **identical per-case results before
  and after** (63 cases; NFLX and COST earnings buys unaffected because they
  enter on dips/flat, not pops).

## Caveats

n=13 over three weeks, and July recs won while August recs lost — regime is a
confounder. The cap is kept conservative (+4%, matching the winners' range)
and is consistent with the pre-existing gate doc rather than fit to this
sample alone.

## Part 2 (2026-08-18): Exit Plan — Can It Beat SPY?

Follow-up question: can following the buys beat holding SPY? Expanded replay
over the full live history (170 unique episodes, all actions, May 25 → Aug 14;
tuning split before Jul 23, validation after).

Findings:

- **The signal universe has negative drift vs SPY.** Mean 10-trading-day
  excess is −2.6% across all 130 scoreable episodes, negative in both splits
  and in nearly every slice (theme, confirmation, freshness, confidence).
  Post-news names systematically lag SPY after selection; hold-to-21-days is
  worse (−7%). Delayed and pullback entries stay negative.
- **But the names spike before they fade.** With honest fills (take-profit
  only fillable from the session *after* the rec — same-day daily highs are
  look-ahead), a +4% take-profit with a 10-trading-day time stop on the
  buy lane (`buy_now` + `early_accumulation`) is positive in BOTH eras:
  tuning +1.70%/trade excess vs SPY (9/14 win), validation +1.62%/trade
  (4/6 win). The same exits on the whole universe (incl. watch) stay
  negative — selection still matters.
- **Portfolio framing: SPY rotation.** Cash drag loses to a rallying SPY, so
  the policy is: park in SPY, rotate a slice into a signal only while held,
  return to SPY on exit. $100 on the validation window: $104.72 (TP4, ⅓
  slices) vs SPY $105.17 — a wash on 16 trading days, dragged by three
  overlapping August time-stops crowding out the TTWO winner; the analytic
  per-trade sum is ≈ +0.9% over SPY. The per-trade edge is the robust claim;
  the 3-week portfolio realization is noise-dominated.

### Change Made (Part 2)

- `signals.py`: buy-lane recommendations now carry an `exit_plan`
  (`EXIT_TAKE_PROFIT_PCT = 0.04`, `EXIT_MAX_HOLD_TRADING_DAYS = 10`) with the
  SPY-rotation policy spelled out.
- `market.py`: `get_take_profit_hit()` (no-look-ahead: signal-day highs are
  ignored) and `get_benchmark_return(..., end_iso=)` so reviews can score the
  benchmark over the actual holding window.
- `reviews.py` + `run.py review_signals`: reviews of exit-planned buys score
  the managed trade — TP hit ⇒ +4% banked, compared to SPY up to the hit
  date; time-stop ⇒ price at window end. Legacy scoring is untouched for
  non-buy actions and for recs without an `exit_plan`.
- `notify.py`: buy alerts include the exit plan line.

### Validation (Part 2)

- `python3 -m pytest` — 23 passed (6 new in `test_exit_plan.py`).
- `historical_replay.py --split full` — per-case results identical (the
  engine's action logic is untouched by Part 2).
- `get_take_profit_hit` spot-checked against the replay: TTWO (rec Aug 7,
  ref 241.51) → hit Aug 10; BMY (rec Aug 4, ref 65.88) → no hit. Matches.

### Honest Expectations

With ~2-3 signals/week at ⅓ slices and +1.6%/trade excess, expected
outperformance is roughly +1.5-2%/month over SPY **if the per-trade edge
holds** — n=20 across both eras is thin, and the edge must be re-measured as
reviews accumulate under the new scoring. The TP-aware review outcomes now
measure exactly this policy, so `review_summary` becomes the live scoreboard
for whether the edge is real.

## Remaining Gaps (not addressed here)

- Wire `buy_now` recs into the watchlist automatically (paper position) so the
  review cadence can generate `trim`/`sell` guidance mid-hold — the exit plan
  covers the scheduled exits, not thesis-break exits.
- Feed extension/crowding into the confidence label so `high` stops selecting
  late entries.
