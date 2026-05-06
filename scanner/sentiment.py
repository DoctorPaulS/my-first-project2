import requests
from config import get_secret

NEWSAPI_URL = "https://newsapi.org/v2/everything"

NEGATIVE_WORDS = {
    "downgrade", "miss", "loss", "lawsuit", "investigation",
    "recall", "fraud", "decline", "cut", "below", "warning",
    "layoff", "disappoints", "slumps", "plunges",
}
POSITIVE_WORDS = {
    "upgrade", "beat", "record", "growth", "raise", "strong",
    "above", "buy", "profit", "surge", "outperform", "tops",
    "exceeds", "boosts",
}


def get_sentiment(ticker: str) -> tuple[bool, list[str]]:
    """
    Fetch recent headlines for a ticker and return (is_negative, headlines).

    Returns (False, []) if the API key is not set or the request fails.
    """
    api_key = get_secret("NEWSAPI_KEY")
    if not api_key:
        return False, []

    params = {
        "q": ticker,
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": 5,
        "apiKey": api_key,
    }
    try:
        resp = requests.get(NEWSAPI_URL, params=params, timeout=5)
        resp.raise_for_status()
        articles = resp.json().get("articles", [])
        headlines = [a["title"] for a in articles if a.get("title")]

        neg_count = sum(
            1 for h in headlines for w in NEGATIVE_WORDS if w in h.lower()
        )
        pos_count = sum(
            1 for h in headlines for w in POSITIVE_WORDS if w in h.lower()
        )

        is_negative = neg_count > pos_count
        return is_negative, headlines[:3]
    except Exception:
        return False, []
