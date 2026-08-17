"""Earnings/guidance fresh-buy extension gate.

Live Jul-Aug 2026 replay: buys entered >4% into the day's pop (KO, IDXX,
NOMD, EAT) all lagged SPY over their horizon; entries <=4% (TTWO, VZ) held up.
The gate caps how far into a pop a fresh earnings buy may chase.
"""

import signals


def _support(**overrides):
    base = {
        "count": 1,
        "direct_hits": 1,
        "secondary_hits": 0,
        "actionable_count": 1,
        "potentially_actionable_count": 1,
        "high_confidence_count": 1,
        "medium_confidence_count": 0,
        "high_durability_count": 0,
    }
    base.update(overrides)
    return base


def _action(confirmation, crowding, change_pct, volume_ratio, **support_overrides):
    return signals._recommendation_action_raw(
        "earnings_guidance_momentum",
        confirmation,
        crowding,
        "high",
        {"change_pct": change_pct, "volume_ratio": volume_ratio, "trend": "up"},
        {"bullish_points": 3},
        _support(**support_overrides),
        direct_news_candidate=True,
    )


def test_modest_pop_confirmed_setup_is_buy_now():
    assert _action("confirmed", "medium", 0.035, 1.8) == "buy_now"


def test_extended_pop_is_not_a_fresh_buy():
    assert _action("confirmed", "medium", 0.05, 1.8) == "watch_for_confirmation"


def test_overconfirmed_pop_requires_acceptable_crowding():
    assert _action("overconfirmed", "high", 0.03, 1.8) == "hold_not_fresh_buy"


def test_overconfirmed_extended_pop_is_hold_not_fresh_buy():
    assert _action("overconfirmed", "medium", 0.10, 1.8) == "hold_not_fresh_buy"


def test_high_crowding_confirmed_setup_is_hold_not_fresh_buy():
    assert _action("confirmed", "high", 0.03, 1.8) == "hold_not_fresh_buy"


def test_post_earnings_dip_path_still_buys_nflx_style_overshoot():
    assert _action("unconfirmed", "low", -0.09, 4.2) == "buy_now"
