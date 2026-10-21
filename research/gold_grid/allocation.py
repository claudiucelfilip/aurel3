"""Test the declared volatility-only ablation and extend to actual ETF history."""
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import shutil

import numpy as np
import pandas as pd

from redesign import Assumptions, OUT, ROOT, rolling_comparisons, simulate

PROTOCOL = Path('research/gold_grid/allocation_protocol.json')


def load_etfs():
    source = Path('/Users/claudiu/Sites/aurel3/data/multiasset')
    dest = ROOT/'etf_archive'
    dest.mkdir(exist_ok=True)
    manifest_path = dest/'manifest.json'
    if not manifest_path.exists():
        shutil.copy(source/'manifest.json',manifest_path)
    manifest = json.loads(manifest_path.read_text())
    result, hashes = {}, {}
    for name, prefix in [('SPY','spy'),('GLD','gold')]:
        path = dest/f'{name}.csv'
        if not path.exists():
            shutil.copy(source/path.name,path)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest == manifest['files'][path.name]['sha256']
        hashes[name] = digest
        raw = pd.read_csv(path,index_col=0,parse_dates=True)
        ratio = raw['Adj Close']/raw.Close
        for col in ['Open','Close','High','Low']:
            result[prefix+'_'+col.lower()] = raw[col]*ratio
    f = pd.DataFrame(result).dropna().loc[:'2026-10-16']
    assert f.index.is_unique and f.index.is_monotonic_increasing
    assert np.isfinite(f).all().all() and (f>0).all().all()
    f.to_csv(OUT/'allocation_etf_inputs.csv')
    return f, {'source':'Archived Yahoo Finance via yfinance; hashes match earlier manifest',
               'hashes':hashes,'first':str(f.index[0]),'last':str(f.index[-1]),'sessions':len(f)}


def audit(frame,curve,ledger,a):
    cash, q = a.capital, np.zeros(2)
    max_error = 0.0
    by_date = {x.date:x for x in ledger.itertuples()}
    for j,(date,row) in enumerate(curve.iterrows()):
        dt = 0 if j==0 else (date-curve.index[j-1]).days/365.25
        cash -= max(0,-cash)*a.annual_borrowing_cost*dt
        q[1] *= np.exp(-a.annual_gold_holding_cost*dt)
        fill = by_date.get(str(date.date()))
        if fill is not None:
            change = np.array([fill.spy_units,fill.gold_units])
            execution = np.array([fill.spy_price,fill.gold_price])
            cash -= change@execution+fill.fee
            q += change
        close = frame.loc[date,['spy_close','gold_close']].to_numpy(dtype=float)
        expected = cash+q@close*(1-a.cost_per_side)
        max_error = max(max_error,abs(expected-row.equity),abs(cash-row.cash),
                        float(np.abs(q-row[['spy_units','gold_units']].to_numpy()).max()))
    assert max_error<1e-6,max_error
    return {'sessions':len(curve),'trade_days':len(ledger),'max_error':max_error}


def main():
    p = json.loads(PROTOCOL.read_text())
    base_protocol = json.loads(Path('research/gold_grid/redesign_protocol.json').read_text())
    spot = pd.read_csv(OUT/'redesign_daily_inputs.csv',index_col=0,parse_dates=True)
    etf,quality = load_etfs()
    variants = p['variants']
    all_specs = variants+base_protocol['strategies']+base_protocol['controls']
    main_results,stress,neighbors,checks = {},[],[],{}
    curves = {}
    for dataset,frame,starts in [('spot',spot,[2020,2022]),('etf',etf,[2006,2020,2022])]:
        for spec in all_specs if dataset=='etf' else variants:
            a = Assumptions(target_volatility=spec.get('target_volatility',.15),
                            annual_gold_holding_cost=0 if dataset=='etf' else .004)
            for start in starts:
                key = f'{dataset}_{start}_{spec["name"]}'
                s,c,l = simulate(frame,spec,start,a)
                checks[key] = audit(frame,c,l,a)
                main_results[key] = s
                c.to_csv(OUT/f'allocation_{key}_daily.csv')
                l.to_csv(OUT/f'allocation_{key}_trades.csv',index=False)
                if dataset=='etf' and start==2006:
                    curves[spec['name']] = c
                print(key,round(s['ending_equity']),round(s['max_drawdown_daily']*100,1),flush=True)
                if spec in variants or spec['name'] in ('SPY','gold','mix_1p5x','mix_2x','diversified_trend_1p5x'):
                    for label,change in [('higher_costs',{'cost_per_side':.003,'annual_borrowing_cost':.1}),('one_session_delay',{'delay':1})]:
                        t,_,_ = simulate(frame,spec,start,replace(a,**change))
                        stress.append({'dataset':dataset,'stress':label,**t})
    old = {}
    for spec in all_specs:
        a = Assumptions(target_volatility=spec.get('target_volatility',.15),annual_gold_holding_cost=0)
        s,c,l = simulate(etf.loc[:'2019-12-31'],spec,2006,a)
        old[spec['name']] = s
        c.to_csv(OUT/f'allocation_old_{spec["name"]}_daily.csv')
    primary = next(s for s in variants if s['name']==p['display_candidate_before_results'])
    for lookback in [40,80]:
        for start in [2006,2020,2022]:
            a = Assumptions(volatility_sessions=lookback,annual_gold_holding_cost=0)
            s,_,_ = simulate(etf,primary,start,a)
            neighbors.append({'volatility_sessions':lookback,**s})
    result = {'protocol':p,'quality':quality,'main':main_results,'old_period':old,'stress':stress,
              'neighbors':neighbors,'verification':checks,
              'rolling':{str(m):rolling_comparisons(curves,m) for m in [24,36]}}
    (OUT/'allocation_results.json').write_text(json.dumps(result,indent=2,allow_nan=False))
    print('Saved',OUT/'allocation_results.json',flush=True)


if __name__=='__main__':
    main()
