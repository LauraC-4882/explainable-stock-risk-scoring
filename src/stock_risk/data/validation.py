"""Data contract for OHLCV history: schema + business invariants enforced at
the fetch boundary, so bad data fails loudly at the door instead of flowing
silently into CVaR/volatility/beta and poisoning the whole scorecard.

yfinance is an unofficial scrape of Yahoo Finance with no SLA — it can and
does return malformed rows. Before this module existed, the only check in
the pipeline was `df.empty` (see fetcher.py); physically impossible data
(high < low, zero/negative prices, negative volume) passed straight through
and produced +/-inf log returns with nothing louder than a numpy
divide-by-zero RuntimeWarning.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pandera.pandas as pa

# Must match DataPreprocessor.max_gap_days — this checks that raw fetched
# data doesn't have gaps too large for _fill_gaps's ffill(limit=...) to
# safely paper over. 8, not 5: measured live against real CN A-share data
# (600519.SS), Spring Festival / National Day closures create gaps up to 6
# missing trading days — longer than any single US holiday, which is what
# the original max_gap_days=5 (from before this app supported HK/CN
# tickers) was calibrated against. Both constants moved together so
# validation's tolerance and the preprocessor's actual fill capability keep
# telling the same story.
MAX_GAP_TRADING_DAYS = 8


class DataValidationError(ValueError):
    """Raised when fetched OHLCV data violates the data contract.

    Subclasses ValueError so it flows through the same
    `except ValueError -> 404` handling every other "no valid data for this
    ticker" case already uses (see api/app.py's _score_ticker) — a data
    contract violation is a data problem, not a server bug.
    """


OHLCV_SCHEMA = pa.DataFrameSchema(
    columns={
        "open": pa.Column(float, checks=pa.Check.gt(0), nullable=False),
        "high": pa.Column(float, checks=pa.Check.gt(0), nullable=False),
        "low": pa.Column(float, checks=pa.Check.gt(0), nullable=False),
        "close": pa.Column(float, checks=pa.Check.gt(0), nullable=False),
        "volume": pa.Column(float, checks=pa.Check.ge(0), nullable=False),
    },
    strict=False,  # extra columns (e.g. dividends) are fine; only the named ones are enforced
    # yfinance returns volume as int64, not float64 — coerce rather than
    # reject, since this schema's job is catching bad *values*, not
    # policing a dtype that carries no information either way.
    coerce=True,
)
# high >= low is checked separately (not as a DataFrameSchema-level Check)
# because pandera attributes a whole-dataframe check's failures to every
# column's value on the failing rows, not just the columns the check
# actually reasons about — its failure report would otherwise falsely
# implicate "open" for a check that never touches "open" at all.


def _max_missing_trading_days(index: pd.DatetimeIndex) -> int:
    """Largest number of business days strictly between any two consecutive
    rows in *index* (0 for back-to-back trading days, 5 for a week-plus gap
    that still exactly fits ffill(limit=5), etc.)."""
    if len(index) < 2:
        return 0
    dates = index.normalize().values.astype("datetime64[D]")
    advanced = np.busday_count(dates[:-1], dates[1:])
    return int((advanced - 1).max())


def validate_ohlcv(df: pd.DataFrame, ticker: str) -> pd.DataFrame:
    """Validate *df* (as returned by MarketDataFetcher.fetch_history, before
    any preprocessing) against the OHLCV data contract. Returns *df*
    unchanged on success; raises DataValidationError with the ticker,
    violating column(s), and example row(s) on failure.
    """
    if not df.index.is_monotonic_increasing:
        raise DataValidationError(
            f"{ticker}: date index is not strictly increasing "
            f"(first out-of-order position: {_first_non_monotonic(df.index)})"
        )
    if df.index.has_duplicates:
        dupes = df.index[df.index.duplicated()].unique()
        raise DataValidationError(f"{ticker}: duplicate dates in index: {list(dupes[:5])}")

    max_gap = _max_missing_trading_days(df.index)
    if max_gap > MAX_GAP_TRADING_DAYS:
        raise DataValidationError(
            f"{ticker}: largest gap between consecutive rows is {max_gap} trading "
            f"days, exceeds MAX_GAP_TRADING_DAYS={MAX_GAP_TRADING_DAYS}"
        )

    # A still-open trading session ("today," before the market closes)
    # legitimately comes back from yfinance as a partial bar with NaN OHLC —
    # not bad data, just incomplete data that DataPreprocessor.process()
    # already drops via dropna() once returns are computed. Excluded from
    # the strict schema check below (only when it's the *last* row) so that
    # normal case doesn't fail every live fetch; NaN anywhere else in the
    # history is still a real problem and still rejected.
    to_check = df
    if len(df) > 0 and df.iloc[-1][["open", "high", "low", "close"]].isna().any():
        to_check = df.iloc[:-1]

    bad_hl = to_check.index[to_check["high"] < to_check["low"]]
    if len(bad_hl) > 0:
        sample = to_check.loc[bad_hl[:5], ["high", "low"]]
        raise DataValidationError(
            f"{ticker}: high < low on {len(bad_hl)} row(s); columns=['high', 'low']; "
            f"example rows:\n{sample}"
        )

    try:
        OHLCV_SCHEMA.validate(to_check, lazy=True)
    except pa.errors.SchemaErrors as exc:
        failures = exc.failure_cases
        violating_columns = sorted(failures["column"].dropna().unique().tolist())
        sample = failures.head(5).to_dict(orient="records")
        raise DataValidationError(
            f"{ticker}: OHLCV schema violation in column(s) {violating_columns}; "
            f"example failures: {sample}"
        ) from exc

    return df


def _first_non_monotonic(index: pd.DatetimeIndex) -> str:
    for i in range(1, len(index)):
        if index[i] <= index[i - 1]:
            return f"row {i} ({index[i]} <= {index[i - 1]})"
    return "unknown"
