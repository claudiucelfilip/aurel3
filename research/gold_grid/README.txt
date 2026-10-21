Gold grid baseline research
===========================

Correct source: https://www.tiktok.com/@thequantbuilder/video/7699030814419422497
Historical provider: https://www.dukascopy.com/api/data/get/historical-data-export
Archive documentation: https://github.com/kevingtlin/Market-Data-Lab/blob/main/XAUUSD_DUKASCOPY_M1_BID_ASK_README.md

This is an independent reconstruction of the described long gold grid, not a
replication of the creator's proprietary results. All missing settings are
explicit in protocol.json. The Nasdaq opening-move research is unrelated.
Nothing here connects to an execution account or changes Aurel's live strategy.

Run from the repository root (Python 3.12):

  uv venv --python 3.12 /Users/claudiu/Research/gold-grid-env
  uv pip install --python /Users/claudiu/Research/gold-grid-env/bin/python -r research/gold_grid/requirements.txt
  /Users/claudiu/Research/gold-grid-env/bin/python -m pytest research/gold_grid/test_engine.py -q
  /Users/claudiu/Research/gold-grid-env/bin/python research/gold_grid/run.py --spy data/gold_grid/SPY_daily_adjusted.json
  /Users/claudiu/Research/gold-grid-env/bin/python research/gold_grid/report.py
  /Users/claudiu/Research/gold-grid-env/bin/python -m http.server 49889 --bind 127.0.0.1 --directory data/gold_grid/results

The report is at the local server's /index.html. It has 2019/2022 selectors,
intraminute path comparisons, all 54 parameter combinations, fresh-start tests,
financing/leverage stress, charts, and downloadable fills/results.

Data recovery
-------------
The local data/gold_grid directory is deliberately ignored by git. It contains
the monthly archive, original-provider validation samples, parsed parquet file,
SPY input and manifests. Do not overwrite it with fresh data for comparisons.

fetch.py can download the original daily archive; HTTPS repeatedly stalled in
this session, so public non-sensitive data uses HTTP. Downloads were slow and
the full original-provider job was stopped, retaining validation samples.
fetch_mirror.py downloads the pinned GitHub archive, verifies each git blob hash,
and cross-checks all local original-provider samples. GitHub CLI authentication
is needed for its API rate limit; it performs read-only operations.

For a clean data download, first get at least one active day from the provider:

  /Users/claudiu/Research/gold-grid-env/bin/python research/gold_grid/fetch.py --start 2024-01-15 --end 2024-01-16
  /Users/claudiu/Research/gold-grid-env/bin/python research/gold_grid/fetch_mirror.py

The full study also checked original samples in 2022, 2023 and 2026. The SPY input
is the existing Alpaca SIP daily, split/dividend-adjusted JSON export. Its SHA256
is in results.json. A local copy is retained at data/gold_grid/SPY_daily_adjusted.json.
No credentials are stored in this research directory or exported bundle.

Execution and accounting
------------------------
The first purchase is 1 ounce; the default gap is $10 and the target is $1 per
total ounce AFTER entry/exit commission, slippage and accrued financing. The
doubling variant adds 2,4,8... ounces; the fixed variant adds 1 ounce each time.
Starting order size does not compound with account value. Targets include
financing, so a long-held losing basket must recover farther before exit.

Each minute is reconstructed as open-low-high-close and, separately,
open-high-low-close. Bid and ask extrema are paired; these may not occur at
the same instant in real markets. Linear transitions fill grid orders and
targets at crossings. Gaps execute at the next available quote. These paths
are sensitivity scenarios, not guaranteed bounds on a tick-level backtest.

New baskets start on the next active minute. Entirely flat minutes are omitted
because the mirror lacks volume; this removes stale closed-market quotes but
can also remove real quiet minutes. One unmatched bid/ask timestamp is excluded
and recorded in quality.json. Other gaps are not synthesized or forward-filled
for execution; elapsed-time financing continues across them.

Margin uses 20:1 leverage. Additions must satisfy full initial margin. Below
50% of used margin, the whole basket is liquidated, and the account stops
trading. There are NO cash resets, deposits or automatic restarts. Some cash
may remain after liquidation, and negative cash is not clamped if a gap causes
it. This is a research margin model, not a claim about a particular broker.

Financing is 5% annualized on prior notional, accrued each elapsed minute and
across weekends. Historical broker swap rates/triple-roll conventions are not
available. Commission is $0.035/ounce/side and adverse slippage $0.05/ounce/side.
Sensitivity includes zero/10% financing, triple slippage and 10:1/100:1 leverage.

The account value includes unrealized P&L and estimated exit costs throughout.
Open final baskets remain open and are included in total return; they are NOT
counted as completed wins. A second accounting pass reconciles actual fills,
financing, final equity and total basket P&L. Targeted tests exercise failure
cases, including unaffordable additions and gaps through margin thresholds.

SPY daily closes are timestamped at 16:00 New York before availability filtering;
the last benchmark close must precede the final gold quote. Half-day closes
are conservatively treated as available at 16:00. Gold is unleveraged spot,
without fund fees/storage. Benchmark drawdowns are daily-close, not intraday.

Scope
-----
This is baseline characterization. No loss limit, AI filter, optimization,
out-of-sample claim, live execution or tax model is included. All inspected
history is now development evidence. Any later mitigation experiment must
disclose that it has been designed after seeing these results.
