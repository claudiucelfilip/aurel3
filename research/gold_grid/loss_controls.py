"""Evaluate the frozen loss-control variants without changing the baseline artifacts."""
from dataclasses import replace
from itertools import product
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from engine import Settings, simulate
from run import reconcile


ROOT = Path('data/gold_grid')
OUT = ROOT/'results'
PROTOCOL = Path('research/gold_grid/loss_control_protocol.json')


def save_curve(name,frame,result):
    pd.DataFrame({k:result[k] for k in ['equity','balance','quantity']},index=frame.index).resample('1D').last().ffill().to_csv(OUT/f'{name}_daily.csv')
    pd.DataFrame(result['cycles'],columns=['start_index','end_index','pnl','max_ounces','reason','seconds']).to_csv(OUT/f'{name}_cycles.csv',index=False)
    pd.DataFrame(result['ledger'],columns=['minute_index','kind','ounces','fill','balance','equity']).to_csv(OUT/f'{name}_ledger.csv.gz',index=False)


def main():
    frame = pd.read_parquet(ROOT/'XAUUSD_m1.parquet')
    protocol = json.loads(PROTOCOL.read_text())
    old = json.loads(Path('research/gold_grid/result_snapshot.json').read_text())
    consistency = {}
    for year,multiplier,path in product([2019,2022],[1.,2.],[0,1]):
        name = f'{year}_{"doubling" if multiplier==2 else "fixed"}_{"low_first" if path==0 else "high_first"}'
        result = simulate(frame.loc[f'{year}-01-01':],replace(Settings(),multiplier=multiplier,path=path))
        for key,expected in old['baseline'][name].items():
            if key == 'settings':
                continue
            actual = result['summary'][key]
            if isinstance(expected,(int,float)) and not isinstance(expected,bool):
                assert np.isclose(actual,expected,atol=1e-7,rtol=1e-12),(name,key,actual,expected)
            else:
                assert actual == expected,(name,key,actual,expected)
        consistency[name] = True
    print('All eight original baselines reproduced with disabled controls.',flush=True)
    summaries,checks = {},{}
    for year,multiplier,path in product([2019,2022],[1.,2.],[0,1]):
        subset = frame.loc[f'{year}-01-01':]
        for label,controls in protocol['main_variants'].items():
            name = f'controls_{year}_{"doubling" if multiplier==2 else "fixed"}_{"low_first" if path==0 else "high_first"}_{label}'
            settings = replace(Settings(),multiplier=multiplier,path=path,**controls)
            result = simulate(subset,settings,True)
            checks[name] = reconcile(subset,result,settings)
            summaries[name] = {'variant':label,'year':year,'mode':'doubling' if multiplier==2 else 'fixed',
                               'path':'low_first' if path==0 else 'high_first',**result['summary']}
            save_curve(name,subset,result)
            print(name,round(result['summary']['ending_equity'],2),round(100*result['summary']['max_drawdown'],2),
                  'batch stops',result['summary']['batch_loss_exits'],'margin exits',result['summary']['forced_liquidations'],flush=True)
    sensitivity = []
    grid = protocol['sensitivity']
    for multiplier,entries,loss,pause in product([1.,2.],grid['max_entries'],grid['batch_loss_fraction'],grid['cooldown_hours']):
        settings = replace(Settings(),multiplier=multiplier,max_entries=entries,
                           max_notional_multiple=grid['max_notional_multiple'],batch_loss_fraction=loss,cooldown_hours=pause)
        sensitivity.append(simulate(frame,settings)['summary'])
    stress = []
    for year,multiplier,path,label in product([2019,2022],[1.,2.],[0,1],protocol['cost_stress']['variants']):
        settings = replace(Settings(),multiplier=multiplier,path=path,
                           annual_financing=protocol['cost_stress']['annual_financing'],
                           slippage_per_ounce=protocol['cost_stress']['slippage_per_ounce'],
                           **protocol['main_variants'][label])
        stress.append({'variant':label,'year':year,'mode':'doubling' if multiplier==2 else 'fixed',
                       'path':'low_first' if path==0 else 'high_first',
                       **simulate(frame.loc[f'{year}-01-01':],settings)['summary']})
    payload = {'protocol':protocol,'protocol_sha256':hashlib.sha256(PROTOCOL.read_bytes()).hexdigest(),
               'baseline_consistency':consistency,'main':summaries,'verification':checks,
               'sensitivity':sensitivity,'cost_stress':stress,'benchmarks':old['benchmarks'],
               'baseline':old['baseline'],'data_quality':old['data_quality']}
    (OUT/'loss_controls.json').write_text(json.dumps(payload,indent=2))
    print('Saved',OUT/'loss_controls.json',flush=True)


if __name__=='__main__':
    main()
