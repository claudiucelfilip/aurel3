"""Manual trading desk: order lifecycle, ledger math, DCA gating, guard."""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

import desk


@pytest.fixture(autouse=True)
def desk_tmpdir(tmp_path, monkeypatch):
    monkeypatch.setattr(desk, "DESK_DIR", tmp_path)
    monkeypatch.setattr(desk, "ORDERS_PATH", tmp_path / "orders.json")
    monkeypatch.setattr(desk, "LEDGER_PATH", tmp_path / "ledger.jsonl")
    monkeypatch.setattr(desk, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(desk, "INBOX_DIR", tmp_path / "inbox")
    return tmp_path


def _proposal(**overrides):
    base = {
        "source": "core_dca",
        "action": "buy",
        "symbol": "SXR8.DE",
        "currency": "EUR",
        "notional": 1500,
    }
    base.update(overrides)
    return base


def test_propose_validate_and_dedupe():
    order = desk.propose_order(_proposal())
    assert order["status"] == "proposed"
    assert desk.propose_order(_proposal()) is None  # identical open order

    with pytest.raises(ValueError):
        desk.propose_order({"source": "x", "action": "buy", "symbol": "Y"})  # no size


def test_confirm_writes_ledger_and_holdings():
    order = desk.propose_order(_proposal())
    desk.confirm_order(order["id"], price=610.0, quantity=2.0, fees=6.45)
    holdings = desk.compute_holdings()
    assert holdings["SXR8.DE"]["quantity"] == 2.0
    assert holdings["SXR8.DE"]["avg_price"] == 610.0
    orders = desk.load_orders()
    assert orders[0]["status"] == "confirmed"


def test_confirm_matches_open_order_by_symbol():
    desk.propose_order(_proposal())
    order = desk.confirm_order("SXR8", price=600.0, quantity=1.0)
    assert order["symbol"] == "SXR8.DE"


def test_fifo_sell_and_long_term_lot_flag():
    old = datetime(2025, 1, 10, tzinfo=timezone.utc).isoformat()
    recent = datetime(2026, 8, 1, tzinfo=timezone.utc).isoformat()
    desk.append_ledger({"order_id": "a", "source": "s", "action": "buy", "symbol": "SXR8.DE",
                        "currency": "EUR", "price": 500.0, "quantity": 2.0, "fees": 0,
                        "executed_at": old, "recorded_at": old})
    desk.append_ledger({"order_id": "b", "source": "s", "action": "buy", "symbol": "SXR8.DE",
                        "currency": "EUR", "price": 600.0, "quantity": 1.0, "fees": 0,
                        "executed_at": recent, "recorded_at": recent})
    desk.append_ledger({"order_id": "c", "source": "s", "action": "sell", "symbol": "SXR8.DE",
                        "currency": "EUR", "price": 620.0, "quantity": 1.5, "fees": 0,
                        "executed_at": recent, "recorded_at": recent})
    now = datetime(2026, 8, 18, tzinfo=timezone.utc)
    h = desk.compute_holdings(now=now)["SXR8.DE"]
    assert h["quantity"] == 1.5           # 3 bought, 1.5 sold FIFO
    assert h["long_term_quantity"] == 0.5  # remainder of the 2025 lot


def test_expiry_marks_stale_orders():
    order = desk.propose_order(_proposal(expires_at="2026-01-01T00:00:00+00:00"))
    expired = desk.expire_stale_orders(datetime(2026, 2, 1, tzinfo=timezone.utc))
    assert [o["id"] for o in expired] == [order["id"]]


def test_inbox_ingestion_and_rejection(desk_tmpdir):
    inbox = desk_tmpdir / "inbox"
    inbox.mkdir()
    (inbox / "good.json").write_text(json.dumps(_proposal(source="aurel2_test", symbol="XLK")))
    (inbox / "bad.json").write_text(json.dumps({"source": "x"}))
    created = desk.ingest_inbox()
    assert len(created) == 1 and created[0]["symbol"] == "XLK"
    assert not (inbox / "good.json").exists()
    assert (inbox / "bad.rejected").exists()


CORE = {"core": {"symbol": "SXR8.DE", "currency": "EUR", "monthly_amount": 500,
                 "min_ticket": 700, "index_proxy": "SPY"},
        "runtime": {"send_slack": False, "send_ntfy": False},
        "notifications": {}}


def test_dca_carries_over_below_min_ticket_then_orders():
    # July: 500 < 700 -> carryover, no order (first trading day Wed Jul 1)
    assert desk.run_core_dca(CORE, now=datetime(2026, 7, 1, 8, tzinfo=timezone.utc)) is None
    assert desk.load_desk_state()["dca_carryover"] == 500
    # August: 500 + 500 = 1000 >= 700 -> order (first trading day Mon Aug 3)
    order = desk.run_core_dca(CORE, now=datetime(2026, 8, 3, 8, tzinfo=timezone.utc),
                              price_fn=lambda s: 610.0)
    assert order and order["notional"] == 1000
    assert desk.load_desk_state()["dca_carryover"] == 0


def test_dca_is_idempotent_per_month_and_gated_to_first_trading_day():
    # Aug 4 2026 is not the first trading day (Aug 3 was)
    assert desk.run_core_dca(CORE, now=datetime(2026, 8, 4, 8, tzinfo=timezone.utc)) is None
    order = desk.run_core_dca(dict(CORE, core=dict(CORE["core"], monthly_amount=1500)),
                              now=datetime(2026, 8, 3, 8, tzinfo=timezone.utc),
                              price_fn=lambda s: 610.0)
    assert order is not None
    # second run same month: nothing
    assert desk.run_core_dca(CORE, now=datetime(2026, 8, 5, 8, tzinfo=timezone.utc)) is None


def test_guard_fires_once_per_threshold_per_episode():
    cfg = dict(CORE)
    hist_down = [100.0] * 50 + [78.0]          # -22% drawdown
    assert desk.run_core_guard(cfg, history_fn=lambda s: hist_down) == ["-0.10", "-0.20"]
    assert desk.run_core_guard(cfg, history_fn=lambda s: hist_down) == []   # no repeat
    hist_worse = [100.0] * 50 + [68.0]         # -32%
    assert desk.run_core_guard(cfg, history_fn=lambda s: hist_worse) == ["-0.30"]
    hist_newhigh = [100.0] * 50 + [101.0, 88.0]  # new high resets, then -12.9%
    assert desk.run_core_guard(cfg, history_fn=lambda s: hist_newhigh) == ["-0.10"]


def test_order_alert_mentions_confirm_command():
    order = desk.propose_order(_proposal())
    text = desk.format_order_alert(order)
    assert "desk_confirm" in text and "SXR8.DE" in text
