# Systematic options overlays vs S&P 500 total return (descriptive check, 2026-10-28)

User lifted the derivatives exclusion (options allowed; still no borrowing/leverage). Question: does any
automated, rule-based options strategy on the index beat buy-and-hold? The CBOE strategy indices are
exactly that, run mechanically since 1986-2008, gross of commissions and slippage. Source:
cdn.cboe.com daily_prices *_History.csv; benchmark ^SP500TR from yfinance. Scripts in this folder,
run inside the aurel2-real container.

CAGR gap vs S&P 500 TR (t = monthly excess return t-stat):
                    full history          since 2010           since 2019
BXM  ATM buy-write   -3.9 (2002-, t -2.8)  -6.7 (t -3.6)        -8.3 (t -2.4)
BXMD 30d buy-write   -0.5 (1988-, t -1.0)  -3.9 (t -3.2)        -4.8 (t -2.1)
BXY  2% OTM b-write  -1.1 (1988-, t -1.5)  -4.3 (t -3.2)        -5.9 (t -2.2)
PUT  cash-sec. puts  -1.7 (1991-, t -2.2)  -5.9 (t -3.2)        -7.1 (t -2.0)
CLL  95-110 collar   -5.7 (2008-, t -2.1)  -5.5 (t -3.2)        -5.0 (t -1.6)
PPUT 5% OTM put buy  -3.5 (1988-, t -3.7)  -3.6 (t -2.6)        -3.5 (t -1.4)
CMBO combo           -1.8 (1988-, t -2.0)  -5.7 (t -3.6)        -7.3 (t -2.5)

Options-income ETFs (net, real money, automated), total return vs own index:
JEPI -6.6pp vs SPY (2020-), XYLD -6.1 (2013-), DIVO -2.4 (2016-), SVOL -4.8 (2021-),
QYLD -10.4 vs QQQ (2013-), JEPQ -4.2 (2022-).

Every mechanical option overlay, long and short vol alike, trails the index over every window; the
best full-history result (BXMD, -0.5pp gross) still fails before costs. What the overlays buy is lower
volatility (12-15% vs 17-19%) and shallower drawdowns, i.e. a Sharpe improvement that only becomes
extra CAGR with leverage. Account size is a second wall: one SPY contract covers ~$68k notional, and
the real account holds ~$109.

Verdict: FAIL the 3pp hurdle. Nothing to register.
