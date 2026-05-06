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
