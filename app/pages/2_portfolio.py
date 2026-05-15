import streamlit as st
import pandas as pd
import yfinance as yf
from supabase import create_client
from config import get_secret, SIGNAL_EMOJI
from alpaca_client import get_positions, get_account

SECTOR_WARN_PCT = 40  # warn if any sector exceeds this % of invested capital


@st.cache_data(ttl=86400)
def get_sectors(tickers: tuple) -> dict[str, str]:
    """Return {ticker: sector} via yfinance. Cached for 24h."""
    result = {}
    for t in tickers:
        try:
            info = yf.Ticker(t).info
            result[t] = info.get("sector") or "Unknown"
        except Exception:
            result[t] = "Unknown"
    return result

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
        "Ticker":       p["symbol"],
        "Shares":       float(p["qty"]),
        "Price":        float(p["current_price"]),
        "Market Value": float(p["market_value"]),
        "P&L $":        float(p["unrealized_pl"]),
        "P&L %":        pl_pct,
        "Signal":       f"{emoji} {signal}",
        "Score":        float(sig_data["score"]) if sig_data.get("score") not in (None, "—") else None,
    })

st.subheader(f"{len(rows)} open positions")
df = pd.DataFrame(rows)
event = st.dataframe(
    df,
    use_container_width=True,
    hide_index=True,
    on_select="rerun",
    selection_mode="single-row",
    column_config={
        "Shares":       st.column_config.NumberColumn("Shares", format="%.6f"),
        "Price":        st.column_config.NumberColumn("Price", format="$%.2f"),
        "Market Value": st.column_config.NumberColumn("Market Value", format="$%,.2f"),
        "P&L $":        st.column_config.NumberColumn("P&L $", format="$%+,.2f"),
        "P&L %":        st.column_config.NumberColumn("P&L %", format="%+.2f%%"),
        "Score":        st.column_config.NumberColumn("Score", format="%.1f"),
    },
)

# --- Sector concentration ---
st.divider()
st.subheader("Sector Concentration")
with st.spinner("Loading sector data..."):
    sectors = get_sectors(tuple(tickers))

total_invested = sum(float(p["market_value"]) for p in positions)
sector_values: dict[str, float] = {}
for p in positions:
    s = sectors.get(p["symbol"], "Unknown")
    sector_values[s] = sector_values.get(s, 0) + float(p["market_value"])

sector_rows = sorted(
    [{"Sector": s, "Value": v, "Pct": v / total_invested * 100}
     for s, v in sector_values.items()],
    key=lambda x: x["Pct"], reverse=True,
)

for r in sector_rows:
    if r["Pct"] >= SECTOR_WARN_PCT:
        st.warning(f"⚠️ **{r['Sector']}** is {r['Pct']:.1f}% of invested capital — consider diversifying")

sector_df = pd.DataFrame(sector_rows)
st.dataframe(
    sector_df,
    hide_index=True,
    use_container_width=True,
    column_config={
        "Value": st.column_config.NumberColumn("Value", format="$%,.2f"),
        "Pct":   st.column_config.NumberColumn("% of Portfolio", format="%.1f%%"),
    },
)

st.divider()

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
