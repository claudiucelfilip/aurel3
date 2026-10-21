"""Causal daily research on bounded dip buying and trend portfolios."""
from dataclasses import dataclass, replace
from pathlib import Path
import hashlib
import json

import numpy as np
import pandas as pd

ROOT = Path('data/gold_grid')
OUT = ROOT / 'results'
PROTOCOL = Path('research/gold_grid/redesign_protocol.json')


@dataclass(frozen=True)
class Assumptions:
    capital: float = 10000.0
    trend_sessions: int = 200
    volatility_sessions: int = 60
    target_volatility: float = .15
    cost_per_side: float = .001
    annual_borrowing_cost: float = .05
    annual_gold_holding_cost: float = .004
    delay: int = 0


def quote_indices(index, times):
    return np.searchsorted(index.as_unit('ns').asi8, times.as_unit('ns').asi8, side='right')-1


def load_daily():
    gold = pd.read_parquet(ROOT / 'XAUUSD_m1.parquet')
    raw = json.loads((ROOT / 'SPY_daily_adjusted.json').read_text())['bars']['SPY']
    spy = pd.DataFrame(raw)
    dates = pd.to_datetime(spy.t, utc=True).dt.tz_convert('America/New_York').dt.date
    local = pd.DatetimeIndex(dates).tz_localize('America/New_York')
    opens = (local + pd.Timedelta(hours=9, minutes=30)).tz_convert('UTC')
    closes = (local + pd.Timedelta(hours=16)).tz_convert('UTC')
    clock = gold.index.as_unit('ns').asi8
    oi = quote_indices(gold.index, opens)
    ci = quote_indices(gold.index, closes)
    rows, excluded = [], []
    mid_open = (gold.bid_open + gold.ask_open).to_numpy() / 2
    mid_high = (gold.bid_high + gold.ask_high).to_numpy() / 2
    mid_low = (gold.bid_low + gold.ask_low).to_numpy() / 2
    for k in range(len(spy)):
        if opens[k] < gold.index[0] or closes[k] > gold.index[-1]:
            continue
        ages = [(opens[k].value-clock[oi[k]])/1e9, (closes[k].value-clock[ci[k]])/1e9]
        assert min(ages) >= 0, 'A sampled quote comes from the future'
        if max(ages) > 300:
            excluded.append({'date':str(dates.iloc[k]), 'quote_age_seconds':ages})
            continue
        prev = np.searchsorted(clock, closes[k-1].value, side='left') if k else oi[k]
        rows.append({'date':str(dates.iloc[k]), 'gold_open':mid_open[oi[k]],
                     'gold_close':mid_open[ci[k]], 'gold_high':mid_high[prev:ci[k]].max(),
                     'gold_low':mid_low[prev:ci[k]].min(), 'spy_open':spy.o.iloc[k],
                     'spy_close':spy.c.iloc[k], 'open_utc':str(opens[k]), 'close_utc':str(closes[k])})
    frame = pd.DataFrame(rows).set_index('date')
    frame.index = pd.to_datetime(frame.index)
    assert frame.index.is_monotonic_increasing and frame.index.is_unique
    assert np.isfinite(frame.select_dtypes('number')).all().all()
    assert frame.gold_close.nunique() > .9*len(frame)
    frame.to_csv(OUT / 'redesign_daily_inputs.csv')
    return frame, {'first':str(frame.index[0]), 'last':str(frame.index[-1]),
                   'sessions':len(frame), 'excluded_stale_sessions':excluded,
                   'spy_sha256':hashlib.sha256((ROOT / 'SPY_daily_adjusted.json').read_bytes()).hexdigest(),
                   'gold_sha256':hashlib.sha256((ROOT / 'XAUUSD_m1.parquet').read_bytes()).hexdigest()}


def signals(frame, spec, a=Assumptions()):
    prices = frame[['spy_close', 'gold_close']].to_numpy()
    p = pd.DataFrame(prices, index=frame.index)
    ret = p.pct_change()
    ma = p.rolling(a.trend_sessions).mean().to_numpy()
    vol = ret.rolling(a.volatility_sessions).std().to_numpy()*np.sqrt(252)
    mom = p.pct_change(126).to_numpy()
    tr = np.maximum(frame.gold_high-frame.gold_low,
                    np.maximum(abs(frame.gold_high-frame.gold_close.shift()),
                               abs(frame.gold_low-frame.gold_close.shift())))
    atr = tr.rolling(20).mean().to_numpy()
    cov = ret.rolling(a.volatility_sessions).cov().to_numpy().reshape(len(frame), 2, 2)*252
    weights = np.zeros((len(frame), 2))
    valid = np.isfinite(ma).all(axis=1) & np.isfinite(vol).all(axis=1)
    for i in range(len(frame)):
        family, cap = spec['family'], spec['cap']
        if family in ('hold_spy', 'lever_spy'):
            weights[i] = [cap, 0]
        elif family in ('hold_gold', 'lever_gold'):
            weights[i] = [0, cap]
        elif family == 'mix':
            weights[i] = cap/2
        elif valid[i]:
            positive = prices[i] > ma[i]
            if family in ('gold_trend', 'gold_vol'):
                weights[i, 1] = float(positive[1])
            elif family in ('diversified','balanced_vol'):
                eligible = positive if family == 'diversified' else np.ones(2)
                inv = eligible / np.maximum(vol[i], .01)
                if inv.sum() > 0:
                    weights[i] = inv / inv.sum()
            elif family == 'relative':
                eligible = np.where(positive, mom[i], -np.inf)
                if np.isfinite(eligible).any():
                    weights[i, np.argmax(eligible)] = 1
            if family in ('gold_vol', 'diversified', 'relative','balanced_vol') and weights[i].sum() > 0:
                risk = float(np.sqrt(max(0, weights[i] @ cov[i] @ weights[i])))
                weights[i] *= min(cap, a.target_volatility / max(risk, .01))
            elif family == 'gold_trend':
                weights[i] *= cap
    return weights, ma, atr


def trade_to_weights(cash, units, prices, weights, cost_rate):
    nav = cash + units @ prices
    post = nav
    for _ in range(40):
        desired = weights * post / prices
        cost = np.abs((desired-units)*prices).sum()*cost_rate
        post = nav-cost
    desired = weights * post / prices
    turnover = np.abs((desired-units)*prices).sum()
    cost = turnover*cost_rate
    next_cash = cash - (desired-units) @ prices-cost
    assert abs(next_cash+desired@prices-(nav-cost)) < 1e-7
    return next_cash, desired, cost, turnover


def simulate(frame, spec, start=2020, a=Assumptions(), weights_override=None):
    if spec['family']=='dip' and a.delay:
        raise ValueError('Stateful dip latency requires a pending-order model; this stress is excluded.')
    weights, ma, atr = signals(frame, spec, a)
    if weights_override is not None:
        weights = weights_override
    opens = frame[['spy_open','gold_open']].to_numpy()
    closes = frame[['spy_close','gold_close']].to_numpy()
    dates = frame.index
    first = int(np.searchsorted(dates.year, start))
    cash, units = a.capital, np.zeros(2)
    rows, ledger = [], []
    fees = funding = holding = turnover_total = 0.0
    last_week = last_month = None
    entered = False
    batch_cash, batch_atr, last_entry = a.capital, 0.0, 0.0
    tranches, reenter = 0, first
    stopped = False
    for i in range(first, len(frame)):
        dt = 0 if i == first else (dates[i]-dates[i-1]).days/365.25
        borrow = max(0, -cash)*a.annual_borrowing_cost*dt
        cash -= borrow
        funding += borrow
        old_gold = units[1]
        units[1] *= np.exp(-a.annual_gold_holding_cost*dt)
        hold = (old_gold-units[1])*closes[i-1,1] if i > first else 0
        holding += hold
        scheduled = i-a.delay
        schedule_ready = scheduled >= first
        prev = scheduled-1
        nav_open = cash+units@opens[i]
        week = tuple(dates[max(0,scheduled)].isocalendar()[:2])
        month = (dates[max(0,scheduled)].year, dates[max(0,scheduled)].month)
        family = spec['family']
        target = None
        reason = ''
        if nav_open <= 0:
            stopped = True
            target, reason = np.zeros(2), 'insolvent'
        elif not stopped and schedule_ready and prev >= 0:
            if family == 'dip':
                good = np.isfinite(ma[prev,1]) and closes[prev,1] > ma[prev,1]
                prior_nav = rows[prev-first]['equity'] if prev >= first else a.capital
                if units[1] > 0:
                    profit = (prior_nav-batch_cash)/units[1]
                    loss_stop = prior_nav <= batch_cash*.95
                    take = spec.get('take_profit_atr', 0) > 0 and profit >= batch_atr*spec['take_profit_atr']
                    if not good or loss_stop or take:
                        target, reason = np.zeros(2), 'dip_exit'
                        if prior_nav < batch_cash:
                            reenter = i+20
                        tranches = 0
                    elif tranches < 3 and closes[prev,1] <= last_entry-atr[prev]:
                        current_weight = units[1]*opens[i,1]/nav_open
                        target = np.array([0, min(spec['cap'], current_weight+spec['cap']*.25)])
                        reason = 'dip_add'
                        tranches += 1
                        last_entry = opens[i,1]
                    elif units[1]*closes[prev,1] > spec['cap']*prior_nav:
                        target, reason = np.array([0, spec['cap']]), 'dip_trim'
                elif good and i >= reenter and np.isfinite(atr[prev]):
                    target, reason = np.array([0, spec['cap']*.5]), 'dip_entry'
                    batch_cash, batch_atr, last_entry = nav_open, atr[prev], opens[i,1]
                    tranches = 1
            elif weights_override is not None or family not in ('hold_spy','hold_gold','lever_spy','lever_gold','mix'):
                if week != last_week:
                    target, reason = weights[prev], 'weekly'
            elif family in ('hold_spy','hold_gold'):
                if not entered:
                    target, reason = weights[prev], 'initial'
            elif month != last_month:
                target, reason = weights[prev], 'monthly'
        if target is not None and nav_open > 0:
            old_units, old_cash = units.copy(), cash
            cash, units, cost, turn = trade_to_weights(cash, units, opens[i], target, a.cost_per_side)
            fees += cost
            turnover_total += turn
            if turn > 1e-6:
                ledger.append({'date':str(dates[i].date()), 'reason':reason,
                               'spy_units':units[0]-old_units[0], 'gold_units':units[1]-old_units[1],
                               'spy_price':opens[i,0], 'gold_price':opens[i,1], 'fee':cost,
                               'cash_before':old_cash, 'cash_after':cash, 'turnover':turn})
            entered = True
        elif stopped and units.sum() > 0:
            turn = units@opens[i]
            cash += turn*(1-a.cost_per_side)
            fees += turn*a.cost_per_side
            units[:] = 0
        gross = units@closes[i]
        nav = cash+gross
        liquidation = max(0,gross)*a.cost_per_side
        rows.append({'date':dates[i], 'equity':nav-liquidation, 'gross_equity':nav,
                     'cash':cash, 'spy_units':units[0], 'gold_units':units[1],
                     'exposure':gross/nav if nav > 0 else 0,
                     'fees_cumulative':fees, 'funding_cumulative':funding,
                     'gold_drag_cumulative':holding, 'turnover_cumulative':turnover_total})
        if schedule_ready:
            last_week, last_month = week, month
    curve = pd.DataFrame(rows).set_index('date')
    returns = curve.equity.pct_change()
    returns.iloc[0] = curve.equity.iloc[0]/a.capital-1
    years = (dates[-1]-dates[first]).days/365.25
    annual = (1+returns).groupby(curve.index.year).prod()-1
    peak = np.maximum.accumulate(np.r_[a.capital, curve.equity])[1:]
    end = float(curve.equity.iloc[-1])
    summary = {'name':spec['name'], 'family':family, 'start':start, 'ending_equity':end,
               'total_return':end/a.capital-1, 'cagr':(end/a.capital)**(1/years)-1 if end>0 else -1,
               'max_drawdown_daily':float((1-curve.equity/peak).max()),
               'annual_returns':{str(k):float(v) for k,v in annual.items()},
               'realized_volatility':float(returns.std()*np.sqrt(252)),
               'trade_days':len(ledger), 'trade_days_per_year':len(ledger)/years,
               'trading_cost':fees, 'borrowing_cost':funding, 'gold_holding_drag':holding,
               'terminal_liquidation_cost':float(liquidation),
               'turnover_dollars':turnover_total, 'mean_exposure':float(curve.exposure.mean()),
               'maximum_close_exposure':float(curve.exposure.max()), 'insolvent':stopped,
               'first_date':str(dates[first].date()), 'last_date':str(dates[-1].date())}
    return summary, curve, pd.DataFrame(ledger)


def rolling_comparisons(curves, months):
    values = pd.DataFrame({k:v.equity for k,v in curves.items()}).resample('ME').last()
    r = values.pct_change(months).dropna()
    answer = {}
    for name in r:
        success = (r[name] > r.SPY) & (r[name] > r.gold)
        answer[name] = {'windows':len(r), 'beat_both':int(success.sum()),
                        'fraction':float(success.mean()),
                        'worst_return':float(r[name].min()),
                        'median_excess_to_best':float((r[name]-r[['SPY','gold']].max(axis=1)).median())}
    return answer


def main():
    protocol = json.loads(PROTOCOL.read_text())
    frame, quality = load_daily()
    a = Assumptions()
    specs = protocol['strategies']+protocol['controls']
    main_results, curves = {}, {}
    for start in protocol['evaluation_starts']:
        for spec in specs:
            key = f'{start}_{spec["name"]}'
            s,c,l = simulate(frame,spec,start,a)
            main_results[key] = s
            c.to_csv(OUT/f'redesign_{key}_daily.csv')
            l.to_csv(OUT/f'redesign_{key}_trades.csv',index=False)
            if start == 2020:
                curves[spec['name']] = c
            print(key,round(s['ending_equity']),round(s['max_drawdown_daily']*100,1),flush=True)
    primary = next(s for s in specs if s['name']==protocol['primary_candidate'])
    neighbors = []
    for field, values in protocol['robustness']['primary_neighbors_one_at_a_time'].items():
        for value in values:
            for start in protocol['evaluation_starts']:
                s,_,_ = simulate(frame,primary,start,replace(a,**{field:value}))
                neighbors.append({'changed':field, 'value':value, **s})
    stress = []
    for spec in specs:
        for start in protocol['evaluation_starts']:
            for label,change in [('higher_costs',protocol['robustness']['cost_stress']),('one_session_delay',{'delay':1})]:
                if spec['family']=='dip' and label=='one_session_delay':
                    continue
                s,_,_ = simulate(frame,spec,start,replace(a,**change))
                stress.append({'stress':label,**s})
    fresh = []
    for start in protocol['robustness']['fresh_annual_starts']:
        for spec in specs:
            s,_,_ = simulate(frame,spec,start,a)
            fresh.append(s)
    choices, wf_curves, wf_ledgers = [], [], []
    wf_capital = a.capital
    for year in range(2023,frame.index[-1].year+1):
        train = frame.loc[frame.index.year < year]
        candidates = [simulate(train,spec,2020,a)[0] for spec in protocol['strategies']]
        eligible = [s for s in candidates if s['max_drawdown_daily']<=.25 and s['cagr']>0]
        chosen = max(eligible,key=lambda s:s['cagr']) if eligible else None
        choices.append({'year':year,'chosen':chosen['name'] if chosen else 'cash','training':candidates})
        spec = next(s for s in specs if chosen and s['name']==chosen['name']) if chosen else {'name':'cash','family':'mix','cap':0}
        s,c,l = simulate(frame.loc[frame.index.year<=year],spec,year,replace(a,capital=wf_capital))
        wf_capital = s['ending_equity']
        wf_curves.append(c)
        wf_ledgers.append(l)
    c = pd.concat(wf_curves)
    l = pd.concat(wf_ledgers)
    years = (c.index[-1]-c.index[0]).days/365.25
    peak = np.maximum.accumulate(np.r_[a.capital,c.equity])[1:]
    s = {'name':'walk_forward','ending_equity':wf_capital,'cagr':(wf_capital/a.capital)**(1/years)-1,
         'max_drawdown_daily':float((1-c.equity/peak).max()),'trade_days':len(l),
         'note':'Each year starts from cash after prior year-end liquidation at modeled exit cost; fixed rule chosen only on earlier years.'}
    c.to_csv(OUT/'redesign_walk_forward_daily.csv')
    l.to_csv(OUT/'redesign_walk_forward_trades.csv',index=False)
    wf_benchmarks = {spec['name']:simulate(frame,spec,2023,a)[0] for spec in specs if spec['name'] in ('SPY','gold','mix_1p5x')}
    payload = {'protocol':protocol,'protocol_sha256':hashlib.sha256(PROTOCOL.read_bytes()).hexdigest(),
               'excluded_stress':'Extra execution latency on stateful dip rules; requires pending-order model',
               'quality':quality,'main':main_results,'neighbors':neighbors,'stress':stress,
               'fresh_starts':fresh,'rolling':{str(m):rolling_comparisons(curves,m) for m in [24,36]},
               'walk_forward':{'summary':s,'choices':choices,'benchmarks':wf_benchmarks}}
    (OUT/'redesign_results.json').write_text(json.dumps(payload,indent=2,allow_nan=False))
    print('Saved',OUT/'redesign_results.json',flush=True)


if __name__ == '__main__':
    main()
