Live stock-selection research — 22 October 2026

Decision: SPMO's published stock-ranking approach is the strongest lead in
this exploratory screen, but no Aurel replacement or AI contribution is
validated. It beats SPY and gold over the common live interval and since
2022, lags SPY before 2024, and has only a small lead over gold since 2022.
The report retains weaker candidates, data failures and selection limits.

Source rules and issuer:
https://www.spglobal.com/spdji/en/documents/methodologies/methodology-sp-momentum-indices.pdf
https://www.invesco.com/us/en/financial-products/etfs/invesco-sp-500-momentum-etf.html

Reproduce from the repository root with Python, pandas, yfinance and matplotlib:
  python research/live_funds/fetch.py
  python research/live_funds/analyze.py
  python research/live_funds/report.py
  python research/live_funds/validate.py
  python research/live_funds/report.py

fetch.py caches downloaded histories; it does not silently refresh existing
files. manifest.json fingerprints the inputs and the comparison plan.
identity_notes.json explains why the AIED series supplies AMOM history.
The old AMOM query and QRFT download failure are retained. A fresh QRFT
failure is expected; the report must not quietly discard the fund.

Output: data/gold_grid/results/live_funds/index.html
Inputs: data/live_funds/
All saved results: data/gold_grid/results/live_funds/results.json
Numerical validation: data/gold_grid/results/live_funds/validation.json
Evidence bundle: data/gold_grid/results/live_funds/evidence.zip

The report includes its own stylesheet; the rendered HTML works standalone.
Serve data/gold_grid/results on the existing local HTTP server to view it.

Verified: declared fund-window arithmetic, market-price coverage, cash-funded
buy-and-hold accounting, ticker/strategy changes and limited issuer cross-check.
Assumed: adjusted closes as a reinvested-distribution proxy and 0.10% per side.
Out of scope: Romanian tax and FX, broker availability, historical internal
fund exposure, a holdings-level clone, live trading, or independent prediction
validation. All comparisons are exploratory and selected after public headlines.

No parameter search, paid data, model API call, deployment or live trade.
