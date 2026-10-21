"""Adaptive second round: activate trailing exits at fixed profit milestones."""
from dataclasses import replace
from itertools import product
import hashlib
import json
from pathlib import Path

import pandas as pd

from engine import Settings, simulate
from loss_controls import save_curve
from run import reconcile


def main():
    protocol_file = Path('research/gold_grid/profit_lock_protocol.json')
    protocol = json.loads(protocol_file.read_text())
    frame = pd.read_parquet('data/gold_grid/XAUUSD_m1.parquet')
    summaries,checks = {},{}
    for year,multiplier,path,activation,drawdown in product([2019,2022],[1.,2.],[0,1],
            protocol['activation_multiples'],protocol['trailing_drawdown_fractions']):
        subset = frame.loc[f'{year}-01-01':]
        mode = 'doubling' if multiplier==2 else 'fixed'
        order = 'low_first' if path==0 else 'high_first'
        name = f'profit_lock_{year}_{mode}_{order}_{activation:g}_{drawdown:g}'
        settings = replace(Settings(),multiplier=multiplier,path=path,
                           account_drawdown_fraction=drawdown,drawdown_activation_multiple=activation)
        result = simulate(subset,settings,True)
        summaries[name] = {'year':year,'mode':mode,'path':order,**result['summary']}
        checks[name] = reconcile(subset,result,settings)
        save_curve(name,subset,result)
        print(name,round(result['summary']['ending_equity'],2),round(result['summary']['max_drawdown']*100,2),
              result['summary']['stop_reason'],result['summary']['stopped_at'],flush=True)
    payload = {'protocol':protocol,'protocol_sha256':hashlib.sha256(protocol_file.read_bytes()).hexdigest(),
               'main':summaries,'verification':checks}
    Path('data/gold_grid/results/profit_locks.json').write_text(json.dumps(payload,indent=2))
    print('Saved profit_locks.json',flush=True)


if __name__=='__main__':
    main()
