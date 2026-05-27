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
st.caption("You vs Algorithm vs Claude — three Alpaca paper accounts compared")

_url = get_secret("SUPABASE_URL")
_key = get_secret("SUPABASE_KEY")
db   = create_client(_url, _key)

BASE = "https://paper-api.alpaca.markets/v2"

YF_PERIOD_MAP   = {"1D": "1d",  "1W": "5d",  "1M": "1mo", "3M": "3mo", "6M": "6mo", "1Y": "1y"}
YF_INTERVAL_MAP = {"1D": "15m", "1W": "1h",  "1M": "1d",  "3M": "1d",  "6M": "1d",  "1Y": "1d"}
ALP_PERIOD_MAP  = {"1D": ("1D", "15Min"), "1W": ("1W", "1D"), "1M": ("1M", "1D"),
                   "3M": ("3M", "1D"),    "6M": ("6M", "1D"), "1Y": ("1A", "1D")}
DTICK_MAP       = {"1D": 0.1,  "1W": 0.25, "1M": 0.5,   "3M": 1.0,   "6M": 1.0,   "1Y": 2.0}


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

def _claude_headers() -> dict:
    return {
        "APCA-API-KEY-ID":     get_secret("ALPACA_CLAUDE_API_KEY"),
        "APCA-API-SECRET-KEY": get_secret("ALPACA_CLAUDE_SECRET_KEY"),
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
claude_acct = _fetch_account(_claude_headers())

st.subheader("Account Summary")
col_manual, col_auto, col_claude = st.columns(3)

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

with col_claude:
    st.markdown("#### 🧠 Claude (Autonomous)")
    if "error" in claude_acct:
        st.error(claude_acct["error"])
    else:
        c1, c2 = st.columns(2)
        c1.metric("Portfolio Value", f"${float(claude_acct['portfolio_value']):,.2f}")
        c2.metric("Buying Power",    f"${float(claude_acct['buying_power']):,.2f}")

st.divider()

# --- Equity curve ---
st.subheader("Equity Curve")
c1, c2 = st.columns([2, 2])
period_label = c1.selectbox("Period", list(YF_PERIOD_MAP.keys()), index=2)
view         = c2.radio("View", ["Invested positions only", "Total account (incl. cash)"], horizontal=True)

yf_period   = YF_PERIOD_MAP[period_label]
yf_interval = YF_INTERVAL_MAP[period_label]
alp_period, alp_timeframe = ALP_PERIOD_MAP[period_label]
dtick       = DTICK_MAP[period_label]

def _to_et(s: pd.Series) -> pd.Series:
    idx = pd.DatetimeIndex(s.index)
    if idx.tz is None:
        idx = idx.tz_localize("UTC")
    return s.set_axis(idx.tz_convert("America/New_York"))


fig = go.Figure()

def _add_benchmark(ticker: str, name: str, color: str) -> None:
    try:
        data = yf.download(ticker, period=yf_period, interval=yf_interval,
                           auto_adjust=True, progress=False)["Close"].squeeze()
        if data.empty or len(data) < 2:
            return
        idx = data.index.tz_localize(None) if data.index.tz else data.index
        data.index = idx
        pct = (data / data.iloc[0] - 1) * 100
        fig.add_trace(go.Scatter(
            x=_to_et(pct).index, y=pct,
            name=name, line=dict(color=color, width=1.5, dash="dash"),
        ))
    except Exception:
        pass


if view == "Invested positions only":
    with st.spinner("Loading position performance..."):
        m_ret  = _invested_performance(_manual_headers(), yf_period, yf_interval)
        a_ret  = _invested_performance(_auto_headers(),   yf_period, yf_interval)
        cl_ret = _invested_performance(_claude_headers(), yf_period, yf_interval)

    def _add_invested(ret, name, color):
        if ret is None or len(ret.dropna()) < 2:
            return
        s = _to_et(ret.dropna())
        fig.add_trace(go.Scatter(x=s.index, y=s * 100, name=name, line=dict(color=color, width=2)))

    _add_invested(m_ret,  "👤 You",        "#4FC3F7")
    _add_invested(a_ret,  "🤖 Algorithm",  "#81C784")
    _add_invested(cl_ret, "🧠 Claude",     "#FFB74D")
    _add_benchmark("SPY", "SPY (S&P 500)",    "#4A90D9")
    _add_benchmark("VTI", "VTI (Total Mkt)",  "#F5A623")
    fig.update_layout(yaxis=dict(title="Return on invested capital (%)", tickformat="+.1f", ticksuffix="%", dtick=dtick))

else:
    manual_hist = _fetch_history(_manual_headers(), alp_period, alp_timeframe)
    auto_hist   = _fetch_history(_auto_headers(),   alp_period, alp_timeframe)
    claude_hist = _fetch_history(_claude_headers(),  alp_period, alp_timeframe)

    def _add_total(hist, name, color):
        if not hist:
            return
        from zoneinfo import ZoneInfo
        ET = ZoneInfo("America/New_York")
        ts  = [datetime.fromtimestamp(t, tz=timezone.utc).astimezone(ET) for t in hist["timestamp"]]
        eq  = hist["equity"]
        nonzero = [v for v in eq if v and v > 0]
        if not nonzero:
            return
        base = nonzero[0]
        pct  = [(v / base - 1) * 100 if v else None for v in eq]
        fig.add_trace(go.Scatter(x=ts, y=pct, name=name, line=dict(color=color, width=2)))

    _add_total(manual_hist, "👤 You",       "#4FC3F7")
    _add_total(auto_hist,   "🤖 Algorithm", "#81C784")
    _add_total(claude_hist, "🧠 Claude",    "#FFB74D")
    _add_benchmark("SPY", "SPY (S&P 500)",   "#4A90D9")
    _add_benchmark("VTI", "VTI (Total Mkt)", "#F5A623")
    fig.update_layout(yaxis=dict(title="Total account return (%)", tickformat="+.1f", ticksuffix="%", dtick=dtick))

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
pos_m, pos_a, pos_cl = st.columns(3)

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

with pos_cl:
    st.markdown("#### 🧠 Claude")
    claude_pos = _fetch_positions(_claude_headers())
    if claude_pos:
        st.dataframe(pd.DataFrame(_pos_rows(claude_pos)), hide_index=True, use_container_width=True)
    else:
        st.caption("No open positions yet")

st.divider()

# --- Trade logs ---
col_log_a, col_log_cl = st.columns(2)

with col_log_a:
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
        st.info("No automated trades yet. Runs weekdays at 9:35am ET.")

with col_log_cl:
    st.subheader("Claude Trade Log")
    cl_trades = db.table("claude_trades").select("*").order("traded_at", desc=True).limit(50).execute()
    if cl_trades.data:
        df2 = pd.DataFrame(cl_trades.data)
        df2["traded_at"] = df2["traded_at"].apply(utc_to_et)
        display_cols2 = ["traded_at", "ticker", "action", "qty", "limit_price", "stop_price", "allocation_pct", "reasoning", "status", "error"]
        display_cols2 = [c for c in display_cols2 if c in df2.columns]
        df2 = df2[display_cols2].rename(columns={
            "traded_at": "Time", "ticker": "Ticker", "action": "Action",
            "qty": "Qty", "limit_price": "Limit $", "stop_price": "Stop $",
            "allocation_pct": "Alloc %", "reasoning": "Reasoning",
            "status": "Status", "error": "Error",
        })
        st.dataframe(df2, hide_index=True, use_container_width=True)
    else:
        st.info("No Claude trades yet. Runs weekdays at 9:35am and 1:00pm ET.")
