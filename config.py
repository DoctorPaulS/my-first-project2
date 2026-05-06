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

MARKET_OPEN_HOUR_ET = 9
MARKET_OPEN_MINUTE_ET = 30
MARKET_CLOSE_HOUR_ET = 16

SCAN_LOOKBACK_PERIOD = "6mo"
EARNINGS_WARNING_DAYS = 7
EARNINGS_CRITICAL_DAYS = 3
ALERTS_EXPIRE_DAYS = 7
PORTFOLIO_CACHE_SECONDS = 60


def get_secret(key: str) -> str:
    """Get a secret from Streamlit secrets (in app) or environment variables (in scanner)."""
    try:
        import streamlit as st
        return st.secrets[key]
    except Exception:
        return os.environ.get(key, "")
