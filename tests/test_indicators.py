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
