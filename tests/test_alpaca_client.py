# tests/test_alpaca_client.py
import pytest
from unittest.mock import MagicMock, patch
from alpaca_client import get_positions, get_account, get_portfolio_history


def _mock_trading_client():
    mock = MagicMock()
    pos = MagicMock()
    pos.symbol = "AAPL"
    pos.qty = "10"
    pos.current_price = "175.00"
    pos.market_value = "1750.00"
    pos.unrealized_pl = "50.00"
    pos.unrealized_plpc = "0.029"
    pos.cost_basis = "1700.00"
    mock.get_all_positions.return_value = [pos]

    acct = MagicMock()
    acct.portfolio_value = "50000.00"
    acct.buying_power = "25000.00"
    acct.cash = "10000.00"
    mock.get_account.return_value = acct

    return mock


def test_get_positions_returns_list(monkeypatch):
    mock_client = _mock_trading_client()
    monkeypatch.setattr("alpaca_client._get_trading_client", lambda: mock_client)
    positions = get_positions()
    assert isinstance(positions, list)
    assert positions[0]["symbol"] == "AAPL"
    assert positions[0]["qty"] == 10.0


def test_get_account_returns_dict(monkeypatch):
    mock_client = _mock_trading_client()
    monkeypatch.setattr("alpaca_client._get_trading_client", lambda: mock_client)
    acct = get_account()
    assert "portfolio_value" in acct
    assert acct["portfolio_value"] == 50000.0
