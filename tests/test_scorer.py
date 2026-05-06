# tests/test_scorer.py
import pytest
from scorer import compute_score, signal_from_score, format_signal


def test_compute_score_returns_0_to_100(uptrend_ohlcv):
    result = compute_score(uptrend_ohlcv)
    assert 0.0 <= result["score"] <= 100.0


def test_compute_score_has_required_keys(uptrend_ohlcv):
    result = compute_score(uptrend_ohlcv)
    assert "score" in result
    assert "signal" in result
    assert "reasoning" in result
    assert "indicator_detail" in result


def test_uptrend_scores_higher_than_downtrend(uptrend_ohlcv, downtrend_ohlcv):
    up = compute_score(uptrend_ohlcv)
    down = compute_score(downtrend_ohlcv)
    assert up["score"] > down["score"]


def test_signal_from_score_boundaries():
    assert signal_from_score(80) == "BUY"
    assert signal_from_score(65) == "WATCH CAREFULLY"
    assert signal_from_score(45) == "HOLD"
    assert signal_from_score(30) == "REDUCE"
    assert signal_from_score(10) == "EXIT"


def test_format_signal_appends_earnings_warning():
    result = format_signal("BUY", earnings_warning=True, sentiment_flag=False, days_to_earnings=5)
    assert "⚠️" in result


def test_format_signal_overrides_buy_near_earnings():
    result = format_signal("BUY", earnings_warning=True, sentiment_flag=False, days_to_earnings=2)
    assert "WATCH CAREFULLY" in result
