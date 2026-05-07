import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from supabase import create_client
from config import get_secret, MAX_WATCHLIST_SIZE, SP500_WIKIPEDIA_URL
from scorer import format_signal
from scanner.data_fetcher import fetch_ohlcv

st.set_page_config(page_title="Screener", page_icon="🔍", layout="wide")
st.title("🔍 Stock Screener")

_url = get_secret("SUPABASE_URL")
_key = get_secret("SUPABASE_KEY")


@st.cache_data(ttl=86400)
def _load_company_names() -> dict:
    try:
        tables = pd.read_html(
            SP500_WIKIPEDIA_URL,
            storage_options={"User-Agent": "Mozilla/5.0 (compatible; stock-advisor-bot/1.0)"},
        )
        df = tables[0]
        return dict(zip(df["Symbol"].str.replace(".", "-", regex=False), df["Security"]))
    except Exception:
        return {}


_company_names = _load_company_names()


@st.cache_data(ttl=300)
def load_latest_scan(url: str, key: str) -> pd.DataFrame:
    db = create_client(url, key)
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


try:
    df = load_latest_scan(_url, _key)
except Exception as e:
    st.error(f"Database error: {e}")
    st.stop()

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
}).copy()
display_df["Reason"] = display_df["Reason"].str[:300] + "..."

st.subheader(f"{len(filtered)} stocks match your filters")
event = st.dataframe(
    display_df,
    use_container_width=True,
    hide_index=True,
    on_select="rerun",
    selection_mode="single-row",
    column_config={
        "Score": st.column_config.NumberColumn("Score", format="%.1f"),
    },
)

# --- Expanded analysis card ---
if event.selection.rows:
    idx = event.selection.rows[0]
    row = filtered.iloc[idx]
    ticker = row["ticker"]

    st.divider()
    company_name = _company_names.get(ticker, ticker)

    col_title, col_btn = st.columns([4, 1])
    with col_title:
        st.subheader(f"{company_name} ({ticker})")
    with col_btn:
        _db = create_client(_url, _key)
        watchlist_result = _db.table("watchlist").select("ticker").eq("ticker", ticker).execute()
        on_watchlist = bool(watchlist_result.data)
        if not on_watchlist:
            if st.button("➕ Add to Watchlist"):
                count = _db.table("watchlist").select("id", count="exact").execute()
                if count.count >= MAX_WATCHLIST_SIZE:
                    st.error(f"Watchlist is full ({MAX_WATCHLIST_SIZE} stocks max).")
                else:
                    _db.table("watchlist").insert({"ticker": ticker}).execute()
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

    if isinstance(row["indicator_detail"], dict) and row["indicator_detail"]:
        st.markdown("**Indicator Breakdown:**")
        detail = row["indicator_detail"]
        detail_df = pd.DataFrame([
            {"Indicator": name, "Score": f"{v['score']:.1f}/10", "Group": v["group"], "Notes": v["reasoning"]}
            for name, v in detail.items()
        ])
        st.dataframe(detail_df, use_container_width=True, hide_index=True)

    st.markdown("**Price Chart (6 months):**")
    try:
        ohlcv = fetch_ohlcv(ticker, period="6mo")
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
