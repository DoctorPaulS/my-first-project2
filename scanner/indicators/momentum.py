import pandas as pd
import ta
from .base import BaseIndicator
from .registry import register


@register(group="momentum")
class MACDIndicator(BaseIndicator):
    def score(self, ohlcv: pd.DataFrame) -> tuple[float, str]:
        if len(ohlcv) < 35:
            return 5.0, "Insufficient data for MACD."

        close = ohlcv["Close"]
        macd_obj = ta.trend.MACD(close=close, window_slow=26, window_fast=12, window_sign=9)
        macd_line = macd_obj.macd().iloc[-1]
        signal_line = macd_obj.macd_signal().iloc[-1]
        histogram = macd_obj.macd_diff().iloc[-1]
        prev_histogram = macd_obj.macd_diff().iloc[-2]

        points = 5.0
        parts = []

        if macd_line > signal_line:
            points += 2
            parts.append("MACD above signal line (bullish)")
        else:
            points -= 2
            parts.append("MACD below signal line (bearish)")

        if histogram > 0 and histogram > prev_histogram:
            points += 2
            parts.append("histogram expanding upward (momentum building)")
        elif histogram > 0:
            points += 1
            parts.append("histogram positive but shrinking")
        elif histogram < 0 and histogram < prev_histogram:
            points -= 2
            parts.append("histogram expanding downward (momentum falling)")
        else:
            points -= 1
            parts.append("histogram negative")

        if macd_line > 0:
            points += 1
            parts.append("MACD above zero line")
        else:
            points -= 1
            parts.append("MACD below zero line")

        reasoning = "; ".join(parts) + "."
        return max(0.0, min(10.0, points)), reasoning


@register(group="momentum")
class RSIIndicator(BaseIndicator):
    def score(self, ohlcv: pd.DataFrame) -> tuple[float, str]:
        if len(ohlcv) < 20:
            return 5.0, "Insufficient data for RSI."

        rsi = ta.momentum.RSIIndicator(close=ohlcv["Close"], window=14).rsi().iloc[-1]

        if rsi > 80:
            points, label = 2.0, f"RSI at {rsi:.1f} — severely overbought, high reversal risk"
        elif rsi > 70:
            points, label = 4.0, f"RSI at {rsi:.1f} — overbought, watch for pullback"
        elif rsi >= 50:
            points, label = 8.0, f"RSI at {rsi:.1f} — healthy momentum, room to run"
        elif rsi >= 40:
            points, label = 6.0, f"RSI at {rsi:.1f} — neutral, no clear momentum edge"
        elif rsi >= 30:
            points, label = 4.0, f"RSI at {rsi:.1f} — weakening momentum"
        else:
            points, label = 2.0, f"RSI at {rsi:.1f} — oversold (potential bounce, but trend broken)"

        return points, label + "."
