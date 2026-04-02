"""Market coverage and tradability mapping for Aurel3."""

from __future__ import annotations


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
}

DEFAULT_US = {"exchange": "USA", "region": "USA", "accessible": True, "preference": 2}
DEFAULT_CRYPTO = {"exchange": "CRYPTO", "region": "Global", "accessible": True, "preference": 1}
DEFAULT_UNKNOWN = {"exchange": "UNKNOWN", "region": "Unknown", "accessible": False, "preference": 0}


def infer_market_profile(ticker: str) -> dict:
    if ticker.endswith(".X"):
        return DEFAULT_CRYPTO.copy()

    if "." in ticker:
        suffix = ticker.split(".")[-1].upper()
        profile = MARKET_MAP.get(suffix)
        if profile:
            return profile.copy()

    if ticker.isupper():
        return DEFAULT_US.copy()

    return DEFAULT_UNKNOWN.copy()
