"""
Daily portfolio brief generator.
Builds a structured summary for each position in both accounts.
Used by both send_brief.py (email) and the Daily Brief app page.
"""
import requests
import anthropic
from config import get_secret
from db.client import get_db
from scanner.ai_summary import fetch_headlines
from scanner.exit_targets import calc_exit_targets
from scanner.data_fetcher import fetch_ohlcv

BASE = "https://paper-api.alpaca.markets/v2"

SIGNAL_EMOJI = {
    "BUY": "🟢", "WATCH CAREFULLY": "👀",
    "HOLD": "🟡", "REDUCE": "🔴", "EXIT": "🚨",
}


def _headers(key: str, secret: str) -> dict:
    return {
        "APCA-API-KEY-ID":     get_secret(key),
        "APCA-API-SECRET-KEY": get_secret(secret),
    }


def _get_account(headers: dict) -> dict:
    try:
        r = requests.get(f"{BASE}/account", headers=headers, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception:
        return {}


def _get_positions(headers: dict) -> list[dict]:
    try:
        r = requests.get(f"{BASE}/positions", headers=headers, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception:
        return []


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
        result = db.table("price_targets").select("*").eq("ticker", ticker).execute()
        return result.data[0] if result.data else None
    except Exception:
        return None


def _ai_recommendation(
    ticker: str, signal: str, score: float,
    current_price: float, entry_price: float, pnl_pct: float,
    stop: float, t1: float, t2: float,
    headlines: list[str],
) -> str:
    api_key = get_secret("ANTHROPIC_API_KEY")
    if not api_key:
        return "AI summary unavailable — add ANTHROPIC_API_KEY to secrets."

    pct_to_stop = (stop - current_price) / current_price * 100
    pct_to_t1   = (t1   - current_price) / current_price * 100
    pct_to_t2   = (t2   - current_price) / current_price * 100
    news_block  = "\n".join(f"- {h}" for h in headlines) if headlines else "No recent headlines."

    prompt = f"""You are a concise stock portfolio advisor. Write a 2-3 sentence action-oriented daily brief for {ticker}.

Position:
- Signal: {signal} | Score: {score:.0f}/100
- Entry: ${entry_price:.2f} | Current: ${current_price:.2f} | P&L: {pnl_pct:+.1f}%
- Stop loss: ${stop:.2f} ({pct_to_stop:+.1f}% away)
- Target 1: ${t1:.2f} ({pct_to_t1:+.1f}% away)
- Target 2: ${t2:.2f} ({pct_to_t2:+.1f}% away)

Recent news:
{news_block}

Give a clear recommendation: hold, add, reduce, or exit. Mention the single most important risk or opportunity. Be direct — no disclaimers."""

    try:
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text
    except Exception as e:
        return f"AI unavailable: {e}"


def build_position_brief(pos: dict, signals: dict, db) -> dict:
    ticker       = pos["symbol"]
    qty          = float(pos["qty"])
    current_price = float(pos["current_price"])
    cost_basis   = float(pos["cost_basis"])
    entry_price  = cost_basis / qty
    pnl_pct      = float(pos["unrealized_plpc"]) * 100
    pnl_dollars  = float(pos["unrealized_pl"])

    sig_data = signals.get(ticker, {})
    signal   = sig_data.get("signal", "—")
    score    = float(sig_data.get("score", 0))

    saved = _get_price_targets(db, ticker)
    if saved:
        stop, t1, t2 = saved["stop_loss"], saved["target1"], saved["target2"]
    else:
        try:
            ohlcv = fetch_ohlcv(ticker, period="1y")
            calc  = calc_exit_targets(ohlcv)
            stop, t1, t2 = calc["stop"], calc["target1"], calc["target2"]
        except Exception:
            stop = current_price * 0.92
            t1   = current_price * 1.08
            t2   = current_price * 1.12

    headlines  = fetch_headlines(ticker)
    ai_summary = _ai_recommendation(
        ticker, signal, score,
        current_price, entry_price, pnl_pct,
        stop, t1, t2, headlines,
    )

    return {
        "ticker":        ticker,
        "signal":        signal,
        "signal_emoji":  SIGNAL_EMOJI.get(signal, ""),
        "score":         score,
        "qty":           int(qty),
        "current_price": current_price,
        "entry_price":   entry_price,
        "market_value":  float(pos["market_value"]),
        "pnl_pct":       pnl_pct,
        "pnl_dollars":   pnl_dollars,
        "stop":          stop,
        "target1":       t1,
        "target2":       t2,
        "pct_to_stop":   (stop - current_price) / current_price * 100,
        "pct_to_t1":     (t1   - current_price) / current_price * 100,
        "pct_to_t2":     (t2   - current_price) / current_price * 100,
        "headlines":     headlines,
        "ai_summary":    ai_summary,
    }


def build_account_brief(label: str, key: str, secret: str) -> dict:
    db        = get_db()
    headers   = _headers(key, secret)
    account   = _get_account(headers)
    positions = _get_positions(headers)
    signals   = _get_latest_signals(db)

    briefs = []
    for pos in positions:
        try:
            briefs.append(build_position_brief(pos, signals, db))
        except Exception as e:
            briefs.append({"ticker": pos.get("symbol", "?"), "error": str(e)})

    return {
        "label":           label,
        "portfolio_value": float(account.get("portfolio_value", 0)),
        "buying_power":    float(account.get("buying_power", 0)),
        "positions":       briefs,
    }


def build_full_brief() -> list[dict]:
    """Build briefs for both accounts. Returns list of two account dicts."""
    return [
        build_account_brief("👤 Your Account (Manual)", "ALPACA_API_KEY",      "ALPACA_SECRET_KEY"),
        build_account_brief("🤖 Algorithm Account",     "ALPACA_AUTO_API_KEY", "ALPACA_AUTO_SECRET_KEY"),
    ]
