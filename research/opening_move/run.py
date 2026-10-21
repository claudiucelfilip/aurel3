"""Run fixed research variants, lock development selection, then evaluate."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
import exchange_calendars as xc
from engine import Costs, equity_stats, prepare, simulate_trade, walk_forward_predictions

HERE=Path(__file__).resolve().parent
DATA=HERE.parents[1]/'data'/'opening_move'
OUT=DATA/'results'
VARIANTS=['baseline','strength','volume','timeout','ml_filter']
WINDOWS={'development':('2019-01-01','2021-12-31'),'validation':('2022-01-01','2024-12-31'),
         'final':('2025-01-01','2026-10-20'),'recent':('2022-01-01','2026-10-20'),
         'full':('2019-01-01','2026-10-20')}


def load():
    parts=[pd.read_csv(p,parse_dates=['timestamp']) for p in sorted(DATA.glob('QQQ_*_1min.csv.gz'))]
    raw=pd.concat(parts,ignore_index=True);raw['timestamp']=pd.to_datetime(raw.timestamp,utc=True)
    schedule=xc.get_calendar('XNYS',start='2016-01-01',end='2026-10-21').schedule.loc['2016-01-01':'2026-10-20']
    groups,setups,coverage=prepare(raw.set_index('timestamp'),schedule)
    (OUT/'coverage.json').write_text(json.dumps(coverage,indent=2))
    setups.to_csv(OUT/'setups.csv')
    return groups,setups,schedule,coverage


def trades_for(groups,setups,costs,delay=0,timeout=False):
    rows=[]
    for date,s in setups.iterrows():
        t=simulate_trade(groups[date],s,costs,delay=delay,timeout=timeout)
        if t is not None:rows.append({'date':date,**t})
    return pd.DataFrame(rows).set_index('date')


def choose_mask(name,setups,predictions):
    if name in ['baseline','timeout']:
        return pd.Series(True,index=setups.index)
    if name=='strength':
        return (setups.opening_body_fraction>=.5)&(setups.ema_distance_atr>=.25)
    if name=='volume':
        return setups.relative_open_volume>=1
    return predictions>.05


def summarize(trades,dates):
    rr=trades.net_return.reindex(dates,fill_value=0.)
    stats=equity_stats(rr)
    stats['dates']=['start',*dates]
    stats.update({'trades':len(trades),'trades_per_week':len(trades)/(len(dates)/5),
                  'win_rate':float((trades.net_return>0).mean()) if len(trades) else None,
                  'mean_minutes_held':float(trades.minutes_held.mean()) if len(trades) else None,
                  'average_notional_fraction':float(trades.weight.mean()) if len(trades) else None,
                  'costs_fixed_capital_fraction':float(trades.cost_return.sum())})
    return stats


def benchmark(symbol,dates,cost_multiplier=1):
    d=json.loads((DATA/f'{symbol}_daily_adjusted.json').read_text())
    frame=pd.DataFrame(d['bars'][symbol]);frame['date']=pd.to_datetime(frame.t,utc=True).dt.tz_convert('America/New_York').dt.strftime('%Y-%m-%d')
    frame=frame.set_index('date').loc[dates]
    ret=frame.c.pct_change();ret.iloc[0]=frame.c.iloc[0]/frame.o.iloc[0]-1
    ret.iloc[0]=(1+ret.iloc[0])/(1+.00025*cost_multiplier)-1
    ret.iloc[-1]=(1+ret.iloc[-1])*(1-.00025*cost_multiplier)-1
    stats=equity_stats(ret);stats['dates']=['start',*dates]
    return stats


def attribution(base,variant):
    gross=variant.gross_return.reindex(base.index,fill_value=0.)
    winners=base.gross_return>0;losers=base.gross_return<0
    wins=float(base.loc[winners,'gross_return'].sum());loss=float(-base.loc[losers,'gross_return'].sum())
    return {'winning_profit_retained':float(gross.loc[winners].sum()/wins) if wins else None,
            'losing_profit_avoided':float(1+gross.loc[losers].sum()/loss) if loss else None,
            'fixed_capital_attribution':True}


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    print('Preparing sessions and causal features',flush=True)
    groups,setups,schedule,coverage=load()
    print(f'{len(groups)} sessions; {len(setups)} usable signals',flush=True)
    base=trades_for(groups,setups,Costs());base.to_csv(OUT/'baseline_all_years.csv')
    predictions,model_audit=walk_forward_predictions(base,setups)
    predictions.to_csv(OUT/'ml_predictions.csv',header=['predicted_net_R'])
    (OUT/'model_audit.json').write_text(json.dumps(model_audit,indent=2))
    masks={v:choose_mask(v,setups,predictions) for v in VARIANTS}
    timeout=trades_for(groups,setups,Costs(),timeout=True)
    base_trades={v:(timeout if v=='timeout' else base).loc[lambda x:masks[v].reindex(x.index,fill_value=False)] for v in VARIANTS}
    dates=schedule.index.strftime('%Y-%m-%d').tolist()
    dev_dates=[d for d in dates if '2019-01-01'<=d<='2021-12-31']
    dev={v:summarize(t.loc[t.index.isin(dev_dates)],dev_dates) for v,t in base_trades.items()}
    eligible=[v for v in VARIANTS if v!='baseline' and dev[v]['cagr']>=dev['baseline']['cagr'] and dev[v]['max_drawdown']>dev['baseline']['max_drawdown']]
    chosen=max(eligible,key=lambda v:dev[v]['cagr']) if eligible else 'baseline'
    selection={'variant':chosen,'chosen_at':datetime.now(timezone.utc).isoformat(),'development_metrics':dev,
               'protocol_sha256':hashlib.sha256((HERE/'protocol.json').read_bytes()).hexdigest(),
               'reason':'Highest development CAGR among modifiers meeting baseline return and lower drawdown; otherwise baseline.'}
    (OUT/'selection.json').write_text(json.dumps(selection,indent=2))
    print(f'Development selection locked: {chosen}',flush=True)
    all_trades={'base':base_trades}
    for scenario,costs,delay in [('double_cost',Costs(.0004,.0001,.02/252),0),('delay_1min',Costs(),1)]:
        b=trades_for(groups,setups,costs,delay=delay)
        tm=trades_for(groups,setups,costs,delay=delay,timeout=True)
        all_trades[scenario]={v:(tm if v=='timeout' else b).loc[lambda x:masks[v].reindex(x.index,fill_value=False)] for v in VARIANTS}
    report={'selection':chosen,'windows':{},'coverage_summary':{'sessions':len(coverage),
            'missing_bar_sessions':sum(c['missing_minutes']>0 for c in coverage),
            'total_missing_minutes':sum(c['missing_minutes'] for c in coverage),
            'usable_signals':len(setups),'executed_baseline_trades':len(base)},'model_audit':model_audit}
    rows=[]
    for name,(start,end) in WINDOWS.items():
        ds=[d for d in dates if start<=d<=end]
        report['windows'][name]={'start':ds[0],'end':ds[-1],'scenarios':{},'benchmarks':{s:benchmark(s,ds) for s in ['SPY','QQQ']}}
        for scenario,variants in all_trades.items():
            values={}
            b=variants['baseline'].loc[lambda x:x.index.isin(ds)]
            for v,t in variants.items():
                subset=t.loc[t.index.isin(ds)]
                m=summarize(subset,ds);m.update(attribution(b,subset))
                values[v]=m
                rows.append({'window':name,'scenario':scenario,'variant':v,**{k:x for k,x in m.items() if k not in ['equity','dates']}})
            report['windows'][name]['scenarios'][scenario]=values
    gates={}
    for window in ['recent','final']:
        w=report['windows'][window];s=w['scenarios']['base'][chosen];b=w['scenarios']['base']['baseline'];spy=w['benchmarks']['SPY']
        gates[window]={
            'retains_90pct_winning_profit':s['winning_profit_retained']>=.9,
            'avoids_25pct_losing_profit':s['losing_profit_avoided']>=.25,
            'reduces_drawdown_20pct':abs(s['max_drawdown'])<=.8*abs(b['max_drawdown']),
            'retains_baseline_cagr':s['cagr']>=b['cagr'],
            'beats_spy_3pp':s['cagr']>=spy['cagr']+.03,
            'drawdown_no_worse_than_spy':s['max_drawdown']>=spy['max_drawdown'],
            'stress_returns_above_spy':all(w['scenarios'][c][chosen]['cagr']>spy['cagr'] for c in ['double_cost','delay_1min'])}
    report['gates']=gates;report['qualifies']=all(all(g.values()) for g in gates.values())
    for scenario,vs in all_trades.items():
        for v,t in vs.items():t.to_csv(OUT/f'{scenario}_{v}_trades.csv')
    pd.DataFrame(rows).to_csv(OUT/'summary.csv',index=False)
    (OUT/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    for window in ['development','validation','final','recent']:
        w=report['windows'][window];print(window,flush=True)
        for v,m in w['scenarios']['base'].items():
            print(v,'CAGR',round(m['cagr']*100,2),'DD',round(m['max_drawdown']*100,2),'trades',m['trades'],flush=True)
        print('SPY',round(w['benchmarks']['SPY']['cagr']*100,2),'QQQ',round(w['benchmarks']['QQQ']['cagr']*100,2),flush=True)
    print('Qualifies:',report['qualifies'],flush=True)

if __name__=='__main__':
    main()
