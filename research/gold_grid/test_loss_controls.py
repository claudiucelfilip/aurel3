from dataclasses import replace

import pandas as pd
import pytest

from engine import simulate
from test_engine import bars, ZERO
from run import reconcile


def test_entry_cap_includes_initial_purchase():
    r = simulate(bars([[100,100,80,100,100,100,80,100]]),replace(ZERO,max_entries=2),True)
    assert [e[2] for e in r['ledger'] if e[1]==1] == [1,2]
    assert r['summary']['ending_equity'] == pytest.approx(10003)


def test_exposure_cap_rejects_unaffordable_new_notional():
    r = simulate(bars([[100,105,80,105,100,105,80,105]]),
                 replace(ZERO,capital=100,max_notional_multiple=2),True)
    assert [e[2] for e in r['ledger'] if e[1]==1] == [1]
    assert r['summary']['exposure_limit_checks']>0
    assert r['summary']['ending_equity'] == pytest.approx(101)


def test_batch_exit_includes_all_fees_and_slippage():
    s = replace(ZERO,capital=100,batch_loss_fraction=.05,
                commission_per_ounce=.2,slippage_per_ounce=.1)
    r = simulate(bars([[100,100,90,90,100,100,90,90]]),s,True)
    assert r['summary']['ending_equity'] == pytest.approx(95)
    assert r['summary']['batch_loss_exits'] == 1
    assert r['cycles'][0][4] == 5
    assert r['summary']['forced_liquidations'] == 0


def test_rejected_addition_cannot_skip_batch_stop():
    s = replace(ZERO,capital=100,grid_dollars=1,max_notional_multiple=1.1,batch_loss_fraction=.2)
    r = simulate(bars([[100,100,70,70,100,100,70,70]]),s,True)
    assert [e[2] for e in r['ledger'] if e[1]==1] == [1]
    assert r['summary']['ending_equity'] == pytest.approx(80)
    assert r['summary']['batch_loss_exits'] == 1


def test_repeated_stops_use_remaining_cash_without_refilling_account():
    s = replace(ZERO,capital=100,batch_loss_fraction=.05)
    f = bars([[100,100,80,80,100,100,80,80]]*3)
    r = simulate(f,s,True)
    assert r['summary']['batch_loss_exits'] == 3
    assert r['summary']['ending_equity'] == pytest.approx(100*.95**3)
    assert r['summary']['gross_wins'] == 0
    reconcile(f,r,s)


def test_cooldown_uses_elapsed_calendar_time():
    f = bars([[100,100,80,80,100,100,80,80]]+[[100]*8]*4)
    f.index = pd.to_datetime(['2020-01-01T00:00Z','2020-01-01T01:00Z',
                             '2020-01-01T23:00Z','2020-01-02T00:00Z','2020-01-02T01:00Z'])
    r = simulate(f,replace(ZERO,capital=100,batch_loss_fraction=.05,cooldown_hours=24),True)
    assert [e[0] for e in r['ledger'] if e[1]==1] == [0,3]


def test_account_drawdown_exit_stops_permanently():
    f = bars([[100,100,70,70,100,100,70,70],[100,200,100,200,100,200,100,200]])
    r = simulate(f,replace(ZERO,capital=100,account_drawdown_fraction=.2),True)
    assert r['summary']['ending_equity'] == pytest.approx(80)
    assert r['summary']['account_drawdown_halts'] == 1
    assert r['summary']['batch_loss_exits'] == 0
    assert r['cycles'][0][4] == 6
    assert all(e[0]==0 for e in r['ledger'] if e[1]==1)


def test_gap_can_exceed_loss_limit_and_halt_account_before_reentry():
    f = bars([[100]*8,[50]*8,[100,200,100,200,100,200,100,200]])
    s = replace(ZERO,capital=100,batch_loss_fraction=.05,account_drawdown_fraction=.2)
    r = simulate(f,s,True)
    assert r['summary']['ending_equity'] == pytest.approx(50)
    assert r['summary']['account_drawdown_halts'] == 1
    assert r['summary']['largest_cycle_loss'] == pytest.approx(-50)
    assert len([e for e in r['ledger'] if e[1]==1]) == 1


def test_financing_and_stop_reentry_reconcile():
    f = bars([[100,100,80,80,100,100,80,80]]*4)
    f.index = pd.date_range('2020-01-01',periods=4,freq='2D',tz='UTC')
    s = replace(ZERO,capital=100,batch_loss_fraction=.1,annual_financing=.1)
    r = simulate(f,s,True)
    reconcile(f,r,s)


def test_profit_lock_activates_at_milestone_then_follows_running_peak():
    f = bars([[100,160,100,150,100,160,100,150], [150,150,120,120,150,150,120,120]])
    s = replace(ZERO,capital=100,grid_dollars=200,target_dollars=100,
                account_drawdown_fraction=.2,drawdown_activation_multiple=1.5)
    r = simulate(f,s,True)
    assert r['summary']['ending_equity'] == pytest.approx(128)
    assert r['summary']['account_drawdown_halts'] == 1
    reconcile(f,r,s)


def test_profit_lock_does_not_activate_before_milestone():
    f = bars([[100,160,100,150,100,160,100,150], [150,150,120,120,150,150,120,120]])
    s = replace(ZERO,capital=100,grid_dollars=200,target_dollars=100,
                account_drawdown_fraction=.2,drawdown_activation_multiple=2)
    r = simulate(f,s,True)
    assert r['summary']['ending_equity'] == pytest.approx(120)
    assert r['summary']['account_drawdown_halts'] == 0
    assert r['summary']['open_ounces'] == 1
