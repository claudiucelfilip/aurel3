"""Build one Yahoo ticker per holding and cache adjusted closes. Unpriced names are reported, not filled."""
import json
from pathlib import Path
import pandas as pd

HERE = Path(__file__).resolve().parent
DATA = HERE.parents[1] / 'data' / 'spmo_diagnostic'
# OpenFIGI returned a foreign line, a stale code or nothing; mapped by hand from the security name.
ISIN_OVERRIDES = {
    'BMG169621056': 'BG', 'BMG475671050': 'INFO', 'CH0102993182': 'TEL', 'GB00BWFY5505': 'NLSN',
    'IE00BY9D5467': 'AGN', 'IE00BZ12WP82': 'LIN', 'JE00B783TY65': 'APTV', 'JE00BJ1F3079': 'AMCR',
    'PA1436583006': 'CCL', 'US2166484020': 'COO', 'US3696041033': 'GE', 'US3137472060': 'FRT',
    'IE00B58JVZ52': 'STX', 'GB00B5BT0K07': 'AON', 'IE00B6330302': 'TT', 'US40414L1098': 'PEAK',
    'US1248572026': 'PARA', 'US8679141031': 'STI',
}


def ticker_table():
    h = pd.read_csv(DATA / 'holdings.csv', parse_dates=['date'])
    h = h[h['assetCat'] == 'EC'].copy()
    cus = json.loads((DATA / 'cusip_figi.json').read_text())
    isin = json.loads((DATA / 'isin_figi.json').read_text())

    def pick(row):
        if row['isin'] in ISIN_OVERRIDES:
            return ISIN_OVERRIDES[row['isin']]
        t = cus.get(row['cusip'], {}).get('ticker') if isinstance(row['cusip'], str) else None
        t = t or isin.get(row['isin'])
        return t.replace('/', '-') if t else None
    h['ticker'] = h.apply(pick, axis=1)
    return h


def main():
    import yfinance as yf
    h = ticker_table()
    h.to_csv(DATA / 'holdings_tickers.csv', index=False)
    path = DATA / 'stock_prices.csv'
    tickers = sorted(h['ticker'].dropna().unique())
    if not path.exists():
        f = yf.download(tickers, start='2019-08-01', end='2026-10-17', auto_adjust=False,
                        progress=False, threads=True)
        f['Adj Close'].to_csv(path)
    px = pd.read_csv(path, index_col=0, parse_dates=True)
    empty = [t for t in tickers if t not in px or px[t].notna().sum() == 0]
    print(len(tickers), 'tickers; no prices for', len(empty), empty)


if __name__ == '__main__':
    main()
