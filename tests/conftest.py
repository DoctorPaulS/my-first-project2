# tests/conftest.py
import pytest
import pandas as pd
import numpy as np


@pytest.fixture
def uptrend_ohlcv():
    """200 days of synthetic OHLCV data in a clear uptrend."""
    np.random.seed(42)
    dates = pd.date_range(end="2024-12-31", periods=200, freq="B")
    close = 100 + np.cumsum(np.abs(np.random.randn(200)) * 0.3 + 0.2)
    high = close + np.abs(np.random.randn(200) * 0.3)
    low = close - np.abs(np.random.randn(200) * 0.3)
    open_ = close - np.random.randn(200) * 0.1
    volume = np.random.randint(1_000_000, 5_000_000, 200).astype(float)
    return pd.DataFrame(
        {"Open": open_, "High": high, "Low": low, "Close": close, "Volume": volume},
        index=dates,
    )


@pytest.fixture
def downtrend_ohlcv():
    """200 days of synthetic OHLCV data in a clear downtrend."""
    np.random.seed(99)
    dates = pd.date_range(end="2024-12-31", periods=200, freq="B")
    close = 200 - np.cumsum(np.abs(np.random.randn(200)) * 0.3 + 0.2)
    high = close + np.abs(np.random.randn(200) * 0.3)
    low = close - np.abs(np.random.randn(200) * 0.3)
    open_ = close + np.random.randn(200) * 0.1
    volume = np.random.randint(1_000_000, 5_000_000, 200).astype(float)
    return pd.DataFrame(
        {"Open": open_, "High": high, "Low": low, "Close": close, "Volume": volume},
        index=dates,
    )
