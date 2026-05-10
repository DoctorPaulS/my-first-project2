"""
Automated paper trading entry point.
Reads BUY signals from latest scan, sizes at 5% of portfolio,
places limit orders (or market for score >= 85), then sets stop-loss orders.

Run with: python -m scanner.auto_trader
"""
import sys
import logging
import requests
from datetime import datetime, timezone
from db.client import get_db
from config import get_secret

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

HIGH_CONVICTION_SCORE = 85
POSITION_SIZE_PCT     = 0.05   # 5% of portfolio per trade
LIMIT_BUFFER_PCT      = 0.005  # limit price = last price + 0.5%
BUY_SIGNALS           = {"BUY"}


def _base_url() -> str:
    return "https://paper-api.alpaca.markets/v2"


def _headers() -> dict:
    return {
        "APCA-API-KEY-ID":     get_secret("ALPACA_AUTO_API_KEY"),
        "APCA-API-SECRET-KEY": get_secret("ALPACA_AUTO_SECRET_KEY"),
    }


def _get(path: str, params: dict = None) -> dict | list:
    r = requests.get(f"{_base_url()}{path}", headers=_headers(), params=params)
    r.raise_for_status()
    return r.json()


def _post(path: str, body: dict) -> dict:
    r = requests.post(f"{_base_url()}{path}", headers=_headers(), json=body)
    if not r.ok:
        raise requests.HTTPError(f"{r.status_code} {r.reason}: {r.text}", response=r)
    return r.json()


def get_account() -> dict:
    return _get("/account")


def get_positions() -> set[str]:
    positions = _get("/positions")
    return {p["symbol"] for p in positions}


def get_latest_price(ticker: str) -> float | None:
    try:
        data = requests.get(
            f"https://data.alpaca.markets/v2/stocks/{ticker}/trades/latest",
            headers=_headers(),
        )
        data.raise_for_status()
        return float(data.json()["trade"]["p"])
    except Exception:
        return None


def place_buy_order(ticker: str, qty: int, order_type: str, limit_price: float | None, stop_price: float | None) -> dict:
    """Place a buy order with an attached stop-loss (OTO bracket)."""
    body = {
        "symbol":        ticker,
        "qty":           str(qty),
        "side":          "buy",
        "type":          order_type,
        "time_in_force": "day",
        "order_class":   "oto",
        "stop_loss":     {"stop_price": str(round(stop_price, 2))},
    }
    if order_type == "limit" and limit_price:
        body["limit_price"] = str(round(limit_price, 2))
    return _post("/orders", body)


def load_buy_signals(db) -> list[dict]:
    latest = (
        db.table("scan_results")
        .select("scanned_at")
        .order("scanned_at", desc=True)
        .limit(1)
        .execute()
    )
    if not latest.data:
        return []
    scan_time = latest.data[0]["scanned_at"]
    results = (
        db.table("scan_results")
        .select("ticker,score,signal,indicator_detail")
        .eq("scanned_at", scan_time)
        .in_("signal", list(BUY_SIGNALS))
        .order("score", desc=True)
        .execute()
    )
    return results.data


def log_trade(db, record: dict) -> None:
    db.table("auto_trades").insert(record).execute()


def run_auto_trader() -> None:
    log.info("Starting auto trader...")
    db = get_db()

    account  = get_account()
    portfolio_value = float(account["portfolio_value"])
    buying_power    = float(account["buying_power"])
    log.info(f"Portfolio: ${portfolio_value:,.2f} | Buying power: ${buying_power:,.2f}")

    existing_positions = get_positions()
    log.info(f"Current positions: {existing_positions or 'none'}")

    signals = load_buy_signals(db)
    log.info(f"BUY signals from latest scan: {len(signals)}")

    trade_budget = portfolio_value * POSITION_SIZE_PCT
    executed = 0

    for sig in signals:
        ticker = sig["ticker"]
        score  = float(sig["score"])

        if ticker in existing_positions:
            log.info(f"  SKIP {ticker} — already in position")
            continue

        if buying_power < trade_budget:
            log.warning(f"  STOP — insufficient buying power (${buying_power:,.2f} < ${trade_budget:,.2f})")
            break

        price = get_latest_price(ticker)
        if not price:
            log.warning(f"  SKIP {ticker} — could not fetch price")
            continue

        qty = int(trade_budget / price)
        if qty < 1:
            log.info(f"  SKIP {ticker} — price ${price:.2f} too high for budget ${trade_budget:.0f}")
            continue

        stop_price = round(price * 0.92, 2)  # 8% trailing stop fallback

        if score >= HIGH_CONVICTION_SCORE:
            order_type  = "market"
            limit_price = None
            log.info(f"  {ticker} score={score:.1f} → MARKET order {qty} shares")
        else:
            order_type  = "limit"
            limit_price = round(price * (1 + LIMIT_BUFFER_PCT), 2)
            log.info(f"  {ticker} score={score:.1f} → LIMIT ${limit_price:.2f} x {qty} shares, stop ${stop_price:.2f}")

        try:
            order = place_buy_order(ticker, qty, order_type, limit_price, stop_price)
            order_id = order.get("id", "unknown")
            log.info(f"  {ticker} order placed (with stop ${stop_price:.2f}): {order_id}")

            log_trade(db, {
                "ticker":       ticker,
                "score":        score,
                "signal":       sig["signal"],
                "order_type":   order_type,
                "qty":          qty,
                "limit_price":  limit_price,
                "stop_price":   stop_price,
                "order_id":     order_id,
                "status":       "placed",
                "traded_at":    datetime.now(timezone.utc).isoformat(),
            })

            buying_power -= trade_budget
            existing_positions.add(ticker)
            executed += 1

        except Exception as e:
            log.error(f"  {ticker} order failed: {e}")
            log_trade(db, {
                "ticker":     ticker,
                "score":      score,
                "signal":     sig["signal"],
                "order_type": order_type,
                "qty":        qty,
                "status":     "failed",
                "error":      str(e),
                "traded_at":  datetime.now(timezone.utc).isoformat(),
            })

    log.info(f"Auto trader complete. {executed} orders placed.")


if __name__ == "__main__":
    run_auto_trader()
