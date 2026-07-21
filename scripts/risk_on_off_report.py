"""[G6] End-to-end risk-on / risk-off report.

Runs the whole [G6] layer against live data and prints the tables it exists to
produce:

  1. Per-sector and per-basket risk/return (annualised return, volatility,
     Sharpe, beta vs the benchmark) for the cyclical and defensive baskets.
  2. Correlation matrix within each basket — the diversification check.
  3. Tail risk (VaR 95, expected shortfall, max drawdown) for both baskets and
     the benchmark.
  4. The regime-switching strategy: hold cyclicals when realised volatility is
     below the lagged VIX plus a buffer, defensives otherwise — scored against
     buy-and-hold on the benchmark, which is the only comparison that decides
     whether the rule is worth anything.

The classification (which sectors are "risk-on") is an assumption this script
*tests* rather than asserts: if the defensive basket does not show the lower
beta, lower volatility, and shallower drawdown the label claims, the label is
wrong for the sample period and the tables will say so.

Usage:
    python scripts/risk_on_off_report.py
    python scripts/risk_on_off_report.py --period 10y --benchmark SPY
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pandas as pd  # noqa: E402

from stock_risk.backtest.performance import compare_performance  # noqa: E402
from stock_risk.backtest.signals import backtest_signal  # noqa: E402
from stock_risk.data.fetcher import MarketDataFetcher  # noqa: E402
from stock_risk.data.preprocessor import DataPreprocessor  # noqa: E402
from stock_risk.features.regime import RegimeFeatures, risk_on_allocation  # noqa: E402
from stock_risk.features.sector_rotation import (  # noqa: E402
    RISK_OFF_TICKERS,
    RISK_ON_TICKERS,
    basket_performance,
    correlation_matrix,
    equal_weight_basket,
)


def fetch_returns(
    fetcher: MarketDataFetcher, tickers: list[str], period: str
) -> dict[str, pd.Series]:
    """Daily simple returns per ticker. A ticker that fails to fetch is skipped
    with a warning rather than aborting the report — a partial basket is still
    informative, a crashed script is not."""
    pre = DataPreprocessor()
    out: dict[str, pd.Series] = {}
    for ticker in tickers:
        try:
            out[ticker] = pre.process(fetcher.fetch_history(ticker, period=period))["pct_return"]
        except Exception as exc:
            print(f"  warning: skipping {ticker} — {exc}", file=sys.stderr)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--period", default="5y")
    parser.add_argument("--benchmark", default="SPY")
    parser.add_argument("--buffer-pct", type=float, default=2.0,
                        help="percentage-point cushion in the regime rule (default 2.0)")
    args = parser.parse_args()

    fetcher = MarketDataFetcher()
    pre = DataPreprocessor()

    print(f"fetching {args.period} of history …")
    bench_df = pre.process(fetcher.fetch_history(args.benchmark, period=args.period))
    bench_returns = bench_df["pct_return"]

    risk_on = fetch_returns(fetcher, RISK_ON_TICKERS, args.period)
    risk_off = fetch_returns(fetcher, RISK_OFF_TICKERS, args.period)
    if not risk_on or not risk_off:
        print("could not fetch either basket — aborting", file=sys.stderr)
        return 1

    # ── 1. Risk/return per sector and per basket ─────────────────────────────
    print(f"\n=== Risk-ON basket (cyclical) vs {args.benchmark} ===")
    print(basket_performance(risk_on, benchmark=bench_returns).round(4).to_string())
    print(f"\n=== Risk-OFF basket (defensive) vs {args.benchmark} ===")
    print(basket_performance(risk_off, benchmark=bench_returns).round(4).to_string())

    # ── 2. Diversification within each basket ────────────────────────────────
    print("\n=== Correlation within Risk-ON basket ===")
    print(correlation_matrix(risk_on).round(2).to_string())
    print("\n=== Correlation within Risk-OFF basket ===")
    print(correlation_matrix(risk_off).round(2).to_string())

    # ── 3. Tail risk ─────────────────────────────────────────────────────────
    on_basket = equal_weight_basket(risk_on)
    off_basket = equal_weight_basket(risk_off)
    print("\n=== Tail risk (VaR 95 / ES 95 / max drawdown) ===")
    tail = compare_performance({
        args.benchmark: bench_returns,
        "RiskOn": on_basket,
        "RiskOff": off_basket,
    })
    print(tail[["annualized_return", "annualized_volatility", "sharpe_ratio",
                "var_95", "expected_shortfall_95", "max_drawdown"]].round(4).to_string())

    # ── 4. The regime-switching strategy ─────────────────────────────────────
    vix_close = None
    try:
        vix_close = fetcher.fetch_history("^VIX", period=args.period)["close"]
    except Exception as exc:
        print(f"\nwarning: no VIX history ({exc}) — skipping the regime strategy",
              file=sys.stderr)

    if vix_close is not None:
        regime = RegimeFeatures(buffer_pct=args.buffer_pct).compute(bench_df, vix_close)
        strategy = risk_on_allocation(regime, on_basket, off_basket).dropna()
        share_on = regime["risk_on"].mean()

        print(f"\n=== Regime strategy (buffer {args.buffer_pct}pp) vs buy-and-hold ===")
        print(f"risk-on {share_on:.1%} of days; {len(strategy)} traded days")
        comparison = compare_performance({
            "RegimeSwitch": strategy,
            f"BuyAndHold{args.benchmark}": backtest_signal(
                pd.Series(1.0, index=bench_df.index), bench_df["close"]
            ),
            "AlwaysRiskOn": on_basket,
            "AlwaysRiskOff": off_basket,
        })
        print(comparison.round(4).to_string())
        print("\nIf RegimeSwitch does not beat BuyAndHold on Sharpe AND on max "
              "drawdown, the switching rule is not paying for its turnover.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
