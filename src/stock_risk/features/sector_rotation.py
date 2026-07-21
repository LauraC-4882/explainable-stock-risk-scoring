"""[G6] Risk-on / risk-off sector basket features and basket analytics.

The sector split is the standard cyclical-vs-defensive one, expressed through
SPDR sector ETFs:

  - **Risk-on (cyclical)**: XLB materials, XLI industrials, XLK technology,
    XLY consumer discretionary — sectors whose earnings track the business
    cycle, so they lead in expansions and fall hardest in contractions.
  - **Risk-off (defensive)**: XLP consumer staples, XLU utilities, XLV health
    care — inelastic demand, so cash flows hold up through downturns.

What this adds over the existing single-benchmark beta (`beta_63d` in
`risk_metrics.py`): a stock's beta to SPY is one number that cannot distinguish
"moves with the market because it is cyclical" from "moves with the market
because it is large". Splitting the benchmark into cyclical and defensive legs
turns that one number into a *tilt* — `risk_on_tilt = beta_on - beta_off` — which
says which side of the rotation the stock actually sits on. A stock with equal
betas to both baskets is genuinely market-like; a high tilt means the stock's
drawdown risk is concentrated in exactly the regime where the risk-off flag in
`regime.py` says to be defensive.

`rotation_spread_63d` is a market-level column (identical for every stock on a
given date): how much the cyclical basket has out- or under-performed the
defensive one over the last quarter. It is the rotation itself, independent of
the stock — useful as regime context alongside the per-stock tilt.

Every column degrades to all-NaN when basket returns are unavailable, matching
the rest of the feature layer.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

RISK_ON_TICKERS = ["XLB", "XLI", "XLK", "XLY"]
RISK_OFF_TICKERS = ["XLP", "XLU", "XLV"]

TRADING_DAYS = 252
DEFAULT_WINDOW = 63  # one quarter, matching beta_63d/sharpe_63d in risk_metrics

SECTOR_COLS = [
    "beta_risk_on_63d",
    "beta_risk_off_63d",
    "corr_risk_on_63d",
    "corr_risk_off_63d",
    "risk_on_tilt",
    "rotation_spread_63d",
]


def equal_weight_basket(returns: dict[str, pd.Series]) -> pd.Series:
    """Equal-weighted daily return of a basket, rebalanced daily.

    Daily rebalancing (a plain cross-sectional mean of returns) rather than
    buy-and-hold drift, so the basket keeps its stated equal weighting instead
    of quietly becoming a momentum bet on whichever member ran up most. Members
    missing on a date are skipped for that date, not treated as zero return.
    """
    if not returns:
        return pd.Series(dtype=float)
    return pd.DataFrame(returns).mean(axis=1, skipna=True)


class SectorRotationFeatures:
    """Rolling betas/correlations to the risk-on and risk-off baskets."""

    def __init__(self, window: int = DEFAULT_WINDOW):
        self.window = window

    def compute(
        self,
        df: pd.DataFrame,
        risk_on_returns: pd.Series | None = None,
        risk_off_returns: pd.Series | None = None,
    ) -> pd.DataFrame:
        df = df.copy()

        if risk_on_returns is None or risk_off_returns is None:
            for col in SECTOR_COLS:
                df[col] = np.nan
            return df

        r = df["log_return"] if "log_return" in df.columns else df["close"].pct_change()
        on = risk_on_returns.reindex(df.index)
        off = risk_off_returns.reindex(df.index)

        df["beta_risk_on_63d"] = _rolling_beta(r, on, self.window)
        df["beta_risk_off_63d"] = _rolling_beta(r, off, self.window)
        df["corr_risk_on_63d"] = r.rolling(self.window).corr(on)
        df["corr_risk_off_63d"] = r.rolling(self.window).corr(off)
        df["risk_on_tilt"] = df["beta_risk_on_63d"] - df["beta_risk_off_63d"]

        # Market-level rotation: cumulative cyclical-minus-defensive performance
        # over the window. Positive = cyclicals leading.
        df["rotation_spread_63d"] = (
            on.rolling(self.window).sum() - off.rolling(self.window).sum()
        )
        return df


def _rolling_beta(stock: pd.Series, bench: pd.Series, window: int) -> pd.Series:
    """Rolling cov/var beta.

    Vectorised via pandas' own rolling cov/var rather than a per-window
    `.apply` — on a 5-year daily frame the apply version runs ~1200 python-level
    regressions per column and dominates the whole feature build.
    """
    cov = stock.rolling(window).cov(bench)
    var = bench.rolling(window).var()
    return cov / var.where(var > 0)


def basket_performance(
    returns: dict[str, pd.Series], benchmark: pd.Series | None = None
) -> pd.DataFrame:
    """Per-member and equal-weight-basket risk/return table.

    One row per ticker plus a `BASKET` row: annualised return, annualised
    volatility, Sharpe ratio, and (when a benchmark is given) beta. This is the
    per-sector summary table that motivates the split above — run it on
    RISK_ON_TICKERS and RISK_OFF_TICKERS to check the classification still
    holds on current data rather than assuming it.
    """
    from ..backtest.performance import annualized_return, annualized_volatility, sharpe_ratio

    series = dict(returns)
    series["BASKET"] = equal_weight_basket(returns)

    rows = []
    for ticker, r in series.items():
        clean = r.dropna()
        row = {
            "ticker": ticker,
            "annualized_return": annualized_return(clean),
            "annualized_volatility": annualized_volatility(clean),
            "sharpe_ratio": sharpe_ratio(clean),
        }
        if benchmark is not None:
            aligned = pd.concat([clean, benchmark.reindex(clean.index)], axis=1).dropna()
            if len(aligned) >= 10:
                cov = np.cov(aligned.iloc[:, 0], aligned.iloc[:, 1])
                row["beta"] = cov[0, 1] / cov[1, 1] if cov[1, 1] > 0 else np.nan
            else:
                row["beta"] = np.nan
        rows.append(row)
    return pd.DataFrame(rows).set_index("ticker")


def correlation_matrix(returns: dict[str, pd.Series]) -> pd.DataFrame:
    """Pairwise return correlation across basket members.

    Diversification check: a "basket" whose members all correlate ~0.9 is one
    position wearing four tickers' worth of fees, and the equal weighting above
    buys nothing.
    """
    return pd.DataFrame(returns).corr()
