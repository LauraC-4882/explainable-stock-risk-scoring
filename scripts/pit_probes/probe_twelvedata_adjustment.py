"""PIT probe — Twelve Data's default price-adjustment semantics (audit row A2).

NOT run by CI or the test suite; run manually, once, on a machine with a real
TWELVE_DATA_KEY in .env and an unthrottled connection.

Needs      : TWELVE_DATA_KEY (free tier is enough — 2 requests).
Question   : with no adjustment parameter (exactly what production sends,
             fetcher.py `_fetch_us_twelvedata`), are the returned closes
             split-adjusted only, or split+dividend-adjusted like yfinance's
             auto_adjust=True?
Method     : fetch a dividend-paying, recently-split-free ticker (default KO)
             over a window containing a known ex-dividend date from both
             Twelve Data (production parameters) and yfinance
             (auto_adjust=True and =False), align on date, and compare the
             day-before-ex-date close.
Reads as   : TD close == yfinance auto_adjust=True close (±0.01)
                 -> TD default includes dividends: sources consistent,
                    audit row A2 resolves to clean.
             TD close == yfinance auto_adjust=False close (splits aside)
                 -> TD default excludes dividends: keyed and keyless US
                    deployments compute DIFFERENT returns across ex-dates;
                    A2 escalates to confirmed-leak (cross-source).
Backfill   : docs_internal/POINT_IN_TIME_AUDIT.md, section A2, first bullet;
             then retire this script or convert the finding into a pinned
             mock test with the observed payload.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

TICKER = "KO"


def main() -> int:
    import requests
    import yfinance as yf

    from stock_risk.config import settings

    if not settings.twelve_data_key:
        print("TWELVE_DATA_KEY is not set — this probe needs it.", file=sys.stderr)
        return 2

    td = requests.get(
        "https://api.twelvedata.com/time_series",
        params={
            "symbol": TICKER,
            "interval": "1day",
            "outputsize": 90,
            "apikey": settings.twelve_data_key,
        },
        timeout=30,
    ).json()
    if td.get("status") == "error":
        print(f"Twelve Data error: {td.get('message')}", file=sys.stderr)
        return 2

    adj = yf.Ticker(TICKER).history(period="6mo", auto_adjust=True)
    raw = yf.Ticker(TICKER).history(period="6mo", auto_adjust=False)

    print(f"{'date':12s} {'TD(default)':>12s} {'yf adj=True':>12s} {'yf adj=False':>12s}")
    td_by_date = {v["datetime"]: float(v["close"]) for v in td["values"]}
    hits = 0
    for ts, row in adj.iterrows():
        key = ts.strftime("%Y-%m-%d")
        if key in td_by_date and hits < 15:
            print(f"{key:12s} {td_by_date[key]:12.4f} {row['Close']:12.4f} "
                  f"{raw.loc[ts, 'Close']:12.4f}")
            hits += 1
    print("\nCompare the columns across an ex-dividend date: whichever yfinance")
    print("column TD tracks is TD's default adjustment. Record the verdict in")
    print("audit row A2.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
