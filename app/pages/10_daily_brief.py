import streamlit as st
from config import get_secret, utc_to_et, SIGNAL_EMOJI
from supabase import create_client

st.set_page_config(page_title="Daily Brief", page_icon="📋", layout="wide")
st.title("📋 Daily Brief")
st.caption("Position-by-position summary with signals, targets, news, and AI recommendations")

# Lazy import to avoid slow load — only runs when page is active
from scanner.daily_brief import build_full_brief

SIGNAL_COLOR = {
    "BUY": "green", "WATCH CAREFULLY": "blue",
    "HOLD": "orange", "REDUCE": "red", "EXIT": "red",
}


def _pnl_color(val: float) -> str:
    return "green" if val >= 0 else "red"


col_refresh, col_note = st.columns([1, 4])
with col_refresh:
    refresh = st.button("🔄 Refresh Brief")
with col_note:
    st.caption("Generating the brief calls the AI for each position — takes ~30 seconds.")

if "brief_data" not in st.session_state or refresh:
    with st.spinner("Building portfolio brief... this may take a moment."):
        st.session_state["brief_data"] = build_full_brief()

accounts = st.session_state["brief_data"]

for account in accounts:
    st.divider()
    c1, c2, c3 = st.columns(3)
    c1.subheader(account["label"])
    c2.metric("Portfolio Value", f"${account['portfolio_value']:,.2f}")
    c3.metric("Buying Power",    f"${account['buying_power']:,.2f}")

    positions = account["positions"]
    if not positions:
        st.info("No open positions in this account.")
        continue

    for p in positions:
        if "error" in p:
            st.warning(f"**{p['ticker']}** — could not load: {p['error']}")
            continue

        with st.expander(
            f"{p['signal_emoji']} **{p['ticker']}** — {p['signal']} ({p['score']:.0f}/100)  "
            f"| P&L: {p['pnl_pct']:+.1f}% (${p['pnl_dollars']:+,.0f})",
            expanded=True,
        ):
            m1, m2, m3, m4, m5 = st.columns(5)
            m1.metric("Entry",    f"${p['entry_price']:.2f}")
            m2.metric("Current",  f"${p['current_price']:.2f}")
            m3.metric("P&L",      f"{p['pnl_pct']:+.1f}%",    delta_color="normal")
            m4.metric("Stop",     f"${p['stop']:.2f}",
                      f"{p['pct_to_stop']:+.1f}%", delta_color="inverse")
            m5.metric("Target 1", f"${p['target1']:.2f}",
                      f"{p['pct_to_t1']:+.1f}%")

            t1, t2 = st.columns(2)
            with t1:
                st.metric("Target 2", f"${p['target2']:.2f}", f"{p['pct_to_t2']:+.1f}%")

            st.markdown("**💡 AI Recommendation:**")
            st.info(p["ai_summary"])

            if p["headlines"]:
                with st.expander("📰 News headlines"):
                    for h in p["headlines"]:
                        st.markdown(f"- {h}")
