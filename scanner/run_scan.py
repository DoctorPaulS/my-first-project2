"""
Entry point for the GitHub Actions scheduled scan.
Run with: python -m scanner.run_scan
"""
import sys
import logging
from datetime import datetime, timezone, date, timedelta
from scanner.universe import get_sp500_tickers
from scanner.data_fetcher import fetch_ohlcv_batch, fetch_earnings_date
from scanner.sentiment import get_sentiment
from scorer import compute_score, format_signal
from db.client import get_db
from config import EARNINGS_WARNING_DAYS, get_secret

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)


def run_scan() -> None:
    log.info("Starting S&P 500 scan...")
    tickers = get_sp500_tickers()
    log.info(f"Universe: {len(tickers)} tickers")

    log.info("Downloading price data (batch)...")
    ohlcv_map = fetch_ohlcv_batch(tickers)
    log.info(f"Got data for {len(ohlcv_map)} tickers")

    scan_time = datetime.now(timezone.utc).isoformat()
    db = get_db()

    # Fetch current watchlist to know which stocks need alert comparison
    watchlist_result = db.table("watchlist").select("ticker").execute()
    watchlist_tickers = {row["ticker"] for row in watchlist_result.data}

    # Get previous signals for watchlist stocks
    prev_signals: dict[str, str] = {}
    if watchlist_tickers:
        prev = (
            db.table("scan_results")
            .select("ticker, signal, scanned_at")
            .in_("ticker", list(watchlist_tickers))
            .order("scanned_at", desc=True)
            .limit(len(watchlist_tickers) * 5)
            .execute()
        )
        seen = set()
        for row in prev.data:
            if row["ticker"] not in seen:
                prev_signals[row["ticker"]] = row["signal"]
                seen.add(row["ticker"])

    rows_to_insert = []
    alerts_to_insert = []

    for ticker, ohlcv in ohlcv_map.items():
        try:
            result = compute_score(ohlcv)
            earnings_date = fetch_earnings_date(ticker)
            days_to_earnings = None
            earnings_warning = False

            if earnings_date:
                days_to_earnings = (earnings_date - date.today()).days
                earnings_warning = 0 <= days_to_earnings <= EARNINGS_WARNING_DAYS

            sentiment_flag, _ = get_sentiment(ticker) if ticker in watchlist_tickers else (False, [])

            rows_to_insert.append({
                "ticker": ticker,
                "scanned_at": scan_time,
                "score": result["score"],
                "signal": result["signal"],
                "reasoning": result["reasoning"],
                "indicator_detail": result["indicator_detail"],
                "earnings_warning": earnings_warning,
                "sentiment_flag": sentiment_flag,
            })

            # Generate alert if watchlist signal changed
            if ticker in watchlist_tickers and ticker in prev_signals:
                if prev_signals[ticker] != result["signal"]:
                    alerts_to_insert.append({
                        "ticker": ticker,
                        "previous_signal": prev_signals[ticker],
                        "new_signal": result["signal"],
                    })

        except Exception as e:
            log.warning(f"Failed to score {ticker}: {e}")
            continue

    # Batch insert scan results
    log.info(f"Writing {len(rows_to_insert)} scan results to Supabase...")
    batch_size = 100
    for i in range(0, len(rows_to_insert), batch_size):
        db.table("scan_results").insert(rows_to_insert[i : i + batch_size]).execute()

    if alerts_to_insert:
        log.info(f"Writing {len(alerts_to_insert)} alerts...")
        db.table("alerts").insert(alerts_to_insert).execute()

    log.info("Scan complete.")


if __name__ == "__main__":
    run_scan()
