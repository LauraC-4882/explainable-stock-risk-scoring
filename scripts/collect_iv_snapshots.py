"""[G4] Daily IV snapshot collector — the phase-2 foundation.

yfinance only serves the CURRENT options chain; there is no historical IV
series, which is exactly why stock-level IV rank (and any rigorous backtest
of put_skew / IV-HV) is locked today. This script appends one JSONL line per
ticker per run ({date, ticker, atm_iv, put_skew, expiry}) to
data/iv_snapshots.jsonl; after ~252 trading days of collection, IV rank
unlocks by feeding the accumulated series through the exact same percentile
machinery the composite score already uses
(risk_categories._historical_percentile). This script only collects — rank
computation is deliberately out of scope until the data exists.

Run it daily (task scheduler / cron / alongside scripts/monitor.py):

    python scripts/collect_iv_snapshots.py --tickers AAPL MSFT TSLA NVDA SPY
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from loguru import logger  # noqa: E402

from stock_risk.data.fetcher import MarketDataFetcher  # noqa: E402

ROOT = Path(__file__).parent.parent
OUT_PATH = ROOT / "data" / "iv_snapshots.jsonl"
DEFAULT_TICKERS = ["AAPL", "MSFT", "TSLA", "NVDA", "SPY"]


def main() -> int:
    parser = argparse.ArgumentParser(description="[G4] daily IV snapshot collector")
    parser.add_argument("--tickers", nargs="+", default=DEFAULT_TICKERS)
    args = parser.parse_args()

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    fetcher = MarketDataFetcher()
    today = date.today().isoformat()
    written = 0
    with OUT_PATH.open("a", encoding="utf-8") as f:
        for ticker in args.tickers:
            sig = fetcher.fetch_options_signals(ticker)
            row = {
                "date": today,
                "ticker": ticker.upper(),
                "atm_iv": sig["atm_iv"],
                "put_skew": sig["put_skew"],
                "expiry": sig["expiry"],
            }
            f.write(json.dumps(row) + "\n")
            written += 1
            status = "ok" if sig["atm_iv"] is not None else "no-chain/throttled (nulls recorded)"
            logger.info(f"{ticker}: {status}")
    print(f"appended {written} rows to {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
