"""Category collinearity diagnostic: correlation matrix + PCA across the
five risk categories (volatility, tail, drawdown, sensitivity, liquidity).

The composite score treats these as five independent risk dimensions with
hand-set weights (25/25/20/15/15). If several of them move together almost
in lockstep — plausible, since volatility, VaR, CVaR, and drawdown are all
different lenses on the same underlying price-move-size — the score isn't
really blending five independent signals; it's counting a smaller number
of underlying factors multiple times, and the weight percentages imply a
precision about "how much each dimension matters" that collinear inputs
don't support.

No lookahead concerns here (unlike scripts/validate_score.py): this only
ever scores the *latest* row per ticker, once — normal production usage,
not a historical replay.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from loguru import logger

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from stock_risk.data.fetcher import MarketDataFetcher  # noqa: E402
from stock_risk.data.preprocessor import DataPreprocessor  # noqa: E402
from stock_risk.features.risk_metrics import RiskMetrics  # noqa: E402
from stock_risk.scoring.risk_categories import CATEGORY_WEIGHTS, composite_score  # noqa: E402

DEFAULT_TICKERS = [
    "AAPL", "MSFT", "GOOGL", "NVDA", "META", "AMZN", "TSLA",
    "JPM", "XOM", "JNJ", "KO", "BA", "DIS", "NEE",
]
CATEGORIES = list(CATEGORY_WEIGHTS.keys())


def score_ticker_history(
    ticker: str, period: str, benchmark_returns: pd.Series, min_history: int = 60
) -> list[dict]:
    """Category scores for every trading day (not a single latest-row
    snapshot) — a handful of tickers' current-day scores alone wouldn't
    give enough (ticker, date) points for a meaningful correlation
    estimate; scoring each ticker's own history the same way
    validate_score.py does gives a much larger, still-real sample.

    benchmark_returns must be passed — without it, RiskMetrics never
    computes beta_63d, and the whole "sensitivity" category (and hence
    every observation, since composite_score's caller here requires all 5
    categories present) silently comes back empty.
    """
    try:
        raw = MarketDataFetcher().fetch_history(ticker, period=period)
        df = RiskMetrics().compute(
            DataPreprocessor().process(raw), benchmark_returns=benchmark_returns
        )
    except Exception as exc:
        logger.warning(f"Skipping {ticker}: {exc}")
        return []

    records = []
    for i in range(min_history, len(df)):
        result = composite_score(df.iloc[: i + 1])
        row = {"ticker": ticker, "date": df.index[i]}
        for cat in CATEGORIES:
            row[cat] = result["categories"][cat]["score"]
        records.append(row)
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnose collinearity across risk categories")
    parser.add_argument("--tickers", nargs="+", default=DEFAULT_TICKERS)
    parser.add_argument("--period", default="2y")
    args = parser.parse_args()

    spy_raw = MarketDataFetcher().fetch_history("SPY", period=args.period)
    spy_df = DataPreprocessor().process(spy_raw)

    all_records = []
    for ticker in args.tickers:
        records = score_ticker_history(ticker, args.period, spy_df["log_return"])
        all_records.extend(records)
        logger.info(f"{ticker}: {len(records)} scored days")

    obs = pd.DataFrame(all_records).dropna(subset=CATEGORIES)
    print(f"\nTotal (ticker, date) observations with all 5 categories present: {len(obs)}")
    print(f"Tickers: {obs['ticker'].nunique()}\n")

    corr = obs[CATEGORIES].corr()
    print("=" * 70)
    print("CORRELATION MATRIX (category scores)")
    print("=" * 70)
    print(corr.to_string(float_format=lambda x: f"{x:.3f}"))

    high_corr = []
    for i, a in enumerate(CATEGORIES):
        for b in CATEGORIES[i + 1 :]:
            r = corr.loc[a, b]
            if abs(r) > 0.8:
                high_corr.append((a, b, r))
    print("\nPairs with |correlation| > 0.8:")
    if high_corr:
        for a, b, r in high_corr:
            print(f"  {a} <-> {b}: {r:.3f}")
    else:
        print("  (none)")

    # PCA via eigendecomposition of the correlation matrix — equivalent to
    # sklearn's PCA on standardized inputs, no extra dependency needed.
    eigenvalues, _ = np.linalg.eigh(corr.values)
    eigenvalues = eigenvalues[::-1]  # descending
    explained = eigenvalues / eigenvalues.sum()
    cumulative = np.cumsum(explained)

    print("\n" + "=" * 70)
    print("PCA — explained variance by principal component")
    print("=" * 70)
    for i, (ev, exp, cum) in enumerate(zip(eigenvalues, explained, cumulative), start=1):
        print(f"PC{i}: eigenvalue={ev:.3f}  explained={exp:.1%}  cumulative={cum:.1%}")

    n_for_90pct = int(np.searchsorted(cumulative, 0.90) + 1)
    print(f"\nComponents needed to explain >=90% of variance: {n_for_90pct} of {len(CATEGORIES)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
