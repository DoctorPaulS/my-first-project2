import requests
from config import get_secret


def _base_url() -> str:
    paper_val = get_secret("ALPACA_PAPER")
    paper = paper_val.lower() != "false"
    return "https://paper-api.alpaca.markets/v2" if paper else "https://api.alpaca.markets/v2"


def _headers() -> dict:
    return {
        "APCA-API-KEY-ID": get_secret("ALPACA_API_KEY"),
        "APCA-API-SECRET-KEY": get_secret("ALPACA_SECRET_KEY"),
    }


def get_positions() -> list[dict]:
    r = requests.get(f"{_base_url()}/positions", headers=_headers())
    r.raise_for_status()
    return [
        {
            "symbol": p["symbol"],
            "qty": float(p["qty"]),
            "current_price": float(p["current_price"]),
            "market_value": float(p["market_value"]),
            "unrealized_pl": float(p["unrealized_pl"]),
            "unrealized_plpc": float(p["unrealized_plpc"]),
            "cost_basis": float(p["cost_basis"]),
        }
        for p in r.json()
    ]


def get_account() -> dict:
    r = requests.get(f"{_base_url()}/account", headers=_headers())
    r.raise_for_status()
    a = r.json()
    return {
        "portfolio_value": float(a["portfolio_value"]),
        "buying_power": float(a["buying_power"]),
        "cash": float(a["cash"]),
    }


def get_portfolio_history(period: str = "1M") -> dict:
    timeframe = "15Min" if period == "1D" else "1D"
    r = requests.get(
        f"{_base_url()}/account/portfolio/history",
        params={"period": period, "timeframe": timeframe},
        headers=_headers(),
    )
    r.raise_for_status()
    data = r.json()
    return {
        "timestamps": data["timestamp"],
        "equity": data["equity"],
    }
