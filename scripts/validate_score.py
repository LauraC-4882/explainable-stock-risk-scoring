"""Validate the composite risk score's predictive power.

Two industry-standard checks, run against real multi-year, multi-sector
history:

1. Quintile backtest — bucket every (ticker, date) observation by that
   day's composite score, and check whether the subsequent 20-trading-day
   realized max drawdown and realized volatility are monotonically worse
   for higher-scored quintiles. Monotonicity itself is the evidence of
   predictive power (or its absence).
2. Kupiec POF (proportion of failures) test on var_95_21d — it claims "5%
   of days breach this line," so count actual breaches and run a
   likelihood-ratio test on whether the observed breach rate is
   statistically consistent with 5%.

No-lookahead by construction: composite_score(df.iloc[:i+1]) is called at
every step, so _historical_percentile only ever sees data up to and
including the day being scored — the exact same function production uses,
just called on a truncated frame instead of the full one. See
test_validate_score_no_lookahead in tests/test_data.py for the equivalence
check this relies on: scoring day t from a truncated frame must produce
the same score as scoring it from the full frame passed to composite_score
with `latest=` pointing at day t (production never does this, so this is a
belt-and-suspenders proof, not just an assumption).
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from loguru import logger
from scipy import stats

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from stock_risk.data.fetcher import MarketDataFetcher  # noqa: E402
from stock_risk.data.preprocessor import DataPreprocessor  # noqa: E402
from stock_risk.features.risk_metrics import RiskMetrics  # noqa: E402
from stock_risk.scoring.risk_categories import composite_score  # noqa: E402

# Cross-sector universe: tech, consumer discretionary/staples, healthcare,
# financials, energy, industrials, communication, utilities, materials,
# real estate, plus a few high-volatility names for score-range coverage.
DEFAULT_TICKERS = [
    "AAPL", "MSFT", "GOOGL", "NVDA", "META", "ORCL", "CSCO", "INTC", "AMD",
    "AMZN", "TSLA", "HD", "MCD",
    "JNJ", "UNH", "PFE",
    "JPM", "BAC", "GS",
    "XOM", "CVX",
    "BA", "CAT", "GE",
    "KO", "PG", "WMT",
    "DIS", "NFLX",
    "NEE", "DUK",
    "LIN", "AMT",
    "GME", "COIN", "PLTR",
]

MIN_HISTORY = 252  # ~1y warm-up before rolling metrics/percentiles are meaningful
HORIZON = 20  # trading days for forward-looking outcome measurement
N_QUANTILES = 5


def _expanding_outlier_filter(df: pd.DataFrame) -> pd.DataFrame:
    """A point-in-time-safe stand-in for DataPreprocessor._remove_price_outliers,
    for backtesting only.

    Production's version (whole-series mean/std) is correct for how it's
    actually called — a fresh fetch_history(period="2y") always ends
    "today," so "whole series" never includes anything beyond the present.
    This backtest reuses ONE precomputed multi-year frame and slices it at
    each historical date, which breaks that assumption: a mid-window day's
    outlier classification would be computed from a mean/std that includes
    every day up to the *end* of the whole fetch, including years after
    that historical date — real lookahead, caught by
    test_composite_score_has_no_lookahead. Using each row's *expanding*
    (as-of-that-row) mean/std instead reproduces what a fresh, date-limited
    fetch would have computed on that day, without paying for re-running
    the full preprocessing pipeline at every step (RiskMetrics is already
    pure rolling/ewm/cummax — trailing by construction — so it's safe to
    compute once on the cleaned series and slice afterward; only the
    outlier filter needed this fix).
    """
    df = df.copy()
    log_ret = np.log(df["close"] / df["close"].shift(1))
    expanding_mean = log_ret.expanding(min_periods=30).mean()
    expanding_std = log_ret.expanding(min_periods=30).std()
    spike = (log_ret - expanding_mean).abs() > 6 * expanding_std

    next_day_ret = log_ret.shift(-1)
    fat_finger = pd.Series(False, index=df.index)
    for date in df.index[spike.fillna(False)]:
        r_this, r_next = log_ret.loc[date], next_day_ret.loc[date]
        if pd.isna(r_this) or pd.isna(r_next) or r_this == 0:
            continue
        if np.sign(r_this) == np.sign(r_next):
            continue
        if -r_next / r_this > 0.5:
            fat_finger.loc[date] = True

    if fat_finger.any():
        logger.warning(f"Removed {int(fat_finger.sum())} fat-finger row(s) (point-in-time filter)")
        df = df[~fat_finger]
    return df


def build_features(ticker: str, period: str) -> pd.DataFrame | None:
    try:
        raw = MarketDataFetcher().fetch_history(ticker, period=period)
        df = raw.copy()
        df.index = df.index.normalize()
        # same gap-fill as DataPreprocessor._fill_gaps — mechanical, no leak risk
        df = df.asfreq("B").ffill(limit=DataPreprocessor().max_gap_days)
        df = _expanding_outlier_filter(df)
        df["log_return"] = np.log(df["close"] / df["close"].shift(1))
        df["pct_return"] = df["close"].pct_change()
        df = df.dropna(subset=["close", "log_return"])
        df = RiskMetrics().compute(df)  # purely rolling/ewm/cummax — safe to compute once and slice
        return df
    except Exception as exc:
        logger.warning(f"Skipping {ticker}: {exc}")
        return None


def backtest_ticker(ticker: str, df: pd.DataFrame) -> list[dict]:
    """Score every trading day from MIN_HISTORY onward using only data up
    to and including that day (composite_score(df.iloc[:i+1])), then
    measure what actually happened over the following HORIZON days."""
    records = []
    n = len(df)
    for i in range(MIN_HISTORY, n):
        window = df.iloc[: i + 1]  # <= day i only — no lookahead
        result = composite_score(window)
        score = result["composite_score"]

        fwd_max_dd = None
        fwd_vol = None
        if i + HORIZON < n:
            fwd_close = df["close"].iloc[i : i + HORIZON + 1]
            fwd_cum_ret = np.log(fwd_close / fwd_close.iloc[0])
            fwd_max_dd = float(fwd_cum_ret.min())  # most negative cumulative return
            fwd_rets = df["log_return"].iloc[i + 1 : i + HORIZON + 1]
            fwd_vol = float(fwd_rets.std() * np.sqrt(252)) if len(fwd_rets) > 1 else None

        var_95 = df["var_95_21d"].iloc[i] if "var_95_21d" in df.columns else None
        next_ret = df["log_return"].iloc[i + 1] if i + 1 < n else None
        breach = (
            bool(next_ret < var_95)
            if pd.notna(var_95) and next_ret is not None and pd.notna(next_ret)
            else None
        )

        records.append({
            "ticker": ticker,
            "date": df.index[i],
            "score": score,
            "fwd_max_dd": fwd_max_dd,
            "fwd_realized_vol": fwd_vol,
            "var_95_21d": var_95,
            "next_return": next_ret,
            "breach": breach,
        })
    return records


def quintile_table(obs: pd.DataFrame) -> pd.DataFrame:
    scored = obs.dropna(subset=["fwd_max_dd", "fwd_realized_vol"]).copy()
    scored["quintile"] = pd.qcut(scored["score"], N_QUANTILES, labels=False, duplicates="drop")
    table = scored.groupby("quintile").agg(
        n=("score", "size"),
        mean_score=("score", "mean"),
        mean_fwd_max_drawdown=("fwd_max_dd", "mean"),
        mean_fwd_realized_vol=("fwd_realized_vol", "mean"),
    )
    table.index = [f"Q{int(i) + 1}" for i in table.index]
    return table


def kupiec_pof_test(obs: pd.DataFrame, target_rate: float = 0.05) -> dict:
    breaches = obs["breach"].dropna()
    n = len(breaches)
    x = int(breaches.sum())
    if n == 0:
        return {"n": 0, "breaches": 0, "breach_rate": None, "lr_stat": None, "p_value": None}

    observed_rate = x / n
    p = target_rate
    # Kupiec (1995) proportion-of-failures likelihood ratio test.
    # Guard the degenerate x=0 / x=n cases (log(0) undefined) by clamping
    # the observed rate away from the boundary — standard practice for this
    # test, doesn't change the conclusion, just avoids a NaN LR statistic.
    p_hat = min(max(observed_rate, 1e-6), 1 - 1e-6)
    log_l_null = (n - x) * np.log(1 - p) + x * np.log(p)
    log_l_alt = (n - x) * np.log(1 - p_hat) + x * np.log(p_hat)
    lr_stat = -2 * (log_l_null - log_l_alt)
    p_value = float(1 - stats.chi2.cdf(lr_stat, df=1))

    return {
        "n": n,
        "breaches": x,
        "breach_rate": observed_rate,
        "target_rate": target_rate,
        "lr_stat": float(lr_stat),
        "p_value": p_value,
        "reject_at_5pct": p_value < 0.05,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the composite score's predictive power")
    parser.add_argument("--tickers", nargs="+", default=DEFAULT_TICKERS)
    parser.add_argument("--period", default="5y")
    args = parser.parse_args()

    start = time.time()
    all_records = []
    for ticker in args.tickers:
        df = build_features(ticker, args.period)
        if df is None or len(df) <= MIN_HISTORY:
            logger.warning(f"Skipping {ticker}: insufficient history")
            continue
        records = backtest_ticker(ticker, df)
        all_records.extend(records)
        logger.info(f"{ticker}: {len(records)} scored days")

    obs = pd.DataFrame(all_records)
    print(
        f"\nTotal (ticker, date) observations: {len(obs)} across "
        f"{obs['ticker'].nunique()} tickers"
    )
    print(f"Backtest wall time: {time.time() - start:.1f}s\n")

    print("=" * 70)
    print("QUINTILE BACKTEST — score vs. subsequent 20-trading-day outcomes")
    print("=" * 70)
    table = quintile_table(obs)
    print(table.to_string(float_format=lambda x: f"{x:.4f}"))
    dd_monotonic = table["mean_fwd_max_drawdown"].is_monotonic_decreasing
    vol_monotonic = table["mean_fwd_realized_vol"].is_monotonic_increasing
    print(f"\nDrawdown monotonically worse (more negative) with higher quintile: {dd_monotonic}")
    print(f"Realized vol monotonically higher with higher score quintile: {vol_monotonic}")

    print("\n" + "=" * 70)
    print("KUPIEC POF TEST — var_95_21d breach rate vs. claimed 5%")
    print("=" * 70)
    kupiec = kupiec_pof_test(obs)
    for k, v in kupiec.items():
        print(f"{k}: {v}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
