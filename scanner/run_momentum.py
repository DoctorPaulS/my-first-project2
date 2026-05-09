"""
Weekly momentum scan entry point.
Run with: python -m scanner.run_momentum
"""
import sys
import logging
from datetime import datetime, timezone
from scanner.universe import get_universe_tickers
from scanner.data_fetcher import fetch_ohlcv_batch
from scanner.momentum import score_momentum, build_momentum_summary
from db.client import get_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

MIN_SCORE      = 30   # only store stocks with meaningful momentum
TOP_N          = 100  # keep the top N results


def run_momentum_scan() -> None:
    log.info("Starting weekly momentum scan...")
    tickers = get_universe_tickers()
    log.info(f"Universe: {len(tickers)} tickers")

    log.info("Downloading price data...")
    ohlcv_map = fetch_ohlcv_batch(tickers, period="1y")
    log.info(f"Got data for {len(ohlcv_map)} tickers")

    scan_time = datetime.now(timezone.utc).isoformat()
    results = []

    for ticker, ohlcv in ohlcv_map.items():
        try:
            result = score_momentum(ohlcv)
            if result is None or result["momentum_score"] < MIN_SCORE:
                continue
            results.append({
                "ticker":           ticker,
                "scanned_at":       scan_time,
                "current_price":    result["current_price"],
                "volume_surge":     result["volume_surge"],
                "price_change_5d":  result["price_change_5d"],
                "price_change_20d": result["price_change_20d"],
                "pct_from_high":    result["pct_from_high"],
                "momentum_score":   result["momentum_score"],
                "summary":          build_momentum_summary(result),
            })
        except Exception as e:
            log.warning(f"Failed {ticker}: {e}")

    results.sort(key=lambda r: r["momentum_score"], reverse=True)
    results = results[:TOP_N]

    log.info(f"Found {len(results)} momentum candidates — writing to Supabase...")
    db = get_db()
    batch_size = 50
    for i in range(0, len(results), batch_size):
        db.table("momentum_results").insert(results[i:i + batch_size]).execute()

    log.info("Momentum scan complete.")


if __name__ == "__main__":
    run_momentum_scan()
