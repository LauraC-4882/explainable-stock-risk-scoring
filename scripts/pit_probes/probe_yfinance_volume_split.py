"""PIT probe — is yfinance volume split-adjusted in step with prices? (row A2)

NOT run by CI or the test suite; run manually on a machine with an
unthrottled connection (no key needed — yfinance only).

Needs      : network access to Yahoo (chronically throttled on some IPs; see
             README "Deployment" — run from a residential connection).
Question   : `auto_adjust=True` adjusts PRICES for splits and dividends. Is
             the volume column adjusted for splits too, or raw shares? If
             raw, `volume_ratio` and `volume_vol_21d` show a fake ~N-fold
             jump across every split, and that jump is rewritten history
             (the split is known only from its date onward).
Method     : fetch a ticker across a known recent split (default NVDA,
             10-for-1 on 2024-06-10) with auto_adjust True and False;
             compare volume columns to each other and across the split date.
Reads as   : volume identical under both flags AND continuous (~same scale)
             across the split -> volume is provider-split-adjusted:
             volume-family features are ratio-safe; A2's volume bullet
             resolves to clean.
             volume steps ~10x at the split -> raw shares: volume features
             carry a split artefact AND a backward-adjustment interaction;
             escalate in audit row A2 and consider excluding the window
             around split dates from volume features.
Backfill   : docs_internal/POINT_IN_TIME_AUDIT.md, section A2, second
             bullet; then retire this script or pin the observed payload as
             a mock test.
"""

from __future__ import annotations

import sys

TICKER = "NVDA"
SPLIT_DATE = "2024-06-10"


def main() -> int:
    import yfinance as yf

    adj = yf.Ticker(TICKER).history(start="2024-05-27", end="2024-06-21", auto_adjust=True)
    raw = yf.Ticker(TICKER).history(start="2024-05-27", end="2024-06-21", auto_adjust=False)
    if adj.empty or raw.empty:
        print("empty response — throttled? try another connection", file=sys.stderr)
        return 2

    print(f"{TICKER} around the {SPLIT_DATE} split")
    print(f"{'date':12s} {'vol adj=True':>14s} {'vol adj=False':>14s} {'close adj=T':>12s}")
    for ts, row in adj.iterrows():
        print(f"{ts.strftime('%Y-%m-%d'):12s} {row['Volume']:14,.0f} "
              f"{raw.loc[ts, 'Volume']:14,.0f} {row['Close']:12.2f}")
    print("\nIf the volume column is continuous across the split under both")
    print("flags, it is split-adjusted; a ~10x step means raw shares. Record")
    print("the verdict in audit row A2.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
