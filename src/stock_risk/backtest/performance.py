"""[G6] Risk/return performance metrics for a strategy return series.

The standard evaluation table — annualised return, annualised volatility,
Sharpe, VaR, expected shortfall, maximum drawdown — computed on a series of
*periodic strategy returns* (not prices, not signals).

Relationship to `features/risk_metrics.py`: that module computes *rolling*
versions of several of these as per-row model features (`var_95_21d`,
`cvar_95_21d`, `max_drawdown_63d`, `sharpe_63d`). This module computes
*full-period scalars* for evaluating a strategy end to end. Same statistics,
different shape and different consumer; neither replaces the other.

Two conventions worth stating explicitly because they are the usual source of
mismatched numbers between implementations:

  - **Annualised return is geometric by default** — `(1 + r).prod() ** (252/n) - 1`,
    the compound rate that actually reproduces the cumulative curve. The
    arithmetic alternative (`mean * 252`) is available via `geometric=False`;
    it runs higher than the geometric figure whenever returns are volatile
    (volatility drag), so a table mixing the two is not comparable.
  - **VaR and ES are reported as the (negative) return at the tail**, e.g.
    -1.90% meaning "the worst 5% of days lost at least 1.90%". They are
    *historical* (empirical quantile), not parametric — no normality assumed,
    which matters precisely in the tail these numbers exist to describe.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_DAYS = 252

METRIC_NAMES = [
    "cumulative_return",
    "annualized_return",
    "annualized_volatility",
    "sharpe_ratio",
    "var_95",
    "expected_shortfall_95",
    "max_drawdown",
    "n_periods",
]


def _clean(returns: pd.Series) -> pd.Series:
    return pd.Series(returns).replace([np.inf, -np.inf], np.nan).dropna()


def cumulative_return(returns: pd.Series) -> float:
    r = _clean(returns)
    return float((1 + r).prod() - 1) if len(r) else float("nan")


def annualized_return(
    returns: pd.Series, periods_per_year: int = TRADING_DAYS, geometric: bool = True
) -> float:
    r = _clean(returns)
    if len(r) == 0:
        return float("nan")
    if not geometric:
        return float(r.mean() * periods_per_year)
    growth = (1 + r).prod()
    if growth <= 0:
        # A -100% path: the strategy was wiped out, and a fractional power of a
        # non-positive number is not a return. Report the total loss instead of
        # a NaN or a complex number.
        return -1.0
    return float(growth ** (periods_per_year / len(r)) - 1)


def annualized_volatility(
    returns: pd.Series, periods_per_year: int = TRADING_DAYS
) -> float:
    r = _clean(returns)
    if len(r) < 2:
        return float("nan")
    return float(r.std(ddof=1) * np.sqrt(periods_per_year))


def sharpe_ratio(
    returns: pd.Series,
    risk_free_rate: float = 0.0,
    periods_per_year: int = TRADING_DAYS,
) -> float:
    """Annualised Sharpe. `risk_free_rate` is an *annual* rate, de-annualised
    per period before subtracting."""
    r = _clean(returns)
    if len(r) < 2:
        return float("nan")
    excess = r - risk_free_rate / periods_per_year
    sd = excess.std(ddof=1)
    if sd == 0:
        return float("nan")
    return float(excess.mean() / sd * np.sqrt(periods_per_year))


def sortino_ratio(
    returns: pd.Series,
    risk_free_rate: float = 0.0,
    periods_per_year: int = TRADING_DAYS,
) -> float:
    """Sharpe with downside deviation in the denominator — upside volatility
    is not a risk a long investor needs compensating for."""
    r = _clean(returns)
    if len(r) < 2:
        return float("nan")
    excess = r - risk_free_rate / periods_per_year
    downside = excess[excess < 0]
    if len(downside) < 2 or downside.std(ddof=1) == 0:
        return float("nan")
    return float(excess.mean() / downside.std(ddof=1) * np.sqrt(periods_per_year))


def value_at_risk(returns: pd.Series, confidence: float = 0.95) -> float:
    """Historical VaR: the `1 - confidence` empirical quantile of returns
    (negative = a loss)."""
    r = _clean(returns)
    if len(r) < 2:
        return float("nan")
    return float(np.quantile(r, 1 - confidence))


def expected_shortfall(returns: pd.Series, confidence: float = 0.95) -> float:
    """Historical expected shortfall (CVaR): mean return conditional on being
    at or beyond the VaR threshold — the average bad day, not just its
    boundary."""
    r = _clean(returns)
    if len(r) < 2:
        return float("nan")
    threshold = np.quantile(r, 1 - confidence)
    tail = r[r <= threshold]
    return float(tail.mean()) if len(tail) else float("nan")


def max_drawdown(returns: pd.Series) -> float:
    """Worst peak-to-trough decline of the compounded equity curve (negative)."""
    r = _clean(returns)
    if len(r) == 0:
        return float("nan")
    equity = (1 + r).cumprod()
    return float((equity / equity.cummax() - 1).min())


def performance_summary(
    returns: pd.Series,
    risk_free_rate: float = 0.0,
    confidence: float = 0.95,
    periods_per_year: int = TRADING_DAYS,
) -> dict:
    """Every metric above in one dict.

    Values are native Python floats — see CLAUDE.md rule 4: numpy scalars that
    reach an API response blow up `json.dumps`, and every metric here is a
    plausible API payload.
    """
    r = _clean(returns)
    return {
        "cumulative_return": cumulative_return(r),
        "annualized_return": annualized_return(r, periods_per_year),
        "annualized_volatility": annualized_volatility(r, periods_per_year),
        "sharpe_ratio": sharpe_ratio(r, risk_free_rate, periods_per_year),
        "sortino_ratio": sortino_ratio(r, risk_free_rate, periods_per_year),
        "var_95": value_at_risk(r, confidence),
        "expected_shortfall_95": expected_shortfall(r, confidence),
        "max_drawdown": max_drawdown(r),
        "n_periods": int(len(r)),
    }


def compare_performance(
    strategies: dict[str, pd.Series],
    risk_free_rate: float = 0.0,
    confidence: float = 0.95,
) -> pd.DataFrame:
    """One row per named strategy, sorted by Sharpe (best first)."""
    rows = {
        name: performance_summary(r, risk_free_rate, confidence)
        for name, r in strategies.items()
    }
    table = pd.DataFrame(rows).T
    return table.sort_values("sharpe_ratio", ascending=False)


def equity_curve(returns: pd.Series) -> pd.Series:
    """Cumulative return path starting at 0 — what the performance charts plot."""
    return (1 + _clean(returns)).cumprod() - 1
