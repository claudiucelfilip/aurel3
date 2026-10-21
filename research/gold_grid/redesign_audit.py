"""Reconcile saved research curves and add requested 2019 and funding diagnostics."""
from dataclasses import replace
import json

import numpy as np
import pandas as pd

from allocation import audit, load_etfs
from redesign import Assumptions, OUT, PROTOCOL, simulate


def main():
    base = json.loads(PROTOCOL.read_text())
    second = json.loads((OUT/'allocation_results.json').read_text())
    spot = pd.read_csv(OUT/'redesign_daily_inputs.csv',index_col=0,parse_dates=True)
    etf,_ = load_etfs()
    specs = base['strategies']+base['controls']+second['protocol']['variants']
    checks, extra, costs = {},{},[]
    for start in [2020,2022]:
        for spec in base['strategies']+base['controls']:
            key = f'{start}_{spec["name"]}'
            curve = pd.read_csv(OUT/f'redesign_{key}_daily.csv',index_col=0,parse_dates=True)
            ledger = pd.read_csv(OUT/f'redesign_{key}_trades.csv')
            checks[key] = audit(spot,curve,ledger,Assumptions())
    for spec in specs:
        a = Assumptions(annual_gold_holding_cost=0,target_volatility=spec.get('target_volatility',.15))
        s,c,l = simulate(etf,spec,2019,a)
        extra[spec['name']] = s
        c.to_csv(OUT/f'allocation_etf_2019_{spec["name"]}_daily.csv')
        l.to_csv(OUT/f'allocation_etf_2019_{spec["name"]}_trades.csv',index=False)
        checks[f'etf_2019_{spec["name"]}'] = audit(etf,c,l,a)
        if spec['name'] in ['mix_1p5x','balanced_vol20_1p5x']:
            for start in [2006,2019,2022]:
                for rate in [.025,.05,.075,.10]:
                    s,_,_ = simulate(etf,spec,start,replace(a,annual_borrowing_cost=rate))
                    costs.append({'borrowing_rate':rate,**s})
    aligned = spot[['spy_close','gold_close']].join(etf[['spy_close','gold_close']],lsuffix='_spot',rsuffix='_etf').dropna()
    cross = {}
    for asset in ['spy','gold']:
        x,y = aligned[f'{asset}_close_spot'],aligned[f'{asset}_close_etf']
        cross[asset] = {'daily_return_correlation':float(x.pct_change().corr(y.pct_change())),
                        'spot_total_return':float(x.iloc[-1]/x.iloc[0]-1),
                        'etf_total_return':float(y.iloc[-1]/y.iloc[0]-1)}
    payload = {'verification':checks,'additional_2019_results':extra,'funding_diagnostic':costs,
               'cross_source':cross,
               'disclosure':'2019 and funding diagnostic added after both rounds; no new strategy selected or tuned.'}
    (OUT/'redesign_audit.json').write_text(json.dumps(payload,indent=2,allow_nan=False))
    print('Reconciled',len(checks),'curves;',sum(v['trade_days'] for v in checks.values()),'trade days; max error',max(v['max_error'] for v in checks.values()))
    print('Cross-source check',cross)
    for x in costs:
        if x['start']==2022:
            print(x['name'],x['borrowing_rate'],round(x['ending_equity']),round(x['max_drawdown_daily']*100,1))


if __name__=='__main__':
    main()
