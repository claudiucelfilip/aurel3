"""Independently check saved fund curves using decimal cash accounting."""
import csv
from decimal import Decimal
import json
from pathlib import Path
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DATA = ROOT / 'data' / 'live_funds'
OUT = ROOT / 'data' / 'gold_grid' / 'results' / 'live_funds'


def main():
    protocol = json.loads((HERE / 'protocol.json').read_text())
    identities = json.loads((HERE / 'identity_notes.json').read_text())
    results = json.loads((OUT / 'results.json').read_text())
    worst_error = Decimal(0)
    observations, curves = 0, 0
    for window, (start, end) in protocol['comparisons'].items():
        for ticker, result in results['windows'][window].items():
            assert 'error' not in result, result
            resolved = identities.get(ticker, {}).get('history_symbol', ticker)
            with (DATA / f'{resolved}.csv').open() as f:
                records = [r for r in csv.DictReader(f) if start <= r['Date'] <= end]
            with (OUT / f'{window}_{ticker}.csv').open() as f:
                saved = list(csv.reader(f))[1:]
            assert len(records) == len(saved)
            prices = [Decimal(r['Adj Close']) for r in records]
            capital = Decimal(str(protocol['capital_usd']))
            cost = Decimal(str(protocol['entry_cost_fraction']))
            units = capital / (prices[0] * (1 + cost))
            cash = capital - units * prices[0] * (1 + cost)
            assert abs(cash) < Decimal('1e-20')
            peak, max_loss = capital, Decimal(0)
            for i, (record, stored) in enumerate(zip(records, saved)):
                assert record['Date'] == stored[0]
                value = cash + units * prices[i]
                if i == len(prices) - 1:
                    value *= 1 - Decimal(str(protocol['exit_cost_fraction']))
                peak = max(peak, value)
                max_loss = max(max_loss, 1 - value / peak)
                error = abs(value - Decimal(stored[1]))
                worst_error = max(error, worst_error)
                assert error < Decimal('0.000001')
                observations += 1
            assert abs(float(max_loss) - result['drawdown_net']) < 1e-12
            assert abs(float(value) - result['ending_equity']) < 1e-6
            curves += 1
    assert 'QRFT' in results['failures']
    assert not any('QRFT' in rows for rows in results['windows'].values())
    outcome = {'curves_recomputed': curves, 'daily_values_recomputed': observations,
               'largest_curve_error_usd': float(worst_error),
               'cash_accounting': 'Funded at entry; no borrowing or added capital.',
               'QRFT_data_failure_retained': True}
    archive = OUT / 'evidence.zip'
    if archive.exists():
        with zipfile.ZipFile(archive) as z:
            assert z.testzip() is None
            outcome['archive_crc'] = 'pass'
    (OUT / 'validation.json').write_text(json.dumps(outcome, indent=2))
    print(json.dumps(outcome, indent=2))


if __name__ == '__main__':
    main()
