import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import yfinance as yf
import requests
from datetime import datetime, timezone
from config import get_secret

st.set_page_config(page_title="Performance", page_icon="📊", layout="wide")
st.title("📊 Performance")
st.caption("Your actual portfolio equity vs S&P 500 (SPY) and Total Market (VTI)")

PERIOD_MAP = {
    "1 Day":   ("1D", "15Min"),
    "1 Week":  ("1W", "1D"),
    "1 Month": ("1M", "1D"),
    "3 Months":("3M", "1D"),
    "6 Months":("6M", "1D"),
    "1 Year":  ("1A", "1D"),
}

YF_PERIOD_MAP   = {"1D": "1d",  "1W": "5d",  "1M": "1mo", "3M": "3mo", "6M": "6mo", "1A": "1y"}
YF_INTERVAL_MAP = {"1D": "15m", "1W": "1h",  "1M": "1d",  "3M": "1d",  "6M": "1d",  "1A": "1d"}

period_label = st.selectbox("Time Period", list(PERIOD_MAP.keys()), index=2)
alpaca_period, alpaca_timeframe = PERIOD_MAP[period_label]
yf_period   = YF_PERIOD_MAP[alpaca_period]
yf_interval = YF_INTERVAL_MAP[alpaca_period]

BASE = "https://paper-api.alpaca.markets/v2"


def _headers() -> dict:
    return {
        "APCA-API-KEY-ID":     get_secret("ALPACA_API_KEY"),
        "APCA-API-SECRET-KEY": get_secret("ALPACA_SECRET_KEY"),
    }


def load_portfolio_history(period: str, timeframe: str) -> pd.Series | None:
    try:
        r = requests.get(
            f"{BASE}/account/portfolio/history",
            headers=_headers(),
            params={"period": period, "timeframe": timeframe},
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        timestamps = data.get("timestamp", [])
        equity     = data.get("equity", [])
        if not timestamps or not equity:
            return None
        series = pd.Series(equity, index=pd.to_datetime(timestamps, unit="s", utc=True))
        series = series[series > 0].dropna()
        return series if len(series) >= 2 else None
    except Exception as e:
        st.warning(f"Could not load portfolio history: {e}")
        return None


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


with st.spinner("Loading portfolio history..."):
    port_series = load_portfolio_history(alpaca_period, alpaca_timeframe)

spy, vti = load_benchmarks(yf_period, yf_interval)

fig = go.Figure()

port_series_for_stats = None
if port_series is not None and len(port_series) >= 2:
    port_norm = port_series / port_series.iloc[0] * 100
    port_series_for_stats = port_series
    fig.add_trace(go.Scatter(
        x=port_norm.index, y=port_norm,
        name="My Portfolio",
        line=dict(color="#00D4AA", width=2),
    ))
else:
    st.info("No trading activity yet — equity curve will appear once positions have been opened and closed or marked to market.")

# Align benchmarks to portfolio start date (strip tz for comparison with yfinance naive index)
bench_start = port_series.index[0].tz_localize(None) if port_series is not None else None

if not spy.empty:
    spy_idx = spy.index.tz_localize(None) if spy.index.tz else spy.index
    spy_plot = spy[spy_idx >= bench_start] if bench_start else spy
    if not spy_plot.empty:
        spy_norm = spy_plot / spy_plot.iloc[0] * 100
        fig.add_trace(go.Scatter(x=spy_norm.index, y=spy_norm, name="SPY (S&P 500)",
                                 line=dict(color="#4A90D9", width=2, dash="dash")))

if not vti.empty:
    vti_idx = vti.index.tz_localize(None) if vti.index.tz else vti.index
    vti_plot = vti[vti_idx >= bench_start] if bench_start else vti
    if not vti_plot.empty:
        vti_norm = vti_plot / vti_plot.iloc[0] * 100
        fig.add_trace(go.Scatter(x=vti_norm.index, y=vti_norm, name="VTI (Total Market)",
                                 line=dict(color="#F5A623", width=2, dash="dot")))

fig.update_layout(
    yaxis_title="Growth (base = 100)",
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
    "My Portfolio": calc_stats(port_series_for_stats),
    "SPY":          calc_stats(spy.reset_index(drop=True) if not spy.empty else None),
    "VTI":          calc_stats(vti.reset_index(drop=True) if not vti.empty else None),
}
st.dataframe(pd.DataFrame(stats), use_container_width=True)
