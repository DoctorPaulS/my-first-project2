import pandas as pd
import ta
from .base import BaseIndicator
from .registry import register


@register(group="trend")
class EMATrendIndicator(BaseIndicator):
    def score(self, ohlcv: pd.DataFrame) -> tuple[float, str]:
        close = ohlcv["Close"]
        if len(close) < 200:
            return 5.0, "Insufficient history for EMA calculation (need 200+ days)."

        ema20 = ta.trend.EMAIndicator(close=close, window=20).ema_indicator().iloc[-1]
        ema50 = ta.trend.EMAIndicator(close=close, window=50).ema_indicator().iloc[-1]
        ema200 = ta.trend.EMAIndicator(close=close, window=200).ema_indicator().iloc[-1]
        last = close.iloc[-1]

        points = 0.0
        parts = []

        if last > ema20:
            points += 2
            parts.append(f"above 20 EMA (${ema20:.2f})")
        else:
            parts.append(f"below 20 EMA (${ema20:.2f})")

        if last > ema50:
            points += 3
            parts.append(f"above 50 EMA (${ema50:.2f})")
        else:
            parts.append(f"below 50 EMA (${ema50:.2f})")

        if last > ema200:
            points += 5
            parts.append(f"above 200 EMA (${ema200:.2f}) — long-term uptrend")
        else:
            parts.append(f"below 200 EMA (${ema200:.2f}) — long-term downtrend")

        reasoning = "Price is " + ", ".join(parts) + "."
        return min(points, 10.0), reasoning


@register(group="trend")
class ADXIndicator(BaseIndicator):
    def score(self, ohlcv: pd.DataFrame) -> tuple[float, str]:
        if len(ohlcv) < 30:
            return 5.0, "Insufficient data for ADX."

        adx_obj = ta.trend.ADXIndicator(
            high=ohlcv["High"], low=ohlcv["Low"], close=ohlcv["Close"], window=14
        )
        adx = adx_obj.adx().iloc[-1]
        adx_pos = adx_obj.adx_pos().iloc[-1]
        adx_neg = adx_obj.adx_neg().iloc[-1]

        if adx >= 40:
            points, strength = 10.0, "very strong"
        elif adx >= 25:
            points, strength = 7.0, "strong"
        elif adx >= 20:
            points, strength = 5.0, "moderate"
        else:
            points, strength = 2.0, "weak/choppy"

        direction = "bullish" if adx_pos > adx_neg else "bearish"
        reasoning = f"ADX at {adx:.1f} — {strength} trend with {direction} direction."
        return points, reasoning
