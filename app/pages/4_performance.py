import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import yfinance as yf
import requests
from config import get_secret

st.set_page_config(page_title="Performance", page_icon="📊", layout="wide")
st.title("📊 Performance")
st.caption("Chart shows position performance over the selected period. All-time P&L since entry is shown in the header above.")

YF_PERIOD_MAP   = {"1D": "1d",  "1W": "5d",  "1M": "1mo", "3M": "3mo", "6M": "6mo", "1Y": "1y"}
YF_INTERVAL_MAP = {"1D": "15m", "1W": "1h",  "1M": "1d",  "3M": "1d",  "6M": "1d",  "1Y": "1d"}

period_label = st.selectbox("Time Period", list(YF_PERIOD_MAP.keys()), index=2)
yf_period   = YF_PERIOD_MAP[period_label]
yf_interval = YF_INTERVAL_MAP[period_label]

BASE = "https://paper-api.alpaca.markets/v2"


def _headers() -> dict:
    return {
        "APCA-API-KEY-ID":     get_secret("ALPACA_API_KEY"),
        "APCA-API-SECRET-KEY": get_secret("ALPACA_SECRET_KEY"),
    }


def get_positions() -> list[dict]:
    try:
        r = requests.get(f"{BASE}/positions", headers=_headers(), timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception:
        return []


def get_filled_orders() -> dict[str, dict]:
    """Return {ticker: {entry_date, avg_price, qty}} from filled buy orders."""
    try:
        r = requests.get(
            f"{BASE}/orders",
            headers=_headers(),
            params={"status": "filled", "limit": 100, "direction": "asc"},
            timeout=10,
        )
        r.raise_for_status()
        entries = {}
        for o in r.json():
            if o.get("side") == "buy" and o.get("filled_at") and o.get("filled_avg_price"):
                ticker = o["symbol"]
                if ticker not in entries:
                    ts = pd.Timestamp(o["filled_at"])
                    # tz_convert(None) strips timezone from tz-aware timestamps
                    entry_date = ts.tz_convert(None) if ts.tzinfo else ts
                    entries[ticker] = {
                        "entry_date":  entry_date,
                        "entry_price": float(o["filled_avg_price"]),
                        "qty":         float(o.get("filled_qty", 0)),
                    }
        return entries
    except Exception:
        return {}


@st.cache_data(ttl=3600)
def load_benchmarks(yf_period: str, yf_interval: str):
    try:
        spy = yf.download("SPY", period=yf_period, interval=yf_interval, auto_adjust=True, progress=False)["Close"].squeeze()
        vti = yf.download("VTI", period=yf_period, interval=yf_interval, auto_adjust=True, progress=False)["Close"].squeeze()
    except Exception:
        spy = pd.Series(dtype=float)
        vti = pd.Series(dtype=float)
    return spy, vti


def load_invested_performance(yf_period: str, yf_interval: str,
                              positions: list[dict], filled: dict) -> pd.Series | None:
    if not positions:
        return None

    total_cost = sum(float(p["cost_basis"]) for p in positions)
    if total_cost == 0:
        return None

    # Build a map of Alpaca's real-time prices per ticker
    live_prices = {p["symbol"]: float(p["current_price"]) for p in positions}

    portfolio_return = None

    for pos in positions:
        ticker     = pos["symbol"]
        qty        = float(pos["qty"])
        cost_basis = float(pos["cost_basis"])
        weight     = cost_basis / total_cost

        entry_info  = filled.get(ticker, {})
        entry_price = entry_info.get("entry_price") or (cost_basis / qty)
        entry_date  = entry_info.get("entry_date")

        try:
            prices = yf.download(
                ticker, period=yf_period, interval=yf_interval,
                auto_adjust=True, progress=False,
            )["Close"].squeeze()
            if prices.empty or len(prices) < 2:
                continue

            # Strip timezone for consistent comparison
            idx = prices.index.tz_localize(None) if prices.index.tz else prices.index
            prices.index = idx

            # Override the last bar with Alpaca's real-time price so the
            # chart endpoint always matches the live P&L header
            if ticker in live_prices:
                prices.iloc[-1] = live_prices[ticker]

            # Determine anchor point for this position
            if yf_period == "1d":
                anchor = float(prices.iloc[0])
            elif entry_date is not None and entry_date > idx[0]:
                prices = prices[idx >= entry_date]
                if len(prices) < 2:
                    continue
                anchor = entry_price
            else:
                anchor = float(prices.iloc[0])

            ret = (prices / anchor - 1) * weight
            portfolio_return = ret if portfolio_return is None else portfolio_return.add(ret, fill_value=0)

        except Exception:
            continue

    return portfolio_return


# --- Live P&L from Alpaca (ground truth) ---
_live_positions = get_positions()
if _live_positions:
    _total_cost = sum(float(p["cost_basis"])    for p in _live_positions)
    _total_mkt  = sum(float(p["market_value"])  for p in _live_positions)
    _total_pl   = sum(float(p["unrealized_pl"]) for p in _live_positions)
    _total_pct  = (_total_pl / _total_cost * 100) if _total_cost else 0
    lc1, lc2, lc3, lc4 = st.columns(4)
    lc1.metric("Invested",       f"${_total_cost:,.2f}")
    lc2.metric("Market Value",   f"${_total_mkt:,.2f}")
    lc3.metric("Unrealized P&L", f"${_total_pl:+,.0f}", f"{_total_pct:+.2f}%")
    lc4.metric("Open Positions",  len(_live_positions))
    st.divider()

with st.spinner("Loading position performance..."):
    _positions_for_chart = get_positions()
    _filled_for_chart    = get_filled_orders()
    port_return = load_invested_performance(yf_period, yf_interval, _positions_for_chart, _filled_for_chart)

spy, vti = load_benchmarks(yf_period, yf_interval)

def _to_et(s: pd.Series) -> pd.Series:
    """Convert a Series with naive-UTC index to ET for display."""
    idx = pd.DatetimeIndex(s.index)
    if idx.tz is None:
        idx = idx.tz_localize("UTC")
    return s.set_axis(idx.tz_convert("America/New_York"))


fig = go.Figure()
port_for_stats = None

if port_return is not None and len(port_return.dropna()) >= 2:
    port_clean = port_return.dropna()
    port_norm = 100 + port_clean * 100
    port_for_stats = port_norm
    fig.add_trace(go.Scatter(
        x=_to_et(port_norm).index, y=port_norm,
        name="My Positions",
        line=dict(color="#00D4AA", width=2),
    ))
else:
    st.info("No open positions found — performance will appear once your Alpaca account has filled orders.")

bench_start = port_return.dropna().index[0] if port_return is not None and len(port_return.dropna()) >= 1 else None

if not spy.empty:
    spy_idx = spy.index.tz_localize(None) if spy.index.tz else spy.index
    spy.index = spy_idx
    spy_plot = spy[spy_idx >= bench_start] if bench_start else spy
    if not spy_plot.empty:
        spy_norm = spy_plot / spy_plot.iloc[0] * 100
        fig.add_trace(go.Scatter(x=_to_et(spy_norm).index, y=spy_norm, name="SPY (S&P 500)",
                                 line=dict(color="#4A90D9", width=2, dash="dash")))

if not vti.empty:
    vti_idx = vti.index.tz_localize(None) if vti.index.tz else vti.index
    vti.index = vti_idx
    vti_plot = vti[vti_idx >= bench_start] if bench_start else vti
    if not vti_plot.empty:
        vti_norm = vti_plot / vti_plot.iloc[0] * 100
        fig.add_trace(go.Scatter(x=_to_et(vti_norm).index, y=vti_norm, name="VTI (Total Market)",
                                 line=dict(color="#F5A623", width=2, dash="dot")))

fig.add_hline(y=100, line_dash="dash", line_color="gray", opacity=0.4)
fig.update_layout(
    yaxis_title="Growth (base = 100 at entry)",
    height=450,
    legend=dict(orientation="h", yanchor="bottom", y=1.02),
    margin=dict(l=0, r=0, t=30, b=0),
    hovermode="x unified",
)
st.plotly_chart(fig, use_container_width=True)


def calc_stats(series: pd.Series | None) -> dict:
    if series is None or len(series) < 2:
        return {"Total Return": "—", "Max Drawdown": "—", "Volatility (ann.)": "—"}
    series = series.dropna()
    ret      = (series.iloc[-1] / series.iloc[0]) - 1
    daily    = series.pct_change().dropna()
    drawdown = ((series - series.cummax()) / series.cummax()).min()
    vol      = daily.std() * (252 ** 0.5)
    return {
        "Total Return":      f"{ret:+.1%}",
        "Max Drawdown":      f"{drawdown:.1%}",
        "Volatility (ann.)": f"{vol:.1%}",
    }


st.subheader("Summary")
stats = {
    "My Positions": calc_stats(port_for_stats),
    "SPY":          calc_stats(spy.reset_index(drop=True) if not spy.empty else None),
    "VTI":          calc_stats(vti.reset_index(drop=True) if not vti.empty else None),
}
st.dataframe(pd.DataFrame(stats), use_container_width=True)

# --- Position breakdown ---
positions = get_positions()
if positions:
    st.subheader("Position Breakdown")
    rows = []
    for p in positions:
        qty         = float(p["qty"])
        cost_basis  = float(p["cost_basis"])
        mkt_value   = float(p["market_value"])
        entry_price = cost_basis / qty
        rows.append({
            "Ticker":       p["symbol"],
            "Qty":          qty,
            "Entry $":      entry_price,
            "Current $":    float(p["current_price"]),
            "Market Value": mkt_value,
            "Return %":     float(p["unrealized_plpc"]) * 100,
            "P&L $":        float(p["unrealized_pl"]),
        })
    st.dataframe(
        pd.DataFrame(rows),
        hide_index=True,
        use_container_width=True,
        column_config={
            "Qty":          st.column_config.NumberColumn("Qty",          format="%.6f"),
            "Entry $":      st.column_config.NumberColumn("Entry $",      format="$%.2f"),
            "Current $":    st.column_config.NumberColumn("Current $",    format="$%.2f"),
            "Market Value": st.column_config.NumberColumn("Market Value", format="$%,.2f"),
            "Return %":     st.column_config.NumberColumn("Return %",     format="%+.2f%%"),
            "P&L $":        st.column_config.NumberColumn("P&L $",        format="$%+,.2f"),
        },
    )
