Aurel3 multi-asset validation
===========================

Research only. These scripts never import the live desk, send alerts, propose
orders, read broker credentials, or modify the existing recommendation engine.

Run from the repository root with Python, numpy, pandas >= 2.2 and yfinance:
  python research/multiasset/fetch.py
  python research/multiasset/run.py
  python -m pytest research/multiasset/test_engine.py
  python research/multiasset/report.py

Use an isolated Python environment with the required packages. This research
does not require changing any production environment.

Inputs and outputs are under data/multiasset/ (gitignored). fetch.py downloads
original first-release CPI and payroll data, plus price histories, then hashes
the input files. protocol.json records the hypotheses before portfolio returns
are computed. Every scenario is retained; none is promoted based on winning.

The three candidate specifications are simple rejection screens. They are not
exact replicas of AQR models, tests of every multi-asset strategy, or deployable
broker portfolios. Fund proxies represent bonds, commodities and currencies;
crypto is spot BTC/ETH. All are long/cash, without leverage or short positions.

Economic-release availability uses a deliberately delayed 90-day assumption,
stressed to 120 days. First-release values solve revision leakage, but the
workbooks do not provide original publication timestamps. This is not a fully
certified point-in-time replay. Missing first-release data stay missing.

Signals use the previous UTC crypto close at US market close. Crypto trades are
delayed until the UTC opening after the ETF execution date. Daily valuation
combines US equity closes and later UTC crypto closes. Cash earns the return of
the BIL total-return proxy when invested; idle settlement cash earns nothing.
Adjusted price units are synthetic total-return units, not executable shares.

Minimum simulated orders are max(USD100, 1% NAV), initial capital is illustrative
USD25,000, and fills are fractional. ETF costs are 25bps each way, crypto 75bps,
minimum USD1/order. No tax, FX conversion, subscriptions, whole-share constraints,
or broker availability certification. Never label these outputs 'after tax'.
The simulator uses one cash pool; broker transfer delays and separate-account
funding constraints are not modeled. This makes it unsuitable for live orders.

ML uses nonlinear fixed features, train-only standardization and annual ridge
fits. Training labels must end before fitting. No retrospective language-model
decisions or invented news are used. There is no claim of an untouched recent
holdout: 2022 onward has already informed the broader research conversation.

Passing a 3pp return hurdle requires additional independent verification;
failing it is sufficient to reject this specification. Bootstrap intervals are
descriptive and not multiple-testing-adjusted. A failed candidate does not need
statistical significance to be rejected for this user's performance objective.

The existing manual desk can later receive qualified recommendations. This work
does not enable that connection. Multiple broker accounts, cash, currencies and
derivative contracts still require a portfolio-ledger extension before use.
