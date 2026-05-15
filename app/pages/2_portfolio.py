import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import yfinance as yf
from supabase import create_client
from config import get_secret, SIGNAL_EMOJI
from alpaca_client import get_positions, get_account

SECTOR_WARN_PCT  = 40   # warn if any sector exceeds this % of invested capital
TREND_SCAN_LIMIT = 10   # how many recent scan runs to look back for trend


@st.cache_data(ttl=86400)
def get_sectors(tickers: tuple) -> dict[str, str]:
    result = {}
    for t in tickers:
        try:
            result[t] = yf.Ticker(t).info.get("sector") or "Unknown"
        except Exception:
            result[t] = "Unknown"
    return result


def load_score_history(db, tickers: list[str], n_scans: int = TREND_SCAN_LIMIT) -> dict[str, list]:
    """Return {ticker: [(scanned_at, score), ...]} sorted oldest→newest."""
    try:
        # Get the N most recent distinct scan times
        times_rows = (
            db.table("scan_results")
            .select("scanned_at")
            .order("scanned_at", desc=True)
            .limit(n_scans * len(tickers))
            .execute()
        )
        all_times = pd.Series([r["scanned_at"] for r in times_rows.data]).unique()
        recent_times = list(all_times[:n_scans])

        if not recent_times:
            return {}

        rows = (
            db.table("scan_results")
            .select("ticker, scanned_at, score")
            .in_("ticker", tickers)
            .in_("scanned_at", recent_times)
            .order("scanned_at", desc=False)
            .execute()
        )
        history: dict[str, list] = {t: [] for t in tickers}
        for r in rows.data:
            history[r["ticker"]].append((r["scanned_at"], float(r["score"])))
        return history
    except Exception:
        return {}


def score_trend(scores: list[float]) -> tuple[str, float]:
    """Return (arrow, delta) from oldest to newest score."""
    if len(scores) < 2:
        return "—", 0.0
    delta = scores[-1] - scores[0]
    if   delta >= 10: arrow = "↑"
    elif delta >=  3: arrow = "↗"
    elif delta <= -10: arrow = "↓"
    elif delta <=  -3: arrow = "↘"
    else:              arrow = "→"
    return arrow, delta


_url = get_secret("SUPABASE_URL")
_key = get_secret("SUPABASE_KEY")

st.set_page_config(page_title="Portfolio", page_icon="💼", layout="wide")
st.title("💼 Portfolio")
st.caption("Live Alpaca positions — read-only. Execute trades at alpaca.markets.")


def load_portfolio():
    try:
        return get_positions(), get_account(), None
    except Exception as e:
        return [], {}, str(e)


positions, account, error = load_portfolio()

if error:
    st.error(f"Could not connect to Alpaca: {error}")
    st.info("Make sure ALPACA_API_KEY and ALPACA_SECRET_KEY are set in your Streamlit secrets.")
    st.stop()

# --- Account summary ---
col1, col2, col3 = st.columns(3)
col1.metric("Portfolio Value", f"${account.get('portfolio_value', 0):,.2f}")
col2.metric("Buying Power",    f"${account.get('buying_power', 0):,.2f}")
col3.metric("Cash",            f"${account.get('cash', 0):,.2f}")

st.divider()

if not positions:
    st.info("No open positions found in your Alpaca account.")
    st.stop()

tickers = [p["symbol"] for p in positions]
_db = create_client(_url, _key)

# --- Latest signals ---
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

# --- Score history for trend ---
score_history = load_score_history(_db, tickers)

rows = []
for p in positions:
    sig_data = signal_map.get(p["symbol"], {})
    signal   = sig_data.get("signal", "—")
    emoji    = SIGNAL_EMOJI.get(signal, "")
    pl_pct   = p["unrealized_plpc"] * 100

    history  = score_history.get(p["symbol"], [])
    scores   = [s for _, s in history]
    arrow, delta = score_trend(scores)
    trend_str = f"{arrow} {delta:+.1f}" if arrow != "—" else "—"

    rows.append({
        "Ticker":       p["symbol"],
        "Shares":       float(p["qty"]),
        "Price":        float(p["current_price"]),
        "Market Value": float(p["market_value"]),
        "P&L $":        float(p["unrealized_pl"]),
        "P&L %":        pl_pct,
        "Signal":       f"{emoji} {signal}",
        "Score":        float(sig_data["score"]) if sig_data.get("score") not in (None, "—") else None,
        "Trend":        trend_str,
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
        "Shares":       st.column_config.NumberColumn("Shares",       format="%.6f"),
        "Price":        st.column_config.NumberColumn("Price",        format="$%.2f"),
        "Market Value": st.column_config.NumberColumn("Market Value", format="$%,.2f"),
        "P&L $":        st.column_config.NumberColumn("P&L $",        format="$%+,.2f"),
        "P&L %":        st.column_config.NumberColumn("P&L %",        format="%+.2f%%"),
        "Score":        st.column_config.NumberColumn("Score",        format="%.1f"),
        "Trend":        st.column_config.TextColumn("Trend (10 scans)"),
    },
)

# --- Selected position detail ---
if event.selection.rows:
    idx    = event.selection.rows[0]
    ticker = rows[idx]["Ticker"]
    sig_data = signal_map.get(ticker, {})

    st.divider()
    st.subheader(f"Signal detail: {ticker}")

    # Score history chart
    history = score_history.get(ticker, [])
    if len(history) >= 2:
        times  = [t for t, _ in history]
        scores = [s for _, s in history]
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=times, y=scores,
            mode="lines+markers",
            line=dict(color="#00D4AA", width=2),
            marker=dict(size=6),
        ))
        fig.add_hline(y=75, line_dash="dash", line_color="#00C48C",
                      opacity=0.5, annotation_text="BUY")
        fig.add_hline(y=55, line_dash="dash", line_color="#4A90D9",
                      opacity=0.5, annotation_text="WATCH")
        fig.add_hline(y=35, line_dash="dash", line_color="#F5A623",
                      opacity=0.5, annotation_text="HOLD")
        fig.add_hline(y=25, line_dash="dash", line_color="#E55A4E",
                      opacity=0.5, annotation_text="REDUCE")
        fig.update_layout(
            height=220, margin=dict(l=0, r=0, t=10, b=0),
            yaxis=dict(range=[0, 100], title="Score"),
            xaxis_title="Scan time",
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.caption("Not enough scan history yet for this ticker.")

    if sig_data:
        st.write(sig_data.get("reasoning", "No reasoning available."))
        if sig_data.get("earnings_warning"):
            st.warning("⚠️ Earnings within 7 days")
    else:
        st.info("No scan data available for this ticker yet.")

    st.markdown(f"[Trade on Alpaca →](https://app.alpaca.markets/trade/{ticker})")

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

st.dataframe(
    pd.DataFrame(sector_rows),
    hide_index=True,
    use_container_width=True,
    column_config={
        "Value": st.column_config.NumberColumn("Value",          format="$%,.2f"),
        "Pct":   st.column_config.NumberColumn("% of Portfolio", format="%.1f%%"),
    },
)
