"""Accounting and chronology tests for the actual research execution path."""
import copy
import json

import numpy as np
import pandas as pd
import pytest

from research.multiasset.engine import (DATA, PROTOCOL, execute_batch, features,
    load_market, macro_series, metrics, ridge_forecast, simulate, targets)


def test_cash_constrained_buy_charges_fees_without_borrowing():
    units, cash, turnover, fees, count, events = execute_batch(
        np.zeros(2), 1000, np.array([10., 20.]), np.array([.6, .4]),
        [0, 1], np.array([100., 100.]), 1, 1)
    assert cash >= 0
    assert np.isclose(cash + units @ np.array([10., 20.]) + fees, 1000)
    assert count == 2
    assert turnover <= 1000


def test_sell_before_buy_and_do_not_sell_unowned_shares():
    units, cash, _, fees, _, _ = execute_batch(
        np.array([100., 0.]), 0, np.array([10., 20.]), np.array([0., 1.]),
        [0, 1], np.array([25., 25.]), 1, 1)
    assert units[0] == 0
    assert units[1] > 0
    assert cash >= 0
    assert np.isclose(cash + units[1] * 20 + fees, 1000)


def test_minimum_ticket_suppresses_small_changes():
    result = execute_batch(np.array([100., 0.]), 0, np.array([10., 20.]),
                           np.array([.99, .01]), [0, 1], np.array([25., 25.]), 1, 100)
    assert result[4] == 0


@pytest.fixture(scope="module")
def market():
    if not (DATA / "manifest.json").exists():
        pytest.skip("Run fetch.py for the real-data integration checks")
    return load_market()


def test_macro_cannot_appear_before_assumed_availability():
    if not (DATA / "pcpi-rows.json").exists():
        pytest.skip("Run fetch.py")
    s90, s120 = macro_series(lag=90), macro_series(lag=120)
    assert list(s120.index - s90.index) == [pd.Timedelta(days=30)] * len(s90)
    np.testing.assert_allclose(s90.to_numpy(), s120.to_numpy(), equal_nan=True)


def test_crypto_signal_uses_previous_utc_close(market):
    date = pd.Timestamp("2024-06-14")
    assert market.signal_close.loc[date, "BTC-USD"] == market.close.loc[date-pd.Timedelta(days=1), "BTC-USD"]


def test_future_prices_do_not_change_prior_predictions(market):
    cut = pd.Timestamp("2020-01-01")
    before, x_before = features(market)
    mutated = copy.deepcopy(market)
    mutated.signal_close.loc[mutated.signal_close.index >= cut] *= 3
    after, x_after = features(mutated)
    old = before.date < cut
    pd.testing.assert_frame_equal(x_before.loc[old], x_after.loc[old])
    p_before, audit = ridge_forecast(before, x_before)
    p_after, _ = ridge_forecast(after, x_after)
    np.testing.assert_allclose(p_before[old], p_after[old], equal_nan=True)
    assert all(a["last_label_end"] < a["fit_date"] for a in audit)


def test_targets_sum_to_one_and_crypto_stays_within_budget(market):
    panel, x = features(market)
    pred, _ = ridge_forecast(panel, x)
    for name in PROTOCOL["candidates"]:
        t = targets(panel, pred, name)
        np.testing.assert_allclose(t.sum(axis=1), 1)
        assert (t >= 0).all().all()
        assert (t[["BTC-USD", "ETH-USD"]].sum(axis=1) <= .100000001).all()


def test_delay_and_skip_are_applied_to_real_fill_records(market):
    panel, _ = features(market)
    pred = pd.Series(np.nan, index=panel.index)
    t = targets(panel, pred, "static").loc["2023":]
    normal, fills1 = simulate(market, t, start="2023-01-01")
    delayed, fills3 = simulate(market, t, delay=3, start="2023-01-01")
    skipped, fills_skip = simulate(market, t, skip=True, start="2023-01-01")
    positions = {d: i for i, d in enumerate(market.sessions)}
    for fills, delay in [(fills1, 1), (fills3, 3)]:
        for row in fills.itertuples():
            signal = pd.Timestamp(row.signal_date)
            expected = market.sessions[positions[signal] + delay]
            if row.ticker.endswith("-USD"):
                expected += pd.Timedelta(days=1)
            assert pd.Timestamp(row.fill_date) == expected
    assert fills_skip.signal_date.nunique() < fills1.signal_date.nunique()
    assert normal.fees.sum() > 0
    assert normal.nav.min() > 0


def test_zero_cost_spy_matches_independent_buy_and_hold(market):
    date = pd.Timestamp("2019-01-04")
    t = pd.DataFrame(0., index=[date], columns=market.close.columns)
    t["SPY"] = 1
    f, fills = simulate(market, t, cost_multiplier=0, start="2019-01-01")
    fill_date = pd.Timestamp(fills.iloc[0].fill_date)
    expected = PROTOCOL["initial_usd"] * market.close.SPY.iloc[-1] / market.opening.loc[fill_date, "SPY"]
    assert np.isclose(f.nav.iloc[-1], expected)
    assert len(fills) == 1


def test_first_day_loss_is_included_in_drawdown():
    f = pd.DataFrame({"return": [-.1, 0], "turnover": [0, 0], "fees": [0, 0],
                      "orders": [0, 0], "cash_weight": [0, 0]}, index=pd.date_range("2020-01-01", periods=2))
    assert np.isclose(metrics(f, "2020")['max_drawdown'], -.1)
