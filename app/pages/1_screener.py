import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from supabase import create_client
from config import get_secret, MAX_WATCHLIST_SIZE, SP500_WIKIPEDIA_URL
from scorer import format_signal
from scanner.data_fetcher import fetch_ohlcv
from scanner.exit_targets import calc_exit_targets
from scanner.ai_summary import generate_ai_summary, fetch_headlines

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
        "Ticker": st.column_config.TextColumn("Ticker", width="small"),
        "Score": st.column_config.NumberColumn("Score", format="%.1f", width="small"),
        "Signal": st.column_config.TextColumn("Signal", width="medium"),
        "Reason": st.column_config.TextColumn("Reason"),
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

    # --- Bullish / Bearish bullets ---
    detail = row["indicator_detail"] if isinstance(row["indicator_detail"], dict) else {}
    if detail:
        bullish = [(n, v) for n, v in detail.items() if v.get("score", 0) >= 6]
        bearish = [(n, v) for n, v in detail.items() if v.get("score", 0) < 4]
        mixed   = [(n, v) for n, v in detail.items() if 4 <= v.get("score", 0) < 6]

        col_bull, col_bear, col_mix = st.columns(3)
        with col_bull:
            st.markdown("**🟢 Why Buy**")
            if bullish:
                for name, v in bullish:
                    st.markdown(f"- **{name}** ({v['score']:.1f}/10): {v['reasoning']}")
            else:
                st.caption("No strongly bullish indicators")
        with col_bear:
            st.markdown("**🔴 Why Reduce / Risk**")
            if bearish:
                for name, v in bearish:
                    st.markdown(f"- **{name}** ({v['score']:.1f}/10): {v['reasoning']}")
            else:
                st.caption("No strongly bearish indicators")
        with col_mix:
            st.markdown("**🟡 Mixed / Watch**")
            if mixed:
                for name, v in mixed:
                    st.markdown(f"- **{name}** ({v['score']:.1f}/10): {v['reasoning']}")
            else:
                st.caption("No mixed indicators")

    # --- Price chart + exit targets ---
    st.markdown("**Price Chart (6 months):**")
    try:
        ohlcv_chart = fetch_ohlcv(ticker, period="6mo")
        ohlcv_full  = fetch_ohlcv(ticker, period="1y")

        fig = go.Figure(data=[
            go.Candlestick(
                x=ohlcv_chart.index,
                open=ohlcv_chart["Open"], high=ohlcv_chart["High"],
                low=ohlcv_chart["Low"], close=ohlcv_chart["Close"],
                name=ticker,
            )
        ])

        targets = calc_exit_targets(ohlcv_full)
        for label, price, color, dash in [
            ("Stop Loss", targets["stop"], "red", "dash"),
            ("Target 1 (2:1)", targets["target1"], "lime", "dot"),
            ("Target 2 (3:1)", targets["target2"], "cyan", "dot"),
            ("Resistance", targets["resistance"], "orange", "dashdot"),
        ]:
            fig.add_hline(y=price, line_color=color, line_dash=dash,
                          annotation_text=f"{label} ${price:.2f}",
                          annotation_position="right")

        fig.update_layout(xaxis_rangeslider_visible=False, height=450, margin=dict(l=0, r=0, t=30, b=0))
        st.plotly_chart(fig, use_container_width=True)

        ec1, ec2, ec3, ec4 = st.columns(4)
        ec1.metric("Stop Loss", f"${targets['stop']:.2f}", f"-{targets['risk_pct']:.1f}%", delta_color="inverse")
        ec2.metric("Target 1 (2:1 R/R)", f"${targets['target1']:.2f}")
        ec3.metric("Target 2 (3:1 R/R)", f"${targets['target2']:.2f}")
        ec4.metric("Resistance", f"${targets['resistance']:.2f}")

    except Exception as e:
        st.warning(f"Could not load chart: {e}")

    # --- AI Summary ---
    st.markdown("**AI Analyst Summary:**")
    with st.spinner("Generating summary..."):
        headlines = fetch_headlines(ticker)
        summary = generate_ai_summary(
            ticker=ticker,
            company_name=company_name,
            signal=row["signal"],
            score=row["score"],
            indicator_detail=detail,
            headlines=headlines,
        )
    st.info(summary)
    if headlines:
        with st.expander("News headlines used"):
            for h in headlines:
                st.markdown(f"- {h}")
