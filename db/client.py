from supabase import create_client, Client
from config import get_secret


def get_db() -> Client:
    url = get_secret("SUPABASE_URL")
    key = get_secret("SUPABASE_KEY")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set.")
    return create_client(url, key)


def get_settings(key: str, default: dict) -> dict:
    """Load a settings row from Supabase, falling back to default."""
    try:
        db = get_db()
        result = db.table("settings").select("value").eq("key", key).single().execute()
        return result.data["value"]
    except Exception:
        return default


def save_settings(key: str, value: dict) -> None:
    db = get_db()
    db.table("settings").upsert({"key": key, "value": value}).execute()


def get_latest_signals(db, fields: str = "ticker,score,signal") -> dict:
    """Return {ticker: row} for the most recent scan batch."""
    try:
        latest = (
            db.table("scan_results")
            .select("scanned_at")
            .order("scanned_at", desc=True)
            .limit(1)
            .execute()
        )
        if not latest.data:
            return {}
        scan_time = latest.data[0]["scanned_at"]
        rows = (
            db.table("scan_results")
            .select(fields)
            .eq("scanned_at", scan_time)
            .execute()
        )
        return {r["ticker"]: r for r in rows.data}
    except Exception:
        return {}
