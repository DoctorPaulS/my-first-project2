from alpaca.trading.client import TradingClient
from config import get_secret


def _get_trading_client() -> TradingClient:
    api_key = get_secret("ALPACA_API_KEY")
    secret_key = get_secret("ALPACA_SECRET_KEY")
    paper_val = get_secret("ALPACA_PAPER")
    paper = paper_val.lower() != "false"  # default to paper=True unless explicitly set to "false"
    if not api_key or not secret_key:
        raise RuntimeError("ALPACA_API_KEY and ALPACA_SECRET_KEY must be set.")
    return TradingClient(api_key=api_key, secret_key=secret_key, paper=paper)


def get_positions() -> list[dict]:
    """Return all open Alpaca positions as plain dicts."""
    client = _get_trading_client()
    positions = client.get_all_positions()
    return [
        {
            "symbol": p.symbol,
            "qty": float(p.qty),
            "current_price": float(p.current_price),
            "market_value": float(p.market_value),
            "unrealized_pl": float(p.unrealized_pl),
            "unrealized_plpc": float(p.unrealized_plpc),
            "cost_basis": float(p.cost_basis),
        }
        for p in positions
    ]


def get_account() -> dict:
    """Return key account metrics as a plain dict."""
    client = _get_trading_client()
    a = client.get_account()
    return {
        "portfolio_value": float(a.portfolio_value),
        "buying_power": float(a.buying_power),
        "cash": float(a.cash),
    }


def get_portfolio_history(period: str = "1M") -> dict:
    """Return portfolio equity history for charting. Period: 1W, 1M, 3M, 6M, 1Y."""
    from alpaca.trading.requests import GetPortfolioHistoryRequest
    client = _get_trading_client()
    req = GetPortfolioHistoryRequest(period=period, timeframe="1D")
    history = client.get_portfolio_history(filter=req)
    return {
        "timestamps": history.timestamp,
        "equity": history.equity,
    }
