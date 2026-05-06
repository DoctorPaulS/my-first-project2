# tests/test_indicators.py
import pytest
from scanner.indicators.trend import EMATrendIndicator, ADXIndicator


def test_ema_uptrend_scores_high(uptrend_ohlcv):
    indicator = EMATrendIndicator()
    score, reasoning = indicator.score(uptrend_ohlcv)
    assert 0.0 <= score <= 10.0
    assert score >= 7.0, f"Expected high score in uptrend, got {score}"
    assert isinstance(reasoning, str)
    assert len(reasoning) > 0


def test_ema_downtrend_scores_low(downtrend_ohlcv):
    indicator = EMATrendIndicator()
    score, reasoning = indicator.score(downtrend_ohlcv)
    assert score <= 4.0, f"Expected low score in downtrend, got {score}"


def test_adx_returns_valid_score(uptrend_ohlcv):
    indicator = ADXIndicator()
    score, reasoning = indicator.score(uptrend_ohlcv)
    assert 0.0 <= score <= 10.0
    assert isinstance(reasoning, str)


from scanner.indicators.momentum import MACDIndicator, RSIIndicator


def test_macd_returns_valid_score(uptrend_ohlcv):
    indicator = MACDIndicator()
    score, reasoning = indicator.score(uptrend_ohlcv)
    assert 0.0 <= score <= 10.0
    assert isinstance(reasoning, str)


def test_rsi_uptrend_not_oversold(uptrend_ohlcv):
    indicator = RSIIndicator()
    score, reasoning = indicator.score(uptrend_ohlcv)
    assert 0.0 <= score <= 10.0
    assert "RSI" in reasoning


def test_rsi_downtrend_lower_score(downtrend_ohlcv):
    indicator = RSIIndicator()
    score_down, _ = indicator.score(downtrend_ohlcv)
    assert score_down <= 5.0


from scanner.indicators.volume import OBVIndicator, RelativeVolumeIndicator


def test_obv_returns_valid_score(uptrend_ohlcv):
    indicator = OBVIndicator()
    score, reasoning = indicator.score(uptrend_ohlcv)
    assert 0.0 <= score <= 10.0
    assert isinstance(reasoning, str)


def test_relative_volume_returns_valid_score(uptrend_ohlcv):
    indicator = RelativeVolumeIndicator()
    score, reasoning = indicator.score(uptrend_ohlcv)
    assert 0.0 <= score <= 10.0
    assert "volume" in reasoning.lower()


from scanner.indicators.volatility import BollingerBandsIndicator, ATRIndicator


def test_bollinger_returns_valid_score(uptrend_ohlcv):
    indicator = BollingerBandsIndicator()
    score, reasoning = indicator.score(uptrend_ohlcv)
    assert 0.0 <= score <= 10.0
    assert isinstance(reasoning, str)


def test_atr_returns_valid_score(uptrend_ohlcv):
    indicator = ATRIndicator()
    score, reasoning = indicator.score(uptrend_ohlcv)
    assert 0.0 <= score <= 10.0
    assert "ATR" in reasoning
