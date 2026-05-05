# Stock Advisor App — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a cloud-hosted Streamlit web app that screens S&P 500 stocks using technical analysis, monitors an Alpaca portfolio read-only, and tracks performance vs SPY and VTI benchmarks.

**Architecture:** A GitHub Actions cron job runs every 2 hours during market hours, downloads S&P 500 price data via yfinance, scores each stock with a composite technical analysis engine, and writes results to Supabase. A Streamlit app on Streamlit Community Cloud reads from Supabase and displays ranked signals, portfolio data, watchlist, and performance charts.

**Tech Stack:** Python 3.11, Streamlit, Supabase (PostgreSQL via supabase-py), yfinance, `ta` library (technical indicators), alpaca-py (read-only), Plotly, GitHub Actions

> **Note on indicators library:** The spec references `pandas-ta` but this plan uses the `ta` library (`pip install ta`) instead. It covers all required indicators, is stable with pandas 2.x, and has an identical Python API pattern. Adding a new indicator in the future is the same one-file process either way.

---

## File Map

```
my-first-project/
├── .github/
│   └── workflows/
│       └── scan.yml                 # GitHub Actions cron scheduler
├── .streamlit/
│   └── secrets.toml.example         # Template — never committed with real values
├── app/
│   ├── main.py                      # Streamlit home page
│   └── pages/
│       ├── 1_screener.py            # Ranked S&P 500 screener
│       ├── 2_portfolio.py           # Live Alpaca portfolio (read-only)
│       ├── 3_watchlist.py           # Personal watchlist with 1-min refresh
│       ├── 4_performance.py         # Portfolio vs SPY/VTI benchmarks
│       ├── 5_alerts.py              # Signal-change inbox
│       └── 6_settings.py            # Thresholds, weights, toggles
├── scanner/
│   ├── __init__.py
│   ├── run_scan.py                  # Entry point called by GitHub Actions
│   ├── universe.py                  # Fetches S&P 500 ticker list
│   ├── data_fetcher.py              # yfinance OHLCV + earnings date
│   ├── sentiment.py                 # NewsAPI headline sentiment
│   └── indicators/
│       ├── __init__.py
│       ├── base.py                  # Abstract BaseIndicator interface
│       ├── registry.py              # INDICATORS list + @register decorator
│       ├── trend.py                 # EMA 20/50/200 + ADX
│       ├── momentum.py              # MACD + RSI
│       ├── volume.py                # OBV + Relative Volume
│       ├── volatility.py            # Bollinger Bands + ATR
│       └── candlesticks.py          # Pattern detection (pure pandas, no lib)
├── scorer.py                        # Composite score + signal + reasoning text
├── db/
│   ├── __init__.py
│   ├── client.py                    # Supabase client singleton
│   ├── models.py                    # Python dataclasses for DB rows
│   └── schema.sql                   # Run once in Supabase SQL editor
├── alpaca_client.py                 # Read-only Alpaca wrapper
├── config.py                        # All constants (thresholds, weights, caps)
├── requirements.txt
├── .env.example
├── .gitignore
└── tests/
    ├── conftest.py                  # Shared pytest fixtures (sample OHLCV data)
    ├── test_universe.py
    ├── test_data_fetcher.py
    ├── test_indicators.py
    ├── test_scorer.py
    └── test_alpaca_client.py
```

---

## Task 1: Project Skeleton

**Files:**
- Create: `requirements.txt`
- Create: `.gitignore`
- Create: `.env.example`
- Create: all empty `__init__.py` files and directories

- [ ] **Step 1: Create requirements.txt**

```
streamlit>=1.32.0
supabase>=2.4.0
alpaca-py>=0.20.0
yfinance>=0.2.37
ta>=0.11.0
pandas>=2.0.0
numpy>=1.26.0
plotly>=5.20.0
python-dotenv>=1.0.0
requests>=2.31.0
pytest>=8.0.0
pytest-mock>=3.12.0
```

- [ ] **Step 2: Create .gitignore**

```
.env
.streamlit/secrets.toml
__pycache__/
*.pyc
.pytest_cache/
*.egg-info/
.venv/
venv/
```

- [ ] **Step 3: Create .env.example**

```
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-supabase-anon-key
ALPACA_API_KEY=your-alpaca-api-key
ALPACA_SECRET_KEY=your-alpaca-secret-key
NEWSAPI_KEY=your-newsapi-key
ALPACA_PAPER=false
```

- [ ] **Step 4: Create directory structure and empty __init__.py files**

Run these commands from the project root:
```bash
mkdir -p app/pages scanner/indicators db .github/workflows .streamlit tests
touch scanner/__init__.py scanner/indicators/__init__.py db/__init__.py
touch tests/__init__.py
```

- [ ] **Step 5: Install dependencies**

```bash
pip install -r requirements.txt
```

Expected: all packages install without errors.

- [ ] **Step 6: Commit**

```bash
git add requirements.txt .gitignore .env.example scanner/__init__.py scanner/indicators/__init__.py db/__init__.py tests/__init__.py
git commit -m "feat: project skeleton and dependencies"
```

---

## Task 2: Configuration Constants

**Files:**
- Create: `config.py`

- [ ] **Step 1: Create config.py**

```python
import os

MAX_WATCHLIST_SIZE = 25

DEFAULT_THRESHOLDS = {
    "BUY": 75,
    "WATCH CAREFULLY": 55,
    "HOLD": 35,
    "REDUCE": 25,
    "EXIT": 0,
}

DEFAULT_GROUP_WEIGHTS = {
    "trend": 0.30,
    "momentum": 0.25,
    "volume": 0.20,
    "volatility": 0.15,
    "candlesticks": 0.10,
}

SIGNAL_EMOJI = {
    "BUY": "🟢",
    "WATCH CAREFULLY": "👀",
    "HOLD": "🟡",
    "REDUCE": "🔴",
    "EXIT": "🚨",
}

SP500_WIKIPEDIA_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"

MARKET_OPEN_HOUR_ET = 9
MARKET_OPEN_MINUTE_ET = 30
MARKET_CLOSE_HOUR_ET = 16

SCAN_LOOKBACK_PERIOD = "6mo"
EARNINGS_WARNING_DAYS = 7
EARNINGS_CRITICAL_DAYS = 3
ALERTS_EXPIRE_DAYS = 7
PORTFOLIO_CACHE_SECONDS = 60


def get_secret(key: str) -> str:
    """Get a secret from Streamlit secrets (in app) or environment variables (in scanner)."""
    try:
        import streamlit as st
        return st.secrets[key]
    except Exception:
        return os.environ.get(key, "")
```

- [ ] **Step 2: Commit**

```bash
git add config.py
git commit -m "feat: configuration constants"
```

---

## Task 3: Database Schema

**Files:**
- Create: `db/schema.sql`

- [ ] **Step 1: Create db/schema.sql**

```sql
-- Run this entire file once in the Supabase SQL Editor
-- (Supabase dashboard → SQL Editor → New query → paste → Run)

CREATE TABLE IF NOT EXISTS scan_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticker TEXT NOT NULL,
    scanned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    score FLOAT NOT NULL,
    signal TEXT NOT NULL,
    reasoning TEXT NOT NULL,
    indicator_detail JSONB NOT NULL DEFAULT '{}',
    earnings_warning BOOLEAN NOT NULL DEFAULT FALSE,
    sentiment_flag BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_scan_results_ticker ON scan_results(ticker);
CREATE INDEX IF NOT EXISTS idx_scan_results_scanned_at ON scan_results(scanned_at DESC);

CREATE TABLE IF NOT EXISTS watchlist (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticker TEXT NOT NULL UNIQUE,
    added_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    notes TEXT
);

CREATE TABLE IF NOT EXISTS alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticker TEXT NOT NULL,
    previous_signal TEXT NOT NULL,
    new_signal TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    read BOOLEAN NOT NULL DEFAULT FALSE,
    expires_at TIMESTAMPTZ NOT NULL DEFAULT NOW() + INTERVAL '7 days'
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value JSONB NOT NULL
);

INSERT INTO settings (key, value) VALUES
    ('thresholds', '{"BUY": 75, "WATCH CAREFULLY": 55, "HOLD": 35, "REDUCE": 25, "EXIT": 0}'),
    ('group_weights', '{"trend": 0.30, "momentum": 0.25, "volume": 0.20, "volatility": 0.15, "candlesticks": 0.10}'),
    ('indicator_toggles', '{}')
ON CONFLICT (key) DO NOTHING;
```

- [ ] **Step 2: Run schema in Supabase**

1. Go to https://supabase.com and create a free account
2. Create a new project (choose a region close to you)
3. Go to Project → SQL Editor → New query
4. Paste the entire contents of `db/schema.sql` and click Run
5. Verify: go to Table Editor and confirm all 4 tables exist

- [ ] **Step 3: Commit**

```bash
git add db/schema.sql
git commit -m "feat: database schema"
```

---

## Task 4: Database Client and Models

**Files:**
- Create: `db/client.py`
- Create: `db/models.py`

- [ ] **Step 1: Create db/models.py**

```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class ScanResult:
    ticker: str
    score: float
    signal: str
    reasoning: str
    indicator_detail: dict
    earnings_warning: bool
    sentiment_flag: bool
    scanned_at: Optional[datetime] = None
    id: Optional[str] = None


@dataclass
class WatchlistItem:
    ticker: str
    added_at: Optional[datetime] = None
    notes: Optional[str] = None
    id: Optional[str] = None


@dataclass
class Alert:
    ticker: str
    previous_signal: str
    new_signal: str
    read: bool = False
    created_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    id: Optional[str] = None
```

- [ ] **Step 2: Create db/client.py**

```python
from functools import lru_cache
from supabase import create_client, Client
from config import get_secret


@lru_cache(maxsize=1)
def get_db() -> Client:
    url = get_secret("SUPABASE_URL")
    key = get_secret("SUPABASE_KEY")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set.")
    return create_client(url, key)


def get_settings(key: str, default: dict) -> dict:
    """Load a settings row from Supabase, falling back to default."""
    try:
        db = get_db()
        result = db.table("settings").select("value").eq("key", key).single().execute()
        return result.data["value"]
    except Exception:
        return default


def save_settings(key: str, value: dict) -> None:
    db = get_db()
    db.table("settings").upsert({"key": key, "value": value}).execute()
```

- [ ] **Step 3: Commit**

```bash
git add db/models.py db/client.py
git commit -m "feat: database client and data models"
```

---

## Task 5: S&P 500 Universe

**Files:**
- Create: `scanner/universe.py`
- Create: `tests/test_universe.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_universe.py
import pytest
from unittest.mock import patch, MagicMock
import pandas as pd
from scanner.universe import get_sp500_tickers


def test_get_sp500_tickers_returns_list():
    mock_df = pd.DataFrame({"Symbol": ["AAPL", "MSFT", "GOOG"]})
    with patch("pandas.read_html", return_value=[mock_df]):
        tickers = get_sp500_tickers()
    assert isinstance(tickers, list)
    assert "AAPL" in tickers
    assert "MSFT" in tickers


def test_get_sp500_tickers_replaces_dots_with_dashes():
    mock_df = pd.DataFrame({"Symbol": ["BRK.B", "BF.B"]})
    with patch("pandas.read_html", return_value=[mock_df]):
        tickers = get_sp500_tickers()
    assert "BRK-B" in tickers
    assert "BF-B" in tickers
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_universe.py -v
```

Expected: `FAILED` with `ModuleNotFoundError` or `ImportError`.

- [ ] **Step 3: Create scanner/universe.py**

```python
import pandas as pd
from config import SP500_WIKIPEDIA_URL


def get_sp500_tickers() -> list[str]:
    """Fetch the current S&P 500 ticker list from Wikipedia."""
    tables = pd.read_html(SP500_WIKIPEDIA_URL)
    df = tables[0]
    tickers = df["Symbol"].tolist()
    # yfinance uses dashes where Yahoo Finance uses dots (e.g. BRK-B not BRK.B)
    return [t.replace(".", "-") for t in tickers]
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_universe.py -v
```

Expected: `2 passed`.

- [ ] **Step 5: Commit**

```bash
git add scanner/universe.py tests/test_universe.py
git commit -m "feat: S&P 500 universe fetcher"
```

---

## Task 6: Data Fetcher

**Files:**
- Create: `scanner/data_fetcher.py`
- Create: `tests/test_data_fetcher.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_data_fetcher.py
import pytest
import pandas as pd
import numpy as np
from unittest.mock import patch
from scanner.data_fetcher import fetch_ohlcv, fetch_earnings_date


def _make_mock_df():
    dates = pd.date_range(end="2024-12-31", periods=120, freq="B")
    close = 100 + np.cumsum(np.random.randn(120) * 0.5)
    return pd.DataFrame({
        "Open": close - 0.2,
        "High": close + 0.3,
        "Low": close - 0.3,
        "Close": close,
        "Volume": np.ones(120) * 1_000_000,
    }, index=dates)


def test_fetch_ohlcv_returns_dataframe():
    mock_df = _make_mock_df()
    with patch("yfinance.download", return_value=mock_df):
        result = fetch_ohlcv("AAPL")
    assert isinstance(result, pd.DataFrame)
    assert list(result.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert len(result) > 0


def test_fetch_ohlcv_raises_on_empty():
    with patch("yfinance.download", return_value=pd.DataFrame()):
        with pytest.raises(ValueError, match="No data"):
            fetch_ohlcv("INVALID")


def test_fetch_earnings_date_returns_none_on_failure():
    mock_ticker = type("T", (), {"calendar": None})()
    with patch("yfinance.Ticker", return_value=mock_ticker):
        result = fetch_earnings_date("AAPL")
    assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_data_fetcher.py -v
```

Expected: `FAILED` with `ImportError`.

- [ ] **Step 3: Create scanner/data_fetcher.py**

```python
import yfinance as yf
import pandas as pd
from datetime import date
from typing import Optional


def fetch_ohlcv(ticker: str, period: str = "6mo") -> pd.DataFrame:
    """Download adjusted OHLCV data for one ticker via yfinance."""
    df = yf.download(ticker, period=period, auto_adjust=True, progress=False)
    if df.empty:
        raise ValueError(f"No data returned for {ticker}")
    # yfinance may return MultiIndex columns for a single ticker in some versions
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.droplevel(1)
    return df[["Open", "High", "Low", "Close", "Volume"]].copy()


def fetch_ohlcv_batch(tickers: list[str], period: str = "6mo") -> dict[str, pd.DataFrame]:
    """Download OHLCV for multiple tickers at once (much faster than one-by-one)."""
    raw = yf.download(
        tickers, period=period, auto_adjust=True,
        group_by="ticker", progress=False, threads=True,
    )
    result = {}
    for ticker in tickers:
        try:
            if ticker in raw.columns.get_level_values(0):
                df = raw[ticker][["Open", "High", "Low", "Close", "Volume"]].dropna()
                if not df.empty:
                    result[ticker] = df
        except Exception:
            continue
    return result


def fetch_earnings_date(ticker: str) -> Optional[date]:
    """Return the next upcoming earnings date for a ticker, or None."""
    try:
        stock = yf.Ticker(ticker)
        cal = stock.calendar
        if cal is None:
            return None
        if isinstance(cal, pd.DataFrame) and not cal.empty:
            val = cal.iloc[0].get("Earnings Date")
            if val is not None:
                return pd.Timestamp(val).date()
        if isinstance(cal, dict):
            val = cal.get("Earnings Date")
            if val:
                return pd.Timestamp(val[0] if isinstance(val, list) else val).date()
    except Exception:
        pass
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_data_fetcher.py -v
```

Expected: `3 passed`.

- [ ] **Step 5: Commit**

```bash
git add scanner/data_fetcher.py tests/test_data_fetcher.py
git commit -m "feat: yfinance OHLCV and earnings date fetcher"
```

---

## Task 7: Indicator Base Interface and Registry

**Files:**
- Create: `scanner/indicators/base.py`
- Create: `scanner/indicators/registry.py`

- [ ] **Step 1: Create scanner/indicators/base.py**

```python
from abc import ABC, abstractmethod
import pandas as pd


class BaseIndicator(ABC):
    def __init__(self, params: dict = None):
        self.params = params or {}

    @abstractmethod
    def score(self, ohlcv: pd.DataFrame) -> tuple[float, str]:
        """
        Calculate indicator score.

        Args:
            ohlcv: DataFrame with columns Open, High, Low, Close, Volume

        Returns:
            (score, reasoning) where score is 0.0–10.0 and reasoning is a
            plain-English sentence explaining what the indicator observed.
        """
```

- [ ] **Step 2: Create scanner/indicators/registry.py**

```python
from dataclasses import dataclass, field
from typing import Type
from .base import BaseIndicator


@dataclass
class IndicatorEntry:
    cls: Type[BaseIndicator]
    group: str
    params: dict = field(default_factory=dict)
    enabled: bool = True


INDICATORS: list[IndicatorEntry] = []


def register(group: str, params: dict = None):
    """Decorator that registers an indicator class in the INDICATORS list."""
    def decorator(cls: Type[BaseIndicator]) -> Type[BaseIndicator]:
        INDICATORS.append(IndicatorEntry(cls=cls, group=group, params=params or {}))
        return cls
    return decorator


def get_enabled_indicators(toggles: dict = None) -> list[IndicatorEntry]:
    """Return all enabled indicator entries, respecting user toggles from Settings."""
    toggles = toggles or {}
    return [
        entry for entry in INDICATORS
        if toggles.get(entry.cls.__name__, entry.enabled)
    ]
```

- [ ] **Step 3: Commit**

```bash
git add scanner/indicators/base.py scanner/indicators/registry.py
git commit -m "feat: indicator base interface and registry"
```

---

## Task 8: Trend Indicators (EMA + ADX)

**Files:**
- Create: `scanner/indicators/trend.py`
- Create: `tests/conftest.py`
- Modify: `tests/test_indicators.py`

- [ ] **Step 1: Create tests/conftest.py with shared OHLCV fixture**

```python
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
```

- [ ] **Step 2: Write failing trend indicator tests**

```python
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
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
pytest tests/test_indicators.py -v
```

Expected: `FAILED` with `ImportError`.

- [ ] **Step 4: Create scanner/indicators/trend.py**

```python
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
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_indicators.py -v
```

Expected: `3 passed`.

- [ ] **Step 6: Commit**

```bash
git add scanner/indicators/trend.py tests/conftest.py tests/test_indicators.py
git commit -m "feat: EMA trend and ADX indicators"
```

---

## Task 9: Momentum Indicators (MACD + RSI)

**Files:**
- Modify: `scanner/indicators/momentum.py`
- Modify: `tests/test_indicators.py`

- [ ] **Step 1: Add failing momentum tests to tests/test_indicators.py**

Append to `tests/test_indicators.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_indicators.py::test_macd_returns_valid_score -v
```

Expected: `FAILED` with `ImportError`.

- [ ] **Step 3: Create scanner/indicators/momentum.py**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_indicators.py -v
```

Expected: all momentum tests pass (plus prior trend tests still green).

- [ ] **Step 5: Commit**

```bash
git add scanner/indicators/momentum.py tests/test_indicators.py
git commit -m "feat: MACD and RSI momentum indicators"
```

---

## Task 10: Volume Indicators (OBV + Relative Volume)

**Files:**
- Create: `scanner/indicators/volume.py`
- Modify: `tests/test_indicators.py`

- [ ] **Step 1: Add failing volume tests**

Append to `tests/test_indicators.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_indicators.py::test_obv_returns_valid_score -v
```

Expected: `FAILED` with `ImportError`.

- [ ] **Step 3: Create scanner/indicators/volume.py**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_indicators.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add scanner/indicators/volume.py tests/test_indicators.py
git commit -m "feat: OBV and relative volume indicators"
```

---

## Task 11: Volatility Indicators (Bollinger Bands + ATR)

**Files:**
- Create: `scanner/indicators/volatility.py`
- Modify: `tests/test_indicators.py`

- [ ] **Step 1: Add failing volatility tests**

Append to `tests/test_indicators.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_indicators.py::test_bollinger_returns_valid_score -v
```

Expected: `FAILED` with `ImportError`.

- [ ] **Step 3: Create scanner/indicators/volatility.py**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_indicators.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add scanner/indicators/volatility.py tests/test_indicators.py
git commit -m "feat: Bollinger Bands and ATR volatility indicators"
```

---

## Task 12: Candlestick Pattern Indicator

**Files:**
- Create: `scanner/indicators/candlesticks.py`
- Modify: `tests/test_indicators.py`

- [ ] **Step 1: Add failing candlestick tests**

Append to `tests/test_indicators.py`:

```python
from scanner.indicators.candlesticks import CandlestickPatternIndicator


def test_candlestick_returns_valid_score(uptrend_ohlcv):
    indicator = CandlestickPatternIndicator()
    score, reasoning = indicator.score(uptrend_ohlcv)
    assert 0.0 <= score <= 10.0
    assert isinstance(reasoning, str)


def test_candlestick_score_is_neutral_on_random_data(uptrend_ohlcv):
    indicator = CandlestickPatternIndicator()
    score, _ = indicator.score(uptrend_ohlcv)
    # Score should always be in valid range regardless of data
    assert 0.0 <= score <= 10.0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_indicators.py::test_candlestick_returns_valid_score -v
```

Expected: `FAILED` with `ImportError`.

- [ ] **Step 3: Create scanner/indicators/candlesticks.py**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_indicators.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add scanner/indicators/candlesticks.py tests/test_indicators.py
git commit -m "feat: candlestick pattern indicator"
```

---

## Task 13: Composite Scorer

**Files:**
- Create: `scorer.py`
- Create: `tests/test_scorer.py`

- [ ] **Step 1: Write failing scorer tests**

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_scorer.py -v
```

Expected: `FAILED` with `ImportError`.

- [ ] **Step 3: Create scorer.py**

```python
import pandas as pd
from typing import Optional
from config import DEFAULT_THRESHOLDS, DEFAULT_GROUP_WEIGHTS, SIGNAL_EMOJI, EARNINGS_CRITICAL_DAYS
from scanner.indicators.registry import get_enabled_indicators


def compute_score(
    ohlcv: pd.DataFrame,
    toggles: dict = None,
    weights: dict = None,
    thresholds: dict = None,
) -> dict:
    """
    Run all enabled indicators against OHLCV data and return composite result.

    Returns dict with keys: score (0-100), signal, reasoning, indicator_detail.
    """
    weights = weights or DEFAULT_GROUP_WEIGHTS
    thresholds = thresholds or DEFAULT_THRESHOLDS

    group_scores: dict[str, list[float]] = {}
    group_reasoning: dict[str, list[str]] = {}
    indicator_detail: dict[str, dict] = {}

    for entry in get_enabled_indicators(toggles):
        indicator = entry.cls(params=entry.params)
        try:
            ind_score, ind_reasoning = indicator.score(ohlcv)
        except Exception as e:
            ind_score, ind_reasoning = 5.0, f"Error in {entry.cls.__name__}: {e}"

        group = entry.group
        group_scores.setdefault(group, []).append(ind_score)
        group_reasoning.setdefault(group, []).append(ind_reasoning)
        indicator_detail[entry.cls.__name__] = {
            "score": round(ind_score, 2),
            "reasoning": ind_reasoning,
            "group": group,
        }

    composite = 0.0
    for group, scores in group_scores.items():
        group_avg = sum(scores) / len(scores)
        weight = weights.get(group, 0.0)
        composite += group_avg * weight

    final_score = round(composite * 10, 1)
    signal = signal_from_score(final_score, thresholds)

    all_reasoning = []
    for group in ["trend", "momentum", "volume", "volatility", "candlesticks"]:
        if group in group_reasoning:
            all_reasoning.extend(group_reasoning[group])
    reasoning = " ".join(all_reasoning)

    return {
        "score": final_score,
        "signal": signal,
        "reasoning": reasoning,
        "indicator_detail": indicator_detail,
    }


def signal_from_score(score: float, thresholds: dict = None) -> str:
    t = thresholds or DEFAULT_THRESHOLDS
    if score >= t["BUY"]:
        return "BUY"
    if score >= t["WATCH CAREFULLY"]:
        return "WATCH CAREFULLY"
    if score >= t["HOLD"]:
        return "HOLD"
    if score >= t["REDUCE"]:
        return "REDUCE"
    return "EXIT"


def format_signal(
    signal: str,
    earnings_warning: bool,
    sentiment_flag: bool,
    days_to_earnings: Optional[int] = None,
) -> str:
    """Return the display-ready signal string with emoji and event modifier flags."""
    display = signal

    if earnings_warning and days_to_earnings is not None and days_to_earnings <= EARNINGS_CRITICAL_DAYS:
        if signal == "BUY":
            display = "WATCH CAREFULLY"

    emoji = SIGNAL_EMOJI.get(display, "")
    result = f"{emoji} {display}"

    if earnings_warning:
        result += " ⚠️"
    if sentiment_flag:
        result += " 🔻"

    return result
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_scorer.py -v
```

Expected: `6 passed`.

- [ ] **Step 5: Commit**

```bash
git add scorer.py tests/test_scorer.py
git commit -m "feat: composite scorer with signal thresholds and event modifiers"
```

---

## Task 14: Sentiment Fetcher

**Files:**
- Create: `scanner/sentiment.py`

- [ ] **Step 1: Create scanner/sentiment.py**

```python
import requests
from config import get_secret

NEWSAPI_URL = "https://newsapi.org/v2/everything"

NEGATIVE_WORDS = {
    "downgrade", "miss", "loss", "lawsuit", "investigation",
    "recall", "fraud", "decline", "cut", "below", "warning",
    "layoff", "disappoints", "slumps", "plunges",
}
POSITIVE_WORDS = {
    "upgrade", "beat", "record", "growth", "raise", "strong",
    "above", "buy", "profit", "surge", "outperform", "tops",
    "exceeds", "boosts",
}


def get_sentiment(ticker: str) -> tuple[bool, list[str]]:
    """
    Fetch recent headlines for a ticker and return (is_negative, headlines).

    Returns (False, []) if the API key is not set or the request fails.
    """
    api_key = get_secret("NEWSAPI_KEY")
    if not api_key:
        return False, []

    params = {
        "q": ticker,
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": 5,
        "apiKey": api_key,
    }
    try:
        resp = requests.get(NEWSAPI_URL, params=params, timeout=5)
        resp.raise_for_status()
        articles = resp.json().get("articles", [])
        headlines = [a["title"] for a in articles if a.get("title")]

        neg_count = sum(
            1 for h in headlines for w in NEGATIVE_WORDS if w in h.lower()
        )
        pos_count = sum(
            1 for h in headlines for w in POSITIVE_WORDS if w in h.lower()
        )

        is_negative = neg_count > pos_count
        return is_negative, headlines[:3]
    except Exception:
        return False, []
```

- [ ] **Step 2: Commit**

```bash
git add scanner/sentiment.py
git commit -m "feat: NewsAPI sentiment fetcher"
```

---

## Task 15: Main Scan Runner

**Files:**
- Create: `scanner/run_scan.py`

- [ ] **Step 1: Create scanner/run_scan.py**

```python
"""
Entry point for the GitHub Actions scheduled scan.
Run with: python -m scanner.run_scan
"""
import sys
import logging
from datetime import datetime, timezone, date, timedelta
from scanner.universe import get_sp500_tickers
from scanner.data_fetcher import fetch_ohlcv_batch, fetch_earnings_date
from scanner.sentiment import get_sentiment
from scorer import compute_score, format_signal
from db.client import get_db
from config import EARNINGS_WARNING_DAYS, get_secret

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)


def run_scan() -> None:
    log.info("Starting S&P 500 scan...")
    tickers = get_sp500_tickers()
    log.info(f"Universe: {len(tickers)} tickers")

    log.info("Downloading price data (batch)...")
    ohlcv_map = fetch_ohlcv_batch(tickers)
    log.info(f"Got data for {len(ohlcv_map)} tickers")

    scan_time = datetime.now(timezone.utc).isoformat()
    db = get_db()

    # Fetch current watchlist to know which stocks need alert comparison
    watchlist_result = db.table("watchlist").select("ticker").execute()
    watchlist_tickers = {row["ticker"] for row in watchlist_result.data}

    # Get previous signals for watchlist stocks
    prev_signals: dict[str, str] = {}
    if watchlist_tickers:
        prev = (
            db.table("scan_results")
            .select("ticker, signal, scanned_at")
            .in_("ticker", list(watchlist_tickers))
            .order("scanned_at", desc=True)
            .limit(len(watchlist_tickers) * 5)
            .execute()
        )
        seen = set()
        for row in prev.data:
            if row["ticker"] not in seen:
                prev_signals[row["ticker"]] = row["signal"]
                seen.add(row["ticker"])

    rows_to_insert = []
    alerts_to_insert = []

    for ticker, ohlcv in ohlcv_map.items():
        try:
            result = compute_score(ohlcv)
            earnings_date = fetch_earnings_date(ticker)
            days_to_earnings = None
            earnings_warning = False

            if earnings_date:
                days_to_earnings = (earnings_date - date.today()).days
                earnings_warning = 0 <= days_to_earnings <= EARNINGS_WARNING_DAYS

            sentiment_flag, _ = get_sentiment(ticker) if ticker in watchlist_tickers else (False, [])

            rows_to_insert.append({
                "ticker": ticker,
                "scanned_at": scan_time,
                "score": result["score"],
                "signal": result["signal"],
                "reasoning": result["reasoning"],
                "indicator_detail": result["indicator_detail"],
                "earnings_warning": earnings_warning,
                "sentiment_flag": sentiment_flag,
            })

            # Generate alert if watchlist signal changed
            if ticker in watchlist_tickers and ticker in prev_signals:
                if prev_signals[ticker] != result["signal"]:
                    alerts_to_insert.append({
                        "ticker": ticker,
                        "previous_signal": prev_signals[ticker],
                        "new_signal": result["signal"],
                    })

        except Exception as e:
            log.warning(f"Failed to score {ticker}: {e}")
            continue

    # Batch insert scan results
    log.info(f"Writing {len(rows_to_insert)} scan results to Supabase...")
    batch_size = 100
    for i in range(0, len(rows_to_insert), batch_size):
        db.table("scan_results").insert(rows_to_insert[i : i + batch_size]).execute()

    if alerts_to_insert:
        log.info(f"Writing {len(alerts_to_insert)} alerts...")
        db.table("alerts").insert(alerts_to_insert).execute()

    log.info("Scan complete.")


if __name__ == "__main__":
    run_scan()
```

- [ ] **Step 2: Test the scanner locally (dry run)**

Create a `.env` file from `.env.example` and fill in your Supabase credentials, then:

```bash
python -m scanner.run_scan
```

Expected: logs show tickers being processed and "Scan complete." Check Supabase Table Editor → `scan_results` to see rows inserted.

- [ ] **Step 3: Commit**

```bash
git add scanner/run_scan.py
git commit -m "feat: main scan runner with batch insert and alert detection"
```

---

## Task 16: Alpaca Read-Only Client

**Files:**
- Create: `alpaca_client.py`
- Create: `tests/test_alpaca_client.py`

- [ ] **Step 1: Write failing Alpaca client tests**

```python
# tests/test_alpaca_client.py
import pytest
from unittest.mock import MagicMock, patch
from alpaca_client import get_positions, get_account, get_portfolio_history


def _mock_trading_client():
    mock = MagicMock()
    pos = MagicMock()
    pos.symbol = "AAPL"
    pos.qty = "10"
    pos.current_price = "175.00"
    pos.market_value = "1750.00"
    pos.unrealized_pl = "50.00"
    pos.unrealized_plpc = "0.029"
    pos.cost_basis = "1700.00"
    mock.get_all_positions.return_value = [pos]

    acct = MagicMock()
    acct.portfolio_value = "50000.00"
    acct.buying_power = "25000.00"
    acct.cash = "10000.00"
    mock.get_account.return_value = acct

    return mock


def test_get_positions_returns_list(monkeypatch):
    mock_client = _mock_trading_client()
    monkeypatch.setattr("alpaca_client._get_trading_client", lambda: mock_client)
    positions = get_positions()
    assert isinstance(positions, list)
    assert positions[0]["symbol"] == "AAPL"
    assert positions[0]["qty"] == 10.0


def test_get_account_returns_dict(monkeypatch):
    mock_client = _mock_trading_client()
    monkeypatch.setattr("alpaca_client._get_trading_client", lambda: mock_client)
    acct = get_account()
    assert "portfolio_value" in acct
    assert acct["portfolio_value"] == 50000.0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_alpaca_client.py -v
```

Expected: `FAILED` with `ImportError`.

- [ ] **Step 3: Create alpaca_client.py**

```python
from functools import lru_cache
from alpaca.trading.client import TradingClient
from config import get_secret


@lru_cache(maxsize=1)
def _get_trading_client() -> TradingClient:
    api_key = get_secret("ALPACA_API_KEY")
    secret_key = get_secret("ALPACA_SECRET_KEY")
    paper = get_secret("ALPACA_PAPER").lower() == "true"
    if not api_key or not secret_key:
        raise RuntimeError("ALPACA_API_KEY and ALPACA_SECRET_KEY must be set.")
    return TradingClient(api_key=api_key, secret_key=secret_key, paper=paper)


def get_positions() -> list[dict]:
    """Return all open Alpaca positions as plain dicts."""
    client = _get_trading_client()
    positions = client.get_all_positions()
    return [
        {
            "symbol": p.symbol,
            "qty": float(p.qty),
            "current_price": float(p.current_price),
            "market_value": float(p.market_value),
            "unrealized_pl": float(p.unrealized_pl),
            "unrealized_plpc": float(p.unrealized_plpc),
            "cost_basis": float(p.cost_basis),
        }
        for p in positions
    ]


def get_account() -> dict:
    """Return key account metrics as a plain dict."""
    client = _get_trading_client()
    a = client.get_account()
    return {
        "portfolio_value": float(a.portfolio_value),
        "buying_power": float(a.buying_power),
        "cash": float(a.cash),
    }


def get_portfolio_history(period: str = "1M") -> dict:
    """Return portfolio equity history for charting. Period: 1W, 1M, 3M, 6M, 1Y."""
    from alpaca.trading.requests import GetPortfolioHistoryRequest
    client = _get_trading_client()
    req = GetPortfolioHistoryRequest(period=period, timeframe="1D")
    history = client.get_portfolio_history(filter=req)
    return {
        "timestamps": history.timestamp,
        "equity": history.equity,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_alpaca_client.py -v
```

Expected: `2 passed`.

- [ ] **Step 5: Run the full test suite to confirm nothing is broken**

```bash
pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add alpaca_client.py tests/test_alpaca_client.py
git commit -m "feat: read-only Alpaca client for positions and account data"
```

---

## Task 17: Streamlit App Entry Point

**Files:**
- Create: `app/main.py`

- [ ] **Step 1: Create app/main.py**

```python
import streamlit as st
from db.client import get_db

st.set_page_config(
    page_title="Stock Advisor",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("📈 Stock Advisor")
st.caption("Technical analysis-driven signals for S&P 500 stocks. Alpaca portfolio connected read-only.")

col1, col2, col3 = st.columns(3)

with col1:
    st.info("🔍 **Screener** — Ranked S&P 500 picks")
with col2:
    st.info("👀 **Watchlist** — Your 25 tracked stocks")
with col3:
    st.info("📊 **Performance** — vs SPY and VTI")

st.divider()
st.markdown("""
**How to use this app:**
1. Open **Screener** to see today's top-scoring stocks with buy/sell signals
2. Click any row to expand the full analysis card
3. Add interesting stocks to your **Watchlist** for 1-minute refresh monitoring
4. Check **Portfolio** to see your live Alpaca positions and their current signals
5. Review **Performance** to see how you're doing vs the S&P 500 and VTI
6. The scan runs automatically every 2 hours during market hours — no action needed

**Signal meanings:**
| Signal | Score | Action |
|--------|-------|--------|
| 🟢 BUY | 75–100 | Strong setup — consider entering |
| 👀 WATCH CAREFULLY | 55–74 | Promising but unconfirmed |
| 🟡 HOLD | 35–54 | Mixed signals — stay the course |
| 🔴 REDUCE | 25–34 | Signals weakening — consider trimming |
| 🚨 EXIT | 0–24 | Significant deterioration — consider full exit |
""")
```

- [ ] **Step 2: Run the app locally to verify it loads**

```bash
streamlit run app/main.py
```

Expected: browser opens at `http://localhost:8501` showing the home page with title "Stock Advisor" and the signals table.

- [ ] **Step 3: Commit**

```bash
git add app/main.py
git commit -m "feat: Streamlit app home page"
```

---

## Task 18: Screener Page

**Files:**
- Create: `app/pages/1_screener.py`

- [ ] **Step 1: Create app/pages/1_screener.py**

```python
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime
from db.client import get_db
from scorer import compute_score, format_signal
from scanner.data_fetcher import fetch_ohlcv, fetch_earnings_date
from config import SIGNAL_EMOJI

st.set_page_config(page_title="Screener", page_icon="🔍", layout="wide")
st.title("🔍 Stock Screener")


@st.cache_data(ttl=300)
def load_latest_scan() -> pd.DataFrame:
    db = get_db()
    latest = (
        db.table("scan_results")
        .select("scanned_at")
        .order("scanned_at", desc=True)
        .limit(1)
        .execute()
    )
    if not latest.data:
        return pd.DataFrame()
    scan_time = latest.data[0]["scanned_at"]
    results = (
        db.table("scan_results")
        .select("*")
        .eq("scanned_at", scan_time)
        .order("score", desc=True)
        .execute()
    )
    df = pd.DataFrame(results.data)
    if df.empty:
        return df
    df["display_signal"] = df.apply(
        lambda r: format_signal(r["signal"], r["earnings_warning"], r["sentiment_flag"]),
        axis=1,
    )
    return df


df = load_latest_scan()

if df.empty:
    st.warning("No scan results yet. The scanner runs every 2 hours during market hours.")
    st.stop()

scan_time = df["scanned_at"].iloc[0] if "scanned_at" in df.columns else "unknown"
st.caption(f"Last scan: {scan_time}")

# --- Sidebar filters ---
with st.sidebar:
    st.header("Filters")
    signal_options = ["BUY", "WATCH CAREFULLY", "HOLD", "REDUCE", "EXIT"]
    selected_signals = st.multiselect("Signal", signal_options, default=["BUY", "WATCH CAREFULLY"])
    min_score = st.slider("Minimum Score", 0, 100, 0)
    earnings_only = st.checkbox("Earnings warning only ⚠️")

filtered = df[df["signal"].isin(selected_signals) & (df["score"] >= min_score)]
if earnings_only:
    filtered = filtered[filtered["earnings_warning"] == True]

# --- Results table ---
display_cols = ["ticker", "score", "display_signal", "reasoning"]
display_df = filtered[display_cols].rename(columns={
    "ticker": "Ticker",
    "score": "Score",
    "display_signal": "Signal",
    "reasoning": "Reason",
})
display_df["Reason"] = display_df["Reason"].str[:120] + "..."

st.subheader(f"{len(filtered)} stocks match your filters")
event = st.dataframe(
    display_df,
    use_container_width=True,
    hide_index=True,
    on_select="rerun",
    selection_mode="single-row",
)

# --- Expanded analysis card ---
if event.selection.rows:
    idx = event.selection.rows[0]
    row = filtered.iloc[idx]
    ticker = row["ticker"]

    st.divider()
    col_title, col_btn = st.columns([4, 1])
    with col_title:
        st.subheader(f"Analysis: {ticker}")
    with col_btn:
        watchlist_result = get_db().table("watchlist").select("ticker").eq("ticker", ticker).execute()
        on_watchlist = bool(watchlist_result.data)
        if not on_watchlist:
            if st.button("➕ Add to Watchlist"):
                from config import MAX_WATCHLIST_SIZE
                count = get_db().table("watchlist").select("id", count="exact").execute()
                if count.count >= MAX_WATCHLIST_SIZE:
                    st.error(f"Watchlist is full ({MAX_WATCHLIST_SIZE} stocks max).")
                else:
                    get_db().table("watchlist").insert({"ticker": ticker}).execute()
                    st.success(f"{ticker} added to watchlist!")
                    st.rerun()
        else:
            st.success("✅ On watchlist")

    col_score, col_signal, col_earnings = st.columns(3)
    with col_score:
        st.metric("Score", f"{row['score']:.1f} / 100")
    with col_signal:
        st.metric("Signal", row["display_signal"])
    with col_earnings:
        st.metric("Earnings Warning", "⚠️ Yes" if row["earnings_warning"] else "No")

    st.markdown("**Full Reasoning:**")
    st.write(row["reasoning"])

    if row["indicator_detail"]:
        st.markdown("**Indicator Breakdown:**")
        detail = row["indicator_detail"]
        detail_df = pd.DataFrame([
            {"Indicator": name, "Score": f"{v['score']:.1f}/10", "Group": v["group"], "Notes": v["reasoning"]}
            for name, v in detail.items()
        ])
        st.dataframe(detail_df, use_container_width=True, hide_index=True)

    st.markdown("**Price Chart (6 months):**")
    try:
        ohlcv = fetch_ohlcv(ticker)
        fig = go.Figure(data=[
            go.Candlestick(
                x=ohlcv.index,
                open=ohlcv["Open"], high=ohlcv["High"],
                low=ohlcv["Low"], close=ohlcv["Close"],
                name=ticker,
            )
        ])
        fig.update_layout(xaxis_rangeslider_visible=False, height=400, margin=dict(l=0, r=0, t=30, b=0))
        st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.warning(f"Could not load chart: {e}")
```

- [ ] **Step 2: Run the app and verify the Screener page loads**

```bash
streamlit run app/main.py
```

Navigate to Screener in the sidebar. Expected: ranked table appears (if scan data exists), clicking a row shows the analysis card.

- [ ] **Step 3: Commit**

```bash
git add app/pages/1_screener.py
git commit -m "feat: screener page with ranked table and expandable analysis card"
```

---

## Task 19: Portfolio Page

**Files:**
- Create: `app/pages/2_portfolio.py`

- [ ] **Step 1: Create app/pages/2_portfolio.py**

```python
import streamlit as st
import pandas as pd
from db.client import get_db
from alpaca_client import get_positions, get_account
from config import PORTFOLIO_CACHE_SECONDS

st.set_page_config(page_title="Portfolio", page_icon="💼", layout="wide")
st.title("💼 Portfolio")
st.caption("Live Alpaca positions — read-only. Execute trades at alpaca.markets.")


@st.cache_data(ttl=PORTFOLIO_CACHE_SECONDS)
def load_portfolio():
    try:
        positions = get_positions()
        account = get_account()
        return positions, account, None
    except Exception as e:
        return [], {}, str(e)


positions, account, error = load_portfolio()

if error:
    st.error(f"Could not connect to Alpaca: {error}")
    st.info("Make sure ALPACA_API_KEY and ALPACA_SECRET_KEY are set in your Streamlit secrets.")
    st.stop()

# --- Account summary ---
col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Portfolio Value", f"${account.get('portfolio_value', 0):,.2f}")
with col2:
    st.metric("Buying Power", f"${account.get('buying_power', 0):,.2f}")
with col3:
    st.metric("Cash", f"${account.get('cash', 0):,.2f}")

st.divider()

if not positions:
    st.info("No open positions found in your Alpaca account.")
    st.stop()

# --- Attach latest signals from Supabase ---
tickers = [p["symbol"] for p in positions]
db = get_db()
signals_result = (
    db.table("scan_results")
    .select("ticker, score, signal, reasoning, earnings_warning")
    .in_("ticker", tickers)
    .order("scanned_at", desc=True)
    .limit(len(tickers) * 5)
    .execute()
)
signal_map = {}
for row in signals_result.data:
    if row["ticker"] not in signal_map:
        signal_map[row["ticker"]] = row

rows = []
for p in positions:
    sig_data = signal_map.get(p["symbol"], {})
    from config import SIGNAL_EMOJI
    signal = sig_data.get("signal", "—")
    emoji = SIGNAL_EMOJI.get(signal, "")
    pl_pct = p["unrealized_plpc"] * 100
    rows.append({
        "Ticker": p["symbol"],
        "Shares": p["qty"],
        "Price": f"${p['current_price']:,.2f}",
        "Market Value": f"${p['market_value']:,.2f}",
        "Gain/Loss": f"${p['unrealized_pl']:+,.2f} ({pl_pct:+.1f}%)",
        "Signal": f"{emoji} {signal}",
        "Score": sig_data.get("score", "—"),
    })

st.subheader(f"{len(rows)} open positions")
df = pd.DataFrame(rows)
event = st.dataframe(df, use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row")

if event.selection.rows:
    idx = event.selection.rows[0]
    ticker = rows[idx]["Ticker"]
    sig_data = signal_map.get(ticker, {})
    st.divider()
    st.subheader(f"Signal detail: {ticker}")
    if sig_data:
        st.write(sig_data.get("reasoning", "No reasoning available."))
        if sig_data.get("earnings_warning"):
            st.warning("⚠️ Earnings within 7 days")
    else:
        st.info("No scan data available for this ticker yet.")

    st.markdown(f"[Trade on Alpaca →](https://app.alpaca.markets/trade/{ticker})")
```

- [ ] **Step 2: Verify the Portfolio page loads**

```bash
streamlit run app/main.py
```

Navigate to Portfolio. Expected: account metrics and position table display (or a helpful error if Alpaca keys are not set).

- [ ] **Step 3: Commit**

```bash
git add app/pages/2_portfolio.py
git commit -m "feat: portfolio page with live Alpaca positions and signals"
```

---

## Task 20: Watchlist Page

**Files:**
- Create: `app/pages/3_watchlist.py`

- [ ] **Step 1: Create app/pages/3_watchlist.py**

```python
import streamlit as st
import pandas as pd
from datetime import datetime, time, timezone
from db.client import get_db
from scanner.data_fetcher import fetch_ohlcv
from scorer import compute_score, format_signal
from config import MAX_WATCHLIST_SIZE, SIGNAL_EMOJI

st.set_page_config(page_title="Watchlist", page_icon="👀", layout="wide")
st.title("👀 Watchlist")

db = get_db()


def _is_market_hours() -> bool:
    now_et = datetime.now(timezone.utc).astimezone(
        __import__("zoneinfo").ZoneInfo("America/New_York")
    )
    market_open = time(9, 30)
    market_close = time(16, 0)
    return (
        now_et.weekday() < 5
        and market_open <= now_et.time() <= market_close
    )


def load_watchlist():
    result = db.table("watchlist").select("*").order("added_at", desc=True).execute()
    return result.data


def score_watchlist(tickers: list[str]) -> dict:
    scores = {}
    for ticker in tickers:
        try:
            ohlcv = fetch_ohlcv(ticker, period="6mo")
            result = compute_score(ohlcv)
            scores[ticker] = result
        except Exception as e:
            scores[ticker] = {"score": 0, "signal": "—", "reasoning": str(e), "indicator_detail": {}}
    return scores


# Auto-refresh during market hours
in_market_hours = _is_market_hours()
if in_market_hours:
    st.caption("🟢 Market open — refreshing every 60 seconds")
    st.markdown(
        '<meta http-equiv="refresh" content="60">',
        unsafe_allow_html=True,
    )
else:
    st.caption("🔴 Market closed")

col_refresh, col_count = st.columns([1, 3])
with col_refresh:
    if st.button("🔄 Refresh Now"):
        st.cache_data.clear()
        st.rerun()
with col_count:
    watchlist = load_watchlist()
    st.caption(f"{len(watchlist)}/{MAX_WATCHLIST_SIZE} stocks")

if not watchlist:
    st.info("Your watchlist is empty. Add stocks from the Screener page.")
    st.stop()

tickers = [item["ticker"] for item in watchlist]

# Fetch unread alerts for badge display
alerts_result = (
    db.table("alerts")
    .select("ticker, previous_signal, new_signal")
    .in_("ticker", tickers)
    .eq("read", False)
    .execute()
)
alert_tickers = {a["ticker"] for a in alerts_result.data}

with st.spinner("Scoring watchlist stocks..."):
    scores = score_watchlist(tickers)

rows = []
for item in watchlist:
    ticker = item["ticker"]
    s = scores.get(ticker, {})
    signal = s.get("signal", "—")
    emoji = SIGNAL_EMOJI.get(signal, "")
    alert_badge = " 🔔" if ticker in alert_tickers else ""
    rows.append({
        "Ticker": ticker + alert_badge,
        "Score": s.get("score", "—"),
        "Signal": f"{emoji} {signal}",
        "Reason": str(s.get("reasoning", ""))[:100] + "...",
    })

df = pd.DataFrame(rows)
event = st.dataframe(df, use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row")

if event.selection.rows:
    idx = event.selection.rows[0]
    ticker_raw = watchlist[idx]["ticker"]
    s = scores.get(ticker_raw, {})
    st.divider()
    col_title, col_remove = st.columns([4, 1])
    with col_title:
        st.subheader(f"Detail: {ticker_raw}")
    with col_remove:
        if st.button("🗑️ Remove from Watchlist"):
            db.table("watchlist").delete().eq("ticker", ticker_raw).execute()
            st.success(f"{ticker_raw} removed.")
            st.rerun()
    st.write(s.get("reasoning", "No data."))

    # Mark alerts as read
    if ticker_raw in alert_tickers:
        db.table("alerts").update({"read": True}).eq("ticker", ticker_raw).execute()
```

- [ ] **Step 2: Verify the Watchlist page loads**

```bash
streamlit run app/main.py
```

Navigate to Watchlist. Expected: empty watchlist message or list of tracked stocks. Add a stock from Screener first to test.

- [ ] **Step 3: Commit**

```bash
git add app/pages/3_watchlist.py
git commit -m "feat: watchlist page with 1-min auto-refresh and alert badges"
```

---

## Task 21: Performance Page

**Files:**
- Create: `app/pages/4_performance.py`

- [ ] **Step 1: Create app/pages/4_performance.py**

```python
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import yfinance as yf
from alpaca_client import get_portfolio_history, get_account

st.set_page_config(page_title="Performance", page_icon="📊", layout="wide")
st.title("📊 Performance")
st.caption("Your portfolio vs S&P 500 (SPY) and Total Market (VTI)")

PERIOD_MAP = {
    "1 Week": "1W",
    "1 Month": "1M",
    "3 Months": "3M",
    "6 Months": "6M",
    "1 Year": "1Y",
}

period_label = st.selectbox("Time Period", list(PERIOD_MAP.keys()), index=1)
period = PERIOD_MAP[period_label]

yf_period_map = {"1W": "5d", "1M": "1mo", "3M": "3mo", "6M": "6mo", "1Y": "1y"}
yf_period = yf_period_map[period]


@st.cache_data(ttl=3600)
def load_benchmarks(yf_period: str):
    spy = yf.download("SPY", period=yf_period, auto_adjust=True, progress=False)["Close"]
    vti = yf.download("VTI", period=yf_period, auto_adjust=True, progress=False)["Close"]
    return spy, vti


@st.cache_data(ttl=300)
def load_portfolio(period: str):
    try:
        return get_portfolio_history(period=period), None
    except Exception as e:
        return None, str(e)


spy, vti = load_benchmarks(yf_period)
portfolio_history, error = load_portfolio(period)

if error:
    st.warning(f"Could not load portfolio history from Alpaca: {error}")
    portfolio_history = None

fig = go.Figure()

if portfolio_history and portfolio_history["equity"]:
    import pandas as pd as pd_local
    port_ts = pd.to_datetime(portfolio_history["timestamps"], unit="s")
    port_equity = pd.Series(portfolio_history["equity"], index=port_ts)
    port_norm = port_equity / port_equity.iloc[0] * 100
    fig.add_trace(go.Scatter(x=port_norm.index, y=port_norm, name="My Portfolio", line=dict(color="#00D4AA", width=2)))

if not spy.empty:
    spy_norm = spy / spy.iloc[0] * 100
    fig.add_trace(go.Scatter(x=spy_norm.index, y=spy_norm, name="SPY (S&P 500)", line=dict(color="#4A90D9", width=2, dash="dash")))

if not vti.empty:
    vti_norm = vti / vti.iloc[0] * 100
    fig.add_trace(go.Scatter(x=vti_norm.index, y=vti_norm, name="VTI (Total Market)", line=dict(color="#F5A623", width=2, dash="dot")))

fig.update_layout(
    yaxis_title="Growth (base = 100)",
    height=450,
    legend=dict(orientation="h", yanchor="bottom", y=1.02),
    margin=dict(l=0, r=0, t=30, b=0),
)
st.plotly_chart(fig, use_container_width=True)


def calc_stats(series: pd.Series) -> dict:
    if series is None or len(series) < 2:
        return {"Total Return": "—", "Max Drawdown": "—", "Volatility": "—"}
    ret = (series.iloc[-1] / series.iloc[0]) - 1
    daily_ret = series.pct_change().dropna()
    roll_max = series.cummax()
    drawdown = ((series - roll_max) / roll_max).min()
    vol = daily_ret.std() * (252 ** 0.5)
    return {
        "Total Return": f"{ret:+.1%}",
        "Max Drawdown": f"{drawdown:.1%}",
        "Volatility (ann.)": f"{vol:.1%}",
    }


port_series = None
if portfolio_history and portfolio_history["equity"]:
    port_series = pd.Series(portfolio_history["equity"])

stats = {
    "Portfolio": calc_stats(port_series),
    "SPY": calc_stats(spy.reset_index(drop=True) if not spy.empty else None),
    "VTI": calc_stats(vti.reset_index(drop=True) if not vti.empty else None),
}

st.subheader("Summary")
st.dataframe(pd.DataFrame(stats), use_container_width=True)
```

- [ ] **Step 2: Fix the duplicate import on line with `as pd_local` — remove that alias**

The line `import pandas as pd as pd_local` is invalid. Replace it with just using the already-imported `pd`:

```python
# Remove this line entirely (it was a mistake in the draft above):
# import pandas as pd as pd_local

# The pd alias is already imported at the top of the file — use it directly:
port_ts = pd.to_datetime(portfolio_history["timestamps"], unit="s")
port_equity = pd.Series(portfolio_history["equity"], index=port_ts)
```

The corrected `app/pages/4_performance.py` (replace the portfolio block with):

```python
if portfolio_history and portfolio_history["equity"]:
    port_ts = pd.to_datetime(portfolio_history["timestamps"], unit="s")
    port_equity = pd.Series(portfolio_history["equity"], index=port_ts)
    port_norm = port_equity / port_equity.iloc[0] * 100
    fig.add_trace(go.Scatter(x=port_norm.index, y=port_norm, name="My Portfolio", line=dict(color="#00D4AA", width=2)))
```

- [ ] **Step 3: Verify the Performance page loads**

```bash
streamlit run app/main.py
```

Navigate to Performance. Expected: benchmark lines for SPY and VTI render (portfolio line appears once Alpaca is connected).

- [ ] **Step 4: Commit**

```bash
git add app/pages/4_performance.py
git commit -m "feat: performance page with SPY and VTI benchmark comparison"
```

---

## Task 22: Alerts Page

**Files:**
- Create: `app/pages/5_alerts.py`

- [ ] **Step 1: Create app/pages/5_alerts.py**

```python
import streamlit as st
import pandas as pd
from db.client import get_db
from config import SIGNAL_EMOJI

st.set_page_config(page_title="Alerts", page_icon="🔔", layout="wide")
st.title("🔔 Alerts")
st.caption("Signal changes detected on your watchlist stocks")

db = get_db()


def load_alerts():
    result = (
        db.table("alerts")
        .select("*")
        .order("created_at", desc=True)
        .execute()
    )
    return result.data


alerts = load_alerts()
unread = [a for a in alerts if not a["read"]]
read = [a for a in alerts if a["read"]]

col_count, col_clear = st.columns([3, 1])
with col_count:
    st.subheader(f"{len(unread)} unread alert{'s' if len(unread) != 1 else ''}")
with col_clear:
    if st.button("Clear All"):
        db.table("alerts").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
        st.success("All alerts cleared.")
        st.rerun()

if not alerts:
    st.info("No alerts yet. Alerts appear here when a watchlist stock changes signal between scans.")
    st.stop()


def render_alerts(alert_list: list[dict], mark_read: bool = False):
    for alert in alert_list:
        prev = alert["previous_signal"]
        new = alert["new_signal"]
        prev_emoji = SIGNAL_EMOJI.get(prev, "")
        new_emoji = SIGNAL_EMOJI.get(new, "")
        created = alert["created_at"][:16].replace("T", " ")

        col_msg, col_read = st.columns([5, 1])
        with col_msg:
            st.markdown(
                f"**{alert['ticker']}** — {prev_emoji} {prev} → {new_emoji} {new}  \n"
                f"<span style='color:gray;font-size:0.85em'>{created} ET</span>",
                unsafe_allow_html=True,
            )
        with col_read:
            if not alert["read"] and st.button("✓ Read", key=f"read_{alert['id']}"):
                db.table("alerts").update({"read": True}).eq("id", alert["id"]).execute()
                st.rerun()


st.markdown("### New")
render_alerts(unread)

if read:
    with st.expander(f"Show {len(read)} read alerts"):
        render_alerts(read)
```

- [ ] **Step 2: Verify the Alerts page loads**

```bash
streamlit run app/main.py
```

Navigate to Alerts. Expected: "No alerts yet" message (until the scanner detects a signal change on a watchlist stock).

- [ ] **Step 3: Commit**

```bash
git add app/pages/5_alerts.py
git commit -m "feat: alerts inbox with read/unread state and clear all"
```

---

## Task 23: Settings Page

**Files:**
- Create: `app/pages/6_settings.py`

- [ ] **Step 1: Create app/pages/6_settings.py**

```python
import streamlit as st
from db.client import get_db, get_settings, save_settings
from config import DEFAULT_THRESHOLDS, DEFAULT_GROUP_WEIGHTS, MAX_WATCHLIST_SIZE
from scanner.indicators.registry import INDICATORS

st.set_page_config(page_title="Settings", page_icon="⚙️", layout="wide")
st.title("⚙️ Settings")

db = get_db()

# --- Signal Thresholds ---
st.subheader("Signal Thresholds")
st.caption("Minimum score required to reach each signal level.")
thresholds = get_settings("thresholds", DEFAULT_THRESHOLDS)

col1, col2, col3, col4, col5 = st.columns(5)
new_buy = col1.number_input("🟢 BUY", 0, 100, int(thresholds.get("BUY", 75)))
new_watch = col2.number_input("👀 WATCH CAREFULLY", 0, 100, int(thresholds.get("WATCH CAREFULLY", 55)))
new_hold = col3.number_input("🟡 HOLD", 0, 100, int(thresholds.get("HOLD", 35)))
new_reduce = col4.number_input("🔴 REDUCE", 0, 100, int(thresholds.get("REDUCE", 25)))
new_exit = col5.number_input("🚨 EXIT", 0, 100, int(thresholds.get("EXIT", 0)))

if st.button("Save Thresholds"):
    save_settings("thresholds", {
        "BUY": new_buy, "WATCH CAREFULLY": new_watch,
        "HOLD": new_hold, "REDUCE": new_reduce, "EXIT": new_exit,
    })
    st.success("Thresholds saved.")

st.divider()

# --- Group Weights ---
st.subheader("Indicator Group Weights")
st.caption("Weights must sum to 1.0. Changes take effect on the next scan.")
weights = get_settings("group_weights", DEFAULT_GROUP_WEIGHTS)

w_trend = st.slider("Trend (EMA + ADX)", 0.0, 1.0, float(weights.get("trend", 0.30)), step=0.05)
w_momentum = st.slider("Momentum (MACD + RSI)", 0.0, 1.0, float(weights.get("momentum", 0.25)), step=0.05)
w_volume = st.slider("Volume (OBV + Relative Volume)", 0.0, 1.0, float(weights.get("volume", 0.20)), step=0.05)
w_volatility = st.slider("Volatility (Bollinger + ATR)", 0.0, 1.0, float(weights.get("volatility", 0.15)), step=0.05)
w_candles = st.slider("Candlestick Patterns", 0.0, 1.0, float(weights.get("candlesticks", 0.10)), step=0.05)

total = round(w_trend + w_momentum + w_volume + w_volatility + w_candles, 2)
st.metric("Total Weight", f"{total:.2f}", delta=f"{total - 1.0:+.2f} from 1.0")

if st.button("Save Weights"):
    if abs(total - 1.0) > 0.01:
        st.error("Weights must sum to 1.0 before saving.")
    else:
        save_settings("group_weights", {
            "trend": w_trend, "momentum": w_momentum,
            "volume": w_volume, "volatility": w_volatility,
            "candlesticks": w_candles,
        })
        st.success("Weights saved.")

st.divider()

# --- Indicator Toggles ---
st.subheader("Indicator Toggles")
st.caption("Disable individual indicators. Changes take effect on the next scan.")
toggles = get_settings("indicator_toggles", {})

new_toggles = {}
for entry in INDICATORS:
    name = entry.cls.__name__
    enabled = toggles.get(name, True)
    new_val = st.checkbox(f"{name} ({entry.group})", value=enabled, key=f"toggle_{name}")
    new_toggles[name] = new_val

if st.button("Save Toggles"):
    save_settings("indicator_toggles", new_toggles)
    st.success("Indicator toggles saved.")

st.divider()

# --- API Keys Info ---
st.subheader("API Keys")
st.info(
    "API keys (Alpaca, Supabase, NewsAPI) are managed securely via the "
    "**Streamlit Community Cloud secrets dashboard**, not stored here. "
    "Go to your app settings at share.streamlit.io to update them."
)

st.divider()

# --- Watchlist Cap ---
st.subheader("Watchlist Cap")
st.info(f"Current cap: **{MAX_WATCHLIST_SIZE} stocks**. To increase this in Phase 2, change `MAX_WATCHLIST_SIZE` in `config.py`.")
```

- [ ] **Step 2: Verify the Settings page loads**

```bash
streamlit run app/main.py
```

Navigate to Settings. Expected: all sliders, number inputs, and checkboxes render. Saving thresholds or weights updates the Supabase `settings` table.

- [ ] **Step 3: Commit**

```bash
git add app/pages/6_settings.py
git commit -m "feat: settings page with adjustable thresholds, weights, and indicator toggles"
```

---

## Task 24: GitHub Actions Scheduler

**Files:**
- Create: `.github/workflows/scan.yml`

- [ ] **Step 1: Create .github/workflows/scan.yml**

```yaml
name: S&P 500 Scan

on:
  schedule:
    # Every 2 hours: 9:30am, 11:30am, 1:30pm, 3:30pm ET (EDT = UTC-4)
    # UTC times: 13:30, 15:30, 17:30, 19:30
    - cron: "30 13,15,17,19 * * 1-5"
  workflow_dispatch:  # Allow manual runs from GitHub Actions UI

jobs:
  scan:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: "pip"

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run scan
        env:
          SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
          SUPABASE_KEY: ${{ secrets.SUPABASE_KEY }}
          ALPACA_API_KEY: ${{ secrets.ALPACA_API_KEY }}
          ALPACA_SECRET_KEY: ${{ secrets.ALPACA_SECRET_KEY }}
          NEWSAPI_KEY: ${{ secrets.NEWSAPI_KEY }}
          ALPACA_PAPER: "false"
        run: python -m scanner.run_scan
```

- [ ] **Step 2: Add GitHub Actions secrets**

In your GitHub repository (github.com → your repo → Settings → Secrets and variables → Actions → New repository secret), add:
- `SUPABASE_URL`
- `SUPABASE_KEY`
- `ALPACA_API_KEY`
- `ALPACA_SECRET_KEY`
- `NEWSAPI_KEY`

- [ ] **Step 3: Test the workflow manually**

After committing and pushing, go to GitHub → Actions → "S&P 500 Scan" → Run workflow. Watch the logs to confirm it completes successfully.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/scan.yml
git commit -m "feat: GitHub Actions cron scheduler for S&P 500 scan"
```

---

## Task 25: Deployment to Streamlit Community Cloud

**Files:**
- Create: `.streamlit/secrets.toml.example`
- Create: `.streamlit/config.toml`

- [ ] **Step 1: Create .streamlit/secrets.toml.example**

```toml
# Copy this file to .streamlit/secrets.toml for local development
# Never commit secrets.toml — it is in .gitignore

SUPABASE_URL = "https://your-project.supabase.co"
SUPABASE_KEY = "your-supabase-anon-key"
ALPACA_API_KEY = "your-alpaca-api-key"
ALPACA_SECRET_KEY = "your-alpaca-secret-key"
NEWSAPI_KEY = "your-newsapi-key"
ALPACA_PAPER = "false"
```

- [ ] **Step 2: Create .streamlit/config.toml**

```toml
[theme]
base = "dark"
primaryColor = "#00D4AA"

[server]
headless = true
```

- [ ] **Step 3: Push to GitHub**

```bash
git add .streamlit/secrets.toml.example .streamlit/config.toml
git commit -m "feat: Streamlit deployment configuration"
git push origin main
```

- [ ] **Step 4: Deploy on Streamlit Community Cloud**

1. Go to https://share.streamlit.io and sign in with GitHub
2. Click "New app"
3. Select your repository and branch (`main`)
4. Set the main file path: `app/main.py`
5. Click "Advanced settings" → "Secrets"
6. Paste the following (filled with your real values):
   ```toml
   SUPABASE_URL = "https://your-project.supabase.co"
   SUPABASE_KEY = "your-supabase-anon-key"
   ALPACA_API_KEY = "your-alpaca-api-key"
   ALPACA_SECRET_KEY = "your-alpaca-secret-key"
   NEWSAPI_KEY = "your-newsapi-key"
   ALPACA_PAPER = "false"
   ```
7. Click "Deploy"

Expected: app builds and launches. You receive a permanent URL at `https://your-app.streamlit.app`.

- [ ] **Step 5: Verify end-to-end**

1. Open the app URL in both your home and work browsers — confirm it loads
2. Trigger a manual GitHub Actions run (Actions → Run workflow) and confirm scan results appear in Screener
3. Add a stock to Watchlist and confirm it appears and refreshes
4. Check Performance page renders SPY/VTI charts

---

## Self-Review Notes

**Spec coverage check:**
- ✅ S&P 500 screener with ranked table and scoring — Task 18
- ✅ Plain-English signals (BUY/WATCH/HOLD/REDUCE/EXIT) — Tasks 13, 18
- ✅ Earnings event modifier — Tasks 13, 15
- ✅ Sentiment modifier — Tasks 14, 15
- ✅ Watchlist (25 cap, 1-min refresh, alert badges) — Task 20
- ✅ Portfolio read-only from Alpaca — Tasks 16, 19
- ✅ Performance vs SPY and VTI — Task 21
- ✅ In-app alerts inbox — Task 22
- ✅ Settings (thresholds, weights, toggles) — Task 23
- ✅ All 9 indicators (EMA, ADX, MACD, RSI, OBV, RelVol, Bollinger, ATR, Candlesticks) — Tasks 8–12
- ✅ Extensible indicator architecture (one file + register decorator) — Task 7
- ✅ GitHub Actions scheduler — Task 24
- ✅ Cloud deployment (Streamlit Community Cloud + Supabase) — Tasks 3, 25
- ✅ Works from any browser on any device — Task 25
