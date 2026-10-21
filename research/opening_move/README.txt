AUREL OPENING-MOVE RESEARCH

Own QQQ implementation, not a reproduction of a proprietary trading bot.
Research only: these scripts make no trading requests and do not alter the app.

RESULT
The selected AI filter fails the investment gates. See FINDINGS.txt.
Do not tune parameters against these evaluation dates and call them unseen.
This does not evaluate the original QuantLab bot: see REPLICATION.txt and
replication.html for the verified mismatches and unresolved original rules.

REPLAY (from the repository root, Python 3.12)
python3 -m venv /tmp/aurel-opening-env
/tmp/aurel-opening-env/bin/pip install -r research/opening_move/requirements.txt
/tmp/aurel-opening-env/bin/pytest -q research/opening_move/test_engine.py
/tmp/aurel-opening-env/bin/python research/opening_move/run.py
/tmp/aurel-opening-env/bin/python research/opening_move/verify.py
/tmp/aurel-opening-env/bin/python research/opening_move/report.py
/tmp/aurel-opening-env/bin/python -m http.server 49888 --bind 127.0.0.1

The report is data/opening_move/results/index.html beneath that local server.
run.py requires the cached input files described below. Fetching newer vendor
data can change results if the vendor corrects history; retain manifest.json.

INPUT DATA
data/opening_move/ is deliberately ignored by Git. It contains raw consolidated
SIP QQQ minute bars for 2016 through 20 October 2026, adjusted SPY/QQQ daily
bars, and a SHA256 manifest. No market data or credentials are committed.

To obtain the data with an existing Alpaca account, run:
python3 research/opening_move/fetch.py --env-file /path/to/private.env --output data/opening_move

Replace /path/to/private.env with an existing private file containing
APCA_API_KEY_ID and APCA_API_SECRET_KEY. Do not put credentials in Git.
The fetcher uses historical market-data GET requests only, paginates results,
and uses fixed start/end dates. It does not place or cancel orders.

FILES
protocol.json       Fixed rules, model settings, selection and rejection gates.
fetch.py            Read-only data download and input fingerprints.
engine.py           Session preparation, causal features, fills, yearly models.
run.py              Development selection, evaluation and execution stress.
test_engine.py      Synthetic tests of execution, calendar and causal features.
verify.py           Separate cash-flow reconciliation and timing audit.
report.py           Browser report from saved output; no model selection.
FINDINGS.txt        Durable result summary from the first completed run.
result_snapshot.json Metrics, gates and input hashes from that completed run.

OUTPUTS (data/opening_move/results/)
summary.csv         Every variant, period and cost/delay scenario.
report.json         Metrics, daily equity paths, benchmarks and gates.
selection.json      Development-only choice and protocol fingerprint.
model_audit.json    Training cutoffs and observation counts.
coverage.json       Every expected session and missing-minute details.
verification.json  Input hashes, cash-flow checks and timing audit.
*_trades.csv        Entry, exit, sizing, costs and return for each trade.
ml_predictions.csv Predictions before the fixed trade/no-trade threshold.
setups.csv          Features available at the daily decision.

LIMITS
Results are before tax and FX; idle cash earns zero. Minute data cannot verify
tick-level fills or worst intraday drawdown. Fractional shares and short
availability are assumed. Positions use no more than 100% notional exposure;
the planned 0.5% stop risk is not a guaranteed loss cap when prices gap.
SPY/QQQ buy-and-hold use fully adjusted daily prices and base entry/exit costs.
All variants use the same benchmark, including in execution stress scenarios.
Historical data may have been corrected. Models train chronologically, but
the general market history was known before this retrospective experiment.
No live broker execution, portfolio recommendation or app integration is done.
