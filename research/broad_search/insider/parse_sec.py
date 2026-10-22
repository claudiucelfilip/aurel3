"""Extract officer/director open-market purchases (Forms 4/5, code P) from SEC zips -> purchases.parquet."""
import re
import zipfile
from pathlib import Path
import numpy as np
import pandas as pd

DATA = Path(__file__).resolve().parents[3] / 'data' / 'broad_search' / 'insider'
SYM = re.compile(r'^[A-Z]{1,5}([.-][A-Z])?$')


def read(z, name, cols):
    with z.open(name) as f:
        return pd.read_csv(f, sep='\t', usecols=cols, dtype=str, quoting=3, keep_default_na=False,
                           on_bad_lines='skip', encoding='latin-1')


def one(path):
    z = zipfile.ZipFile(path)
    sub = read(z, 'SUBMISSION.tsv', ['ACCESSION_NUMBER', 'FILING_DATE', 'DOCUMENT_TYPE', 'ISSUERCIK',
                                     'ISSUERTRADINGSYMBOL'])
    sub = sub[sub['DOCUMENT_TYPE'].str.strip().isin(['4', '5'])]
    tr = read(z, 'NONDERIV_TRANS.tsv', ['ACCESSION_NUMBER', 'TRANS_CODE', 'TRANS_SHARES',
                                        'TRANS_PRICEPERSHARE', 'TRANS_ACQUIRED_DISP_CD'])
    tr = tr[(tr['TRANS_CODE'].str.strip() == 'P') & (tr['TRANS_ACQUIRED_DISP_CD'].str.strip() == 'A')]
    tr = tr.assign(shares=pd.to_numeric(tr['TRANS_SHARES'], errors='coerce'),
                   price=pd.to_numeric(tr['TRANS_PRICEPERSHARE'], errors='coerce'))
    n_p = len(tr)
    tr = tr[(tr['shares'] > 0) & (tr['price'] > 0)]
    tr = tr.assign(value=tr['shares'] * tr['price']).groupby('ACCESSION_NUMBER', as_index=False)['value'].sum()
    own = read(z, 'REPORTINGOWNER.tsv', ['ACCESSION_NUMBER', 'RPTOWNERCIK', 'RPTOWNER_RELATIONSHIP'])
    od = own[own['RPTOWNER_RELATIONSHIP'].str.contains('Officer|Director', case=False, regex=True)]
    od = od.groupby('ACCESSION_NUMBER', as_index=False)['RPTOWNERCIK'].min().rename(columns={'RPTOWNERCIK': 'insider'})
    m = tr.merge(sub, on='ACCESSION_NUMBER').merge(od, on='ACCESSION_NUMBER')
    m['filing_date'] = pd.to_datetime(m['FILING_DATE'], format='%d-%b-%Y', errors='coerce')
    m['symbol_raw'] = m['ISSUERTRADINGSYMBOL'].str.strip().str.upper()
    ok = m['symbol_raw'].str.match(SYM)
    m['ticker'] = np.where(ok, m['symbol_raw'].str.replace('.', '-', regex=False), '')
    stats = {'file': path.name, 'p_rows': n_p, 'od_filings': len(m), 'unmappable_filings': int((~ok).sum())}
    return m[['ACCESSION_NUMBER', 'filing_date', 'ISSUERCIK', 'symbol_raw', 'ticker', 'insider', 'value']], stats


def main():
    frames, stats = [], []
    for p in sorted((DATA / 'sec_zips').glob('*_form345.zip')):
        f, s = one(p)
        frames.append(f)
        stats.append(s)
        print(s, flush=True)
    df = pd.concat(frames).drop_duplicates('ACCESSION_NUMBER').dropna(subset=['filing_date'])
    df.to_parquet(DATA / 'purchases.parquet')
    pd.DataFrame(stats).to_csv(DATA / 'parse_stats.csv', index=False)
    print(len(df), 'officer/director purchase filings', df['filing_date'].min(), df['filing_date'].max())


if __name__ == '__main__':
    main()
