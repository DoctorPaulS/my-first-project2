import streamlit as st
import pandas as pd
from supabase import create_client
from config import get_secret, SIGNAL_EMOJI
from alpaca_client import get_positions, get_account

_url = get_secret("SUPABASE_URL")
_key = get_secret("SUPABASE_KEY")

st.set_page_config(page_title="Portfolio", page_icon="💼", layout="wide")
st.title("💼 Portfolio")
st.caption("Live Alpaca positions — read-only. Execute trades at alpaca.markets.")


def load_portfolio():
    try:
        positions = get_positions()
        account = get_account()
        return positions, account, None
    except Exception as e:
        return [], {}, str(e)


positions, account, error = load_portfolio()

if error:
    st.error(f"Could not connect to Alpaca: {error}")
    st.info("Make sure ALPACA_API_KEY and ALPACA_SECRET_KEY are set in your Streamlit secrets.")
    st.stop()

# --- Account summary ---
col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Portfolio Value", f"${account.get('portfolio_value', 0):,.2f}")
with col2:
    st.metric("Buying Power", f"${account.get('buying_power', 0):,.2f}")
with col3:
    st.metric("Cash", f"${account.get('cash', 0):,.2f}")

st.divider()

if not positions:
    st.info("No open positions found in your Alpaca account.")
    st.stop()

# --- Attach latest signals from Supabase ---
tickers = [p["symbol"] for p in positions]
_db = create_client(_url, _key)
signals_result = (
    _db.table("scan_results")
    .select("ticker, score, signal, reasoning, earnings_warning")
    .in_("ticker", tickers)
    .order("scanned_at", desc=True)
    .limit(len(tickers) * 5)
    .execute()
)
signal_map = {}
for row in signals_result.data:
    if row["ticker"] not in signal_map:
        signal_map[row["ticker"]] = row

rows = []
for p in positions:
    sig_data = signal_map.get(p["symbol"], {})
    signal = sig_data.get("signal", "—")
    emoji = SIGNAL_EMOJI.get(signal, "")
    pl_pct = p["unrealized_plpc"] * 100
    rows.append({
        "Ticker": p["symbol"],
        "Shares": p["qty"],
        "Price": f"${p['current_price']:,.2f}",
        "Market Value": f"${p['market_value']:,.2f}",
        "Gain/Loss": f"${p['unrealized_pl']:+,.2f} ({pl_pct:+.1f}%)",
        "Signal": f"{emoji} {signal}",
        "Score": sig_data.get("score", "—"),
    })

st.subheader(f"{len(rows)} open positions")
df = pd.DataFrame(rows)
event = st.dataframe(df, use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row")

if event.selection.rows:
    idx = event.selection.rows[0]
    ticker = rows[idx]["Ticker"]
    sig_data = signal_map.get(ticker, {})
    st.divider()
    st.subheader(f"Signal detail: {ticker}")
    if sig_data:
        st.write(sig_data.get("reasoning", "No reasoning available."))
        if sig_data.get("earnings_warning"):
            st.warning("⚠️ Earnings within 7 days")
    else:
        st.info("No scan data available for this ticker yet.")

    st.markdown(f"[Trade on Alpaca →](https://app.alpaca.markets/trade/{ticker})")
