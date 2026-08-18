# Manual Trading Desk

Broker-agnostic order flow with a human executing the trades. Strategies
propose orders; the desk notifies, nags until the fill is confirmed, and keeps
the ledger. Because execution is manual, the same desk works unchanged on
Tradeville today and any other broker later.

## Why it exists

The backtest work of Aug 2026 (REPLAY_LIVE_BUYS_2026_08.md) showed the most
reliable edge available is behavioral: disciplined monthly index buying beat
panic-selling in 92% and dip-waiting in 100% of rolling 10-year windows since
1993 (+0.65–0.9%/yr). The desk automates the *decision and the accountability*;
the human keeps the 30-second execution click.

## Components

- `desk.py` — order store, ledger, holdings/lot math, notifications, DCA
  producer, anti-panic guard.
- `data/desk/orders.json` — every order and its lifecycle
  (`proposed → confirmed | skipped | expired`).
- `data/desk/ledger.jsonl` — append-only confirmed executions (the source of
  truth for holdings, FIFO lots, and tax ages).
- `data/desk/inbox/` — file-drop for external producers (see contract below).
- `data/desk/state.json` — DCA carryover, guard episode state, nag timestamps.

## Commands

```bash
python3 run.py core_dca        # cron, daily: proposes the monthly core buy on
                               # the first trading day (idempotent per month;
                               # amounts below min_ticket carry over)
python3 run.py core_guard      # cron, daily: -10/-20/-30% drawdown -> one
                               # "plan says do nothing" message per episode
python3 run.py desk_notify     # cron, daily: ingest inbox, expire stale
                               # orders, notify + nag unconfirmed ones
python3 run.py desk_confirm SXR8 614.20 2 6.45   # record the fill (price qty [fees])
python3 run.py desk_skip SXR8 reason...          # record a deliberate deviation
python3 run.py desk_status     # open orders, holdings, lot ages, deviations
```

Configuration lives in `config.json` under `"core"`. `monthly_amount: 0`
disables the DCA producer; set it to the real monthly contribution to go live.
Order size stays ≥ `min_ticket` (€700 — below that Tradeville's €3 Xetra
minimum exceeds the 0.43% rate; smaller months carry over).

## Producer contract (for aurel2 or any other strategy)

Drop a JSON file into `data/desk/inbox/`; the next `desk_notify` run validates
and proposes it (invalid files are renamed `*.rejected`):

```json
{
  "source": "aurel2_dual_momentum",
  "action": "buy",
  "symbol": "XLK",
  "name": "Technology Select Sector SPDR",
  "exchange": "USA",
  "currency": "USD",
  "notional": 1500,
  "reference_price": 243.10,
  "reason": "Dual momentum rotated into tech.",
  "exit_plan": {"policy": "Sell at +4% or after 10 trading days."}
}
```

Required: `source`, `action` (buy/sell), `symbol`, and one of
`notional`/`quantity`. Everything else is optional.

This is the migration path off Alpaca: aurel2 keeps trading its Alpaca paper
account as a parallel shadow ledger, and additionally drops its orders into
this inbox. The human-executed Tradeville ledger and the Alpaca shadow ledger
can then be compared like-for-like before any real-money switch.

## Tax notes encoded in the desk

- Lots are FIFO; `desk_status` reports quantity already past 365 days
  (Romanian withholding drops from 6% to 3% for holds over a year).
- The guard message reminds that panic-selling also triggers the 6% tax.
- The DCA instrument is an accumulating UCITS ETF, so no dividend events.
