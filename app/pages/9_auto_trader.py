import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests
from datetime import datetime, timezone
from supabase import create_client
from config import get_secret

st.set_page_config(page_title="Auto Trader", page_icon="🤖", layout="wide")
st.title("🤖 Auto Trader")
st.caption("Algorithm vs You — both running on Alpaca paper accounts")

_url = get_secret("SUPABASE_URL")
_key = get_secret("SUPABASE_KEY")
db   = create_client(_url, _key)

BASE = "https://paper-api.alpaca.markets/v2"

def _manual_headers() -> dict:
    return {
        "APCA-API-KEY-ID":     get_secret("ALPACA_API_KEY"),
        "APCA-API-SECRET-KEY": get_secret("ALPACA_SECRET_KEY"),
    }

def _auto_headers() -> dict:
    return {
        "APCA-API-KEY-ID":     get_secret("ALPACA_AUTO_API_KEY"),
        "APCA-API-SECRET-KEY": get_secret("ALPACA_AUTO_SECRET_KEY"),
    }


def _fetch_account(headers: dict) -> dict | None:
    try:
        r = requests.get(f"{BASE}/account", headers=headers, timeout=5)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"error": str(e)}


def _fetch_history(headers: dict, period: str = "1M") -> dict | None:
    try:
        r = requests.get(
            f"{BASE}/account/portfolio/history",
            headers=headers,
            params={"period": period, "timeframe": "1D"},
            timeout=5,
        )
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def _fetch_positions(headers: dict) -> list[dict]:
    try:
        r = requests.get(f"{BASE}/positions", headers=headers, timeout=5)
        r.raise_for_status()
        return r.json()
    except Exception:
        return []


# --- Account summary cards ---
manual_acct = _fetch_account(_manual_headers())
auto_acct   = _fetch_account(_auto_headers())

st.subheader("Account Summary")
col_manual, col_auto = st.columns(2)

with col_manual:
    st.markdown("#### 👤 You (Manual)")
    if "error" in manual_acct:
        st.error(manual_acct["error"])
    else:
        m1, m2 = st.columns(2)
        m1.metric("Portfolio Value", f"${float(manual_acct['portfolio_value']):,.2f}")
        m2.metric("Buying Power",    f"${float(manual_acct['buying_power']):,.2f}")

with col_auto:
    st.markdown("#### 🤖 Algorithm (Auto)")
    if "error" in auto_acct:
        st.error(auto_acct["error"])
    else:
        a1, a2 = st.columns(2)
        a1.metric("Portfolio Value", f"${float(auto_acct['portfolio_value']):,.2f}")
        a2.metric("Buying Power",    f"${float(auto_acct['buying_power']):,.2f}")

st.divider()

# --- Equity curve comparison ---
st.subheader("Equity Curve")
period = st.selectbox("Period", ["1W", "1M", "3M", "6M", "1A"], index=1)

manual_hist = _fetch_history(_manual_headers(), period)
auto_hist   = _fetch_history(_auto_headers(), period)

if manual_hist and auto_hist:
    fig = go.Figure()

    def _add_trace(hist, name, color):
        ts  = [datetime.fromtimestamp(t, tz=timezone.utc) for t in hist["timestamp"]]
        eq  = hist["equity"]
        base = eq[0] if eq[0] else 1
        pct  = [(v / base - 1) * 100 if base else 0 for v in eq]
        fig.add_trace(go.Scatter(x=ts, y=pct, name=name, line=dict(color=color, width=2)))

    _add_trace(manual_hist, "👤 You", "#4FC3F7")
    _add_trace(auto_hist,   "🤖 Algorithm", "#81C784")

    fig.update_layout(
        yaxis_title="Return (%)",
        height=350,
        margin=dict(l=0, r=0, t=20, b=0),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        hovermode="x unified",
    )
    fig.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.4)
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Not enough history yet to show equity curves.")

st.divider()

# --- Open positions ---
st.subheader("Open Positions")
pos_m, pos_a = st.columns(2)

with pos_m:
    st.markdown("#### 👤 You")
    manual_pos = _fetch_positions(_manual_headers())
    if manual_pos:
        rows = [{"Ticker": p["symbol"],
                 "Qty": float(p["qty"]),
                 "Value": f"${float(p['market_value']):,.2f}",
                 "P&L": f"{float(p['unrealized_plpc'])*100:+.1f}%"} for p in manual_pos]
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    else:
        st.caption("No open positions")

with pos_a:
    st.markdown("#### 🤖 Algorithm")
    auto_pos = _fetch_positions(_auto_headers())
    if auto_pos:
        rows = [{"Ticker": p["symbol"],
                 "Qty": float(p["qty"]),
                 "Value": f"${float(p['market_value']):,.2f}",
                 "P&L": f"{float(p['unrealized_plpc'])*100:+.1f}%"} for p in auto_pos]
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    else:
        st.caption("No open positions yet")

st.divider()

# --- Auto trade log ---
st.subheader("Algorithm Trade Log")
trades = db.table("auto_trades").select("*").order("traded_at", desc=True).limit(50).execute()

if trades.data:
    df = pd.DataFrame(trades.data)
    df["traded_at"] = df["traded_at"].str[:16].str.replace("T", " ")
    display_cols = ["traded_at", "ticker", "score", "order_type", "qty", "limit_price", "stop_price", "status", "error"]
    display_cols = [c for c in display_cols if c in df.columns]
    df = df[display_cols].rename(columns={
        "traded_at": "Time", "ticker": "Ticker", "score": "Score",
        "order_type": "Type", "qty": "Qty", "limit_price": "Limit $",
        "stop_price": "Stop $", "status": "Status", "error": "Error",
    })
    st.dataframe(df, hide_index=True, use_container_width=True)
else:
    st.info("No automated trades yet. The algorithm runs weekdays at 9:35am ET, or trigger it manually from GitHub Actions.")
