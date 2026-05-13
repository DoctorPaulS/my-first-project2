import os

MAX_WATCHLIST_SIZE = 25

DEFAULT_THRESHOLDS = {
    "BUY": 75,
    "WATCH CAREFULLY": 55,
    "HOLD": 35,
    "REDUCE": 25,
    "EXIT": 0,
}

DEFAULT_GROUP_WEIGHTS = {
    "trend": 0.30,
    "momentum": 0.25,
    "volume": 0.20,
    "volatility": 0.15,
    "candlesticks": 0.10,
}

SIGNAL_EMOJI = {
    "BUY": "🟢",
    "WATCH CAREFULLY": "👀",
    "HOLD": "🟡",
    "REDUCE": "🔴",
    "EXIT": "🚨",
}

SP500_WIKIPEDIA_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
SP400_WIKIPEDIA_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_400_companies"

MARKET_OPEN_HOUR_ET = 9
MARKET_OPEN_MINUTE_ET = 30
MARKET_CLOSE_HOUR_ET = 16

SCAN_LOOKBACK_PERIOD = "6mo"
EARNINGS_WARNING_DAYS = 7
EARNINGS_CRITICAL_DAYS = 3
ALERTS_EXPIRE_DAYS = 7
PORTFOLIO_CACHE_SECONDS = 60


def utc_to_et(utc_str: str) -> str:
    """Convert an ISO UTC timestamp string to ET display string (e.g. '2026-05-13 09:35 ET')."""
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo
    try:
        dt = datetime.fromisoformat(utc_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        et = dt.astimezone(ZoneInfo("America/New_York"))
        return et.strftime("%Y-%m-%d %H:%M ET")
    except Exception:
        return utc_str[:16].replace("T", " ")


def get_secret(key: str) -> str:
    """Get a secret from Streamlit secrets (in app) or environment variables (in scanner)."""
    try:
        import streamlit as st
        return st.secrets[key]
    except Exception:
        return os.environ.get(key, "")
