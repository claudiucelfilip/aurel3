# Track K: long-only intraday opening-range breakout on QQQ — 2026-10-26

Source claim: two TikTok clips relayed by Sherlock (Noise Band, Session Momentum), leveraged futures, both directions.
Tested: long-only, unleveraged, cash account, QQQ, Alpaca IEX 1-min bars 2020-07-27 → 2026-10-23 (1,442 sessions).
Development 2020-07-27 → 2022-12-31, holdout 2023-01-01 → 2026-10-23 (halves split 2024-12-31). Hurdle: holdout CAGR ≥ SPY + 3pp net.

## Verdict: FAIL, all 8 grid cells

| cell | holdout CAGR @0bp | @1bp/side | @2bp | vs SPY @1bp |
|---|---|---|---|---|
| K1 ORB R5 | 11.2% | 7.0% | 3.0% | −11.4pp |
| K1 ORB R15 | 13.0% | 9.2% | 5.6% | −9.2pp |
| K1 ORB R30 | 13.0% | 9.8% | 6.6% | −8.7pp |
| K3 R5 +trend | 3.9% | 1.3% | −1.3% | −17.2pp |
| K3 R15 +trend | 6.3% | 4.0% | 1.7% | −14.5pp |
| K3 R30 +trend | 7.0% | 4.9% | 2.9% | −13.5pp |
| K2 SessMom trail1 | 1.1% | −1.6% | −4.3% | −20.1pp |
| K2 SessMom trail2 | 3.5% | 0.8% | −1.9% | −17.7pp |

SPY buy-and-hold holdout: 18.4% CAGR, −18% DD. QQQ price-only: 29.1%.

## What the data says
- The breakout signal is real but tiny: 6–8bp gross per trade, ~1 trade a day, 31–53% win rate. Max drawdowns 5–8%, Sharpe ~1 at 1bp.
- Even with zero costs the best cell makes 13%/yr vs SPY's 18.4%. Long-only, unleveraged, flat overnight means the strategy skips the overnight drift that is most of QQQ's return.
- 1bp per side takes a third of the return, 2bp takes half, 5bp turns every cell negative. Live slippage on a stop-triggered market order is realistically 1–3bp on QQQ.
- Pre-registered selection (development Sharpe at 1bp) picks K3 R5 +trend (dev Sharpe 1.40). Its holdout is 1.3%/yr. The development ranking does not predict the holdout ranking.
- Not run: cash earning T-bill yield while flat. Adding ~4.5pp/yr for 2023–25 would lift the best cell to ~14%, still under SPY.

## Caveats
- IEX bars are ~2–3% of consolidated volume; highs/lows and stop fills are approximations. Could bias either way.
- Six years, one bull market with one bear (2022). No 2008/2020-style crash in holdout.
- The leveraged, two-sided futures version the videos sell was not tested because it violates the handoff rules.

Full output: `data/broad_search/orb/results.txt` (gitignored, regenerate with `python research/broad_search/orb/orb.py`).
