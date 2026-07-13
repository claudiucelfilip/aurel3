import io
import json

import market
import openclaw_import
import run
import signals


def wbd_lawsuit_item(**overrides):
    item = {
        "source_item_id": "news::ma::2026-07-13T16:48:05+03:00::Paramount WBD lawsuit",
        "market_relevant": True,
        "event_type": "merger_litigation",
        "theme_id": "m_and_a_corporate_action",
        "theme_label": "M&A and corporate action",
        "summary": "Twelve states sued to block the Paramount-WBD merger, increasing deal-completion risk.",
        "beneficiary_sectors": [],
        "hurt_sectors": ["media"],
        "direct_beneficiaries": ["WBD"],
        "secondary_beneficiaries": [],
        "ticker_impacts": [
            {
                "ticker": "WBD",
                "direction": "bearish",
                "rationale": "The suit reduces deal-completion probability.",
            }
        ],
        "time_horizon": "1-2 weeks",
        "durability": "medium",
        "confidence": "high",
        "actionability": "potentially_actionable",
        "reasoning_notes": "The named target is directly affected, but the legal catalyst is adverse.",
    }
    item.update(overrides)
    return item


def test_negative_direct_catalyst_does_not_seed_a_long_candidate():
    candidates = signals._candidate_universe({"news": [wbd_lawsuit_item()], "raw_social": []})

    assert all(candidate["ticker"] != "WBD" for candidate in candidates)


def test_legacy_wbd_payload_is_safely_classified_from_text():
    item = wbd_lawsuit_item()
    item.pop("ticker_impacts")

    assert signals._ticker_impact_direction(item, "WBD") == "bearish"
    assert signals._candidate_universe({"news": [item], "raw_social": []}) == []


def test_positive_direct_catalyst_still_seeds_candidate():
    item = wbd_lawsuit_item(
        summary="Regulators approved the transaction, increasing deal-completion certainty.",
        event_type="merger_approval",
        ticker_impacts=[
            {"ticker": "WBD", "direction": "bullish", "rationale": "Approval improves completion odds."}
        ],
    )

    candidates = signals._candidate_universe({"news": [item], "raw_social": []})

    assert candidates[0]["ticker"] == "WBD"
    assert candidates[0]["signal_direction"] == "bullish"


def test_manual_buy_records_unverified_user_price(monkeypatch, capsys):
    captured = {}
    monkeypatch.setattr(run, "find_latest_active_recommendation", lambda _ticker: None)
    monkeypatch.setattr(run, "get_stock_data", lambda _ticker: None)

    def fake_add_position(**kwargs):
        captured.update(kwargs)
        return {"original_theme_driver": "Manual thesis"}

    monkeypatch.setattr(run, "add_position", fake_add_position)

    run.cmd_buy("WBD", "27.42", "1.714")

    output = capsys.readouterr().out
    assert "Aurel3 simulated buy" in output
    assert "user-supplied entry price was not verified" in output
    assert captured["entry_price_source"] == "user_supplied"
    assert captured["entry_price_verification"] == "unverified"
    assert captured["shares"] == 1.714


def test_yahoo_chart_fallback_returns_wbd_quote(monkeypatch):
    class BrokenTicker:
        def __init__(self, _symbol):
            raise RuntimeError("transient yfinance client failure")

    closes = [20 + index * 0.1 for index in range(60)]
    payload = {
        "chart": {
            "result": [
                {
                    "meta": {
                        "regularMarketPrice": 27.18,
                        "chartPreviousClose": 26.90,
                        "regularMarketVolume": 8_000_000,
                        "regularMarketTime": 1783971480,
                        "timezone": "America/New_York",
                    },
                    "indicators": {"quote": [{"close": closes, "volume": [7_000_000] * 60}]},
                }
            ]
        }
    }

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self.close()

    monkeypatch.setattr(market.yf, "Ticker", BrokenTicker)
    monkeypatch.setattr(
        market,
        "urlopen",
        lambda _request, timeout: Response(json.dumps(payload).encode()),
    )

    data = market.get_stock_data("WBD")

    assert data["price"] == 27.18
    assert data["data_source"] == "yahoo_chart"
    assert data["as_of"] is not None


def test_interpreted_payload_requires_valid_ticker_direction():
    item = wbd_lawsuit_item(ticker_impacts=[{"ticker": "WBD", "direction": "up"}])
    batch = {"generated_at": "batch-1", "items": [{"id": item["source_item_id"]}]}
    payload = {"generated_at": "now", "source_batch_generated_at": "batch-1", "items": [item]}

    errors = openclaw_import.validate_payload(payload, batch=batch)

    assert any("invalid direction" in error for error in errors)
