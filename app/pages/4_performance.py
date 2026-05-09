import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import yfinance as yf
from alpaca_client import get_positions

st.set_page_config(page_title="Performance", page_icon="📊", layout="wide")
st.title("📊 Performance")
st.caption("Invested positions vs S&P 500 (SPY) and Total Market (VTI) — cash excluded")

PERIOD_MAP = {
    "1 Day": "1D",
    "1 Week": "1W",
    "1 Month": "1M",
    "3 Months": "3M",
    "6 Months": "6M",
    "1 Year": "1Y",
}

period_label = st.selectbox("Time Period", list(PERIOD_MAP.keys()), index=2)
period = PERIOD_MAP[period_label]

yf_period_map   = {"1D": "1d",  "1W": "5d",  "1M": "1mo", "3M": "3mo", "6M": "6mo", "1Y": "1y"}
yf_interval_map = {"1D": "15m", "1W": "1h",  "1M": "1d",  "3M": "1d",  "6M": "1d",  "1Y": "1d"}
yf_period   = yf_period_map[period]
yf_interval = yf_interval_map[period]


@st.cache_data(ttl=3600)
def load_benchmarks(yf_period: str, yf_interval: str):
    try:
        spy = yf.download("SPY", period=yf_period, interval=yf_interval, auto_adjust=True, progress=False)["Close"].squeeze()
        vti = yf.download("VTI", period=yf_period, interval=yf_interval, auto_adjust=True, progress=False)["Close"].squeeze()
    except Exception as e:
        st.warning(f"Could not load benchmark data: {e}")
        spy = pd.Series(dtype=float)
        vti = pd.Series(dtype=float)
    return spy, vti


def load_positions_performance(yf_period: str, yf_interval: str) -> pd.Series | None:
    """
    Build a portfolio equity curve from actual position quantities × historical prices.
    Cash is excluded — only invested holdings are reflected.
    """
    try:
        positions = get_positions()
    except Exception:
        return None

    if not positions:
        return None

    portfolio_value = None
    for pos in positions:
        ticker = pos["symbol"]
        qty = pos["qty"]
        try:
            prices = yf.download(
                ticker, period=yf_period, interval=yf_interval,
                auto_adjust=True, progress=False,
            )["Close"].squeeze()
            if prices.empty or len(prices) < 2:
                continue
            holding_value = prices * qty
            portfolio_value = holding_value if portfolio_value is None else portfolio_value.add(holding_value, fill_value=0)
        except Exception:
            continue

    return portfolio_value


spy, vti = load_benchmarks(yf_period, yf_interval)

with st.spinner("Loading position history..."):
    port_value = load_positions_performance(yf_period, yf_interval)

fig = go.Figure()

port_series_for_stats = None
if port_value is not None and len(port_value.dropna()) >= 2:
    port_clean = port_value.dropna()
    if port_clean.iloc[0] > 0:
        port_norm = port_clean / port_clean.iloc[0] * 100
        port_series_for_stats = port_clean
        fig.add_trace(go.Scatter(
            x=port_norm.index, y=port_norm,
            name="My Positions",
            line=dict(color="#00D4AA", width=2),
        ))
else:
    st.info("No open positions found — add positions in your Alpaca paper account to see performance.")

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


def calc_stats(series: pd.Series | None) -> dict:
    if series is None or len(series) < 2:
        return {"Total Return": "—", "Max Drawdown": "—", "Volatility (ann.)": "—"}
    series = series.dropna()
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


stats = {
    "My Positions": calc_stats(port_series_for_stats),
    "SPY": calc_stats(spy.reset_index(drop=True) if not spy.empty else None),
    "VTI": calc_stats(vti.reset_index(drop=True) if not vti.empty else None),
}

st.subheader("Summary")
st.dataframe(pd.DataFrame(stats), use_container_width=True)
