import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import yfinance as yf
import requests
from datetime import datetime, timezone
from supabase import create_client
from config import get_secret, utc_to_et

st.set_page_config(page_title="Auto Trader", page_icon="🤖", layout="wide")
st.title("🤖 Auto Trader")
st.caption("Algorithm vs You — both running on Alpaca paper accounts")

_url = get_secret("SUPABASE_URL")
_key = get_secret("SUPABASE_KEY")
db   = create_client(_url, _key)

BASE = "https://paper-api.alpaca.markets/v2"

YF_PERIOD_MAP   = {"1D": "1d",  "1W": "5d",  "1M": "1mo", "3M": "3mo", "6M": "6mo", "1Y": "1y"}
YF_INTERVAL_MAP = {"1D": "15m", "1W": "1h",  "1M": "1d",  "3M": "1d",  "6M": "1d",  "1Y": "1d"}
ALP_PERIOD_MAP  = {"1D": ("1D", "15Min"), "1W": ("1W", "1D"), "1M": ("1M", "1D"),
                   "3M": ("3M", "1D"),    "6M": ("6M", "1D"), "1Y": ("1A", "1D")}


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


def _fetch_account(headers: dict) -> dict:
    try:
        r = requests.get(f"{BASE}/account", headers=headers, timeout=5)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"error": str(e)}


def _fetch_history(headers: dict, period: str, timeframe: str) -> dict | None:
    try:
        r = requests.get(
            f"{BASE}/account/portfolio/history",
            headers=headers,
            params={"period": period, "timeframe": timeframe},
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


def _fetch_filled_orders(headers: dict) -> dict[str, dict]:
    """Return {ticker: {entry_date, entry_price}} from earliest filled buy orders."""
    try:
        r = requests.get(
            f"{BASE}/orders",
            headers=headers,
            params={"status": "filled", "limit": 100, "direction": "asc"},
            timeout=5,
        )
        r.raise_for_status()
        entries = {}
        for o in r.json():
            if o.get("side") == "buy" and o.get("filled_at") and o.get("filled_avg_price"):
                t = o["symbol"]
                if t not in entries:
                    entries[t] = {
                        "entry_date":  pd.Timestamp(o["filled_at"]).tz_localize(None),
                        "entry_price": float(o["filled_avg_price"]),
                    }
        return entries
    except Exception:
        return {}


def _invested_performance(headers: dict, yf_period: str, yf_interval: str) -> pd.Series | None:
    """Weighted return of invested positions only, anchored to fill price."""
    positions = _fetch_positions(headers)
    if not positions:
        return None
    filled    = _fetch_filled_orders(headers)
    total_cost = sum(float(p["cost_basis"]) for p in positions)
    if total_cost == 0:
        return None

    portfolio_return = None
    for pos in positions:
        ticker     = pos["symbol"]
        qty        = float(pos["qty"])
        cost_basis = float(pos["cost_basis"])
        weight     = cost_basis / total_cost
        info       = filled.get(ticker, {})
        entry_price = info.get("entry_price") or (cost_basis / qty)
        entry_date  = info.get("entry_date")

        try:
            prices = yf.download(
                ticker, period=yf_period, interval=yf_interval,
                auto_adjust=True, progress=False,
            )["Close"].squeeze()
            if prices.empty or len(prices) < 2:
                continue
            idx = prices.index.tz_localize(None) if prices.index.tz else prices.index
            prices.index = idx

            if yf_period == "1d":
                anchor = float(prices.iloc[0])
            else:
                if entry_date is not None and entry_date > idx[0]:
                    prices = prices[idx >= entry_date]
                if len(prices) < 2:
                    continue
                anchor = entry_price

            ret = (prices / anchor - 1) * weight
            portfolio_return = ret if portfolio_return is None else portfolio_return.add(ret, fill_value=0)
        except Exception:
            continue

    return portfolio_return


# --- Account summary ---
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

# --- Equity curve ---
st.subheader("Equity Curve")
c1, c2 = st.columns([2, 2])
period_label = c1.selectbox("Period", list(YF_PERIOD_MAP.keys()), index=2)
view         = c2.radio("View", ["Invested positions only", "Total account (incl. cash)"], horizontal=True)

yf_period   = YF_PERIOD_MAP[period_label]
yf_interval = YF_INTERVAL_MAP[period_label]
alp_period, alp_timeframe = ALP_PERIOD_MAP[period_label]

fig = go.Figure()

if view == "Invested positions only":
    with st.spinner("Loading position performance..."):
        m_ret = _invested_performance(_manual_headers(), yf_period, yf_interval)
        a_ret = _invested_performance(_auto_headers(),   yf_period, yf_interval)

    def _add_invested(ret, name, color):
        if ret is None or len(ret.dropna()) < 2:
            return
        s = ret.dropna()
        fig.add_trace(go.Scatter(x=s.index, y=s * 100, name=name, line=dict(color=color, width=2)))

    _add_invested(m_ret, "👤 You",        "#4FC3F7")
    _add_invested(a_ret, "🤖 Algorithm",  "#81C784")
    fig.update_layout(yaxis_title="Return on invested capital (%)")

else:
    manual_hist = _fetch_history(_manual_headers(), alp_period, alp_timeframe)
    auto_hist   = _fetch_history(_auto_headers(),   alp_period, alp_timeframe)

    def _add_total(hist, name, color):
        if not hist:
            return
        ts  = [datetime.fromtimestamp(t, tz=timezone.utc) for t in hist["timestamp"]]
        eq  = hist["equity"]
        nonzero = [v for v in eq if v and v > 0]
        if not nonzero:
            return
        base = nonzero[0]
        pct  = [(v / base - 1) * 100 if v else None for v in eq]
        fig.add_trace(go.Scatter(x=ts, y=pct, name=name, line=dict(color=color, width=2)))

    _add_total(manual_hist, "👤 You",       "#4FC3F7")
    _add_total(auto_hist,   "🤖 Algorithm", "#81C784")
    fig.update_layout(yaxis_title="Total account return (%)")

fig.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.4)
fig.update_layout(
    height=380,
    margin=dict(l=0, r=0, t=20, b=0),
    legend=dict(orientation="h", yanchor="bottom", y=1.02),
    hovermode="x unified",
)
st.plotly_chart(fig, use_container_width=True)

st.divider()

# --- Open positions ---
st.subheader("Open Positions")
pos_m, pos_a = st.columns(2)

def _pos_rows(positions):
    return [{"Ticker": p["symbol"],
             "Qty":    int(float(p["qty"])),
             "Value":  f"${float(p['market_value']):,.2f}",
             "Return": f"{float(p['unrealized_plpc'])*100:+.1f}%",
             "P&L $":  f"${float(p['unrealized_pl']):+,.0f}"} for p in positions]

with pos_m:
    st.markdown("#### 👤 You")
    manual_pos = _fetch_positions(_manual_headers())
    if manual_pos:
        st.dataframe(pd.DataFrame(_pos_rows(manual_pos)), hide_index=True, use_container_width=True)
    else:
        st.caption("No open positions")

with pos_a:
    st.markdown("#### 🤖 Algorithm")
    auto_pos = _fetch_positions(_auto_headers())
    if auto_pos:
        st.dataframe(pd.DataFrame(_pos_rows(auto_pos)), hide_index=True, use_container_width=True)
    else:
        st.caption("No open positions yet")

st.divider()

# --- Auto trade log ---
st.subheader("Algorithm Trade Log")
trades = db.table("auto_trades").select("*").order("traded_at", desc=True).limit(50).execute()

if trades.data:
    df = pd.DataFrame(trades.data)
    df["traded_at"] = df["traded_at"].apply(utc_to_et)
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
