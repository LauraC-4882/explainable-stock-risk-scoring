"""[G6] Directional hit-rate screen for every feature column, split by regime.

For each numeric feature column, form a crude binary prediction ("is the
indicator above its own median?") and score it against tomorrow's direction
("was the next day's return positive?"). Report the hit rate over the full
sample and over a post-cutoff sub-sample (default: post-COVID, 2020-03-01), so
an indicator that only worked before a structural break is visible as such.

How this differs from `factor_screen.py`, which is *not* redundant with it:

  - factor_screen measures **cross-sectional rank correlation** (Spearman IC)
    against a **continuous 20-day forward drawdown**, pooled across a universe,
    with Benjamini-Hochberg FDR control. It answers "does this factor rank
    stocks by forward risk?"
  - this script measures a **time-series hit rate** against **next-day
    direction** for a single ticker. It answers "does this indicator call
    tomorrow, on this name, in this regime?"

Two honest-accounting details this implementation adds over the naive version:

  1. **The median is the leak.** Splitting on the full-sample median tells every
     row where it sits relative to a statistic computed from the whole history,
     future included. Both columns are reported — `acc_insample` (full-sample
     median, the optimistic number) and `acc_live` (expanding median using only
     prior rows, the honest one) — because the gap between them is usually
     larger than the gap between the best and worst indicator.
  2. **50% is the null, and below it is not failure.** A 45% hit rate is a 55%
     hit rate with the sign flipped, so the table sorts on `|acc - 0.5|` (the
     `edge` column) and reports `direction` separately. Sorting on raw accuracy
     silently discards every inverse indicator, which are often the strongest.

Usage:
    python scripts/indicator_accuracy.py SPY
    python scripts/indicator_accuracy.py AAPL MSFT --cutoff 2022-01-01
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from stock_risk.data.fetcher import MarketDataFetcher  # noqa: E402
from stock_risk.data.preprocessor import DataPreprocessor  # noqa: E402
from stock_risk.features.candlestick import CandlestickFeatures  # noqa: E402
from stock_risk.features.risk_metrics import RiskMetrics  # noqa: E402
from stock_risk.features.sma_search import OptimizedSMAFeatures  # noqa: E402
from stock_risk.features.technical import TechnicalFeatures  # noqa: E402

DEFAULT_CUTOFF = "2020-03-01"
MIN_ROWS = 60

# Columns that are prices/levels rather than indicators — scoring "is the close
# above its own median" measures whether the stock went up over the sample, not
# whether anything predicts anything.
_EXCLUDE = {
    "open", "high", "low", "close", "volume", "log_return", "pct_return",
    "ema_20", "ema_50", "ema_200", "sma_50", "sma_25", "obv", "volume_sma_20",
    "BBU_20_2.0", "BBL_20_2.0", "BBM_20_2.0",
}


def build_features(ticker: str, period: str = "5y") -> pd.DataFrame:
    df = DataPreprocessor().process(MarketDataFetcher().fetch_history(ticker, period=period))
    df = TechnicalFeatures().compute(df)
    df = RiskMetrics().compute(df)
    df = CandlestickFeatures().compute(df)
    df = OptimizedSMAFeatures().compute(df)
    return df


def hit_rates(series: pd.Series, target: pd.Series) -> tuple[float, float]:
    """(full-sample-median accuracy, expanding-median accuracy). NaN when there
    is not enough overlap to mean anything."""
    aligned = pd.concat([series, target], axis=1).dropna()
    if len(aligned) < MIN_ROWS:
        return float("nan"), float("nan")
    x, y = aligned.iloc[:, 0], aligned.iloc[:, 1]

    insample = (x > x.median()).astype(int).eq(y).mean()

    # Expanding median uses rows strictly before the current one; the first
    # MIN_ROWS rows have no stable median yet and are dropped rather than
    # scored against a one-or-two-observation "median".
    expanding = x.shift(1).expanding(min_periods=MIN_ROWS).median()
    live_mask = expanding.notna()
    if live_mask.sum() < MIN_ROWS:
        return float(insample), float("nan")
    live = (x[live_mask] > expanding[live_mask]).astype(int).eq(y[live_mask]).mean()
    return float(insample), float(live)


def score_ticker(ticker: str, cutoff: pd.Timestamp, period: str) -> pd.DataFrame:
    df = build_features(ticker, period=period)
    target = (df["close"].pct_change().shift(-1) > 0).astype(int)
    target = target.iloc[:-1]  # last row's forward return is unknown, not zero

    columns = [
        c for c in df.columns
        if c not in _EXCLUDE and pd.api.types.is_numeric_dtype(df[c])
    ]
    post = df.index >= cutoff

    rows = []
    for col in columns:
        acc_insample, acc_live = hit_rates(df[col], target)
        acc_post, _ = hit_rates(df.loc[post, col], target)
        rows.append({
            "indicator": col,
            "acc_insample": acc_insample,
            "acc_live": acc_live,
            "acc_post_cutoff": acc_post,
        })

    table = pd.DataFrame(rows).set_index("indicator")
    # Edge = distance from the 50% coin flip; direction says which way to read it.
    table["edge"] = (table["acc_live"] - 0.5).abs()
    table["direction"] = np.where(table["acc_live"] >= 0.5, "same", "inverse")
    table["regime_gap"] = table["acc_post_cutoff"] - table["acc_insample"]
    return table.sort_values("edge", ascending=False)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tickers", nargs="+")
    parser.add_argument("--cutoff", default=DEFAULT_CUTOFF,
                        help=f"regime split date (default {DEFAULT_CUTOFF}, COVID)")
    parser.add_argument("--period", default="5y")
    parser.add_argument("--top", type=int, default=10)
    args = parser.parse_args()

    cutoff = pd.Timestamp(args.cutoff)

    for ticker in args.tickers:
        try:
            table = score_ticker(ticker, cutoff, args.period)
        except Exception as exc:
            print(f"{ticker}: failed — {exc}", file=sys.stderr)
            continue

        print(f"\n=== {ticker} — directional hit rate (regime split at {cutoff.date()}) ===")
        print(f"baseline: {0.5:.1%} (coin flip). 'acc_live' is the honest column; "
              "'acc_insample' leaks the full-sample median.")
        print(f"\ntop {args.top} by live edge:")
        print(table.head(args.top).round(4).to_string())

        degraded = table[table["regime_gap"] < -0.05].head(args.top)
        if not degraded.empty:
            print("\nworked before the cutoff, degraded after (gap < -5pp):")
            print(degraded[["acc_insample", "acc_post_cutoff", "regime_gap"]]
                  .round(4).to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main())
