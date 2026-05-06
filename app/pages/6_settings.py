import streamlit as st
from db.client import get_db, get_settings, save_settings
from config import DEFAULT_THRESHOLDS, DEFAULT_GROUP_WEIGHTS, MAX_WATCHLIST_SIZE
from scanner.indicators.registry import INDICATORS

st.set_page_config(page_title="Settings", page_icon="⚙️", layout="wide")
st.title("⚙️ Settings")

db = get_db()

# --- Signal Thresholds ---
st.subheader("Signal Thresholds")
st.caption("Minimum score required to reach each signal level.")
thresholds = get_settings("thresholds", DEFAULT_THRESHOLDS)

col1, col2, col3, col4, col5 = st.columns(5)
new_buy = col1.number_input("🟢 BUY", 0, 100, int(thresholds.get("BUY", 75)))
new_watch = col2.number_input("👀 WATCH CAREFULLY", 0, 100, int(thresholds.get("WATCH CAREFULLY", 55)))
new_hold = col3.number_input("🟡 HOLD", 0, 100, int(thresholds.get("HOLD", 35)))
new_reduce = col4.number_input("🔴 REDUCE", 0, 100, int(thresholds.get("REDUCE", 25)))
new_exit = col5.number_input("🚨 EXIT", 0, 100, int(thresholds.get("EXIT", 0)))

if st.button("Save Thresholds"):
    save_settings("thresholds", {
        "BUY": new_buy, "WATCH CAREFULLY": new_watch,
        "HOLD": new_hold, "REDUCE": new_reduce, "EXIT": new_exit,
    })
    st.success("Thresholds saved.")

st.divider()

# --- Group Weights ---
st.subheader("Indicator Group Weights")
st.caption("Weights must sum to 1.0. Changes take effect on the next scan.")
weights = get_settings("group_weights", DEFAULT_GROUP_WEIGHTS)

w_trend = st.slider("Trend (EMA + ADX)", 0.0, 1.0, float(weights.get("trend", 0.30)), step=0.05)
w_momentum = st.slider("Momentum (MACD + RSI)", 0.0, 1.0, float(weights.get("momentum", 0.25)), step=0.05)
w_volume = st.slider("Volume (OBV + Relative Volume)", 0.0, 1.0, float(weights.get("volume", 0.20)), step=0.05)
w_volatility = st.slider("Volatility (Bollinger + ATR)", 0.0, 1.0, float(weights.get("volatility", 0.15)), step=0.05)
w_candles = st.slider("Candlestick Patterns", 0.0, 1.0, float(weights.get("candlesticks", 0.10)), step=0.05)

total = round(w_trend + w_momentum + w_volume + w_volatility + w_candles, 2)
st.metric("Total Weight", f"{total:.2f}", delta=f"{total - 1.0:+.2f} from 1.0")

if st.button("Save Weights"):
    if abs(total - 1.0) > 0.01:
        st.error("Weights must sum to 1.0 before saving.")
    else:
        save_settings("group_weights", {
            "trend": w_trend, "momentum": w_momentum,
            "volume": w_volume, "volatility": w_volatility,
            "candlesticks": w_candles,
        })
        st.success("Weights saved.")

st.divider()

# --- Indicator Toggles ---
st.subheader("Indicator Toggles")
st.caption("Disable individual indicators. Changes take effect on the next scan.")
toggles = get_settings("indicator_toggles", {})

new_toggles = {}
for entry in INDICATORS:
    name = entry.cls.__name__
    enabled = toggles.get(name, True)
    new_val = st.checkbox(f"{name} ({entry.group})", value=enabled, key=f"toggle_{name}")
    new_toggles[name] = new_val

if st.button("Save Toggles"):
    save_settings("indicator_toggles", new_toggles)
    st.success("Indicator toggles saved.")

st.divider()

# --- API Keys Info ---
st.subheader("API Keys")
st.info(
    "API keys (Alpaca, Supabase, NewsAPI) are managed securely via the "
    "**Streamlit Community Cloud secrets dashboard**, not stored here. "
    "Go to your app settings at share.streamlit.io to update them."
)

st.divider()

# --- Watchlist Cap ---
st.subheader("Watchlist Cap")
st.info(f"Current cap: **{MAX_WATCHLIST_SIZE} stocks**. To increase this in Phase 2, change `MAX_WATCHLIST_SIZE` in `config.py`.")
