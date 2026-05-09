import pandas as pd
from config import SP500_WIKIPEDIA_URL, SP400_WIKIPEDIA_URL

_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; stock-advisor-bot/1.0)"}


def _fetch_tickers(url: str, symbol_col: str = "Symbol") -> list[str]:
    tables = pd.read_html(url, storage_options=_HEADERS)
    df = tables[0]
    return [t.replace(".", "-") for t in df[symbol_col].tolist()]


def get_sp500_tickers() -> list[str]:
    return _fetch_tickers(SP500_WIKIPEDIA_URL)


def get_sp400_tickers() -> list[str]:
    return _fetch_tickers(SP400_WIKIPEDIA_URL)


def get_universe_tickers() -> list[str]:
    """Combined S&P 500 + S&P 400, deduplicated."""
    sp500 = get_sp500_tickers()
    sp400 = get_sp400_tickers()
    seen = set(sp500)
    combined = sp500 + [t for t in sp400 if t not in seen]
    return combined
