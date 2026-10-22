"""Cache inputs for the SPMO concentration diagnostic. Existing files are never replaced."""
import hashlib
import io
import json
import re
import time
import urllib.request
import zipfile
from pathlib import Path
import pandas as pd

HERE = Path(__file__).resolve().parent
DATA = HERE.parents[1] / 'data' / 'spmo_diagnostic'
UA = {'User-Agent': 'Aurel3-research personal-noncommercial admin@example.org'}
ETFS = ['SPYG', 'QQQ', 'RSP', 'IVV', 'XLK']
FRENCH = {
    'ff5_monthly.zip': 'https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Research_Data_5_Factors_2x3_CSV.zip',
    'mom_monthly.zip': 'https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Momentum_Factor_CSV.zip',
    'size_mom_6_monthly.zip': 'https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/6_Portfolios_ME_Prior_12_2_CSV.zip',
    'ff3_monthly.zip': 'https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Research_Data_Factors_CSV.zip',
}
SERIES = {'SPMO': ('S000050154', '1378872'), 'IVV': ('S000004310', '1100663')}


def get(url):
    time.sleep(0.15)
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        return r.read()


def cache(path, fetcher):
    if not path.exists():
        path.write_bytes(fetcher())
    return path


def nport_list(series):
    feed = get('https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK='
               f'{series}&type=NPORT-P&dateb=&owner=include&count=100&output=atom').decode()
    return re.findall(r'<accession-number>([^<]+)</accession-number>', feed)


def main():
    import yfinance as yf
    (DATA / 'nport').mkdir(parents=True, exist_ok=True)
    manifest = {'fetched_at': pd.Timestamp.now(tz='UTC').isoformat(), 'files': {}, 'errors': {}}
    for t in ETFS:
        path = DATA / f'{t}.csv'
        if not path.exists():
            f = yf.download(t, start='2013-01-01', end='2026-10-17', auto_adjust=False,
                            progress=False, threads=False)
            if isinstance(f.columns, pd.MultiIndex):
                f.columns = f.columns.get_level_values(0)
            f.to_csv(path)
    for name, url in FRENCH.items():
        try:
            cache(DATA / name, lambda: get(url))
        except Exception as exc:
            manifest['errors'][name] = repr(exc)
    for fund, (series, cik) in SERIES.items():
        for acc in nport_list(series):
            path = DATA / 'nport' / f'{fund}_{acc}.xml'
            if path.exists():
                continue
            # Filing archives sit under the registrant's CIK, even when an agent filed them.
            try:
                txt = get(f'https://www.sec.gov/Archives/edgar/data/{cik}/{acc}.txt').decode('latin1')
            except Exception as exc:
                manifest['errors'][path.name] = repr(exc)
                continue
            m = re.search(r'<XML>(.*?)</XML>', txt, re.S)
            if not m:
                manifest['errors'][path.name] = 'no XML in filing'
                continue
            path.write_text(m.group(1).strip())
    for path in sorted(DATA.rglob('*')):
        if path.is_file() and path.name != 'manifest.json':
            manifest['files'][str(path.relative_to(DATA))] = hashlib.sha256(path.read_bytes()).hexdigest()
    (DATA / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    print(len(manifest['files']), 'files;', 'errors:', manifest['errors'])


if __name__ == '__main__':
    main()
