# tests/test_universe.py
import pytest
from unittest.mock import patch, MagicMock
import pandas as pd
from scanner.universe import get_sp500_tickers


def test_get_sp500_tickers_returns_list():
    mock_df = pd.DataFrame({"Symbol": ["AAPL", "MSFT", "GOOG"]})
    with patch("pandas.read_html", return_value=[mock_df]):
        tickers = get_sp500_tickers()
    assert isinstance(tickers, list)
    assert "AAPL" in tickers
    assert "MSFT" in tickers


def test_get_sp500_tickers_replaces_dots_with_dashes():
    mock_df = pd.DataFrame({"Symbol": ["BRK.B", "BF.B"]})
    with patch("pandas.read_html", return_value=[mock_df]):
        tickers = get_sp500_tickers()
    assert "BRK-B" in tickers
    assert "BF-B" in tickers
