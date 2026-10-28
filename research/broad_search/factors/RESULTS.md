# Long-only factor ETFs vs SPY (descriptive check, 2026-10-28)

Prompted by the TikTok series "Quantitative Finance from Scratch" (QuantFinanceToGo, parts 24–29:
momentum, value, size, Fama-French, low-volatility anomaly, Carhart). Question: does any long-only,
unleveraged, single-factor ETF beat SPY by the 3pp hurdle? Not a strategy track (no dev/holdout
split, nothing to fit); yfinance adjusted closes, run inside the aurel2-real container.

Since 2013-07-18 (common start, 159 months), CAGR vs SPY 14.0%:
MTUM +1.1pp (t 0.50) · QUAL -0.5 · VLUE -1.2 · SIZE -2.5 · USMV -3.2 · IWD -3.2 · IWM -4.9 · SPLV -5.1.
Since 2019: best MTUM -0.7, VLUE -0.7; low-vol -6 to -8pp. Since 2023: VLUE +3.6 (t 0.63, 45 months), rest below SPY.
No t-statistic above 0.7. The long-short factor premia in the papers do not survive as long-only tilts;
the low-vol "anomaly" is a drawdown reduction (vol 14% vs 20%), not a return edge.

Verdict: FAIL the 3pp hurdle, nothing to register.
