from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from engine import Settings, simulate


def bars(rows):
    return pd.DataFrame(rows, index=pd.date_range('2020-01-01', periods=len(rows), freq='min', tz='UTC'),
                        columns=['bid_open','bid_high','bid_low','bid_close',
                                 'ask_open','ask_high','ask_low','ask_close'])


ZERO = Settings(annual_financing=0, commission_per_ounce=0, slippage_per_ounce=0)


def test_doubling_and_weighted_basket_exit():
    f = bars([[100,100,80,100,100,100,80,100]])
    r = simulate(f, ZERO, True)
    buys = [e for e in r['ledger'] if e[1] == 1]
    assert [e[2] for e in buys] == [1,2,4]
    assert [e[3] for e in buys] == [100,90,80]
    assert r['summary']['ending_equity'] == pytest.approx(10007)
    assert r['summary']['closed_cycles'] == 1


def test_fixed_size_variant():
    r = simulate(bars([[100,100,80,100,100,100,80,100]]), replace(ZERO,multiplier=1), True)
    assert [e[2] for e in r['ledger'] if e[1]==1] == [1,1,1]
    assert r['summary']['ending_equity'] == pytest.approx(10003)


def test_open_loss_is_not_hidden_by_balance():
    f = bars([[100,100,90,90,100,100,90,90]])
    r = simulate(f, replace(ZERO,grid_dollars=50))
    assert r['summary']['ending_balance'] == 10000
    assert r['summary']['ending_equity'] == 9990
    assert r['summary']['open_cycle_pnl'] == -10
    assert r['summary']['closed_cycles'] == 0
    assert r['summary']['win_rate'] is None


def test_forced_liquidation_stops_and_does_not_redeposit():
    f = bars([[100,100,1,10,100,100,1,10], [100,200,100,200,100,200,100,200]])
    s = replace(ZERO,capital=100,grid_dollars=5,leverage=20)
    r = simulate(f,s,True)
    assert r['summary']['forced_liquidations'] == 1
    assert r['summary']['stopped']
    assert r['quantity'][-1] == 0
    assert r['equity'][0] == r['equity'][1]
    assert 0 < r['equity'][-1] < 100
    assert r['summary']['gross_losses'] > 0


def test_gap_liquidates_at_available_quote_not_stop_threshold():
    f = bars([[100,100,100,100,100,100,100,100], [1,1,1,1,1,1,1,1]])
    r = simulate(f, replace(ZERO,capital=10,grid_dollars=200,leverage=20), True)
    sell = [e for e in r['ledger'] if e[1]==3][0]
    assert sell[3] == 1
    assert r['summary']['ending_equity'] == -89


def test_funding_accrues_across_weekend_and_net_target_includes_costs():
    f = bars([[100,100,100,100,100,100,100,100]]*2)
    f.index = pd.to_datetime(['2020-01-03','2020-01-06'], utc=True)
    r = simulate(f,replace(ZERO,annual_financing=.1))
    fee = 100*.1*3/365.25
    assert r['summary']['financing'] == pytest.approx(fee)
    assert r['summary']['ending_equity'] == pytest.approx(10000-fee)


def test_profit_target_pays_spread_slippage_commission():
    f = bars([[99,110,99,110,100,111,100,111]])
    s = replace(ZERO,commission_per_ounce=.2,slippage_per_ounce=.1)
    r = simulate(f,s,True)
    assert r['summary']['ending_equity'] == pytest.approx(10001)
    assert r['summary']['commission'] == pytest.approx(.4)
    assert r['ledger'][-1][3] == pytest.approx(101.5)


def test_intraminute_path_changes_are_explicit():
    f = bars([[100,102,80,100,100,102,80,100]])
    low_first = simulate(f,ZERO,True)
    high_first = simulate(f,replace(ZERO,path=1),True)
    assert low_first['summary']['ending_equity'] == pytest.approx(10007)
    assert high_first['summary']['ending_equity'] == pytest.approx(10001)


def test_future_data_cannot_change_prior_equity_or_orders():
    f = bars([[100,100,95,96,100,100,95,96], [96,96,90,90,96,96,90,90],
              [90,105,90,105,90,105,90,105]])
    short, full = simulate(f.iloc[:2],ZERO,True), simulate(f,ZERO,True)
    np.testing.assert_array_equal(short['equity'],full['equity'][:2])
    assert short['ledger'] == [e for e in full['ledger'] if e[0]<2]


def test_cashflow_conservation():
    f = bars([[100,105,70,103,100.2,105.2,70.2,103.2]]*12)
    s = Settings(annual_financing=0)
    r = simulate(f,s,True)
    cash, qty, basis = s.capital, 0, 0
    for _,kind,amount,price,balance,_ in r['ledger']:
        if kind == 1:
            cash -= amount*s.commission_per_ounce
            qty += amount
            basis += amount*price
        else:
            assert -amount == pytest.approx(qty)
            cash += qty*price-basis-qty*s.commission_per_ounce
            qty,basis = 0,0
        assert cash == pytest.approx(balance)
    nav = cash+qty*(f.bid_close.iloc[-1]-s.slippage_per_ounce-s.commission_per_ounce)-basis
    assert nav == pytest.approx(r['summary']['ending_equity'])


def test_rejected_addition_stays_unfilled_but_basket_can_recover():
    f = bars([[100,110,80,110,100,110,80,110]])
    r = simulate(f,replace(ZERO,capital=100,leverage=2),True)
    assert [x[2] for x in r['ledger'] if x[1]==1] == [1]
    assert r['summary']['rejected_add_checks'] > 0
    assert r['summary']['ending_equity'] == pytest.approx(101)
    assert r['summary']['forced_liquidations'] == 0
