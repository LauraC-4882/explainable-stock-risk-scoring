"""Is this history good enough to *score*, as opposed to merely well-formed?

`validation.py` enforces the OHLCV data contract — the rows are physically
possible and the index is sane. This module asks the next question, which is a
scoring-policy question rather than a data-contract one: given that the frame
is valid, can the pipeline produce a number a user should be shown?

Two ways it can't, each with its own `ScoreErrorCode` so the user is told
which one happened instead of a blanket "Internal scoring error":

* **Too few sessions.** The composite ranks today's metrics inside this
  stock's own history, so with a short history every percentile collapses
  toward the neutral 50 — a confident-looking number carrying almost no
  information. Refusing is more honest than returning it.
* **History that stops long before today.** A suspended or delisted name
  still has a perfectly valid parquet behind it; scoring it would present
  months-old risk as current.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd

from ..errors import DelistedError, InsufficientDataError

# 60 trading days ~= a quarter. Above risk_categories._MIN_HISTORY (20, the
# floor below which a single percentile is untrustworthy) because the
# composite stacks *several* such percentiles plus a 63-day rolling beta and a
# 63-day max-drawdown window: 20 rows clears the per-metric floor while still
# leaving the headline number dominated by warm-up. Matches the 60-observation
# floor /api/score/{ticker}/backtest already applies for the same reason.
MIN_TRADING_DAYS = 60

# A US or CN listing that has not printed a bar in 30 calendar days is not
# "quiet" — it is halted, suspended or gone. Generous enough to absorb the
# longest exchange closure this app sees (CN Spring Festival, ~9 days) plus a
# stale weekend on either side.
STALE_AFTER_DAYS = 30

# Set by MarketDataFetcher.fetch_history on every frame it returns, so this
# module can tell "the market really has not traded this in months" from "we
# are serving a snapshot because upstream is throttling us".
SOURCE_ATTR = "stock_risk_source"


def check_history_scorable(df: pd.DataFrame, ticker: str, *, now: datetime | None = None) -> None:
    """Raise if *df* cannot support an honest score. Returns None otherwise.

    Raises:
        InsufficientDataError: fewer than MIN_TRADING_DAYS rows.
        DelistedError: the newest row is older than STALE_AFTER_DAYS, and the
            frame is known to have come from a live fetch.
    """
    rows = len(df)
    if rows < MIN_TRADING_DAYS:
        raise InsufficientDataError(
            f"{ticker}: only {rows} trading day(s) of history available, "
            f"need at least {MIN_TRADING_DAYS} to rank against",
            ticker=ticker,
        )

    # Staleness is only the *stock's* fault when we know we just fetched it
    # live. A snapshot is stale because upstream throttled us (see fetcher.py's
    # [IP-block resilience] fallback) — blaming the ticker for our own fallback
    # would slap "may be delisted" on healthy names during every outage. A
    # frame with no provenance stamp did not come from MarketDataFetcher at all
    # (a fixture, a test double, a hand-built frame); assuming "live" there
    # would make every synthetic frame look delisted, so it is skipped too.
    if df.attrs.get(SOURCE_ATTR) != "live":
        return

    if rows == 0 or not isinstance(df.index, pd.DatetimeIndex):
        return

    last_session = df.index[-1]
    reference = now or datetime.now(timezone.utc)
    # The fetcher normalises every source to a tz-naive UTC index; compare on
    # the same footing rather than letting pandas raise on naive-vs-aware.
    if reference.tzinfo is not None:
        reference = reference.replace(tzinfo=None)

    age = reference - last_session.to_pydatetime()
    if age > timedelta(days=STALE_AFTER_DAYS):
        raise DelistedError(
            f"{ticker}: newest session is {last_session.date()} "
            f"({age.days} days ago) — the listing appears suspended or delisted",
            ticker=ticker,
        )
