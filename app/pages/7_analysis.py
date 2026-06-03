import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import yfinance as yf
from datetime import datetime, timezone, timedelta
from supabase import create_client
from config import get_secret

st.set_page_config(page_title="Signal Analysis", page_icon="🔬", layout="wide")
st.title("🔬 Signal Analysis")
st.caption("How accurate are our signals? Which indicators actually predict returns?")

_url = get_secret("SUPABASE_URL")
_key = get_secret("SUPABASE_KEY")
db = create_client(_url, _key)

FORWARD_DAYS = st.radio("Forward return window", [14, 30], horizontal=True, index=0)
st.divider()


@st.cache_data(ttl=3600)
def load_scan_history(forward_days: int) -> pd.DataFrame:
    """
    Pull scan results old enough to have forward return data.
    Takes up to the 20 most recent eligible scan batches.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=forward_days + 1)).isoformat()

    # Get distinct scan times older than cutoff
    times_result = (
        db.table("scan_results")
        .select("scanned_at")
        .lt("scanned_at", cutoff)
        .order("scanned_at", desc=True)
        .limit(20 * 505)   # fetch enough rows to find 20 distinct times
        .execute()
    )
    if not times_result.data:
        return pd.DataFrame()

    times_df = pd.DataFrame(times_result.data)
    distinct_times = times_df["scanned_at"].unique()[:20]

    # Pull all scan results for those batches
    results = (
        db.table("scan_results")
        .select("ticker, scanned_at, score, signal, indicator_detail")
        .in_("scanned_at", list(distinct_times))
        .execute()
    )
    if not results.data:
        return pd.DataFrame()

    df = pd.DataFrame(results.data)
    df["scan_date"] = pd.to_datetime(df["scanned_at"]).dt.date
    return df


@st.cache_data(ttl=3600)
def fetch_forward_returns(tickers: tuple, min_date: str, forward_days: int) -> pd.DataFrame:
    """Download price history for all tickers and return a date-indexed price table."""
    end_date = datetime.now(timezone.utc).date() + timedelta(days=5)
    raw = yf.download(
        list(tickers),
        start=min_date,
        end=str(end_date),
        auto_adjust=True,
        progress=False,
        threads=True,
    )
    if raw.empty:
        return pd.DataFrame()
    if isinstance(raw.columns, pd.MultiIndex):
        prices = raw["Close"]
    else:
        prices = raw[["Close"]]
        prices.columns = [tickers[0]]
    return prices


with st.spinner("Loading scan history..."):
    df = load_scan_history(FORWARD_DAYS)

if df.empty:
    st.warning(
        f"Not enough historical data yet — need scan results that are at least {FORWARD_DAYS} days old. "
        "Check back once more time has passed."
    )
    st.stop()

unique_tickers = tuple(df["ticker"].unique())
min_date = str(df["scan_date"].min() - timedelta(days=2))

with st.spinner("Fetching forward prices..."):
    prices = fetch_forward_returns(unique_tickers, min_date, FORWARD_DAYS)

if prices.empty:
    st.error("Could not load price data.")
    st.stop()

# Calculate forward return for each scan result
records = []
for _, row in df.iterrows():
    ticker = row["ticker"]
    scan_date = pd.Timestamp(row["scan_date"])
    fwd_date = scan_date + pd.Timedelta(days=FORWARD_DAYS)

    if ticker not in prices.columns:
        continue

    series = prices[ticker].dropna()
    dates = series.index

    # Find nearest available trading days
    scan_idx = dates.searchsorted(scan_date)
    fwd_idx  = dates.searchsorted(fwd_date)

    if scan_idx >= len(dates) or fwd_idx >= len(dates):
        continue

    p0 = series.iloc[scan_idx]
    p1 = series.iloc[fwd_idx]
    if p0 == 0:
        continue

    fwd_return = (p1 - p0) / p0

    records.append({
        "ticker":      ticker,
        "scan_date":   scan_date,
        "score":       row["score"],
        "signal":      row["signal"],
        "fwd_return":  fwd_return,
        "indicator_detail": row["indicator_detail"],
    })

if not records:
    st.warning("No completed forward return windows yet.")
    st.stop()

results_df = pd.DataFrame(records)

# --- Signal accuracy ---
SIGNAL_ORDER = ["BUY", "WATCH CAREFULLY", "HOLD", "REDUCE", "EXIT"]
BULLISH = {"BUY", "WATCH CAREFULLY"}
BEARISH = {"REDUCE", "EXIT"}

def is_win(row):
    if row["signal"] in BULLISH:
        return row["fwd_return"] > 0
    elif row["signal"] in BEARISH:
        return row["fwd_return"] < 0
    return None   # HOLD is neutral

results_df["win"] = results_df.apply(is_win, axis=1)

st.subheader("Signal Accuracy")
st.caption(f"Win = bullish signals with positive {FORWARD_DAYS}d return, or bearish signals with negative {FORWARD_DAYS}d return")

acc_rows = []
for sig in SIGNAL_ORDER:
    sub = results_df[results_df["signal"] == sig]
    if sub.empty:
        continue
    wins = sub["win"].dropna()
    acc_rows.append({
        "Signal":   sig,
        "Calls":    len(sub),
        "Win Rate": wins.mean() if len(wins) else None,
        "Avg Return": sub["fwd_return"].mean(),
        "Med Return": sub["fwd_return"].median(),
    })

acc_df = pd.DataFrame(acc_rows)

if not acc_df.empty:
    fig_acc = go.Figure()
    colors = {"BUY": "#00C48C", "WATCH CAREFULLY": "#4A90D9", "HOLD": "#F5A623",
              "REDUCE": "#E55A4E", "EXIT": "#C0392B"}
    for _, r in acc_df.iterrows():
        if r["Win Rate"] is not None:
            fig_acc.add_bar(
                x=[r["Signal"]], y=[r["Win Rate"] * 100],
                name=r["Signal"],
                marker_color=colors.get(r["Signal"], "gray"),
                text=[f"{r['Win Rate']*100:.0f}%"],
                textposition="outside",
            )
    fig_acc.add_hline(y=50, line_dash="dash", line_color="white", opacity=0.4,
                      annotation_text="50% baseline")
    fig_acc.update_layout(
        yaxis_title="Win Rate (%)", yaxis_range=[0, 105],
        showlegend=False, height=350, margin=dict(l=0, r=0, t=20, b=0),
    )
    st.plotly_chart(fig_acc, use_container_width=True)

    disp = acc_df.copy()
    disp["Win Rate"]   = disp["Win Rate"].apply(lambda x: f"{x*100:.1f}%" if x is not None else "—")
    disp["Avg Return"] = disp["Avg Return"].apply(lambda x: f"{x*100:+.1f}%")
    disp["Med Return"] = disp["Med Return"].apply(lambda x: f"{x*100:+.1f}%")
    st.dataframe(disp, use_container_width=True, hide_index=True)

st.divider()

# --- Score vs return scatter ---
st.subheader("Score vs Forward Return")
st.caption("Does a higher score predict a better return?")

COLOR_MAP = {"BUY": "#00C48C", "WATCH CAREFULLY": "#4A90D9", "HOLD": "#F5A623",
             "REDUCE": "#E55A4E", "EXIT": "#C0392B"}

fig_scatter = go.Figure()
for sig, grp in results_df.groupby("signal"):
    fig_scatter.add_trace(go.Scatter(
        x=grp["score"],
        y=grp["fwd_return"] * 100,
        mode="markers",
        name=sig,
        marker=dict(color=COLOR_MAP.get(sig, "gray"), opacity=0.5, size=6),
    ))

# Overall trendline via numpy polyfit
x = results_df["score"].values
y = results_df["fwd_return"].values * 100
if len(x) >= 2:
    m, b = np.polyfit(x, y, 1)
    x_line = np.array([x.min(), x.max()])
    fig_scatter.add_trace(go.Scatter(
        x=x_line, y=m * x_line + b,
        mode="lines", name="Trend",
        line=dict(color="white", dash="dash", width=1),
    ))

fig_scatter.add_hline(y=0, line_dash="dot", line_color="white", opacity=0.3)
fig_scatter.update_layout(
    xaxis_title="Score", yaxis_title=f"{FORWARD_DAYS}d Return (%)",
    height=400, margin=dict(l=0, r=0, t=20, b=0),
)
st.plotly_chart(fig_scatter, use_container_width=True)

st.divider()

# --- Indicator alpha ---
st.subheader("Indicator Alpha")
st.caption("Correlation between each indicator's score and forward return. Higher = more predictive.")

indicator_rows = []
for _, row in results_df.iterrows():
    detail = row["indicator_detail"]
    if not isinstance(detail, dict):
        continue
    for ind_name, v in detail.items():
        if isinstance(v, dict) and "score" in v:
            indicator_rows.append({
                "indicator": ind_name,
                "ind_score": v["score"],
                "fwd_return": row["fwd_return"],
                "group": v.get("group", ""),
            })

if indicator_rows:
    ind_df = pd.DataFrame(indicator_rows)
    corr = (
        ind_df.groupby("indicator")
        .apply(lambda g: g["ind_score"].corr(g["fwd_return"]), include_groups=False)
        .reset_index()
    )
    corr.columns = ["Indicator", "Correlation"]
    corr["Abs"] = corr["Correlation"].abs()
    corr = corr.sort_values("Abs", ascending=False)
    corr["Direction"] = corr["Correlation"].apply(lambda x: "✅ Predictive" if x > 0.05 else ("⚠️ Weak" if x > -0.05 else "❌ Inverse"))
    corr["Correlation"] = corr["Correlation"].apply(lambda x: f"{x:+.3f}")
    corr["Abs"] = corr["Abs"].apply(lambda x: f"{x:.3f}")

    st.dataframe(corr, use_container_width=True, hide_index=True)
else:
    st.info("Not enough indicator data yet.")

st.divider()

# --- Best and worst calls ---
st.subheader("Best & Worst Calls")
col_best, col_worst = st.columns(2)

buy_signals = results_df[results_df["signal"].isin(BULLISH)].copy()
buy_signals["Return"] = buy_signals["fwd_return"].apply(lambda x: f"{x*100:+.1f}%")

with col_best:
    st.markdown("**🏆 Top 10 BUY/WATCH calls**")
    best = buy_signals.nlargest(10, "fwd_return")[["ticker", "scan_date", "score", "signal", "Return"]]
    best.columns = ["Ticker", "Date", "Score", "Signal", "Return"]
    st.dataframe(best, use_container_width=True, hide_index=True)

with col_worst:
    st.markdown("**💀 Bottom 10 BUY/WATCH calls**")
    worst = buy_signals.nsmallest(10, "fwd_return")[["ticker", "scan_date", "score", "signal", "Return"]]
    worst.columns = ["Ticker", "Date", "Score", "Signal", "Return"]
    st.dataframe(worst, use_container_width=True, hide_index=True)
