SPMO concentration diagnostic — 22 October 2026

Question: is SPMO's lead over SPY and gold a steady edge, or concentrated after 2023?
protocol.json was committed before any result (commit 8d52d79), including the
reject/continue rules. Everything here is development evidence, not a holdout.

Run from the repository root:
  python research/spmo_diagnostic/fetch.py      # yfinance; caches ETFs, French data, SEC N-PORT
  python research/spmo_diagnostic/holdings.py   # parse N-PORT, map CUSIPs via OpenFIGI (cached)
  python research/spmo_diagnostic/tickers.py    # yfinance; cache holding prices
  python research/spmo_diagnostic/sectors.py    # yfinance; current sector labels
  python research/spmo_diagnostic/analyze.py
  python research/spmo_diagnostic/report.py

Inputs: data/spmo_diagnostic/ (ignored by Git) plus data/live_funds/ unchanged.
Outputs: data/gold_grid/results/spmo_diagnostic/ (results.json, holding_periods.csv,
stock_contributions.csv, index.html). results_snapshot.json here is a copy of results.json.

Deviation from protocol, disclosed: SPMO had zero-volume days until 2017-11-24, so the
main start is 2017-12-29; the protocol's 2015-10-12 start is also reported and gives the
same rule outcome. The 2024-onward holdings window starts at the 2023-11-30 filing.
