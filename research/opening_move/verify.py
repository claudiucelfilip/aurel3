"""Independently reconcile trade cash flows and audit timing and data coverage."""
import hashlib
import json
from pathlib import Path
import pandas as pd

HERE=Path(__file__).resolve().parent
DATA=HERE.parents[1]/'data'/'opening_move'
OUT=DATA/'results'


def main():
    manifest=json.loads((DATA/'manifest.json').read_text())
    for name,checksum in manifest['files'].items():
        assert hashlib.sha256((DATA/name).read_bytes()).hexdigest()==checksum,name
    max_error=0.;n=0
    for file in sorted(OUT.glob('*_trades.csv')):
        if file.name=='baseline_all_years.csv':continue
        trades=pd.read_csv(file)
        fee=.0001 if file.name.startswith('double_cost') else .00005
        for row in trades.itertuples():
            capital=25000.;qty=capital*row.weight/row.entry
            cash=capital-row.direction*qty*row.entry-qty*row.entry*fee
            cash+=row.direction*qty*row.exit-qty*row.exit*fee
            if row.direction<0:cash-=qty*row.entry*(.02/252)
            error=abs((cash/capital-1)-row.net_return)
            max_error=max(max_error,error)
            assert error<1e-12
            entry=pd.Timestamp(row.entry_time);exit=pd.Timestamp(row.exit_time)
            assert entry<=exit
            assert entry.tz_convert('America/New_York').date()==exit.tz_convert('America/New_York').date()
            assert row.weight<=1.0000000001
            n+=1
    models=json.loads((OUT/'model_audit.json').read_text())
    for m in models:
        if m['status']=='trained':assert m['last_training_day']<f'{m["year"]}-01-01'
    report=json.loads((OUT/'report.json').read_text())
    assert report['selection']==json.loads((OUT/'selection.json').read_text())['variant']
    coverage=json.loads((OUT/'coverage.json').read_text())
    missing=[x for x in coverage if x['missing_minutes']]
    validation={'data_fingerprints_passed':len(manifest['files']),'trade_cashflow_checks':n,
                'max_return_reconciliation_error':max_error,'chronological_model_training':'passed',
                'same_session_exits':'passed','position_cap':'passed','missing_session_details':missing}
    (OUT/'verification.json').write_text(json.dumps(validation,indent=2))
    print({k:v for k,v in validation.items() if k!='missing_session_details'})
    print('Missing-bar sessions:',len(missing),'worst:',sorted(missing,key=lambda x:x['missing_minutes'],reverse=True)[:8])

if __name__=='__main__':main()
