# Track D (insider purchases): spec interpretations

Written before any backtest result was computed. Spec: `research/broad_search/protocol.json`
keys `holdout_rules` and `track_D_insider_purchases`. Where the spec is ambiguous the more
conservative reading is used.

## Data
- SEC Insider Transactions Data Sets, every quarterly zip listed on the official SEC page
  (first available quarter: 2006Q1). Tables: SUBMISSION, NONDERIV_TRANS, REPORTINGOWNER.
- Information date = SUBMISSION.FILING_DATE (never the transaction date).
- Forms 4 and 5 only; amendments (4/A, 5/A) are excluded so restated filings are not double counted.
- Transactions: TRANS_CODE = 'P' and TRANS_ACQUIRED_DISP_CD = 'A', with shares > 0 and price > 0.
  Value = shares x price per share. Rows without a usable price are dropped (no value, no signal).
- Officer or director: at least one reporting owner on the filing has RPTOWNER_RELATIONSHIP
  containing "Officer" or "Director". Filings where no owner is an officer/director are ignored.
- A joint filing (several reporting owners) counts as ONE insider (lowest officer/director CIK),
  so joint filings by a director and his own fund cannot create a "cluster" on their own.
- Ticker = ISSUERTRADINGSYMBOL upper-cased and trimmed; only symbols matching `[A-Z]{1,5}`
  optionally followed by `.X` / `-X` (share class) are kept, mapped to Yahoo with `.` -> `-`.
  Anything else ("NONE", "N/A", exchange prefixes, blank) is counted as unmappable and dropped.
- Prices: Yahoo chart endpoint (copy of `research/broad_search/yahoo_chart.py` returning both
  split-adjusted close and adjusted close). Adjusted close drives returns; the $5 entry filter uses
  the split-adjusted (not dividend-adjusted) close, which is closer to the traded price.

## Signals (per ticker, per filing date D)
- "any": officer/director open-market purchases filed on D total >= $100,000.
- "cluster2": on a filing date D with at least one qualifying filing, the officer/director
  purchases filed in [D-29, D] (30 calendar days inclusive) come from >= 2 distinct insiders and
  total >= $100,000.
- Signal on day D -> entry at the close of the first trading day strictly after D (NYSE days =
  SPY trading days). If a ticker is already held, the new signal is ignored (no adding, no extension).

## Portfolio
- Daily, cash-funded, no leverage. Each new position is sized at 1/50 of NAV at the entry close,
  capped by available cash; positions then drift (buy and hold). Weights sum <= 1; the remainder
  earns the cash return.
- Max 50 concurrent positions. Existing positions are never displaced (oldest-first priority);
  when more candidates arrive than free slots on a day, earlier filing date first, then ticker
  alphabetically (deterministic, uses no return information).
- Entry requires a Yahoo close on the exact entry date and split-adjusted close >= $5. Events
  failing because Yahoo has no price on that date (unknown/delisted ticker, or history starting
  later) are counted as "dropped for missing prices"; events failing the $5 rule are counted separately.
- Exit at the close of the first trading day on/after entry date + 3 (or 6) calendar months.
  If Yahoo's history for the ticker ends before the exit date, the position is held at its last
  available price until the scheduled exit (no bankruptcy haircut: an upward bias, reported).
- Costs: 0.25% of traded notional on entry and on exit.
- Cash: BIL adjusted-close daily return; before BIL's first full day, ^IRX yield / 100 / 252 per day
  (previous day's yield).

## Development and holdout
- Development: first trading day 2006 to 2018-12-31. The development backtest is run with filings
  and prices truncated at 2018-12-31 (open positions marked to market at that date), so no 2019+
  number exists when the choice is made. Choice = highest development Sharpe (daily return minus
  cash return, mean/std x sqrt(252)). It is written to `dev_choice.json` before the holdout run.
- Holdout: one continuous backtest 2006 -> 2026-10-16 (positions carry over the split); metrics
  computed on daily returns 2019-01-02 .. 2026-10-16. The development slice of the continuous run
  is checked to equal the truncated development run.
- Metrics vs SPY (data/live_funds/SPY.csv Adj Close): CAGR, CAGR excess, Newey-West t (6 lags,
  Bartlett) of monthly return minus SPY monthly return, CAGR in 2019-2022 and 2023-01-01..2026-10-16
  (H3 = strategy CAGR above SPY's in both), max daily-close drawdown (H4 = strategy DD minus SPY DD
  >= -10 points), development CAGR excess (H5).
