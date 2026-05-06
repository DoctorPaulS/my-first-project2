import yfinance as yf
import pandas as pd
from datetime import date
from typing import Optional


def fetch_ohlcv(ticker: str, period: str = "6mo") -> pd.DataFrame:
    """Download adjusted OHLCV data for one ticker via yfinance."""
    df = yf.download(ticker, period=period, auto_adjust=True, progress=False)
    if df.empty:
        raise ValueError(f"No data returned for {ticker}")
    # yfinance may return MultiIndex columns for a single ticker in some versions
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.droplevel(1)
    return df[["Open", "High", "Low", "Close", "Volume"]].copy()


def fetch_ohlcv_batch(tickers: list[str], period: str = "6mo") -> dict[str, pd.DataFrame]:
    """Download OHLCV for multiple tickers at once (much faster than one-by-one)."""
    raw = yf.download(
        tickers, period=period, auto_adjust=True,
        group_by="ticker", progress=False, threads=True,
    )
    result = {}
    for ticker in tickers:
        try:
            if ticker in raw.columns.get_level_values(0):
                df = raw[ticker][["Open", "High", "Low", "Close", "Volume"]].dropna()
                if not df.empty:
                    result[ticker] = df
        except Exception:
            continue
    return result


def fetch_earnings_date(ticker: str) -> Optional[date]:
    """Return the next upcoming earnings date for a ticker, or None."""
    try:
        stock = yf.Ticker(ticker)
        cal = stock.calendar
        if cal is None:
            return None
        if isinstance(cal, pd.DataFrame) and not cal.empty:
            val = cal.iloc[0].get("Earnings Date")
            if val is not None:
                return pd.Timestamp(val).date()
        if isinstance(cal, dict):
            val = cal.get("Earnings Date")
            if val:
                return pd.Timestamp(val[0] if isinstance(val, list) else val).date()
    except Exception:
        pass
    return None
