"""Chronological, one-position opening-move simulation with explicit fills."""
from dataclasses import dataclass
import numpy as np
import pandas as pd

FEATURES = ['direction', 'opening_body_fraction', 'ema_distance_atr', 'opening_range_atr',
            'relative_open_volume', 'overnight_gap_fraction', 'prior_20day_return',
            'prior_20day_volatility', 'prior_close_vs_sma200', 'stop_fraction']

@dataclass(frozen=True)
class Costs:
    execution: float = .0002
    fee: float = .00005
    short_daily: float = .02 / 252


def prepare(raw, schedule):
    raw = raw.sort_index()
    if raw.index.has_duplicates:
        raise ValueError('Duplicate timestamps')
    if not ((raw.high >= raw[['open','close','low']].max(axis=1)) &
            (raw.low <= raw[['open','close','high']].min(axis=1)) & (raw.low > 0)).all():
        raise ValueError('Invalid OHLC')
    frame = raw.copy()
    frame['session'] = frame.index.tz_convert('America/New_York').strftime('%Y-%m-%d')
    raw_groups = {k:v for k,v in frame.groupby('session',sort=True)}
    groups = {}
    five = []
    records = []
    for date, row in schedule.iterrows():
        date = str(date.date())
        g = raw_groups.get(date, frame.iloc[:0])
        g = g.loc[(g.index >= row.open) & (g.index < row.close)].copy()
        expected = pd.date_range(row.open, row.close, freq='1min', inclusive='left')
        missing = expected.difference(g.index)
        records.append({'date':date,'expected_minutes':len(expected),'observed_minutes':len(g),
                        'missing_minutes':len(missing),'first_missing':[str(x) for x in missing[:20]],
                        'early_close':len(expected)<390})
        if g.empty:
            continue
        groups[date] = g
        f = g.resample('5min', origin=row.open).agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum'})
        f['count'] = g.close.resample('5min',origin=row.open).count()
        f = f.loc[f['count']==5].copy()
        f['session'] = date
        five.append(f)
    bars = pd.concat(five).sort_index()
    bars['ema'] = bars.close.ewm(span=12, adjust=False).mean()
    previous = bars.close.shift()
    tr = pd.concat([bars.high-bars.low,(bars.high-previous).abs(),(bars.low-previous).abs()],axis=1).max(axis=1)
    bars['atr'] = tr.rolling(14,min_periods=14).mean()
    daily = pd.DataFrame({k:{'close':v.close.iloc[-1], 'opening_volume':v.tz_convert('America/New_York').between_time('09:30','09:34').volume.sum() if len(v.tz_convert('America/New_York').between_time('09:30','09:34'))==5 else np.nan} for k,v in groups.items()}).T.sort_index()
    # Features are shifted so today's post-entry prices cannot reach today's signal.
    daily['prior_close']=daily.close.shift()
    daily['prior_20day_return']=daily.close.pct_change(20).shift()
    daily['prior_20day_volatility']=daily.close.pct_change().rolling(20).std().shift()*np.sqrt(252)
    daily['prior_close_vs_sma200']=(daily.close/daily.close.rolling(200).mean()-1).shift()
    daily['median_open_volume']=daily.opening_volume.shift().rolling(20).median()
    setups=[]
    for date,row in schedule.iterrows():
        date=str(date.date())
        if date not in groups or row.open not in bars.index:
            continue
        b=bars.loc[row.open]; d=daily.loc[date]
        if not np.isfinite(b.atr) or not np.isfinite(d.prior_close_vs_sma200):
            continue
        direction=int(np.sign(b.close-b.ema))
        if not direction:
            continue
        dist=max(2*b.atr,.0025*b.close)
        opening_range=b.high-b.low
        setups.append({'date':date,'entry_time':row.open+pd.Timedelta(minutes=5),
                       'exit_time':row.close-pd.Timedelta(minutes=5),
                       'timeout_time':row.open+pd.Timedelta(minutes=35),'direction':direction,
                       'distance':dist,'signal_close':b.close,
                       'opening_body_fraction':abs(b.close-b.open)/opening_range if opening_range else 0.,
                       'ema_distance_atr':abs(b.close-b.ema)/b.atr,
                       'opening_range_atr':opening_range/b.atr,
                       'relative_open_volume':b.volume/d.median_open_volume,
                       'overnight_gap_fraction':b.open/d.prior_close-1,
                       'prior_20day_return':d.prior_20day_return,
                       'prior_20day_volatility':d.prior_20day_volatility,
                       'prior_close_vs_sma200':d.prior_close_vs_sma200,
                       'stop_fraction':dist/b.close})
    return groups,pd.DataFrame(setups).set_index('date'),records


def simulate_trade(bars, setup, costs=Costs(), delay=0, timeout=False):
    direction=int(setup['direction']); dist=float(setup['distance'])
    entry_time=setup['entry_time']+pd.Timedelta(minutes=delay)
    if entry_time not in bars.index:
        return None
    raw_entry=float(bars.loc[entry_time,'open'])
    entry=raw_entry*(1+direction*costs.execution)
    stop=entry-direction*dist
    previous_close=entry
    exit_raw=None;reason=None
    for b in bars.loc[entry_time:].itertuples():
        ts=b.Index
        # Stops carried into a minute precede that minute's trail update.
        if direction*(b.open-stop)<=0:
            exit_raw=float(b.open);reason='stop_gap'
        elif ts>=setup['exit_time']:
            exit_raw=float(b.open);reason='session_exit'
        elif timeout and ts>=setup['timeout_time'] and direction*(previous_close-entry)<.25*dist:
            exit_raw=float(b.open);reason='timeout'
        elif direction==1 and b.low<=stop or direction==-1 and b.high>=stop:
            exit_raw=stop;reason='stop'
        if exit_raw is not None:
            exit_time=ts
            break
        previous_close=float(b.close)
        stop=max(stop,b.close-dist) if direction==1 else min(stop,b.close+dist)
    if exit_raw is None:
        raise ValueError(f'No executable session exit after {setup["exit_time"]}')
    exit_fill=exit_raw*(1-direction*costs.execution)
    weight=min(1.,.005*entry/dist)
    gross_per_share=direction*(exit_raw-raw_entry)
    fee_per_share=costs.fee*(entry+exit_fill)+(costs.short_daily*entry if direction<0 else 0.)
    net_per_share=direction*(exit_fill-entry)-fee_per_share
    return {'entry_time':entry_time,'exit_time':exit_time,'entry':entry,'exit':exit_fill,
            'raw_entry':raw_entry,'raw_exit':exit_raw,'direction':direction,'distance':dist,
            'weight':weight,'reason':reason,'net_return':weight*net_per_share/entry,
            'gross_return':weight*gross_per_share/entry,'net_R':net_per_share/dist,
            'cost_return':weight*(gross_per_share-net_per_share)/entry,
            'minutes_held':(exit_time-entry_time).total_seconds()/60}


def equity_stats(returns):
    r=np.asarray(returns,dtype=float);eq=np.r_[1.,np.cumprod(1+r)]
    if np.any(1+r<=0):
        raise ValueError('Bankrupt path')
    return {'total_return':float(eq[-1]-1),'cagr':float(eq[-1]**(252/len(r))-1),
            'max_drawdown':float(np.min(eq/np.maximum.accumulate(eq)-1)),
            'annual_volatility':float(np.std(r,ddof=1)*np.sqrt(252)) if len(r)>1 else 0.,
            'equity':eq.tolist()}


def walk_forward_predictions(trades, setups):
    from sklearn.ensemble import HistGradientBoostingRegressor
    predictions=pd.Series(np.nan,index=setups.index,dtype=float)
    audit=[]
    for year in range(2019,2027):
        train=trades.loc[(trades.index>=f'{year-3}-01-01') & (trades.index<f'{year}-01-01')].iloc[:-5]
        test=setups.loc[(setups.index>=f'{year}-01-01') & (setups.index<f'{year+1}-01-01')]
        if len(train)<500 or test.empty:
            audit.append({'year':year,'training_trades':len(train),'status':'insufficient_training'})
            continue
        model=HistGradientBoostingRegressor(max_iter=100,max_leaf_nodes=7,min_samples_leaf=50,
                l2_regularization=10,learning_rate=.05,random_state=42,early_stopping=False)
        model.fit(setups.loc[train.index,FEATURES].astype(float),train.net_R)
        predictions.loc[test.index]=model.predict(test[FEATURES].astype(float))
        audit.append({'year':year,'training_trades':len(train),'last_training_day':train.index[-1],
                      'predictions':len(test),'status':'trained'})
    return predictions,audit
