"""Compare declared live fund windows and retain missing observations as failures."""
import hashlib
import json
from pathlib import Path
import pandas as pd

HERE = Path(__file__).resolve().parent
DATA = HERE.parents[1] / 'data' / 'live_funds'
OUT = HERE.parents[1] / 'data' / 'gold_grid' / 'results' / 'live_funds'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def metrics(prices, capital=10000, entry=.001, exit_cost=.001):
    if len(prices) < 2 or not prices.index.is_unique or prices.isna().any() or (prices <= 0).any():
        raise ValueError('Invalid price series')
    equity = capital / (1 + entry) * prices / prices.iloc[0]
    equity.iloc[-1] *= 1 - exit_cost
    days = (prices.index[-1] - prices.index[0]).days
    returns = prices.pct_change().dropna()
    return {'start': str(prices.index[0].date()), 'end': str(prices.index[-1].date()),
            'observations': len(prices), 'ending_equity': float(equity.iloc[-1]),
            'cagr_net': float((equity.iloc[-1] / capital) ** (365.25 / days) - 1),
            'cagr_before_entry_exit': float((prices.iloc[-1] / prices.iloc[0]) ** (365.25 / days) - 1),
            'total_before_entry_exit': float(prices.iloc[-1] / prices.iloc[0] - 1),
            'annual_arithmetic_before_entry_exit': float(returns.mean() * 252),
            'drawdown_net': float(1 - (equity / equity.cummax().clip(lower=capital)).min())}, equity


def main():
    protocol = json.loads((HERE / 'protocol.json').read_text())
    identities = json.loads((HERE / 'identity_notes.json').read_text())
    manifest = json.loads((DATA / 'manifest.json').read_text())
    assert digest(HERE / 'protocol.json') == manifest['protocol_sha256']
    assert digest(HERE / 'identity_notes.json') == manifest['identity_notes_sha256']
    frozen_path = HERE / 'input_snapshot.json'
    if frozen_path.exists():
        frozen = json.loads(frozen_path.read_text())
        for name, info in frozen['files'].items():
            if manifest['files'].get(name, {}).get('sha256') != info['sha256']:
                raise ValueError(f'Frozen input changed: {name}')
    OUT.mkdir(parents=True, exist_ok=True)
    frames, failures = {}, {}
    symbols = protocol['candidates'] + protocol['benchmarks']
    for ticker in symbols:
        resolved = identities.get(ticker, {}).get('history_symbol', ticker)
        if resolved is None:
            failures[ticker] = identities[ticker]['reason']
            continue
        path = DATA / f'{resolved}.csv'
        assert digest(path) == manifest['files'][path.name]['sha256']
        frame = pd.read_csv(path, index_col=0, parse_dates=True)
        assert frame.index.is_monotonic_increasing and frame.index.is_unique
        frames[ticker] = frame['Adj Close']
    results = {'protocol_sha256': manifest['protocol_sha256'], 'failures': failures,
               'windows': {}, 'rolling_36_months': {}, 'data_checks': {}}
    for label, (start, end) in protocol['comparisons'].items():
        calendar = frames['SPY'].loc[start:end].index
        rows = {}
        for ticker, prices in frames.items():
            selected = prices.loc[start:end]
            missing = calendar.difference(selected.index)
            if len(missing) or selected.isna().any():
                rows[ticker] = {'error': 'Incomplete interval', 'missing_dates': [str(x.date()) for x in missing]}
                continue
            row, equity = metrics(selected, protocol['capital_usd'],
                                  protocol['entry_cost_fraction'], protocol['exit_cost_fraction'])
            equity.rename('equity').to_csv(OUT / f'{label}_{ticker}.csv')
            rows[ticker] = row
        results['windows'][label] = rows
    start, end = protocol['comparisons']['common_live']
    monthlies = {}
    for ticker, prices in frames.items():
        s = prices.loc[start:end].resample('ME').last()
        s = s[s.index <= pd.Timestamp(end)]
        monthlies[ticker] = s
    monthly = pd.DataFrame(monthlies)
    rolling = monthly / monthly.shift(36) - 1
    for ticker in protocol['candidates']:
        if ticker not in rolling:
            continue
        sample = rolling[[ticker, 'SPY', 'GLD']].dropna()
        wins = (sample[ticker] > sample['SPY']) & (sample[ticker] > sample['GLD'])
        results['rolling_36_months'][ticker] = {
            'windows': len(sample), 'beat_both': int(wins.sum()),
            'worst_total_return': float(sample[ticker].min()),
            'first_end': str(sample.index[0].date()), 'last_end': str(sample.index[-1].date())}
    rolling.to_csv(OUT / 'rolling_36_months.csv')
    annual = pd.DataFrame({t: s.resample('YE').last().pct_change() for t, s in frames.items()})
    annual.index = annual.index.year
    annual.to_csv(OUT / 'annual_returns.csv')
    # NAV differs from market closes; this is a source cross-check, not an exact reconciliation.
    nav = {2019: .26, 2020: .2817, 2021: .2268, 2022: -.1063,
           2023: .1759, 2024: .4581, 2025: .2668}
    results['spmo_issuer_nav_crosscheck'] = {
        str(year): {'issuer_nav': value, 'vendor_market': float(annual.loc[year, 'SPMO']),
                    'difference_pp': float(100 * (annual.loc[year, 'SPMO'] - value))}
        for year, value in nav.items()}
    for ticker, prices in frames.items():
        check = prices.loc[start:end]
        gaps = frames['SPY'].loc[start:end].index.difference(check.index)
        results['data_checks'][ticker] = {'missing_sessions': len(gaps),
                                          'null_prices': int(check.isna().sum()),
                                          'nonpositive_prices': int((check <= 0).sum())}
    (OUT / 'results.json').write_text(json.dumps(results, indent=2, allow_nan=False))
    for label, rows in results['windows'].items():
        print(label, {t: {k: round(v, 4) for k, v in row.items()
                         if k in ['ending_equity', 'cagr_net', 'drawdown_net']}
                      if 'error' not in row else row for t, row in rows.items()})
    print('rolling', results['rolling_36_months'])
    print('data checks', results['data_checks'])


if __name__ == '__main__':
    main()
