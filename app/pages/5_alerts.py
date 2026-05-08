import streamlit as st
from supabase import create_client
from config import get_secret, SIGNAL_EMOJI

st.set_page_config(page_title="Alerts", page_icon="🔔", layout="wide")
st.title("🔔 Alerts")
st.caption("Signal changes and price target hits")

_url = get_secret("SUPABASE_URL")
_key = get_secret("SUPABASE_KEY")
db = create_client(_url, _key)


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
    st.info("No alerts yet. Alerts appear when a watchlist stock changes signal or a price target is hit.")
    st.stop()

unread = [a for a in alerts if not a["read"]]
read   = [a for a in alerts if a["read"]]

col_count, col_clear = st.columns([3, 1])
with col_count:
    st.subheader(f"{len(unread)} unread alert{'s' if len(unread) != 1 else ''}")
with col_clear:
    if st.button("Clear All"):
        db.table("alerts").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
        st.success("All alerts cleared.")
        st.rerun()


def render_alert(alert: dict):
    alert_type = alert.get("alert_type", "signal")
    created = alert["created_at"][:16].replace("T", " ")

    col_msg, col_read = st.columns([5, 1])
    with col_msg:
        if alert_type == "price_target":
            st.markdown(
                f"{alert['message']}  \n"
                f"<span style='color:gray;font-size:0.85em'>{created} UTC</span>",
                unsafe_allow_html=True,
            )
        else:
            prev = alert.get("previous_signal", "")
            new  = alert.get("new_signal", "")
            prev_emoji = SIGNAL_EMOJI.get(prev, "")
            new_emoji  = SIGNAL_EMOJI.get(new, "")
            st.markdown(
                f"**{alert['ticker']}** — {prev_emoji} {prev} → {new_emoji} {new}  \n"
                f"<span style='color:gray;font-size:0.85em'>{created} UTC</span>",
                unsafe_allow_html=True,
            )
    with col_read:
        if not alert["read"] and st.button("✓ Read", key=f"read_{alert['id']}"):
            db.table("alerts").update({"read": True}).eq("id", alert["id"]).execute()
            st.rerun()


if unread:
    st.markdown("### New")
    for alert in unread:
        render_alert(alert)

if read:
    with st.expander(f"Show {len(read)} read alerts"):
        for alert in read:
            render_alert(alert)
