"""Market coverage and tradability mapping for Aurel3."""

from __future__ import annotations

import json
from pathlib import Path


CONFIG_PATH = Path(__file__).parent / "config.json"

MARKET_MAP = {
    "RO": {"exchange": "BVB", "region": "Romania", "accessible": True, "preference": 3},
    "WA": {"exchange": "WSE", "region": "Poland", "accessible": True, "preference": 3},
    "DE": {"exchange": "XETRA", "region": "Germany", "accessible": True, "preference": 3},
    "DB": {"exchange": "XETRA", "region": "Germany", "accessible": True, "preference": 3},
    "PA": {"exchange": "EURONEXT Paris", "region": "EU", "accessible": True, "preference": 3},
    "AS": {"exchange": "EURONEXT Amsterdam", "region": "EU", "accessible": True, "preference": 3},
    "BR": {"exchange": "EURONEXT Brussels", "region": "EU", "accessible": True, "preference": 3},
    "MI": {"exchange": "Borsa Italiana", "region": "EU", "accessible": True, "preference": 3},
    "L": {"exchange": "LSE", "region": "UK", "accessible": True, "preference": 3},
    "SW": {"exchange": "SIX", "region": "Switzerland", "accessible": True, "preference": 2},
    "CO": {"exchange": "Copenhagen", "region": "Nordics", "accessible": True, "preference": 2},
    "HE": {"exchange": "Helsinki", "region": "Nordics", "accessible": True, "preference": 2},
    "ST": {"exchange": "Stockholm", "region": "Nordics", "accessible": True, "preference": 2},
    "OL": {"exchange": "Oslo", "region": "Nordics", "accessible": True, "preference": 2},
    "T": {"exchange": "JPX", "region": "Japan", "accessible": False, "preference": 0},
    "HK": {"exchange": "HKEX", "region": "Hong Kong", "accessible": False, "preference": 0},
    "SS": {"exchange": "SSE", "region": "China", "accessible": False, "preference": 0},
    "SZ": {"exchange": "SZSE", "region": "China", "accessible": False, "preference": 0},
    "KS": {"exchange": "KRX", "region": "South Korea", "accessible": False, "preference": 0},
    "TW": {"exchange": "TWSE", "region": "Taiwan", "accessible": False, "preference": 0},
    "AX": {"exchange": "ASX", "region": "Australia", "accessible": False, "preference": 0},
    "TO": {"exchange": "TSX", "region": "Canada", "accessible": False, "preference": 0},
    "V": {"exchange": "TSXV", "region": "Canada", "accessible": False, "preference": 0},
    "NS": {"exchange": "NSE", "region": "India", "accessible": False, "preference": 0},
    "BO": {"exchange": "BSE", "region": "India", "accessible": False, "preference": 0},
}

DEFAULT_US = {"exchange": "USA", "region": "USA", "accessible": True, "preference": 2}
DEFAULT_CRYPTO = {"exchange": "CRYPTO", "region": "Global", "accessible": False, "preference": 0}
DEFAULT_UNKNOWN = {"exchange": "UNKNOWN", "region": "Unknown", "accessible": False, "preference": 0}


def load_allowed_markets() -> set[str]:
    try:
        with open(CONFIG_PATH) as f:
            config = json.load(f)
    except Exception:
        return set()
    runtime = config.get("runtime", {})
    allowed = runtime.get("allowed_markets", [])
    return {str(item) for item in allowed}


def infer_market_profile(ticker: str) -> dict:
    if ticker.endswith(".X"):
        return DEFAULT_CRYPTO.copy()

    if "." in ticker:
        suffix = ticker.split(".")[-1].upper()
        profile = MARKET_MAP.get(suffix)
        if profile:
            return profile.copy()

    if ticker.isupper():
        profile = DEFAULT_US.copy()
    else:
        profile = DEFAULT_UNKNOWN.copy()

    allowed_markets = load_allowed_markets()
    if allowed_markets:
        profile["accessible"] = profile["exchange"] in allowed_markets
        if not profile["accessible"]:
            profile["preference"] = 0
    return profile
