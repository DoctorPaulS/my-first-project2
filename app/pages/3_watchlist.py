import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo
from supabase import create_client
from config import get_secret, MAX_WATCHLIST_SIZE, SIGNAL_EMOJI, SP500_WIKIPEDIA_URL, SP400_WIKIPEDIA_URL
from scanner.data_fetcher import fetch_ohlcv
from scanner.exit_targets import calc_exit_targets
from scanner.ai_summary import generate_ai_summary, fetch_headlines
from scorer import compute_score, format_signal

st.set_page_config(page_title="Watchlist", page_icon="👀", layout="wide")
st.title("👀 Watchlist")

_url = get_secret("SUPABASE_URL")
_key = get_secret("SUPABASE_KEY")
db = create_client(_url, _key)


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


_company_names = _load_company_names()


def _is_market_hours() -> bool:
    now_et = datetime.now(timezone.utc).astimezone(ZoneInfo("America/New_York"))
    return now_et.weekday() < 5 and time(9, 30) <= now_et.time() <= time(16, 0)


def load_watchlist():
    result = db.table("watchlist").select("*").order("added_at", desc=True).execute()
    return result.data


@st.cache_data(ttl=60)
def score_watchlist(tickers: tuple) -> dict:
    scores = {}
    for ticker in tickers:
        try:
            ohlcv = fetch_ohlcv(ticker, period="1y")
            result = compute_score(ohlcv)
            result["display_signal"] = format_signal(result["signal"], False, False)
            scores[ticker] = result
        except Exception as e:
            scores[ticker] = {"score": 0, "signal": "—", "display_signal": "—", "reasoning": str(e), "indicator_detail": {}}
    return scores


# Auto-refresh during market hours
in_market_hours = _is_market_hours()
if in_market_hours:
    st.caption("🟢 Market open — refreshing every 60 seconds")
    st.markdown('<meta http-equiv="refresh" content="60">', unsafe_allow_html=True)
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

alerts_result = (
    db.table("alerts")
    .select("ticker")
    .in_("ticker", tickers)
    .eq("read", False)
    .execute()
)
alert_tickers = {a["ticker"] for a in alerts_result.data}

with st.spinner("Scoring watchlist stocks..."):
    scores = score_watchlist(tuple(tickers))

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
    })

df = pd.DataFrame(rows)
event = st.dataframe(
    df,
    use_container_width=True,
    hide_index=True,
    on_select="rerun",
    selection_mode="single-row",
    column_config={"Score": st.column_config.NumberColumn("Score", format="%.1f")},
)

# --- Drill-down ---
if event.selection.rows:
    idx = event.selection.rows[0]
    ticker_raw = watchlist[idx]["ticker"]
    s = scores.get(ticker_raw, {})
    company_name = _company_names.get(ticker_raw, ticker_raw)

    st.divider()
    col_title, col_remove = st.columns([4, 1])
    with col_title:
        st.subheader(f"{company_name} ({ticker_raw})")
    with col_remove:
        if st.button("🗑️ Remove from Watchlist"):
            db.table("watchlist").delete().eq("ticker", ticker_raw).execute()
            st.success(f"{ticker_raw} removed.")
            st.rerun()

    c1, c2 = st.columns(2)
    c1.metric("Score", f"{s.get('score', 0):.1f} / 100")
    c2.metric("Signal", s.get("display_signal", "—"))

    # Mark alerts as read
    if ticker_raw in alert_tickers:
        db.table("alerts").update({"read": True}).eq("ticker", ticker_raw).execute()

    # --- Bullish / Bearish bullets ---
    detail = s.get("indicator_detail") or {}
    if detail:
        bullish = [(n, v) for n, v in detail.items() if v.get("score", 0) >= 6]
        bearish = [(n, v) for n, v in detail.items() if v.get("score", 0) < 4]
        mixed   = [(n, v) for n, v in detail.items() if 4 <= v.get("score", 0) < 6]

        col_bull, col_bear, col_mix = st.columns(3)
        with col_bull:
            st.markdown("**🟢 Why Buy**")
            for name, v in bullish:
                st.markdown(f"- **{name}** ({v['score']:.1f}/10): {v['reasoning']}")
            if not bullish:
                st.caption("No strongly bullish indicators")
        with col_bear:
            st.markdown("**🔴 Why Reduce / Risk**")
            for name, v in bearish:
                st.markdown(f"- **{name}** ({v['score']:.1f}/10): {v['reasoning']}")
            if not bearish:
                st.caption("No strongly bearish indicators")
        with col_mix:
            st.markdown("**🟡 Mixed / Watch**")
            for name, v in mixed:
                st.markdown(f"- **{name}** ({v['score']:.1f}/10): {v['reasoning']}")
            if not mixed:
                st.caption("No mixed indicators")

    # --- Price chart + exit targets ---
    st.markdown("**Price Chart (6 months):**")
    try:
        ohlcv_chart = fetch_ohlcv(ticker_raw, period="6mo")
        ohlcv_full  = fetch_ohlcv(ticker_raw, period="1y")

        fig = go.Figure(data=[go.Candlestick(
            x=ohlcv_chart.index,
            open=ohlcv_chart["Open"], high=ohlcv_chart["High"],
            low=ohlcv_chart["Low"],  close=ohlcv_chart["Close"],
            name=ticker_raw,
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
        ec1.metric("Stop Loss",       f"${targets['stop']:.2f}",    f"-{targets['risk_pct']:.1f}%", delta_color="inverse")
        ec2.metric("Target 1 (2:1)",  f"${targets['target1']:.2f}")
        ec3.metric("Target 2 (3:1)",  f"${targets['target2']:.2f}")
        ec4.metric("Resistance",      f"${targets['resistance']:.2f}")

        # --- Save / manage targets ---
        st.markdown("**Monitor These Targets:**")
        existing = db.table("price_targets").select("*").eq("ticker", ticker_raw).execute()
        saved = existing.data[0] if existing.data else None

        with st.form(key=f"targets_{ticker_raw}"):
            fc1, fc2, fc3 = st.columns(3)
            s_stop = fc1.number_input("Stop Loss ($)", value=round(saved["stop_loss"] if saved else targets["stop"], 2), step=0.01, format="%.2f")
            s_t1   = fc2.number_input("Target 1 ($)",  value=round(saved["target1"]   if saved else targets["target1"], 2), step=0.01, format="%.2f")
            s_t2   = fc3.number_input("Target 2 ($)",  value=round(saved["target2"]   if saved else targets["target2"], 2), step=0.01, format="%.2f")
            btn_col, _ = st.columns([1, 3])
            save_btn   = btn_col.form_submit_button("💾 Save Targets", use_container_width=True)
            remove_btn = btn_col.form_submit_button("🗑️ Remove", use_container_width=True) if saved else False

        if save_btn:
            db.table("price_targets").upsert({
                "ticker": ticker_raw, "stop_loss": s_stop,
                "target1": s_t1, "target2": s_t2,
                "stop_triggered": False, "target1_triggered": False, "target2_triggered": False,
            }, on_conflict="ticker").execute()
            st.success(f"Targets saved for {ticker_raw}.")
            st.rerun()

        if remove_btn:
            db.table("price_targets").delete().eq("ticker", ticker_raw).execute()
            st.success(f"Targets removed for {ticker_raw}.")
            st.rerun()

        if saved:
            flags = [l for l, t in [("🔴 Stop triggered", saved["stop_triggered"]),
                                     ("🟢 Target 1 triggered", saved["target1_triggered"]),
                                     ("🟢 Target 2 triggered", saved["target2_triggered"])] if t]
            if flags:
                st.warning("  |  ".join(flags))
            else:
                st.caption("✅ Monitoring active — alerts fire at next scan when levels are crossed.")

    except Exception as e:
        st.warning(f"Could not load chart: {e}")

    # --- AI Summary ---
    st.markdown("**AI Analyst Summary:**")
    with st.spinner("Generating summary..."):
        headlines = fetch_headlines(ticker_raw)
        summary = generate_ai_summary(
            ticker=ticker_raw,
            company_name=company_name,
            signal=s.get("signal", "—"),
            score=s.get("score", 0),
            indicator_detail=detail,
            headlines=headlines,
        )
    st.info(summary)
    if headlines:
        with st.expander("News headlines used"):
            for h in headlines:
                st.markdown(f"- {h}")
