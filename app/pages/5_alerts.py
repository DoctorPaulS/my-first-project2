import streamlit as st
from db.client import get_db
from config import SIGNAL_EMOJI

st.set_page_config(page_title="Alerts", page_icon="🔔", layout="wide")
st.title("🔔 Alerts")
st.caption("Signal changes detected on your watchlist stocks")

db = get_db()


def load_alerts():
    result = (
        db.table("alerts")
        .select("*")
        .order("created_at", desc=True)
        .execute()
    )
    return result.data


alerts = load_alerts()

if not alerts:
    st.info("No alerts yet. Alerts appear here when a watchlist stock changes signal between scans.")
    st.stop()

unread = [a for a in alerts if not a["read"]]
read = [a for a in alerts if a["read"]]

col_count, col_clear = st.columns([3, 1])
with col_count:
    st.subheader(f"{len(unread)} unread alert{'s' if len(unread) != 1 else ''}")
with col_clear:
    if st.button("Clear All"):
        db.table("alerts").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
        st.success("All alerts cleared.")
        st.rerun()


def render_alerts(alert_list: list[dict]):
    for alert in alert_list:
        prev = alert["previous_signal"]
        new = alert["new_signal"]
        prev_emoji = SIGNAL_EMOJI.get(prev, "")
        new_emoji = SIGNAL_EMOJI.get(new, "")
        created = alert["created_at"][:16].replace("T", " ")

        col_msg, col_read = st.columns([5, 1])
        with col_msg:
            st.markdown(
                f"**{alert['ticker']}** — {prev_emoji} {prev} → {new_emoji} {new}  \n"
                f"<span style='color:gray;font-size:0.85em'>{created} ET</span>",
                unsafe_allow_html=True,
            )
        with col_read:
            if not alert["read"] and st.button("✓ Read", key=f"read_{alert['id']}"):
                db.table("alerts").update({"read": True}).eq("id", alert["id"]).execute()
                st.rerun()


if unread:
    st.markdown("### New")
    render_alerts(unread)

if read:
    with st.expander(f"Show {len(read)} read alerts"):
        render_alerts(read)
