"""
Momentum scan — identifies stocks showing unusual price + volume breakouts.
Runs weekly across the full S&P 500 + 400 universe.

Scoring (0-100):
  40% volume surge  (today's vol / 20-day avg, capped at 5x)
  40% 5-day price change
  20% proximity to 52-week high
"""

import pandas as pd
import numpy as np


def score_momentum(ohlcv: pd.DataFrame) -> dict | None:
    """
    Compute a momentum score for a single ticker.
    Returns None if there is insufficient data.
    """
    if len(ohlcv) < 60:
        return None

    close  = ohlcv["Close"]
    volume = ohlcv["Volume"]

    current_price = float(close.iloc[-1])

    # Volume surge: today vs 20-day average (excluding today)
    avg_vol_20 = float(volume.iloc[-21:-1].mean())
    today_vol  = float(volume.iloc[-1])
    volume_surge = today_vol / avg_vol_20 if avg_vol_20 > 0 else 0.0

    # Price momentum
    price_5d  = float((close.iloc[-1] / close.iloc[-6])  - 1) if len(close) >= 6  else 0.0
    price_20d = float((close.iloc[-1] / close.iloc[-21]) - 1) if len(close) >= 21 else 0.0

    # Proximity to 52-week high
    high_52w = float(close.tail(252).max())
    pct_from_high = float((current_price - high_52w) / high_52w)  # 0 = at high, negative = below

    # --- Composite score (0-100) ---
    # Volume component: surge ratio capped at 5x → mapped to 0-40
    vol_score = min(volume_surge / 5.0, 1.0) * 40

    # 5-day price component: +10% = full score, negative = 0
    price_score = min(max(price_5d / 0.10, 0.0), 1.0) * 40

    # 52-week high proximity: within 2% of high = full score
    high_score = min(max((pct_from_high + 0.10) / 0.10, 0.0), 1.0) * 20

    momentum_score = vol_score + price_score + high_score

    return {
        "current_price":  current_price,
        "volume_surge":   round(volume_surge, 2),
        "price_change_5d":  round(price_5d * 100, 2),
        "price_change_20d": round(price_20d * 100, 2),
        "pct_from_high":  round(pct_from_high * 100, 2),
        "momentum_score": round(momentum_score, 1),
    }


def build_momentum_summary(result: dict) -> str:
    parts = []
    if result["volume_surge"] >= 2.0:
        parts.append(f"volume {result['volume_surge']:.1f}x above average")
    if result["price_change_5d"] >= 3.0:
        parts.append(f"up {result['price_change_5d']:.1f}% in 5 days")
    if result["pct_from_high"] >= -2.0:
        parts.append("near 52-week high")
    elif result["pct_from_high"] >= -5.0:
        parts.append(f"{abs(result['pct_from_high']):.1f}% from 52-week high")
    return "; ".join(parts) if parts else "moderate momentum"
