import numpy as np
import pandas as pd
from dataclasses import replace

from redesign import Assumptions, quote_indices, signals, simulate, trade_to_weights


def fixture(n=800):
    dates = pd.bdate_range('2018-01-01',periods=n)
    x = np.arange(n)
    gold = 100*np.exp(.0004*x+.03*np.sin(x/17))
    spy = 100*np.exp(.0006*x+.04*np.sin(x/29))
    return pd.DataFrame({'gold_open':gold*.998,'gold_close':gold,'gold_high':gold*1.01,
                         'gold_low':gold*.99,'spy_open':spy*.999,'spy_close':spy},index=dates)


def test_budget_and_fee_conservation():
    cash, q, fee, turn = trade_to_weights(10000,np.zeros(2),np.array([100.,200.]),np.array([.75,.75]),.001)
    assert np.isclose(cash+q@np.array([100.,200.]),10000-fee)
    assert np.isclose(q@np.array([100.,200.]),1.5*(10000-fee))
    assert np.isclose(fee,turn*.001)
    assert cash < 0


def test_timestamp_resolution_cannot_select_future_quotes():
    quotes = pd.date_range('2020-01-01',periods=10,freq='min',tz='UTC').as_unit('ns')
    requested = quotes[[1,5,8]].as_unit('us')
    assert np.array_equal(quote_indices(quotes,requested),[1,5,8])
    assert np.array_equal(quote_indices(quotes.as_unit('us'),requested.as_unit('ns')),[1,5,8])


def test_buy_hold_matches_price_ratio_without_costs():
    f = fixture()
    a = Assumptions(cost_per_side=0,annual_borrowing_cost=0,annual_gold_holding_cost=0)
    s,c,l = simulate(f,{'name':'gold','family':'hold_gold','cap':1},2020,a)
    expected = 10000*f.gold_close.iloc[-1]/f.loc['2020':].gold_open.iloc[0]
    assert np.isclose(s['ending_equity'],expected)
    assert len(l)==1
    assert np.allclose(c.cash,0)


def test_gold_drag_accumulates_calendar_time():
    f = fixture()
    f.loc[:,f.columns] = 100
    a = Assumptions(cost_per_side=0,annual_borrowing_cost=0,annual_gold_holding_cost=.1)
    s,_,_ = simulate(f,{'name':'gold','family':'hold_gold','cap':1},2020,a)
    period = (f.index[-1]-f.loc['2020':].index[0]).days/365.25
    assert np.isclose(s['ending_equity'],10000*np.exp(-.1*period))


def test_borrowing_weekend_and_actual_negative_cash():
    f = fixture()
    f.loc[:,f.columns] = 100
    f = f.loc[:'2020-01-06']
    a = Assumptions(cost_per_side=0,annual_borrowing_cost=.1,annual_gold_holding_cost=0)
    s,c,_ = simulate(f,{'name':'x','family':'lever_spy','cap':1.5},2020,a)
    expected = 5000
    for gap in np.diff(c.index.values).astype('timedelta64[D]').astype(int):
        expected *= 1+.1*gap/365.25
    assert np.isclose(s['borrowing_cost'],expected-5000)


def test_future_prices_cannot_change_earlier_positions():
    f = fixture()
    modified = f.copy()
    cut = 650
    modified.iloc[cut:,:] *= 3
    for family in ['dip','gold_trend','gold_vol','diversified','relative','balanced_vol']:
        spec = {'name':family,'family':family,'cap':1.5,'take_profit_atr':0}
        _,before,ledger = simulate(f,spec,2020)
        _,after,other = simulate(modified,spec,2020)
        pd.testing.assert_frame_equal(before.loc[:f.index[cut-1]],after.loc[:f.index[cut-1]])
        boundary = str(f.index[cut].date())
        pd.testing.assert_frame_equal(ledger[ledger.date<boundary],other[other.date<boundary])


def test_intraday_close_does_not_affect_same_open_order():
    f = fixture()
    monday = next(i for i in range(600,700) if f.index[i].weekday()==0)
    g = f.copy()
    g.iloc[monday,g.columns.get_indexer(['gold_close','spy_close'])] *= .1
    spec = {'name':'trend','family':'diversified','cap':1.5}
    _,_,a = simulate(f,spec,2020)
    _,_,b = simulate(g,spec,2020)
    day = str(f.index[monday].date())
    pd.testing.assert_frame_equal(a[a.date<=day],b[b.date<=day])


def test_extra_delay_moves_order_date_with_its_frozen_signal():
    f = fixture()
    spec = {'name':'trend','family':'diversified','cap':1.5}
    a = Assumptions()
    _,_,normal = simulate(f,spec,2020,a)
    _,_,late = simulate(f,spec,2020,replace(a,delay=1))
    first = f.index.get_loc(pd.Timestamp(normal.iloc[0].date))
    assert late.iloc[0].date == str(f.index[first+1].date())
    w,_,_ = signals(f,spec,a)
    fill = late.iloc[0]
    bought = np.array([fill.spy_units*fill.spy_price,fill.gold_units*fill.gold_price])
    assert np.allclose(bought/(fill.cash_before-fill.fee),w[first-1])


def test_signal_exposure_caps_and_cash_when_below_trend():
    f = fixture()
    for family in ['gold_vol','diversified','relative']:
        w,_,_ = signals(f,{'family':family,'cap':1.5})
        assert np.all(w>=0)
        assert np.all(w.sum(axis=1)<=1.5+1e-12)
        assert np.all(w[:199]==0)
    f.loc[:,['spy_close','gold_close']] = np.exp(-np.arange(len(f))[:,None]*.001)*np.ones((1,2))
    w,_,_ = signals(f,{'family':'diversified','cap':1.5})
    assert np.all(w==0)


def test_liquidation_estimate_and_cashflow_ledger():
    f = fixture()
    spec = {'name':'trend','family':'diversified','cap':1.5}
    s,c,l = simulate(f,spec,2020)
    differences = l.cash_before-l.spy_units*l.spy_price-l.gold_units*l.gold_price-l.fee-l.cash_after
    assert abs(differences).max()<1e-8
    expected = c.gross_equity-(c.spy_units*f.spy_close+c.gold_units*f.gold_close).reindex(c.index)*.001
    assert np.allclose(c.equity,expected)
    assert np.isclose(s['trading_cost'],l.fee.sum())


def test_losses_are_not_clamped_at_five_percent():
    f = fixture()
    spec = {'name':'dip','family':'dip','cap':1.5,'take_profit_atr':0}
    _,c,_ = simulate(f,spec,2020)
    held = c.index[c.gold_units>0][5]
    f.loc[held:,['gold_open','gold_close','gold_high','gold_low']] *= .5
    s,c,_ = simulate(f,spec,2020)
    assert s['max_drawdown_daily']>.20


def test_fresh_start_has_no_carried_positions_or_capital():
    f = fixture(1100)
    _,c,l = simulate(f,{'name':'gold','family':'hold_gold','cap':1},2022)
    assert l.iloc[0].cash_before==10000
    assert c.index[0].year==2022
