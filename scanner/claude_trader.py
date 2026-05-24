"""
Claude-driven autonomous trader.
Feeds full portfolio context to Claude Sonnet and executes its decisions.
Runs 2x daily: 9:35am ET (open) and 1:00pm ET (midday reassessment).

Run with: python -m scanner.claude_trader
"""
import sys
import json
import time
import logging
import requests
import anthropic
import yfinance as yf
from datetime import datetime, timezone
from db.client import get_db, get_latest_signals
from config import get_secret
from scanner.ai_summary import fetch_headlines
from scanner.exit_targets import calc_atr_stop

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

BASE             = "https://paper-api.alpaca.markets/v2"
MAX_POSITION_PCT = 0.20   # Hard cap: no single position > 20% of portfolio
MIN_CASH_RESERVE = 0.10   # Keep at least 10% cash at all times
MAX_SECTOR_PCT   = 0.40   # No single sector > 40% of portfolio
BUY_CANDIDATE_MIN_SCORE = 60  # Only show Claude candidates above this score
MAX_CANDIDATES   = 15     # Cap buy candidates to avoid huge prompts


def _headers() -> dict:
    return {
        "APCA-API-KEY-ID":     get_secret("ALPACA_CLAUDE_API_KEY"),
        "APCA-API-SECRET-KEY": get_secret("ALPACA_CLAUDE_SECRET_KEY"),
    }


def _get(path: str, params: dict = None, retries: int = 3):
    for attempt in range(retries):
        try:
            r = requests.get(f"{BASE}{path}", headers=_headers(), params=params, timeout=30)
            r.raise_for_status()
            return r.json()
        except requests.exceptions.Timeout:
            if attempt == retries - 1:
                raise
            log.warning(f"Timeout on GET {path}, retrying ({attempt+1}/{retries})...")


def _post(path: str, body: dict, retries: int = 3) -> dict:
    for attempt in range(retries):
        try:
            r = requests.post(f"{BASE}{path}", headers=_headers(), json=body, timeout=30)
            if not r.ok:
                raise Exception(f"{r.status_code}: {r.text}")
            return r.json()
        except requests.exceptions.Timeout:
            if attempt == retries - 1:
                raise
            log.warning(f"Timeout on POST {path}, retrying ({attempt+1}/{retries})...")


def _delete(path: str) -> None:
    r = requests.delete(f"{BASE}{path}", headers=_headers(), timeout=30)
    if not r.ok:
        raise Exception(f"{r.status_code}: {r.text}")


def _get_account() -> dict:
    return _get("/account")


def _get_positions() -> list[dict]:
    return _get("/positions")


def _get_open_orders() -> list[dict]:
    return _get("/orders", {"status": "open", "limit": 500})


def _get_latest_price(ticker: str) -> float | None:
    try:
        r = requests.get(
            f"https://data.alpaca.markets/v2/stocks/{ticker}/trades/latest",
            headers=_headers(), timeout=5,
        )
        r.raise_for_status()
        return float(r.json()["trade"]["p"])
    except Exception:
        return None


def _place_order(ticker: str, qty: int, side: str, order_type: str = "market",
                 limit_price: float = None) -> dict:
    body = {
        "symbol":        ticker,
        "qty":           str(qty),
        "side":          side,
        "type":          order_type,
        "time_in_force": "day",
    }
    if order_type == "limit" and limit_price:
        body["limit_price"] = str(round(limit_price, 2))
    return _post("/orders", body)


def _place_buy_oto(ticker: str, qty: int, limit_price: float, stop_price: float) -> dict:
    """OTO bracket: limit buy with attached stop. Avoids 403 wash-trade on separate stop."""
    return _post("/orders", {
        "symbol":        ticker,
        "qty":           str(qty),
        "side":          "buy",
        "type":          "limit",
        "time_in_force": "day",
        "order_class":   "oto",
        "limit_price":   str(round(limit_price, 2)),
        "stop_loss":     {"stop_price": str(round(stop_price, 2))},
    })


def _place_gtc_stop(ticker: str, qty: int, stop_price: float) -> dict:
    return _post("/orders", {
        "symbol":        ticker,
        "qty":           str(qty),
        "side":          "sell",
        "type":          "stop",
        "time_in_force": "gtc",
        "stop_price":    str(round(stop_price, 2)),
    })



_sector_cache: dict[str, str] = {}

def _get_sector(ticker: str) -> str:
    if ticker not in _sector_cache:
        try:
            _sector_cache[ticker] = yf.Ticker(ticker).info.get("sector") or "Unknown"
        except Exception:
            _sector_cache[ticker] = "Unknown"
    return _sector_cache[ticker]




def _log_trade(db, record: dict) -> None:
    try:
        db.table("claude_trades").insert(record).execute()
    except Exception as e:
        log.warning(f"Could not log trade: {e}")


def _build_context(account: dict, positions: list, signals: dict,
                   open_orders: list) -> str:
    portfolio_value = float(account["portfolio_value"])
    buying_power    = float(account["buying_power"])
    cash            = float(account["cash"])
    cash_pct        = cash / portfolio_value * 100 if portfolio_value else 0

    # --- Current positions block ---
    open_order_tickers = {o["symbol"] for o in open_orders}
    pos_lines = []
    for p in positions:
        ticker      = p["symbol"]
        qty         = float(p["qty"])
        curr_price  = float(p["current_price"])
        cost_basis  = float(p["cost_basis"])
        entry_price = cost_basis / qty
        pnl_pct     = float(p["unrealized_plpc"]) * 100
        mkt_val     = float(p["market_value"])
        pct_of_port = mkt_val / portfolio_value * 100
        sig         = signals.get(ticker, {})
        signal      = sig.get("signal", "—")
        score       = sig.get("score", 0)
        reasoning   = sig.get("reasoning", "")
        headlines   = fetch_headlines(ticker)
        news_str    = "; ".join(headlines[:2]) if headlines else "No recent news"
        has_order   = "⚠ pending order" if ticker in open_order_tickers else ""

        pos_lines.append(
            f"  {ticker}: {int(qty)} shares | Entry ${entry_price:.2f} → Current ${curr_price:.2f} | "
            f"P&L {pnl_pct:+.1f}% | {pct_of_port:.1f}% of portfolio | "
            f"Signal: {signal} ({score:.0f}/100) {has_order}\n"
            f"    Reasoning: {reasoning}\n"
            f"    News: {news_str}"
        )

    positions_block = "\n".join(pos_lines) if pos_lines else "  No open positions."

    # --- Buy candidates block ---
    buy_candidates = sorted(
        [v for v in signals.values()
         if v.get("signal") in ("BUY", "WATCH CAREFULLY")
         and float(v.get("score", 0)) >= BUY_CANDIDATE_MIN_SCORE
         and v["ticker"] not in {p["symbol"] for p in positions}],
        key=lambda x: float(x.get("score", 0)),
        reverse=True,
    )[:MAX_CANDIDATES]

    cand_lines = []
    for c in buy_candidates:
        ticker    = c["ticker"]
        score     = float(c.get("score", 0))
        signal    = c.get("signal", "")
        reasoning = c.get("reasoning", "")
        headlines = fetch_headlines(ticker)
        news_str  = "; ".join(headlines[:2]) if headlines else "No recent news"
        price     = _get_latest_price(ticker)
        price_str = f"${price:.2f}" if price else "price unavailable"
        cand_lines.append(
            f"  {ticker}: {signal} ({score:.0f}/100) | Current {price_str}\n"
            f"    Reasoning: {reasoning}\n"
            f"    News: {news_str}"
        )

    candidates_block = "\n".join(cand_lines) if cand_lines else "  No strong candidates."

    # --- Sector exposure block ---
    sector_values: dict[str, float] = {}
    for p in positions:
        sector = _get_sector(p["symbol"])
        sector_values[sector] = sector_values.get(sector, 0.0) + float(p["market_value"])
    sector_lines = [
        f"  {s}: {v/portfolio_value*100:.1f}%{' ⚠ NEAR LIMIT' if v/portfolio_value >= 0.35 else ''}"
        for s, v in sorted(sector_values.items(), key=lambda x: x[1], reverse=True)
    ] if sector_values else ["  No positions yet."]
    sector_block = "\n".join(sector_lines)

    return f"""PORTFOLIO STATE — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}
Portfolio Value: ${portfolio_value:,.2f}
Cash: ${cash:,.2f} ({cash_pct:.1f}%)
Buying Power: ${buying_power:,.2f}

SECTOR EXPOSURE (max {MAX_SECTOR_PCT*100:.0f}% per sector):
{sector_block}

CURRENT POSITIONS ({len(positions)}):
{positions_block}

BUY CANDIDATES (not already held, score ≥ {BUY_CANDIDATE_MIN_SCORE}):
{candidates_block}"""


def _ask_claude(context: str) -> list[dict]:
    api_key = get_secret("ANTHROPIC_API_KEY")
    client  = anthropic.Anthropic(api_key=api_key)

    system = """You are an autonomous portfolio manager running a paper trading account.
Your goal is to maximize overall % return (wealth growth) with intelligent risk management.

You will receive a portfolio snapshot and must decide what actions to take RIGHT NOW.

Respond ONLY with a valid JSON object in this exact format:
{
  "market_assessment": "1-2 sentence view of current conditions",
  "decisions": [
    {
      "action": "buy",
      "ticker": "XXXX",
      "allocation_pct": 7.5,
      "reasoning": "Why buying this now"
    },
    {
      "action": "sell",
      "ticker": "XXXX",
      "reasoning": "Why exiting"
    },
    {
      "action": "trim",
      "ticker": "XXXX",
      "trim_pct": 50,
      "reasoning": "Why taking partial profits"
    }
  ],
  "portfolio_notes": "Overall strategy comment"
}

Hard rules you must follow:
- No single position > 20% of total portfolio value
- No single sector > 40% of total portfolio value — check the SECTOR EXPOSURE block before buying
- Keep at least 10% cash reserve at all times
- Only include tickers you want to ACT on (buy/sell/trim) — omit holds
- allocation_pct for buys = % of total portfolio value to deploy
- trim_pct = % of current shares to sell (e.g. 50 = sell half)
- Be selective — quality over quantity
- Consider momentum, signal strength, news sentiment, and portfolio balance
- Don't chase stocks already up significantly without strong catalyst"""

    prompt = f"""Here is your current portfolio state. Make your trading decisions now.

{context}

Respond with your JSON decisions."""

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = msg.content[0].text.strip()
    # Extract JSON if wrapped in code block
    if "```" in raw:
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw)


def _cancel_all_orders_for_ticker(ticker: str, orders_by_ticker: dict,
                                   max_wait: int = 5) -> bool:
    """Cancel all open orders for a ticker using a pre-fetched by-ticker dict.
    Polls by specific order ID (avoids Alpaca paper API's broken symbols filter).
    Returns True if all orders are cleared, False if still stuck after max_wait seconds."""
    ticker_orders = orders_by_ticker.get(ticker, [])
    if not ticker_orders:
        return True

    pending_ids = []
    for o in ticker_orders:
        oid = o["id"]
        try:
            _delete(f"/orders/{oid}")
            log.info(f"  Cancelled {o.get('type','?')} order {oid} for {ticker}")
            pending_ids.append(oid)
        except Exception as e:
            if "pending cancel" in str(e).lower():
                log.info(f"  Order {oid} for {ticker} already pending cancel — waiting")
                pending_ids.append(oid)
            else:
                log.warning(f"  Could not cancel order {oid} for {ticker}: {e}")

    if not pending_ids:
        return True

    # Poll each order ID directly — no broken symbols filter needed
    TERMINAL = {"cancelled", "filled", "expired", "done_for_day"}
    for i in range(max_wait):
        time.sleep(1.0)
        still_open = []
        for oid in pending_ids:
            try:
                o = _get(f"/orders/{oid}")
                if o.get("status") not in TERMINAL:
                    still_open.append(oid)
            except Exception:
                pass  # 404 = order is gone, treat as cleared
        if not still_open:
            return True
        pending_ids = still_open
        log.info(f"  [{i+1}/{max_wait}] Waiting for {ticker} orders to clear ({len(still_open)} remaining)...")

    log.warning(f"  Orders for {ticker} still held after {max_wait}s — skipping")
    return False


def _existing_stop_price(ticker: str, orders_by_ticker: dict) -> float | None:
    """Return the open stop price for a ticker from a pre-fetched by-ticker dict."""
    for o in orders_by_ticker.get(ticker, []):
        if o.get("side") == "sell" and o.get("type") in ("stop", "stop_limit"):
            sp = o.get("stop_price")
            if sp:
                return float(sp)
    return None


def _parse_related_orders(err_str: str) -> list:
    """Extract related_orders IDs from an Alpaca 403 error string."""
    try:
        json_part = err_str.split(":", 1)[1].strip()
        return json.loads(json_part).get("related_orders", [])
    except Exception:
        return []


def _force_close_position(ticker: str, qty: int = None) -> dict:
    """Use Alpaca's position-close endpoint — bypasses held_for_orders when order cancels are stuck."""
    params = {"qty": str(qty)} if qty is not None else None
    r = requests.delete(
        f"{BASE}/positions/{ticker}",
        headers=_headers(),
        params=params,
        timeout=30,
    )
    if not r.ok:
        raise Exception(f"position-close {r.status_code}: {r.text}")
    return r.json()


def _execute_decisions(decisions_response: dict, account: dict,
                       positions: list, db) -> None:
    portfolio_value = float(account["portfolio_value"])
    max_deployable  = portfolio_value * (1 - MIN_CASH_RESERVE)
    pos_map         = {p["symbol"]: p for p in positions}
    decisions       = decisions_response.get("decisions", [])

    log.info(f"Market assessment: {decisions_response.get('market_assessment', '')}")
    log.info(f"Portfolio notes: {decisions_response.get('portfolio_notes', '')}")
    log.info(f"Executing {len(decisions)} decisions...")

    # Re-fetch open orders here — Claude's API call takes ~30s, orders change
    # Use a by-ticker dict; avoid the broken Alpaca paper API symbols filter
    all_open = _get_open_orders()
    orders_by_ticker: dict[str, list] = {}
    for o in all_open:
        orders_by_ticker.setdefault(o["symbol"], []).append(o)
    log.info(f"  Open orders snapshot: {len(all_open)} orders across {len(orders_by_ticker)} tickers")

    for d in decisions:
        action = d.get("action", "").lower()
        ticker = d.get("ticker", "").upper()
        reason = d.get("reasoning", "")

        try:
            if action == "sell":
                pos = pos_map.get(ticker)
                if not pos:
                    log.warning(f"  SKIP sell {ticker} — not in positions")
                    continue
                qty = int(float(pos["qty"]))
                _cancel_all_orders_for_ticker(ticker, orders_by_ticker)
                try:
                    _place_order(ticker, qty, "sell")
                    log.info(f"  SELL {ticker} {qty} shares — {reason}")
                except Exception as sell_err:
                    related = _parse_related_orders(str(sell_err))
                    if not related:
                        raise
                    log.info(f"  {ticker} sell still blocked ({len(related)} held orders) — using position-close API")
                    try:
                        _force_close_position(ticker)
                        log.info(f"  SELL {ticker} via position-close — {reason}")
                    except Exception as fc_err:
                        raise Exception(f"sell failed and position-close also failed: {fc_err}") from sell_err
                _log_trade(db, {
                    "ticker": ticker, "action": "sell", "qty": qty,
                    "reasoning": reason, "status": "placed",
                    "traded_at": datetime.now(timezone.utc).isoformat(),
                })

            elif action == "trim":
                pos = pos_map.get(ticker)
                if not pos:
                    log.warning(f"  SKIP trim {ticker} — not in positions")
                    continue
                trim_pct  = float(d.get("trim_pct", 50)) / 100
                total_qty = int(float(pos["qty"]))
                trim_qty  = max(1, int(total_qty * trim_pct))
                remaining = total_qty - trim_qty

                # Preserve existing stop price before cancelling
                stop_price = _existing_stop_price(ticker, orders_by_ticker)
                if stop_price is None:
                    current_price = _get_latest_price(ticker) or float(pos["current_price"])
                    stop_price = calc_atr_stop(ticker, current_price)

                _cancel_all_orders_for_ticker(ticker, orders_by_ticker)
                try:
                    _place_order(ticker, trim_qty, "sell")
                    log.info(f"  TRIM {ticker} {trim_qty} shares ({d.get('trim_pct', 50):.0f}%) — {reason}")
                except Exception as trim_err:
                    related = _parse_related_orders(str(trim_err))
                    if not related:
                        raise
                    log.info(f"  {ticker} trim still blocked ({len(related)} held orders) — using position-close API")
                    try:
                        _force_close_position(ticker, qty=trim_qty)
                        log.info(f"  TRIM {ticker} {trim_qty} shares via position-close — {reason}")
                    except Exception as fc_err:
                        raise Exception(f"trim failed and position-close also failed: {fc_err}") from trim_err

                if remaining > 0:
                    _place_gtc_stop(ticker, remaining, stop_price)
                    log.info(f"  Re-placed GTC stop for {ticker} {remaining} shares @ ${stop_price:.2f}")

                _log_trade(db, {
                    "ticker": ticker, "action": "trim", "qty": trim_qty,
                    "reasoning": reason, "status": "placed",
                    "traded_at": datetime.now(timezone.utc).isoformat(),
                })

            elif action == "buy":
                alloc_pct = float(d.get("allocation_pct", 5)) / 100
                # Enforce max position size
                alloc_pct = min(alloc_pct, MAX_POSITION_PCT)
                dollar_amt = portfolio_value * alloc_pct

                # Check existing position size
                existing = pos_map.get(ticker)
                if existing:
                    existing_pct = float(existing["market_value"]) / portfolio_value
                    if existing_pct >= MAX_POSITION_PCT:
                        log.info(f"  SKIP buy {ticker} — already at max position size")
                        continue
                    dollar_amt = min(dollar_amt, (MAX_POSITION_PCT - existing_pct) * portfolio_value)

                price = _get_latest_price(ticker)
                if not price:
                    log.warning(f"  SKIP buy {ticker} — price unavailable")
                    continue

                qty = int(dollar_amt / price)
                if qty < 1:
                    log.info(f"  SKIP buy {ticker} — allocation too small for 1 share")
                    continue

                # OTO bracket: limit buy + attached stop (avoids wash-trade 403)
                limit_price = round(price * 1.005, 2)
                stop_price  = calc_atr_stop(ticker, price)
                _place_buy_oto(ticker, qty, limit_price, stop_price)
                log.info(f"  BUY {ticker} {qty} shares @ limit ${limit_price:.2f}, stop ${stop_price:.2f} — {reason}")

                _log_trade(db, {
                    "ticker": ticker, "action": "buy", "qty": qty,
                    "limit_price": limit_price, "stop_price": stop_price,
                    "allocation_pct": alloc_pct * 100,
                    "reasoning": reason, "status": "placed",
                    "traded_at": datetime.now(timezone.utc).isoformat(),
                })

            else:
                log.warning(f"  Unknown action '{action}' for {ticker}")

        except Exception as e:
            log.error(f"  Failed {action} {ticker}: {e}")
            _log_trade(db, {
                "ticker": ticker, "action": action,
                "reasoning": reason, "status": "failed", "error": str(e),
                "traded_at": datetime.now(timezone.utc).isoformat(),
            })


def run_claude_trader() -> None:
    log.info("Starting Claude autonomous trader...")
    db = get_db()

    account     = _get_account()
    positions   = _get_positions()
    open_orders = _get_open_orders()
    signals     = get_latest_signals(db, "ticker,score,signal,reasoning,indicator_detail")

    portfolio_value = float(account["portfolio_value"])
    log.info(f"Portfolio: ${portfolio_value:,.2f} | Positions: {len(positions)} | Signals loaded: {len(signals)}")

    log.info("Building context and calling Claude Sonnet...")
    context = _build_context(account, positions, signals, open_orders)

    try:
        response = _ask_claude(context)
    except Exception as e:
        log.error(f"Claude API call failed: {e}")
        return

    log.info(f"Claude returned {len(response.get('decisions', []))} decisions")
    _execute_decisions(response, account, positions, db)
    log.info("Claude trader complete.")


if __name__ == "__main__":
    run_claude_trader()
