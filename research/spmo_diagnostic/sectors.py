"""Cache current Yahoo sector labels for every priced holding (current labels, applied to the past)."""
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pandas as pd

DATA = Path(__file__).resolve().parents[2] / 'data' / 'spmo_diagnostic'


def main():
    import yfinance as yf
    path = DATA / 'sectors.json'
    known = json.loads(path.read_text()) if path.exists() else {}
    px = pd.read_csv(DATA / 'stock_prices.csv', nrows=1).columns[1:].tolist() + \
        pd.read_csv(DATA / 'stock_prices_extra.csv', nrows=1).columns[1:].tolist()
    todo = [t for t in sorted(set(px)) if t not in known]

    def one(t):
        try:
            return t, yf.Ticker(t).info.get('sector')
        except Exception:
            return t, None
    with ThreadPoolExecutor(8) as ex:
        for t, s in ex.map(one, todo):
            known[t] = s
    path.write_text(json.dumps(known, indent=1, sort_keys=True))
    print(len(known), 'labels;', sum(v is None for v in known.values()), 'missing')


if __name__ == '__main__':
    main()
