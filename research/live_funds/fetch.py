"""Cache the declared live fund histories without changing any trading system."""
import hashlib
import json
from pathlib import Path
import pandas as pd
import yfinance as yf

HERE = Path(__file__).resolve().parent
DATA = HERE.parents[1] / 'data' / 'live_funds'


def main():
    protocol = json.loads((HERE / 'protocol.json').read_text())
    DATA.mkdir(parents=True, exist_ok=True)
    manifest = {'fetched_at': pd.Timestamp.now(tz='UTC').isoformat(),
                'protocol_sha256': hashlib.sha256((HERE / 'protocol.json').read_bytes()).hexdigest(),
                'yfinance_version': yf.__version__, 'files': {}, 'errors': {}}
    for ticker in protocol['candidates'] + protocol['benchmarks']:
        path = DATA / f'{ticker}.csv'
        try:
            if not path.exists():
                frame = yf.download(ticker, start=protocol['download_start'],
                                    end=protocol['end_exclusive'], auto_adjust=False,
                                    progress=False, threads=False)
                if frame.empty:
                    raise ValueError('No prices returned')
                if isinstance(frame.columns, pd.MultiIndex):
                    frame.columns = frame.columns.get_level_values(0)
                frame.to_csv(path)
            frame = pd.read_csv(path, index_col=0, parse_dates=True)
            manifest['files'][path.name] = {
                'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                'source': 'Yahoo Finance via yfinance', 'ticker': ticker,
                'first': str(frame.index.min().date()), 'last': str(frame.index.max().date()),
                'rows': len(frame)}
            print(ticker, manifest['files'][path.name], flush=True)
        except Exception as exc:
            manifest['errors'][ticker] = str(exc)
            print(ticker, type(exc).__name__, str(exc), flush=True)
    identities = json.loads((HERE / 'identity_notes.json').read_text())
    for original, info in identities.items():
        if not isinstance(info, dict):
            continue
        ticker = info.get('history_symbol')
        if ticker is None or ticker == original:
            continue
        path = DATA / f'{ticker}.csv'
        if not path.exists():
            frame = yf.download(ticker, start=protocol['download_start'],
                                end=protocol['end_exclusive'], auto_adjust=False,
                                progress=False, threads=False)
            if frame.empty:
                raise ValueError(f'No predecessor history for {original}')
            if isinstance(frame.columns, pd.MultiIndex):
                frame.columns = frame.columns.get_level_values(0)
            frame.to_csv(path)
        frame = pd.read_csv(path, index_col=0, parse_dates=True)
        manifest['files'][path.name] = {
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'source': 'Yahoo Finance via yfinance', 'ticker': ticker, 'predecessor': original,
            'first': str(frame.index.min().date()), 'last': str(frame.index.max().date()),
            'rows': len(frame)}
    manifest['identity_notes_sha256'] = hashlib.sha256((HERE / 'identity_notes.json').read_bytes()).hexdigest()
    (DATA / 'manifest.json').write_text(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    main()
