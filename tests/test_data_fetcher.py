import pytest
import pandas as pd
import numpy as np
from unittest.mock import patch
from scanner.data_fetcher import fetch_ohlcv, fetch_earnings_date


def _make_mock_df():
    dates = pd.date_range(end="2024-12-31", periods=120, freq="B")
    close = 100 + np.cumsum(np.random.randn(120) * 0.5)
    return pd.DataFrame({
        "Open": close - 0.2,
        "High": close + 0.3,
        "Low": close - 0.3,
        "Close": close,
        "Volume": np.ones(120) * 1_000_000,
    }, index=dates)


def test_fetch_ohlcv_returns_dataframe():
    mock_df = _make_mock_df()
    with patch("yfinance.download", return_value=mock_df):
        result = fetch_ohlcv("AAPL")
    assert isinstance(result, pd.DataFrame)
    assert list(result.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert len(result) > 0


def test_fetch_ohlcv_raises_on_empty():
    with patch("yfinance.download", return_value=pd.DataFrame()):
        with pytest.raises(ValueError, match="No data"):
            fetch_ohlcv("INVALID")


def test_fetch_earnings_date_returns_none_on_failure():
    mock_ticker = type("T", (), {"calendar": None})()
    with patch("yfinance.Ticker", return_value=mock_ticker):
        result = fetch_earnings_date("AAPL")
    assert result is None
