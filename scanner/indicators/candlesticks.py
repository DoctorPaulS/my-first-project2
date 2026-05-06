import pandas as pd
from .base import BaseIndicator
from .registry import register


def _body(df: pd.DataFrame) -> pd.Series:
    return (df["Close"] - df["Open"]).abs()

def _range(df: pd.DataFrame) -> pd.Series:
    return df["High"] - df["Low"]

def _is_bullish(df: pd.DataFrame) -> pd.Series:
    return df["Close"] > df["Open"]

def _is_bearish(df: pd.DataFrame) -> pd.Series:
    return df["Close"] < df["Open"]

def _lower_wick(df: pd.DataFrame) -> pd.Series:
    return df[["Open", "Close"]].min(axis=1) - df["Low"]

def _upper_wick(df: pd.DataFrame) -> pd.Series:
    return df["High"] - df[["Open", "Close"]].max(axis=1)


@register(group="candlesticks")
class CandlestickPatternIndicator(BaseIndicator):
    def score(self, ohlcv: pd.DataFrame) -> tuple[float, str]:
        if len(ohlcv) < 3:
            return 5.0, "Insufficient data for candlestick patterns."

        df = ohlcv.copy()
        found = []

        # --- Check last 3 candles for patterns ---
        last = df.iloc[-1]
        prev = df.iloc[-2]
        prev2 = df.iloc[-3]

        body_last = abs(last["Close"] - last["Open"])
        body_prev = abs(prev["Close"] - prev["Open"])
        range_last = last["High"] - last["Low"]
        lower_w = min(last["Open"], last["Close"]) - last["Low"]
        upper_w = last["High"] - max(last["Open"], last["Close"])

        # Bullish Engulfing
        if (prev["Close"] < prev["Open"] and
                last["Close"] > last["Open"] and
                last["Open"] <= prev["Close"] and
                last["Close"] >= prev["Open"]):
            found.append(("bullish", "Bullish engulfing candle"))

        # Bearish Engulfing
        if (prev["Close"] > prev["Open"] and
                last["Close"] < last["Open"] and
                last["Open"] >= prev["Close"] and
                last["Close"] <= prev["Open"]):
            found.append(("bearish", "Bearish engulfing candle"))

        # Hammer (bullish reversal)
        if (range_last > 0 and
                body_last / range_last < 0.35 and
                lower_w >= 2 * body_last and
                upper_w <= 0.1 * range_last):
            found.append(("bullish", "Hammer candle (bullish reversal signal)"))

        # Shooting Star (bearish reversal)
        if (range_last > 0 and
                body_last / range_last < 0.35 and
                upper_w >= 2 * body_last and
                lower_w <= 0.1 * range_last):
            found.append(("bearish", "Shooting star candle (bearish reversal signal)"))

        # Doji (indecision)
        if range_last > 0 and body_last / range_last < 0.1:
            found.append(("neutral", "Doji candle (market indecision)"))

        # Morning Star (3-candle bullish reversal)
        body_prev2 = abs(prev2["Close"] - prev2["Open"])
        if (prev2["Close"] < prev2["Open"] and
                body_prev < 0.5 * body_prev2 and
                last["Close"] > last["Open"] and
                last["Close"] > (prev2["Open"] + prev2["Close"]) / 2):
            found.append(("bullish", "Morning star pattern (3-candle bullish reversal)"))

        # Evening Star (3-candle bearish reversal)
        if (prev2["Close"] > prev2["Open"] and
                body_prev < 0.5 * body_prev2 and
                last["Close"] < last["Open"] and
                last["Close"] < (prev2["Open"] + prev2["Close"]) / 2):
            found.append(("bearish", "Evening star pattern (3-candle bearish reversal)"))

        if not found:
            return 5.0, "No significant candlestick pattern detected."

        bullish_count = sum(1 for sentiment, _ in found if sentiment == "bullish")
        bearish_count = sum(1 for sentiment, _ in found if sentiment == "bearish")
        names = "; ".join(name for _, name in found)

        if bullish_count > bearish_count:
            points = 7.0 + min(bullish_count - 1, 3.0)
        elif bearish_count > bullish_count:
            points = 3.0 - min(bearish_count - 1, 3.0)
        else:
            points = 5.0

        return max(0.0, min(10.0, points)), f"Pattern detected: {names}."
