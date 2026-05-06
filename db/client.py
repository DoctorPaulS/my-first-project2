from functools import lru_cache
from supabase import create_client, Client
from config import get_secret


@lru_cache(maxsize=1)
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
