import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from supabase import create_client
from config import get_secret, utc_to_et, MAX_WATCHLIST_SIZE, SP500_WIKIPEDIA_URL, SP400_WIKIPEDIA_URL
from scanner.data_fetcher import fetch_ohlcv
from scanner.exit_targets import calc_exit_targets
from scanner.ai_summary import generate_ai_summary, fetch_headlines

st.set_page_config(page_title="Momentum", page_icon="🚀", layout="wide")
st.title("🚀 Momentum Breakouts")
st.caption("Stocks showing unusual volume + price momentum — updated every Monday pre-market")

_url = get_secret("SUPABASE_URL")
_key = get_secret("SUPABASE_KEY")


@st.cache_data(ttl=86400)
def _load_company_names() -> dict:
    headers = {"User-Agent": "Mozilla/5.0 (compatible; stock-advisor-bot/1.0)"}
    names = {}
    for url, col in [(SP500_WIKIPEDIA_URL, "Security"), (SP400_WIKIPEDIA_URL, "Company")]:
        try:
            df = pd.read_html(url, storage_options=headers)[0]
            names.update(dict(zip(df["Symbol"].str.replace(".", "-", regex=False), df[col])))
        except Exception:
            pass
    return names


@st.cache_data(ttl=3600)
def load_momentum(url: str, key: str) -> pd.DataFrame:
    db = create_client(url, key)
    latest = (
        db.table("momentum_results")
        .select("scanned_at")
        .order("scanned_at", desc=True)
        .limit(1)
        .execute()
    )
    if not latest.data:
        return pd.DataFrame()
    scan_time = latest.data[0]["scanned_at"]
    results = (
        db.table("momentum_results")
        .select("*")
        .eq("scanned_at", scan_time)
        .order("momentum_score", desc=True)
        .execute()
    )
    return pd.DataFrame(results.data)


_company_names = _load_company_names()

try:
    df = load_momentum(_url, _key)
except Exception as e:
    st.error(f"Database error: {e}")
    st.stop()

if df.empty:
    st.info("No momentum results yet. The scan runs every Monday at 6am ET — you can also trigger it manually from GitHub Actions.")
    st.stop()

scan_time = utc_to_et(df["scanned_at"].iloc[0])
st.caption(f"Last scan: {scan_time}  —  {len(df)} candidates found")

# --- Sidebar filters ---
with st.sidebar:
    st.header("Filters")
    min_vol_surge = st.slider("Min Volume Surge (x avg)", 1.0, 5.0, 1.5, step=0.25)
    min_price_5d  = st.slider("Min 5-day Price Change (%)", 0.0, 20.0, 0.0, step=0.5)
    min_score     = st.slider("Min Momentum Score", 0, 100, 30)

filtered = df[
    (df["volume_surge"]    >= min_vol_surge) &
    (df["price_change_5d"] >= min_price_5d)  &
    (df["momentum_score"]  >= min_score)
].copy()

# --- Summary metrics ---
c1, c2, c3, c4 = st.columns(4)
c1.metric("Candidates",         len(filtered))
c2.metric("Avg Volume Surge",   f"{filtered['volume_surge'].mean():.1f}x"    if not filtered.empty else "—")
c3.metric("Avg 5d Return",      f"{filtered['price_change_5d'].mean():+.1f}%" if not filtered.empty else "—")
c4.metric("Near 52w High",      len(filtered[filtered["pct_from_high"] >= -3]) if not filtered.empty else 0)

st.divider()

# --- Results table ---
display_df = filtered[["ticker", "momentum_score", "volume_surge", "price_change_5d", "price_change_20d", "pct_from_high", "summary"]].copy()
display_df.columns = ["Ticker", "Score", "Vol Surge", "5d Change", "20d Change", "% from High", "Summary"]
display_df["Vol Surge"]   = display_df["Vol Surge"].apply(lambda x: f"{x:.1f}x")
display_df["5d Change"]   = display_df["5d Change"].apply(lambda x: f"{x:+.1f}%")
display_df["20d Change"]  = display_df["20d Change"].apply(lambda x: f"{x:+.1f}%")
display_df["% from High"] = display_df["% from High"].apply(lambda x: f"{x:+.1f}%")

st.subheader(f"{len(filtered)} momentum candidates")
event = st.dataframe(
    display_df,
    use_container_width=True,
    hide_index=True,
    on_select="rerun",
    selection_mode="single-row",
    column_config={"Score": st.column_config.NumberColumn("Score", format="%.1f")},
)

# --- Drill-down ---
if event.selection.rows:
    idx = event.selection.rows[0]
    row = filtered.iloc[idx]
    ticker = row["ticker"]
    company_name = _company_names.get(ticker, ticker)

    st.divider()
    col_title, col_btn = st.columns([4, 1])
    with col_title:
        st.subheader(f"{company_name} ({ticker})")
        st.caption(row["summary"])
    with col_btn:
        db = create_client(_url, _key)
        wl = db.table("watchlist").select("ticker").eq("ticker", ticker).execute()
        if not wl.data:
            if st.button("➕ Add to Watchlist"):
                count = db.table("watchlist").select("id", count="exact").execute()
                if count.count >= MAX_WATCHLIST_SIZE:
                    st.error(f"Watchlist full ({MAX_WATCHLIST_SIZE} max).")
                else:
                    db.table("watchlist").insert({"ticker": ticker}).execute()
                    st.success(f"{ticker} added!")
                    st.rerun()
        else:
            st.success("✅ On watchlist")

    # Momentum metrics
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Momentum Score",  f"{row['momentum_score']:.1f} / 100")
    m2.metric("Volume Surge",    f"{row['volume_surge']:.1f}x avg")
    m3.metric("5-day Change",    f"{row['price_change_5d']:+.1f}%")
    m4.metric("From 52w High",   f"{row['pct_from_high']:+.1f}%")

    # Chart + exit targets
    st.markdown("**Price Chart (6 months):**")
    try:
        ohlcv_chart = fetch_ohlcv(ticker, period="6mo")
        ohlcv_full  = fetch_ohlcv(ticker, period="1y")

        fig = go.Figure(data=[go.Candlestick(
            x=ohlcv_chart.index,
            open=ohlcv_chart["Open"], high=ohlcv_chart["High"],
            low=ohlcv_chart["Low"],  close=ohlcv_chart["Close"],
            name=ticker,
        )])

        targets = calc_exit_targets(ohlcv_full)
        for label, price, color, dash in [
            ("Stop Loss",      targets["stop"],       "red",    "dash"),
            ("Target 1 (2:1)", targets["target1"],    "lime",   "dot"),
            ("Target 2 (3:1)", targets["target2"],    "cyan",   "dot"),
            ("Resistance",     targets["resistance"], "orange", "dashdot"),
        ]:
            fig.add_hline(y=price, line_color=color, line_dash=dash,
                          annotation_text=f"{label} ${price:.2f}",
                          annotation_position="right")

        fig.update_layout(xaxis_rangeslider_visible=False, height=450, margin=dict(l=0, r=0, t=30, b=0))
        st.plotly_chart(fig, use_container_width=True)

        ec1, ec2, ec3, ec4 = st.columns(4)
        ec1.metric("Stop Loss",      f"${targets['stop']:.2f}",    f"-{targets['risk_pct']:.1f}%", delta_color="inverse")
        ec2.metric("Target 1 (2:1)", f"${targets['target1']:.2f}")
        ec3.metric("Target 2 (3:1)", f"${targets['target2']:.2f}")
        ec4.metric("Resistance",     f"${targets['resistance']:.2f}")

        # Save targets form
        st.markdown("**Monitor These Targets:**")
        existing = db.table("price_targets").select("*").eq("ticker", ticker).execute()
        saved = existing.data[0] if existing.data else None

        with st.form(key=f"targets_{ticker}"):
            fc1, fc2, fc3 = st.columns(3)
            s_stop = fc1.number_input("Stop Loss ($)", value=round(saved["stop_loss"] if saved else targets["stop"], 2), step=0.01, format="%.2f")
            s_t1   = fc2.number_input("Target 1 ($)",  value=round(saved["target1"]   if saved else targets["target1"], 2), step=0.01, format="%.2f")
            s_t2   = fc3.number_input("Target 2 ($)",  value=round(saved["target2"]   if saved else targets["target2"], 2), step=0.01, format="%.2f")
            btn_col, _ = st.columns([1, 3])
            save_btn   = btn_col.form_submit_button("💾 Save Targets", use_container_width=True)
            remove_btn = btn_col.form_submit_button("🗑️ Remove", use_container_width=True) if saved else False

        if save_btn:
            db.table("price_targets").upsert({
                "ticker": ticker, "stop_loss": s_stop,
                "target1": s_t1, "target2": s_t2,
                "stop_triggered": False, "target1_triggered": False, "target2_triggered": False,
            }, on_conflict="ticker").execute()
            st.success(f"Targets saved for {ticker}.")
            st.rerun()

        if remove_btn:
            db.table("price_targets").delete().eq("ticker", ticker).execute()
            st.success(f"Targets removed for {ticker}.")
            st.rerun()

    except Exception as e:
        st.warning(f"Could not load chart: {e}")

    # AI summary
    st.markdown("**AI Analyst Summary:**")
    with st.spinner("Generating summary..."):
        headlines = fetch_headlines(ticker)
        summary = generate_ai_summary(
            ticker=ticker,
            company_name=company_name,
            signal="MOMENTUM BREAKOUT",
            score=row["momentum_score"],
            indicator_detail={
                "Volume Surge":    {"score": min(row["volume_surge"] * 2, 10), "group": "volume",   "reasoning": f"{row['volume_surge']:.1f}x average volume"},
                "5-day Momentum":  {"score": min(row["price_change_5d"] / 2, 10), "group": "momentum", "reasoning": f"{row['price_change_5d']:+.1f}% in 5 days"},
                "52-week High":    {"score": max(10 + row["pct_from_high"] / 5, 0), "group": "trend",    "reasoning": f"{row['pct_from_high']:+.1f}% from 52-week high"},
            },
            headlines=headlines,
        )
    st.info(summary)
    if headlines:
        with st.expander("News headlines used"):
            for h in headlines:
                st.markdown(f"- {h}")
