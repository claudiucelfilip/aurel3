"""Buy-lane extension gate: volume >1.5x demotes buys; buy-lane confidence caps at medium."""

import signals


def test_extended_buy_now_is_demoted():
    assert signals.buy_lane_extension_gate("buy_now", 1.51) == "hold_not_fresh_buy"


def test_extended_early_accumulation_is_demoted():
    assert signals.buy_lane_extension_gate("early_accumulation", 3.6) == "hold_not_fresh_buy"


def test_unextended_buy_passes():
    assert signals.buy_lane_extension_gate("buy_now", 1.5) == "buy_now"
    assert signals.buy_lane_extension_gate("early_accumulation", 0.9) == "early_accumulation"


def test_non_buy_actions_untouched():
    assert signals.buy_lane_extension_gate("watch_for_confirmation", 9.0) == "watch_for_confirmation"


def test_missing_volume_does_not_gate():
    assert signals.buy_lane_extension_gate("buy_now", None) == "buy_now"


def test_buy_lane_high_confidence_capped_to_medium():
    assert signals.buy_lane_confidence("buy_now", "high") == "medium"
    assert signals.buy_lane_confidence("early_accumulation", "high") == "medium"


def test_non_buy_keeps_high_confidence():
    assert signals.buy_lane_confidence("watch_for_confirmation", "high") == "high"
    assert signals.buy_lane_confidence("buy_now", "low") == "low"
