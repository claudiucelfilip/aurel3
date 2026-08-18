"""Exit-plan machinery: buy-lane recs carry a TP/time-stop plan and reviews
score the managed trade instead of the raw drift.

Live May-Aug 2026 replay: signal names usually spiked >=4% above entry within
2 weeks but drifted below SPY afterwards; harvesting the spike (+4% TP, 10
trading-day stop) was the only exit style positive in both eras.
"""

import notify
import signals
from reviews import build_recommendation_review


def _buy_rec(action="buy_now"):
    return {
        "id": "rec_test_x",
        "timestamp": "2026-08-01T15:00:00+00:00",
        "ticker": "TEST",
        "company": "Test Co",
        "action": action,
        "theme_driver": "Earnings / guidance momentum",
        "why_now": "test",
        "confirmation_state": "confirmed",
        "confidence": "high",
        "expected_horizon": "1-2 weeks",
        "reference_price": 100.0,
        "invalidation": "test",
        "exit_plan": signals._exit_plan(action),
    }


def test_buy_lane_actions_carry_exit_plan():
    for action in ("buy_now", "early_accumulation"):
        plan = signals._exit_plan(action)
        assert plan["take_profit_pct"] == signals.EXIT_TAKE_PROFIT_PCT
        assert plan["max_hold_trading_days"] == signals.EXIT_MAX_HOLD_TRADING_DAYS
        assert "SPY" in plan["policy"]


def test_non_buy_actions_have_no_exit_plan():
    for action in ("watch_for_confirmation", "hold_not_fresh_buy", "sell"):
        assert signals._exit_plan(action) is None


def test_review_scores_take_profit_as_worked_when_ahead_of_benchmark():
    review = build_recommendation_review(
        _buy_rec(),
        current_price=97.0,  # drifted below entry after the TP hit
        benchmark_return=0.005,
        avg_daily_move=0.02,
        exit_result={"hit": True, "hit_date": "2026-08-05", "sessions_to_hit": 3, "window_complete": True},
    )
    assert review["exit_plan_applied"] is True
    assert review["take_profit_hit"] is True
    assert review["forward_return_pct"] == 0.04
    assert review["outcome"] == "worked"


def test_review_time_stop_uses_current_price():
    review = build_recommendation_review(
        _buy_rec(),
        current_price=97.0,
        benchmark_return=0.01,
        avg_daily_move=0.02,
        exit_result={"hit": False, "hit_date": None, "sessions_to_hit": None, "window_complete": True},
    )
    assert review["exit_plan_applied"] is True
    assert review["take_profit_hit"] is False
    assert review["forward_return_pct"] == -0.03
    assert review["outcome"] == "failed"


def test_review_without_exit_result_keeps_legacy_scoring():
    review = build_recommendation_review(
        _buy_rec(),
        current_price=110.0,
        benchmark_return=0.01,
        avg_daily_move=0.02,
    )
    assert review["exit_plan_applied"] is False
    assert review["forward_return_pct"] == 0.1
    assert review["outcome"] == "worked"


def test_buy_alert_includes_exit_plan():
    text = notify.format_recommendation_alert(_buy_rec())
    assert "Exit plan:" in text
    assert "10 trading days" in text
