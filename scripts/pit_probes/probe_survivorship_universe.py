"""PIT probe — quantify survivorship bias in the training universe (row G2).

NOT run by CI or the test suite; requires data this repository does not have.

Needs      : a delisting-inclusive constituent history — any one of:
             (a) a point-in-time index-membership file (e.g. S&P 500
                 constituents with add/remove dates, several public research
                 copies exist), (b) a paid PIT database (Sharadar/Norgate),
             or (c) a hand-built list of delistings 2021-2026 for the
             sectors in scripts/tickers_universe.txt. Save as CSV:
             ticker,added,removed (removed empty if still listed).
Question   : what fraction of a point-in-time 2021 universe drawn the same
             way (large caps per sector) is missing from today's
             tickers_universe.txt, and what were those names' forward
             20-day drawdown tails before delisting?
Method     : load the CSV; reconstruct the 2021-01-01 universe; report
             (1) survival rate into the current file, (2) mean/95p forward
             20-day max drawdown of survivors vs non-survivors over their
             final listed year (needs their price history from any source —
             delisted-price coverage is the hard part and the reason this
             cannot run offline).
Reads as   : survival near 100% and similar tails -> G2 downgrades to a
             registered caveat. Survival materially below 100% with fatter
             non-survivor tails (the expected direction) -> G2's "overstates
             stability, understates tails" gets its magnitude; the walk-
             forward AUC and quintile-monotonicity claims should then carry
             the caveat explicitly wherever published.
Backfill   : docs_internal/POINT_IN_TIME_AUDIT.md, section G2 (replace
             "needs-empirical-check" with the measured rate and tail gap).
"""

from __future__ import annotations

import sys
from pathlib import Path

UNIVERSE = Path(__file__).resolve().parents[1] / "tickers_universe.txt"


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        print("usage: probe_survivorship_universe.py <constituents.csv>", file=sys.stderr)
        return 2

    import pandas as pd

    members = pd.read_csv(sys.argv[1], parse_dates=["added", "removed"])
    current = {
        line.split("#", 1)[0].strip().upper()
        for line in UNIVERSE.read_text(encoding="utf-8").splitlines()
        if line.split("#", 1)[0].strip()
    }

    asof = pd.Timestamp("2021-01-01")
    then = members[(members["added"] <= asof)
                   & (members["removed"].isna() | (members["removed"] > asof))]
    survived = then["ticker"].str.upper().isin(current)
    print(f"2021-01-01 universe: {len(then)} names; "
          f"{survived.sum()} ({survived.mean():.1%}) present in tickers_universe.txt today")
    gone = then.loc[~survived, "ticker"].tolist()
    print(f"non-survivors ({len(gone)}): {', '.join(gone[:30])}{' …' if len(gone) > 30 else ''}")
    print("\nNext (needs delisted price history): compare forward 20-day max-")
    print("drawdown tails of survivors vs non-survivors over their final listed")
    print("year, and backfill audit row G2 with both numbers.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
