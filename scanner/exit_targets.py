import pandas as pd
from scanner.data_fetcher import fetch_ohlcv


def calc_exit_targets(ohlcv: pd.DataFrame) -> dict:
    """
    Calculate ATR-based stop loss and price targets from OHLCV data.

    Returns a dict with: stop, target1, target2, atr, resistance
    """
    close = ohlcv["Close"]
    high = ohlcv["High"]
    low = ohlcv["Low"]

    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    atr = tr.rolling(14).mean().iloc[-1]

    current_price = float(close.iloc[-1])
    atr = float(atr)

    stop = current_price - (1.5 * atr)
    risk = current_price - stop
    target1 = current_price + (2.0 * risk)
    target2 = current_price + (3.0 * risk)

    # Nearest overhead resistance: highest high in past 60 sessions
    resistance = float(high.tail(60).max())
    # If resistance is below current price, use target2 as fallback
    if resistance <= current_price:
        resistance = target2

    return {
        "current": current_price,
        "atr": atr,
        "stop": stop,
        "target1": target1,
        "target2": target2,
        "resistance": resistance,
        "risk_pct": (risk / current_price) * 100,
    }


def calc_atr_stop(ticker: str, price: float) -> float:
    """ATR-based stop at 1.5×ATR below price, clamped to 5–15% range."""
    try:
        ohlcv = fetch_ohlcv(ticker, period="1y")
        stop  = calc_exit_targets(ohlcv)["stop"]
        stop  = max(stop, price * 0.85)   # never more than 15% below
        stop  = min(stop, price * 0.95)   # never less than 5% below
        return round(stop, 2)
    except Exception:
        return round(price * 0.92, 2)     # fallback: 8%
