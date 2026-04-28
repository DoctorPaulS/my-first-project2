# Stock Advisor App — Design Spec
**Date:** 2026-04-27
**Status:** Approved

---

## Overview

A cloud-hosted Streamlit web app that screens S&P 500 stocks using technical analysis, surfaces relevant market events, and monitors portfolio performance against benchmark indices. The app advises on what to buy, hold, watch, or sell — the user executes trades manually on Alpaca's own platform. Alpaca is connected read-only in Phase 1.

---

## Goals

- Screen S&P 500 stocks and rank them by a composite technical analysis score
- Provide plain-English buy/sell/hold/watch signals with reasoning
- Surface upcoming events (earnings, sentiment) that could affect picks
- Monitor a personal watchlist of up to 25 stocks with near-real-time updates
- Track portfolio performance vs S&P 500 (SPY) and VTI benchmarks
- Run from any browser on any computer (home or work)
- Be maintainable and extensible by a beginner developer

## Non-Goals (Phase 1)

- Automated or app-initiated order placement (manual execution on Alpaca only)
- Screening beyond the S&P 500 universe
- Email or push notifications
- Watchlist beyond 25 stocks

---

## Tech Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| Language | Python | Beginner-friendly, best data ecosystem |
| Frontend/Backend | Streamlit | Single language, no HTML/CSS/JS needed |
| Database | Supabase (PostgreSQL) | Free, cloud-hosted, syncs across devices |
| Hosting | Streamlit Community Cloud | Free, purpose-built for Streamlit, permanent URL |
| Scheduler | GitHub Actions | Free, runs scans on cron without a server |
| Price/Earnings Data | yfinance | Free, covers all S&P 500 stocks |
| Technical Indicators | pandas-ta | 130+ indicators, simple Python API |
| Portfolio Data | Alpaca Python SDK | Read-only access to live account |
| Sentiment | NewsAPI.org | Free tier sufficient for daily headlines |
| Benchmarks | yfinance (SPY, VTI) | Free |

---

## Architecture

```
Any browser (home or work)
        ↓
Streamlit Community Cloud  ←→  Supabase (PostgreSQL)
        ↓                            ↑
  Alpaca API (read-only)    GitHub Actions (cron scan)
  yfinance                       ↓
  NewsAPI                   yfinance + pandas-ta
                            (scores all S&P 500 stocks,
                             writes results to Supabase)
```

**Key principle:** The GitHub Actions scheduler is the only process that writes scan results. The Streamlit app only reads from Supabase and reads from external APIs (Alpaca, yfinance for watchlist refresh). No order placement in Phase 1.

---

## Data Flow

### Scheduled Scan (GitHub Actions)
- Runs every 2 hours from 9:30am–4:30pm ET on US trading days
- Downloads previous session OHLCV data for all ~503 S&P 500 stocks via yfinance
- Calculates all technical indicators using pandas-ta
- Scores each stock (0–100) and generates reasoning text
- Writes ranked results to Supabase `scan_results` table
- Compares new signals to previous scan; writes any signal changes to `alerts` table for watchlist stocks

### Watchlist Refresh (In-App)
- During market hours, the Watchlist page auto-refreshes every 1 minute
- Fetches latest quotes from Alpaca for watchlist stocks only (fast, targeted)
- Recalculates scores on the fly for those 25 stocks
- Manual "Refresh Now" button available at all times

### Portfolio Sync
- Reads positions, balances, and order history from Alpaca on every page load
- Caches for 60 seconds to avoid hammering the API

---

## Pages

### 1. Screener
The core tool. Displays the most recent scan results as a ranked, filterable table.

**Filters (sidebar):** Sector, minimum score, signal type (BUY only, etc.), minimum average volume.

**Table columns:**
```
Ticker | Company | Score | Signal | Key Reason | Earnings Warning
```

**Signal display:**
- 🟢 BUY
- 👀 WATCH CAREFULLY
- 🟡 HOLD
- 🔴 SELL
- ⚠️ appended when earnings are within 7 days
- 🔻 appended when negative sentiment detected

**Expandable row:** Clicking any row opens a full analysis card containing:
- Interactive price chart (candlestick + indicator overlays)
- Individual indicator readings and sub-scores
- Upcoming events (earnings date, recent news headlines)
- "Add to Watchlist" button

---

### 2. Portfolio
Displays live Alpaca holdings (read-only).

- Position list with current price, quantity, market value, gain/loss
- Each position scored and signaled identically to Screener
- No order placement in Phase 1; a "Trade on Alpaca" link opens alpaca.markets

---

### 3. Watchlist
Personal tracking list, capped at 25 stocks.

- 1-minute auto-refresh during market hours
- Manual "Refresh Now" button
- Alert badges on stocks whose signal changed since last visit
- "Remove from Watchlist" button per stock
- Cap of 25 is stored as a config constant (`MAX_WATCHLIST_SIZE = 25`) — increasing it in Phase 2 is a one-line change

---

### 4. Performance
Compares Alpaca portfolio returns to SPY and VTI.

**Time range selector:** 1W, 1M, 3M, 6M, 1Y, All Time

**Line chart:** Portfolio value vs SPY vs VTI (normalized to 100 at start of period)

**Summary table:**
```
Metric              | Portfolio | SPY   | VTI
--------------------|-----------|-------|------
Total Return        | +12.4%    | +8.1% | +7.9%
Annualized Return   | +18.2%    | +12.0%| +11.7%
Max Drawdown        | -6.3%     | -4.1% | -4.0%
Volatility (σ)      | 14.2%     | 11.8% | 11.6%
```

---

### 5. Alerts
In-app notification inbox.

- Each alert: stock ticker, previous signal, new signal, timestamp
- Example: *"AAPL: HOLD → WATCH CAREFULLY (2026-04-27 14:02 ET)"*
- Alerts auto-expire after 7 days
- "Clear All" button
- Unread count badge shown in sidebar navigation

---

### 6. Settings
- **Indicator toggles:** Enable/disable any individual indicator
- **Score thresholds:** Adjust BUY/WATCH/HOLD/SELL cutoffs (default: 75/55/35/0)
- **Indicator weights:** Adjust group weights (Trend/Momentum/Volume/Volatility/Candlesticks)
- **Watchlist cap:** Displayed (editable in config file for now)
- **Alpaca API keys:** Displayed as masked values; managed via the Streamlit Community Cloud secrets dashboard (not writable from within the app)
- **Paper Trading toggle:** Swaps Alpaca endpoint to paper trading environment for safe testing

---

## Scoring System

### Composite Score (0–100)

| Group | Indicators | Weight |
|-------|-----------|--------|
| Trend | EMA 20, EMA 50, EMA 200, ADX | 30% |
| Momentum | MACD, RSI (14) | 25% |
| Volume | OBV, Relative Volume | 20% |
| Volatility/Timing | Bollinger Bands, ATR | 15% |
| Candlestick Patterns | Engulfing, Hammer, Pin Bar, Doji, Morning/Evening Star | 10% |

Each group produces an internal sub-score of 0–10, multiplied by its weight, summed to 0–100.

### Signal Thresholds (adjustable in Settings)

| Score | Signal |
|-------|--------|
| 75–100 | 🟢 BUY |
| 55–74 | 👀 WATCH CAREFULLY |
| 35–54 | 🟡 HOLD |
| 0–34 | 🔴 SELL |

### Event Modifiers
Applied to the signal display label only — the numeric score is never modified, keeping TA clean:

- Earnings within 7 days → ⚠️ warning appended
- Negative sentiment detected → 🔻 flag appended
- BUY signal + earnings within 3 days → display overrides to WATCH CAREFULLY automatically

### Reasoning Text
Auto-generated plain-English string from fired indicator conditions. Example:

> *"Price is above the 20, 50, and 200 EMA — strong uptrend. MACD crossed bullish 2 days ago. RSI at 58 — room to run without being overbought. Volume is 2.3x the 20-day average. Bullish engulfing candle yesterday confirms buyer conviction."*

---

## Indicator Architecture (Extensibility)

Each indicator is a self-contained Python module implementing a standard interface:

```python
def score(ohlcv: pd.DataFrame, params: dict) -> tuple[float, str]:
    # Returns: (score 0-10, reasoning string)
```

Indicators are registered in a single config list. Adding a new indicator (e.g., Ichimoku Cloud, Supertrend, VWAP) means:
1. Create one new Python file implementing the interface above
2. Add it to the config list with its group and weight

Nothing else in the app changes. pandas-ta provides the underlying calculations for all standard indicators.

---

## Database Schema (Supabase)

### `scan_results`
| Column | Type | Notes |
|--------|------|-------|
| id | uuid | primary key |
| ticker | text | |
| scanned_at | timestamptz | |
| score | float | 0–100 |
| signal | text | BUY / WATCH CAREFULLY / HOLD / SELL |
| reasoning | text | plain-English explanation |
| indicator_detail | jsonb | sub-scores per indicator |
| earnings_warning | bool | |
| sentiment_flag | bool | |

### `watchlist`
| Column | Type | Notes |
|--------|------|-------|
| id | uuid | primary key |
| ticker | text | |
| added_at | timestamptz | |
| notes | text | optional user notes |

### `alerts`
| Column | Type | Notes |
|--------|------|-------|
| id | uuid | primary key |
| ticker | text | |
| previous_signal | text | |
| new_signal | text | |
| created_at | timestamptz | |
| read | bool | |
| expires_at | timestamptz | auto-set to created_at + 7 days |

### `settings`
| Column | Type | Notes |
|--------|------|-------|
| key | text | primary key |
| value | jsonb | thresholds, weights, toggles |

---

## Deployment

### Streamlit Community Cloud
- Connect GitHub repository
- Set Alpaca API keys and Supabase credentials as secrets (never in code)
- App available at permanent `https://your-app.streamlit.app` URL
- Accessible from any browser on any device

### GitHub Actions Scheduler
- Cron: `30 13,15,17,19 * * 1-5` (UTC — equivalent to 9:30am, 11:30am, 1:30pm, 3:30pm ET during EDT; adjust by 1hr during EST)
- Runs `scripts/run_scan.py`
- Supabase and API credentials stored as GitHub Actions secrets

---

## Future Phases

| Phase | Feature |
|-------|---------|
| 2 | Expand universe beyond S&P 500 (Russell 1000, full US market) |
| 2 | Increase watchlist cap beyond 25 |
| 2 | Order placement via app with confirmation dialog |
| 3 | Email notifications for significant signal changes |
| 3 | Backtesting — see how signals performed historically |
| 3 | Custom stock screens (user-defined indicator combinations) |
