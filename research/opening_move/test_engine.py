import numpy as np
import pandas as pd
import pytest
from engine import Costs, equity_stats, prepare, simulate_trade

ZERO=Costs(0,0,0)

def example(rows, direction=1):
    index=pd.date_range('2024-01-02 14:35',periods=len(rows),freq='min',tz='UTC')
    bars=pd.DataFrame(rows,columns=['open','high','low','close'],index=index)
    setup={'direction':direction,'distance':1.,'entry_time':index[0],
           'exit_time':index[-1],'timeout_time':index[0]+pd.Timedelta(minutes=30)}
    return bars,setup


def test_entry_does_not_use_signal_candle_price():
    b,s=example([[102,102.5,101.5,102],[103,103,103,103]])
    s['signal_close']=100
    t=simulate_trade(b,s,ZERO)
    assert t['entry']==102


def test_long_stop_gaps_fill_at_actual_open():
    b,s=example([[100,100.2,99.8,100],[97,98,96,97]])
    t=simulate_trade(b,s,ZERO)
    assert t['exit']==97 and t['reason']=='stop_gap'


def test_short_stop_gaps_fill_at_actual_open():
    b,s=example([[100,100.2,99.8,100],[103,104,102,103]],-1)
    assert simulate_trade(b,s,ZERO)['exit']==103


def test_trailing_stop_uses_previous_completed_close():
    b,s=example([[100,105,99.5,104],[104,104.5,102,103],[103,104,102,103]])
    t=simulate_trade(b,s,ZERO)
    assert t['exit_time']==b.index[1] and t['exit']==103


def test_costs_reconcile():
    b,s=example([[100,100.2,99.8,100],[100.5,101,100,100.5]])
    t=simulate_trade(b,s)
    assert t['gross_return']-t['cost_return']==pytest.approx(t['net_return'])
    assert 0<t['weight']<=1
    assert t['entry']>100 and t['exit']<100.5


def test_extra_delay_keeps_original_signal():
    b,s=example([[100,100.2,99.8,100],[101,101.2,100.8,101],[101.5,102,101,101.5]])
    assert simulate_trade(b,s,ZERO,delay=1)['entry']==101


def test_future_missing_bar_does_not_remove_trade():
    b,s=example([[100,100.2,99.8,100],[99.5,100,99.2,99.5],[97,98,96,97]])
    t=simulate_trade(b.drop(b.index[1]),s,ZERO)
    assert t['exit']==97


def test_missing_entry_returns_no_trade():
    b,s=example([[100,101,99,100],[101,102,100,101]])
    assert simulate_trade(b.iloc[1:],s,ZERO) is None


def test_missing_scheduled_exit_is_not_silently_closed_earlier():
    b,s=example([[100,100.1,99.9,100],[100,100.1,99.9,100]])
    s['exit_time']+=pd.Timedelta(minutes=5)
    with pytest.raises(ValueError):simulate_trade(b,s,ZERO)


def test_timeout_uses_only_previous_close():
    b,s=example([[100,100.1,99.9,100],[100.1,101,100,100.8],[101,102,100,101]])
    s['timeout_time']=b.index[1]
    t=simulate_trade(b,s,ZERO,timeout=True)
    assert t['reason']=='timeout' and t['raw_exit']==100.1


def test_initial_loss_is_in_drawdown():
    assert equity_stats([-.1])['max_drawdown']==pytest.approx(-.1)


def test_calendar_dst_and_early_close():
    import exchange_calendars as xc
    schedule=xc.get_calendar('XNYS',start='2023-01-01',end='2025-01-01').schedule
    assert schedule.loc['2024-03-08','open'].hour==14
    assert schedule.loc['2024-03-11','open'].hour==13
    day=schedule.loc['2024-11-29']
    assert (day.close-day.open).total_seconds()/60==210


def test_signal_features_ignore_future_prices():
    import exchange_calendars as xc
    schedule=xc.get_calendar('XNYS',start='2023-01-01',end='2025-01-01').schedule.iloc[:230]
    chunks=[]
    for i,row in enumerate(schedule.itertuples()):
        idx=pd.date_range(row.open,row.close,freq='min',inclusive='left')
        c=100+i*.1+np.arange(len(idx))*.001
        chunks.append(pd.DataFrame({'open':c,'high':c+.05,'low':c-.05,'close':c+.01,'volume':1000},index=idx))
    data=pd.concat(chunks)
    _,setups,_=prepare(data,schedule)
    cutoff=setups.index[3]
    signal_time=setups.loc[cutoff,'entry_time']
    changed=data.copy();changed.loc[changed.index>=signal_time,['open','high','low','close']]*=2
    _,other,_=prepare(changed,schedule)
    pd.testing.assert_frame_equal(setups.loc[:cutoff],other.loc[:cutoff])
