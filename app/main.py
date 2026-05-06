import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
from db.client import get_db

st.set_page_config(
    page_title="Stock Advisor",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("📈 Stock Advisor")
st.caption("Technical analysis-driven signals for S&P 500 stocks. Alpaca portfolio connected read-only.")

col1, col2, col3 = st.columns(3)

with col1:
    st.info("🔍 **Screener** — Ranked S&P 500 picks")
with col2:
    st.info("👀 **Watchlist** — Your 25 tracked stocks")
with col3:
    st.info("📊 **Performance** — vs SPY and VTI")

st.divider()
st.markdown("""
**How to use this app:**
1. Open **Screener** to see today's top-scoring stocks with buy/sell signals
2. Click any row to expand the full analysis card
3. Add interesting stocks to your **Watchlist** for 1-minute refresh monitoring
4. Check **Portfolio** to see your live Alpaca positions and their current signals
5. Review **Performance** to see how you're doing vs the S&P 500 and VTI
6. The scan runs automatically every 2 hours during market hours — no action needed

**Signal meanings:**
| Signal | Score | Action |
|--------|-------|--------|
| 🟢 BUY | 75–100 | Strong setup — consider entering |
| 👀 WATCH CAREFULLY | 55–74 | Promising but unconfirmed |
| 🟡 HOLD | 35–54 | Mixed signals — stay the course |
| 🔴 REDUCE | 25–34 | Signals weakening — consider trimming |
| 🚨 EXIT | 0–24 | Significant deterioration — consider full exit |
""")
