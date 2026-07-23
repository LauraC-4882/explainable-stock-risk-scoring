"""Refresh the tracked snapshots/ OHLCV fallback data for the demo universe.

Run daily by .github/workflows/refresh-snapshot.yml (and runnable locally any
time a Yahoo window is open). Rate-limit tolerant by design: fetch whatever
Yahoo allows this run, keep existing snapshots for the rest, always exit 0 —
a partial refresh is strictly better than none, and a red cron for an
external throttle helps no one (the workflow prints a warning instead).

The universe is the UI's quick-pick chips (both markets) plus each market's
benchmark — exactly the tickers a demo visitor is most likely to hit cold.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from loguru import logger  # noqa: E402

from stock_risk.data.fetcher import MarketDataFetcher  # noqa: E402

# Keep in sync with ui/web/src/components/EmptyState.jsx POPULAR + benchmarks.
UNIVERSE = [
    "AAPL", "TSLA", "MSFT", "GOOGL", "NVDA", "AMZN", "META", "JPM",  # US chips
    "600519.SS", "000001.SZ", "601318.SS",  # CN A-share chips
    "SPY", "510300.SS",  # benchmarks (scorer.MARKET_BENCHMARKS)
]
PERIOD = "2y"  # matches RiskScorer.score()'s default fetch


def main() -> int:
    fetcher = MarketDataFetcher()
    ok, failed = [], []
    for ticker in UNIVERSE:
        try:
            df = fetcher.fetch_history(ticker, period=PERIOD)  # auto-persists snapshot
            ok.append(ticker)
            logger.info(f"{ticker}: {len(df)} rows through {df.index[-1].date()}")
        except Exception as exc:
            failed.append(ticker)
            logger.warning(f"{ticker}: {str(exc)[:80]}")

    print(f"refreshed {len(ok)}/{len(UNIVERSE)} snapshots; failed: {failed or 'none'}")
    if not ok:
        # GitHub Actions warning annotation — visible without failing the cron.
        print("::warning title=snapshot refresh::0 tickers refreshed (Yahoo throttled the runner)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
