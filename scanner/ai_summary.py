import anthropic
from config import get_secret


def fetch_headlines(ticker: str) -> list[str]:
    """Fetch recent news headlines for a ticker via NewsAPI."""
    import requests
    api_key = get_secret("NEWSAPI_KEY")
    if not api_key:
        return []
    try:
        resp = requests.get(
            "https://newsapi.org/v2/everything",
            params={"q": ticker, "language": "en", "sortBy": "publishedAt", "pageSize": 5, "apiKey": api_key},
            timeout=5,
        )
        resp.raise_for_status()
        return [a["title"] for a in resp.json().get("articles", []) if a.get("title")][:5]
    except Exception:
        return []


def generate_ai_summary(
    ticker: str,
    company_name: str,
    signal: str,
    score: float,
    indicator_detail: dict,
    headlines: list[str],
) -> str:
    """Call Claude to generate a 2-3 sentence analyst summary."""
    api_key = get_secret("ANTHROPIC_API_KEY")
    if not api_key:
        return "AI summary unavailable — add ANTHROPIC_API_KEY to Streamlit secrets."

    bullish = [(n, v) for n, v in indicator_detail.items() if v.get("score", 0) >= 6]
    bearish = [(n, v) for n, v in indicator_detail.items() if v.get("score", 0) < 4]
    mixed = [(n, v) for n, v in indicator_detail.items() if 4 <= v.get("score", 0) < 6]

    def fmt(items):
        return "; ".join(f"{n} ({v['score']:.1f}/10): {v['reasoning']}" for n, v in items) or "none"

    news_block = "\n".join(f"- {h}" for h in headlines) if headlines else "No recent headlines available."

    prompt = f"""You are a concise stock analyst. Write a 2-3 sentence investment summary for {company_name} ({ticker}).

Current signal: {signal} | Score: {score:.1f}/100

Bullish indicators: {fmt(bullish)}
Bearish indicators: {fmt(bearish)}
Mixed indicators: {fmt(mixed)}

Recent news:
{news_block}

Write naturally, integrating the technical picture with any relevant news context. Cover short-term setup and longer-term potential. Be specific and direct. No disclaimers."""

    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=250,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text
    except Exception as e:
        return f"AI summary unavailable: {e}"
