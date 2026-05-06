import pandas as pd
import ta
from .base import BaseIndicator
from .registry import register


@register(group="volatility")
class BollingerBandsIndicator(BaseIndicator):
    def score(self, ohlcv: pd.DataFrame) -> tuple[float, str]:
        if len(ohlcv) < 25:
            return 5.0, "Insufficient data for Bollinger Bands."

        close = ohlcv["Close"]
        bb = ta.volatility.BollingerBands(close=close, window=20, window_dev=2)
        bb_high = bb.bollinger_hband().iloc[-1]
        bb_low = bb.bollinger_lband().iloc[-1]
        bb_mid = bb.bollinger_mavg().iloc[-1]
        bb_width = bb.bollinger_wband().iloc[-1]
        bb_pct = bb.bollinger_pband().iloc[-1]
        prev_width = bb.bollinger_wband().iloc[-6:-1].mean()
        last = close.iloc[-1]

        squeezing = bb_width < prev_width
        parts = []

        if bb_pct < 0.2:
            points = 7.0
            parts.append(f"price near lower band (${bb_low:.2f}) — potential bounce zone")
        elif bb_pct > 0.8:
            points = 3.0
            parts.append(f"price near upper band (${bb_high:.2f}) — extended, watch for pullback")
        else:
            points = 6.0
            parts.append(f"price mid-band (${bb_mid:.2f}) — neutral positioning")

        if squeezing:
            points = min(10.0, points + 2)
            parts.append("bands squeezing — potential breakout setup forming")
        else:
            parts.append("bands expanding — volatility already elevated")

        return points, "Bollinger: " + "; ".join(parts) + "."


@register(group="volatility")
class ATRIndicator(BaseIndicator):
    def score(self, ohlcv: pd.DataFrame) -> tuple[float, str]:
        if len(ohlcv) < 20:
            return 5.0, "Insufficient data for ATR."

        close = ohlcv["Close"]
        atr = ta.volatility.AverageTrueRange(
            high=ohlcv["High"], low=ohlcv["Low"], close=close, window=14
        ).average_true_range()

        atr_now = atr.iloc[-1]
        atr_20d_avg = atr.iloc[-20:].mean()
        atr_pct = atr_now / close.iloc[-1] * 100

        rising = atr_now > atr_20d_avg

        if atr_pct < 1.0:
            points = 7.0
            label = f"ATR at {atr_pct:.1f}% of price — low volatility, manageable risk"
        elif atr_pct < 2.5:
            points = 6.0
            label = f"ATR at {atr_pct:.1f}% of price — moderate volatility"
        elif atr_pct < 4.0:
            points = 4.0
            label = f"ATR at {atr_pct:.1f}% of price — elevated volatility, wider stops needed"
        else:
            points = 2.0
            label = f"ATR at {atr_pct:.1f}% of price — very high volatility, use caution"

        trend = " and rising (volatility expanding)" if rising else " and stable/falling"
        return points, label + trend + "."
