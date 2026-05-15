"""
Exit manager — runs every morning before the auto trader to:
1. Place GTC stop-loss for any open position missing one
2. Close positions with REDUCE/EXIT signals
3. Sell 50% at Target 1, move stop to breakeven, close remainder at Target 2

Run with: python -m scanner.exit_manager
"""
import sys
import logging
import requests
from datetime import datetime, timezone
from db.client import get_db
from config import get_secret
from scanner.exit_targets import calc_exit_targets
from scanner.data_fetcher import fetch_ohlcv

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

BASE         = "https://paper-api.alpaca.markets/v2"
EXIT_SIGNALS = {"REDUCE", "EXIT"}


def _headers(account: str = "auto") -> dict:
    if account == "claude":
        return {
            "APCA-API-KEY-ID":     get_secret("ALPACA_CLAUDE_API_KEY"),
            "APCA-API-SECRET-KEY": get_secret("ALPACA_CLAUDE_SECRET_KEY"),
        }
    return {
        "APCA-API-KEY-ID":     get_secret("ALPACA_AUTO_API_KEY"),
        "APCA-API-SECRET-KEY": get_secret("ALPACA_AUTO_SECRET_KEY"),
    }


def _get(path: str, headers: dict, params: dict = None):
    r = requests.get(f"{BASE}{path}", headers=headers, params=params, timeout=10)
    r.raise_for_status()
    return r.json()


def _post(path: str, headers: dict, body: dict) -> dict:
    r = requests.post(f"{BASE}{path}", headers=headers, json=body, timeout=10)
    if not r.ok:
        raise Exception(f"{r.status_code}: {r.text}")
    return r.json()


def _delete(path: str, headers: dict) -> None:
    r = requests.delete(f"{BASE}{path}", headers=headers, timeout=10)
    if not r.ok:
        raise Exception(f"{r.status_code}: {r.text}")


def _get_positions(headers: dict) -> list[dict]:
    return _get("/positions", headers)


def _get_open_orders(headers: dict) -> dict[str, list]:
    orders = _get("/orders", headers, {"status": "open", "limit": 500})
    by_ticker: dict[str, list] = {}
    for o in orders:
        by_ticker.setdefault(o["symbol"], []).append(o)
    return by_ticker


def _has_active_stop(ticker: str, open_orders: dict) -> bool:
    return any(
        o.get("side") == "sell" and o.get("type") in ("stop", "stop_limit")
        for o in open_orders.get(ticker, [])
    )


def _cancel_open_orders(ticker: str, open_orders: dict, headers: dict) -> None:
    for o in open_orders.get(ticker, []):
        try:
            _delete(f"/orders/{o['id']}", headers)
        except Exception as e:
            log.warning(f"    Could not cancel order {o['id']}: {e}")


def _place_gtc_stop(ticker: str, qty: int, stop_price: float, headers: dict) -> dict:
    return _post("/orders", headers, {
        "symbol":        ticker,
        "qty":           str(qty),
        "side":          "sell",
        "type":          "stop",
        "time_in_force": "gtc",
        "stop_price":    str(round(stop_price, 2)),
    })


def _close_position(ticker: str, qty: int, headers: dict) -> dict:
    return _post("/orders", headers, {
        "symbol":        ticker,
        "qty":           str(qty),
        "side":          "sell",
        "type":          "market",
        "time_in_force": "day",
    })


def _get_latest_signals(db) -> dict:
    try:
        latest = (
            db.table("scan_results")
            .select("scanned_at")
            .order("scanned_at", desc=True)
            .limit(1)
            .execute()
        )
        if not latest.data:
            return {}
        scan_time = latest.data[0]["scanned_at"]
        rows = (
            db.table("scan_results")
            .select("ticker,score,signal")
            .eq("scanned_at", scan_time)
            .execute()
        )
        return {r["ticker"]: r for r in rows.data}
    except Exception:
        return {}


def _get_price_targets(db, ticker: str) -> dict | None:
    try:
        res = db.table("price_targets").select("*").eq("ticker", ticker).execute()
        return res.data[0] if res.data else None
    except Exception:
        return None


def _log_exit(db, record: dict) -> None:
    try:
        db.table("auto_trades").insert(record).execute()
    except Exception as e:
        log.warning(f"  Could not log exit: {e}")


def _calc_stop(ticker: str, current_price: float) -> float:
    try:
        ohlcv = fetch_ohlcv(ticker, period="1y")
        return round(calc_exit_targets(ohlcv)["stop"], 2)
    except Exception:
        return round(current_price * 0.92, 2)


def _run_for_account(account_name: str, headers: dict, db) -> None:
    log.info(f"  [{account_name}] Checking positions...")
    positions = _get_positions(headers)

    if not positions:
        log.info(f"  [{account_name}] No open positions.")
        return

    open_orders = _get_open_orders(headers)
    signals     = _get_latest_signals(db)
    log.info(f"  [{account_name}] {len(positions)} positions found.")

    for pos in positions:
        ticker        = pos["symbol"]
        qty           = float(pos["qty"])
        current_price = float(pos["current_price"])
        cost_basis    = float(pos["cost_basis"])
        entry_price   = cost_basis / qty

        sig_data = signals.get(ticker, {})
        signal   = sig_data.get("signal", "")
        score    = float(sig_data.get("score", 0))

        # ── 1. Signal-based full exit ─────────────────────────────────────
        if signal in EXIT_SIGNALS:
            log.info(f"  [{account_name}] {ticker} {signal} (score={score:.0f}) → closing")
            try:
                _cancel_open_orders(ticker, open_orders, headers)
                _close_position(ticker, int(qty), headers)
                _log_exit(db, {
                    "ticker": ticker, "score": score, "signal": signal,
                    "order_type": "market", "qty": int(qty),
                    "status": "exit_signal",
                    "traded_at": datetime.now(timezone.utc).isoformat(),
                })
                log.info(f"  [{account_name}] {ticker} closed")
            except Exception as e:
                log.error(f"  [{account_name}] {ticker} close failed: {e}")
            continue

        # ── 2. Price target exits ─────────────────────────────────────────
        saved = _get_price_targets(db, ticker)
        stop  = saved["stop_loss"] if saved else _calc_stop(ticker, current_price)

        if saved:
            t1           = saved["target1"]
            t2           = saved["target2"]
            t1_triggered = saved.get("target1_triggered", False)
            t2_triggered = saved.get("target2_triggered", False)

            if not t2_triggered and current_price >= t2:
                log.info(f"  [{account_name}] {ticker} hit T2 (${t2:.2f}) → closing")
                try:
                    _cancel_open_orders(ticker, open_orders, headers)
                    _close_position(ticker, int(qty), headers)
                    db.table("price_targets").update({"target2_triggered": True}).eq("ticker", ticker).execute()
                    _log_exit(db, {
                        "ticker": ticker, "qty": int(qty), "order_type": "market",
                        "status": "target2_hit",
                        "traded_at": datetime.now(timezone.utc).isoformat(),
                    })
                    log.info(f"  [{account_name}] {ticker} closed at T2")
                except Exception as e:
                    log.error(f"  [{account_name}] {ticker} T2 exit failed: {e}")
                continue

            if not t1_triggered and current_price >= t1:
                half = max(1, int(qty / 2))
                log.info(f"  [{account_name}] {ticker} hit T1 (${t1:.2f}) → selling {half} shares")
                try:
                    _close_position(ticker, half, headers)
                    new_stop = round(entry_price, 2)
                    db.table("price_targets").update({
                        "target1_triggered": True, "stop_loss": new_stop,
                    }).eq("ticker", ticker).execute()
                    _cancel_open_orders(ticker, open_orders, headers)
                    _place_gtc_stop(ticker, int(qty - half), new_stop, headers)
                    _log_exit(db, {
                        "ticker": ticker, "qty": half, "order_type": "market",
                        "status": "target1_hit",
                        "traded_at": datetime.now(timezone.utc).isoformat(),
                    })
                    log.info(f"  [{account_name}] {ticker} half sold, breakeven stop ${new_stop:.2f}")
                except Exception as e:
                    log.error(f"  [{account_name}] {ticker} T1 exit failed: {e}")
                continue

        # ── 3. Ensure GTC stop exists ─────────────────────────────────────
        if _has_active_stop(ticker, open_orders):
            log.info(f"  [{account_name}] {ticker} stop OK")
        else:
            log.info(f"  [{account_name}] {ticker} no active stop → placing GTC stop at ${stop:.2f}")
            try:
                _place_gtc_stop(ticker, int(qty), stop, headers)
                log.info(f"  [{account_name}] {ticker} GTC stop placed at ${stop:.2f}")
            except Exception as e:
                log.error(f"  [{account_name}] {ticker} stop placement failed: {e}")


def run_exit_manager() -> None:
    log.info("Starting exit manager...")
    db = get_db()

    _run_for_account("auto",   _headers("auto"),   db)
    _run_for_account("claude", _headers("claude"),  db)

    log.info("Exit manager complete.")


if __name__ == "__main__":
    run_exit_manager()
