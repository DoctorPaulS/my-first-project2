import pandas as pd
from config import SP500_WIKIPEDIA_URL


def get_sp500_tickers() -> list[str]:
    """Fetch the current S&P 500 ticker list from Wikipedia."""
    tables = pd.read_html(SP500_WIKIPEDIA_URL)
    df = tables[0]
    tickers = df["Symbol"].tolist()
    # yfinance uses dashes where Yahoo Finance uses dots (e.g. BRK-B not BRK.B)
    return [t.replace(".", "-") for t in tickers]
