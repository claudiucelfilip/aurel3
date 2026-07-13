import pytest

import signals


def test_signal_scan_fails_closed_when_market_data_broadly_unavailable(monkeypatch):
    candidates = [
        {"ticker": ticker, "signal_origin": "interpreted_news", "signal_direct": True, "signal_summary": "x"}
        for ticker in ("AMD", "MOS", "SNDK", "FLNC")
    ]
    monkeypatch.setattr(signals, "_candidate_universe", lambda _items: candidates)
    monkeypatch.setattr(signals, "get_stock_data", lambda _ticker: None)

    with pytest.raises(signals.MarketDataCoverageError):
        signals.generate_signal_scan({"news": []})
