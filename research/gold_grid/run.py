"""Run the declared baseline experiments and independently reconcile cash flows."""
from dataclasses import replace
from itertools import product
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from engine import Settings, simulate


def reconcile(frame, result, settings):
    ledger = result['ledger']
    dt = np.diff(frame.index.as_unit('s').asi8,prepend=frame.index.as_unit('s').asi8[0])
    previous_q = np.r_[0, result['quantity'][:-1]]
    previous_bid = np.r_[frame.bid_close.iloc[0], frame.bid_close.to_numpy()[:-1]]
    funding = np.cumsum(previous_q*previous_bid*settings.annual_financing*dt/(365.25*86400))
    assert np.isclose(funding[-1],result['summary']['financing'],atol=1e-6)
    cash, qty, basis, previous_funding = settings.capital, 0.0, 0.0, 0.0
    worst = 0.0
    for row in ledger:
        i, kind, amount, price, reported, _ = row
        i = int(i)
        cash -= funding[i]-previous_funding
        previous_funding = funding[i]
        if kind == 1:
            cash -= amount*settings.commission_per_ounce
            qty += amount
            basis += amount*price
        else:
            assert abs(qty+amount)<1e-7
            cash += qty*price-basis-qty*settings.commission_per_ounce
            qty, basis = 0.0, 0.0
        worst = max(worst,abs(cash-reported))
    cash -= funding[-1]-previous_funding
    final_nav = cash+qty*(frame.bid_close.iloc[-1]-settings.slippage_per_ounce-settings.commission_per_ounce)-basis
    assert np.isclose(final_nav,result['summary']['ending_equity'],atol=1e-6)
    assert worst<1e-6, worst
    assert np.isclose(sum(c[2] for c in result['cycles']),final_nav-settings.capital,atol=1e-6)
    return {'ledger_entries':len(ledger),'maximum_cash_error':worst,
            'final_equity_error':abs(final_nav-result['summary']['ending_equity']),
            'funding_error':abs(funding[-1]-result['summary']['financing'])}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data',default='data/gold_grid')
    parser.add_argument('--spy',required=True)
    args = parser.parse_args()
    root = Path(args.data)
    out = root/'results'
    out.mkdir(exist_ok=True)
    frame = pd.read_parquet(root/'XAUUSD_m1.parquet')
    spy_data = json.loads(Path(args.spy).read_text())['bars']['SPY']
    spy_times = pd.to_datetime([x['t'] for x in spy_data],utc=True)
    # Daily bars are stamped at midnight, but their closing prices are not yet known then.
    close_times = (spy_times.tz_convert('America/New_York').normalize()+pd.Timedelta(hours=16)).tz_convert('UTC')
    spy = pd.Series([x['c'] for x in spy_data],index=close_times)
    summaries, verification, curves = {}, {}, {}
    base = Settings()
    for year in [2019,2022]:
        subset = frame.loc[f'{year}-01-01':]
        for multiplier,path in product([2.0,1.0],[0,1]):
            name = f'{year}_{"doubling" if multiplier==2 else "fixed"}_{"low_first" if path==0 else "high_first"}'
            s = replace(base,multiplier=multiplier,path=path)
            result = simulate(subset,s,True)
            summaries[name] = result['summary']
            verification[name] = reconcile(subset,result,s)
            series = pd.DataFrame({k:result[k] for k in ['equity','balance','quantity']},index=subset.index)
            series.resample('1D').last().ffill().to_csv(out/f'{name}_daily.csv')
            pd.DataFrame(result['cycles'],columns=['start_index','end_index','pnl','max_ounces','reason','seconds']).to_csv(out/f'{name}_cycles.csv',index=False)
            pd.DataFrame(result['ledger'],columns=['minute_index','kind','ounces','fill','balance','equity']).to_csv(out/f'{name}_ledger.csv.gz',index=False)
            curves[name] = series.equity.resample('1D').last().ffill()
            print(name, json.dumps(result['summary']),flush=True)
    sensitivity = []
    for size,gap,target,multiplier in product([.1,.5,1.0],[5.,10.,20.],[.5,1.,2.],[1.,2.]):
        s = replace(base,initial_ounces=size,grid_dollars=gap,target_dollars=target,multiplier=multiplier)
        sensitivity.append(simulate(frame,s)['summary'])
    stress = []
    for multiplier in [1.,2.]:
        for label,change in [('zero_financing',{'annual_financing':0.}),('ten_percent_financing',{'annual_financing':.1}),
                             ('triple_slippage',{'slippage_per_ounce':.15}),('leverage_10',{'leverage':10.}),
                             ('leverage_100',{'leverage':100.})]:
            s = replace(base,multiplier=multiplier,**change)
            stress.append({'label':label,**simulate(frame,s)['summary']})
    starts = []
    for year,multiplier in product(range(2019,2027),[1.,2.]):
        starts.append({'start_year':year,**simulate(frame.loc[f'{year}-01-01':],replace(base,multiplier=multiplier))['summary']})
    benchmarks = {}
    for year in [2019,2022]:
        f = frame.loc[f'{year}-01-01':]
        sg = spy[(spy.index>=f.index[0])&(spy.index<=f.index[-1])]
        gold = f.bid_close.resample('1D').last().dropna()
        for name,series in [('SPY',sg),('gold',gold)]:
            initial = f.ask_open.iloc[0] if name=='gold' else series.iloc[0]
            nav = series/initial*base.capital
            nav.to_csv(out/f'{year}_{name}_daily.csv',header=['equity'])
            years = (series.index[-1]-series.index[0]).total_seconds()/(365.25*86400)
            benchmarks[f'{year}_{name}'] = {'total_return':float(nav.iloc[-1]/base.capital-1),
                    'cagr':float((nav.iloc[-1]/base.capital)**(1/years)-1),
                    'max_drawdown_daily':float((1-nav/nav.cummax()).max()),
                    'ending_equity':float(nav.iloc[-1]),'first_timestamp':str(series.index[0]),'last_timestamp':str(series.index[-1])}
    payload = {'baseline':summaries,'benchmarks':benchmarks,'sensitivity':sensitivity,
               'stress':stress,'fresh_starts':starts,'verification':verification,
               'data_quality':json.loads((root/'quality.json').read_text()),
               'protocol_sha256':hashlib.sha256(Path('research/gold_grid/protocol.json').read_bytes()).hexdigest(),
               'spy_sha256':hashlib.sha256(Path(args.spy).read_bytes()).hexdigest()}
    (out/'results.json').write_text(json.dumps(payload,indent=2))
    print('Saved',out/'results.json',flush=True)


if __name__=='__main__':
    main()
