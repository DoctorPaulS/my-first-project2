import pandas as pd
from config import SP500_WIKIPEDIA_URL


def get_sp500_tickers() -> list[str]:
    tables = pd.read_html(
        SP500_WIKIPEDIA_URL,
        storage_options={"User-Agent": "Mozilla/5.0 (compatible; stock-advisor-bot/1.0)"},
    )
    df = tables[0]
    tickers = df["Symbol"].tolist()
    return [t.replace(".", "-") for t in tickers]
