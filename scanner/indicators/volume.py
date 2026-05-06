import pandas as pd
import ta
from .base import BaseIndicator
from .registry import register


@register(group="volume")
class OBVIndicator(BaseIndicator):
    def score(self, ohlcv: pd.DataFrame) -> tuple[float, str]:
        if len(ohlcv) < 30:
            return 5.0, "Insufficient data for OBV."

        obv = ta.volume.OnBalanceVolumeIndicator(
            close=ohlcv["Close"], volume=ohlcv["Volume"]
        ).on_balance_volume()

        obv_ema = obv.ewm(span=20).mean()
        obv_now = obv.iloc[-1]
        obv_ema_now = obv_ema.iloc[-1]
        obv_20d_ago = obv.iloc[-20]

        trend_up = obv_now > obv_20d_ago
        above_ema = obv_now > obv_ema_now

        if trend_up and above_ema:
            points = 9.0
            reasoning = "OBV rising and above its EMA — strong institutional buying (money flowing in)."
        elif trend_up:
            points = 6.0
            reasoning = "OBV rising but below its EMA — moderate buying interest."
        elif above_ema:
            points = 5.0
            reasoning = "OBV above EMA but declining — buying may be fading."
        else:
            points = 2.0
            reasoning = "OBV falling and below EMA — distribution (money flowing out)."

        return points, reasoning


@register(group="volume")
class RelativeVolumeIndicator(BaseIndicator):
    def score(self, ohlcv: pd.DataFrame) -> tuple[float, str]:
        if len(ohlcv) < 21:
            return 5.0, "Insufficient data for relative volume."

        avg_volume = ohlcv["Volume"].iloc[-21:-1].mean()
        today_volume = ohlcv["Volume"].iloc[-1]

        if avg_volume == 0:
            return 5.0, "Average volume is zero — cannot calculate relative volume."

        rvol = today_volume / avg_volume

        if rvol >= 2.5:
            points = 10.0
            label = f"{rvol:.1f}x average — exceptional volume confirming the move"
        elif rvol >= 1.5:
            points = 8.0
            label = f"{rvol:.1f}x average — strong volume confirmation"
        elif rvol >= 1.0:
            points = 6.0
            label = f"{rvol:.1f}x average — average volume, adequate conviction"
        elif rvol >= 0.7:
            points = 4.0
            label = f"{rvol:.1f}x average — below-average volume, weak conviction"
        else:
            points = 2.0
            label = f"{rvol:.1f}x average — very low volume, move lacks confirmation"

        return points, f"Relative volume at {label}."
