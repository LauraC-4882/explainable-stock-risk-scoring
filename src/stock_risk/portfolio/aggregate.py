"""[R7] Portfolio-level risk aggregation.

Single-name risk scores don't add up. Two stocks each scoring 70 make a
portfolio riskier than either alone if they're the same sector, and materially
safer than either if they're uncorrelated — a weighted average of the scores
says the same thing in both cases, which is why this module computes portfolio
risk from the underlying return series rather than by blending scores.

What it answers that the single-name view cannot:

* **Where does the risk actually come from?** Marginal and component VaR
  decompose total risk by position. The largest position is frequently not the
  largest risk contributor, and the whole point of the decomposition is to
  show that.
* **How concentrated is this?** HHI and effective-N, plus sector exposure.
* **What survives diversification?** The diversification ratio: how much of the
  weighted-average standalone risk the portfolio actually avoids.
* **What happens in a stress scenario, and who causes it?** Stress loss
  attributed per position, not just a portfolio total.

Component VaR is the load-bearing piece. It has the property that makes
attribution meaningful: components sum exactly to portfolio VaR (Euler
allocation, valid because VaR is homogeneous of degree 1 in the weights). A
decomposition whose parts don't sum to the whole isn't an attribution, it's a
set of loosely related numbers.

Everything here is descriptive of historical co-movement. Nothing forecasts,
and nothing recommends a position.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

TRADING_DAYS = 252


@dataclass
class Position:
    ticker: str
    weight: float
    sector: Optional[str] = None


@dataclass
class PortfolioRisk:
    """Aggregate risk plus its per-position decomposition."""

    volatility: float  # annualised
    var_95: float  # 1-day, as a negative return
    cvar_95: float
    diversification_ratio: float
    effective_n: float
    concentration_hhi: float
    component_var: dict[str, float] = field(default_factory=dict)
    marginal_var: dict[str, float] = field(default_factory=dict)
    risk_contribution_pct: dict[str, float] = field(default_factory=dict)
    sector_exposure: dict[str, float] = field(default_factory=dict)
    portfolio_beta: Optional[float] = None
    n_observations: int = 0


def _aligned_returns(returns: dict[str, pd.Series], positions: list[Position]) -> pd.DataFrame:
    """Return matrix over the dates where EVERY position has data.

    Inner join, deliberately. Filling a missing series with zeros would read as
    "this asset didn't move", understating both its volatility and its
    correlation with everything else — the two inputs the whole calculation
    rests on. A shorter shared window is honest; a padded long one is not.
    """
    frame = pd.DataFrame({p.ticker: returns[p.ticker] for p in positions if p.ticker in returns})
    return frame.dropna(how="any")


def _normalise(positions: list[Position]) -> list[Position]:
    total = sum(p.weight for p in positions)
    if total <= 0:
        raise ValueError("portfolio weights must sum to a positive number")
    return [Position(p.ticker, p.weight / total, p.sector) for p in positions]


def compute_portfolio_risk(
    returns: dict[str, pd.Series],
    positions: list[Position],
    benchmark_returns: Optional[pd.Series] = None,
    confidence: float = 0.95,
) -> PortfolioRisk:
    """Aggregate risk and its decomposition for a weighted book of positions."""
    positions = _normalise(positions)
    matrix = _aligned_returns(returns, positions)
    if matrix.empty:
        raise ValueError("no overlapping return history across the given positions")

    present = [p for p in positions if p.ticker in matrix.columns]
    weights = np.array([p.weight / sum(q.weight for q in present) for p in present])
    tickers = [p.ticker for p in present]

    cov = matrix.cov().to_numpy() * TRADING_DAYS
    portfolio_variance = float(weights @ cov @ weights)
    portfolio_vol = float(np.sqrt(max(portfolio_variance, 0.0)))

    portfolio_returns = matrix.to_numpy() @ weights
    alpha = 1 - confidence
    var = float(np.quantile(portfolio_returns, alpha))
    tail = portfolio_returns[portfolio_returns <= var]
    cvar = float(tail.mean()) if tail.size else var

    # Marginal VaR: d(VaR)/d(weight_i). Proportional to the position's
    # covariance with the portfolio, which is why a small position in a
    # high-beta name can contribute more risk than a large uncorrelated one.
    if portfolio_vol > 0:
        marginal = (cov @ weights) / portfolio_vol
        # Component VaR = w_i * marginal_i, scaled so components sum exactly to
        # portfolio VaR (Euler allocation — see module docstring).
        component_vol = weights * marginal
        scale = var / component_vol.sum() if component_vol.sum() != 0 else 0.0
        component_var = component_vol * scale
        contribution_pct = (
            component_vol / component_vol.sum() * 100 if component_vol.sum() != 0 else component_vol
        )
    else:
        marginal = np.zeros_like(weights)
        component_var = np.zeros_like(weights)
        contribution_pct = np.zeros_like(weights)

    # Diversification ratio: weighted-average standalone vol over portfolio vol.
    # 1.0 = no diversification benefit (perfectly correlated); higher is more.
    standalone_vol = matrix.std().to_numpy() * np.sqrt(TRADING_DAYS)
    weighted_standalone = float(weights @ standalone_vol)
    diversification = weighted_standalone / portfolio_vol if portfolio_vol > 0 else 1.0

    # Herfindahl on weights, and its reciprocal: the number of equally-weighted
    # positions that would be as concentrated as this book. More intuitive than
    # the index itself — "effectively 2.3 positions" lands where "HHI 0.43"
    # doesn't.
    hhi = float(np.sum(weights**2))
    effective_n = 1.0 / hhi if hhi > 0 else 0.0

    sector_exposure: dict[str, float] = {}
    for position, weight in zip(present, weights):
        key = position.sector or "unclassified"
        sector_exposure[key] = sector_exposure.get(key, 0.0) + float(weight) * 100

    portfolio_beta = None
    if benchmark_returns is not None:
        joined = pd.concat(
            [pd.Series(portfolio_returns, index=matrix.index), benchmark_returns], axis=1
        ).dropna()
        if len(joined) > 2:
            bench_var = joined.iloc[:, 1].var()
            if bench_var > 0:
                portfolio_beta = float(joined.iloc[:, 0].cov(joined.iloc[:, 1]) / bench_var)

    return PortfolioRisk(
        volatility=round(portfolio_vol, 6),
        var_95=round(var, 6),
        cvar_95=round(cvar, 6),
        diversification_ratio=round(diversification, 4),
        effective_n=round(effective_n, 4),
        concentration_hhi=round(hhi, 6),
        component_var={t: round(float(v), 8) for t, v in zip(tickers, component_var)},
        marginal_var={t: round(float(v), 8) for t, v in zip(tickers, marginal)},
        risk_contribution_pct={t: round(float(v), 4) for t, v in zip(tickers, contribution_pct)},
        sector_exposure={k: round(v, 4) for k, v in sorted(sector_exposure.items())},
        portfolio_beta=round(portfolio_beta, 4) if portfolio_beta is not None else None,
        n_observations=len(matrix),
    )


def stress_loss_attribution(
    returns: dict[str, pd.Series],
    positions: list[Position],
    market_shock: float,
    betas: Optional[dict[str, float]] = None,
) -> dict:
    """Attribute a market-wide shock to individual positions via their betas.

    Beta-scaled rather than applied uniformly: a market-wide drawdown does not
    hit a 0.4-beta utility and a 1.8-beta growth name equally, and a flat shock
    would report a portfolio loss that no plausible scenario produces. Same
    reasoning as scoring/stress_test.py's beta-scaled propagation.

    Betas are estimated from the supplied history when not provided.
    """
    positions = _normalise(positions)
    matrix = _aligned_returns(returns, positions)
    if matrix.empty:
        raise ValueError("no overlapping return history across the given positions")

    present = [p for p in positions if p.ticker in matrix.columns]
    weights = {p.ticker: p.weight / sum(q.weight for q in present) for p in present}

    if betas is None:
        # Equal-weighted portfolio of the holdings as the market proxy: no
        # external benchmark is required, and it keeps the attribution internal
        # to the book being analysed. Named as a proxy rather than presented as
        # a real market beta, because it is not one.
        proxy = matrix.mean(axis=1)
        proxy_var = proxy.var()
        betas = {
            ticker: float(matrix[ticker].cov(proxy) / proxy_var) if proxy_var > 0 else 1.0
            for ticker in matrix.columns
        }

    per_position = {
        ticker: round(weights[ticker] * betas.get(ticker, 1.0) * market_shock, 6)
        for ticker in weights
    }
    total = round(sum(per_position.values()), 6)

    return {
        "market_shock": market_shock,
        "portfolio_loss": total,
        "per_position_loss": per_position,
        "loss_share_pct": {
            t: round(loss / total * 100, 4) if total else 0.0 for t, loss in per_position.items()
        },
        "betas_used": {t: round(b, 4) for t, b in betas.items()},
    }


def concentration_alerts(
    risk: PortfolioRisk,
    *,
    max_position_pct: float = 25.0,
    fair_share_multiple: float = 1.5,
    max_sector_pct: float = 40.0,
    min_effective_n: float = 3.0,
) -> list[str]:
    """Threshold breaches worth surfacing, as plain statements of fact.

    Deliberately worded as observations ("X contributes N% of portfolio risk"),
    never as instructions ("reduce X"). Same advice boundary the rest of this
    product holds: describing a measurement is not recommending a trade.

    The position threshold is relative to the book's size, not a flat
    percentage. A flat 25% fires on any equally-weighted four-position
    portfolio, where every holding contributes ~25% *by construction* — an
    alert that goes off on a textbook-diversified book trains people to ignore
    alerts. What's actually notable is a position carrying substantially more
    than its fair share (1/N) of risk, so the bar is
    `max(max_position_pct, fair_share_multiple * 100/N)`.
    """
    alerts = []
    n_positions = len(risk.risk_contribution_pct)
    fair_share = 100.0 / n_positions if n_positions else 100.0
    position_bar = max(max_position_pct, fair_share_multiple * fair_share)

    for ticker, pct in sorted(
        risk.risk_contribution_pct.items(), key=lambda kv: kv[1], reverse=True
    ):
        if pct > position_bar:
            alerts.append(
                f"{ticker} accounts for {pct:.1f}% of total portfolio risk "
                f"({pct / fair_share:.1f}x an equal share)"
            )
    for sector, pct in risk.sector_exposure.items():
        if pct > max_sector_pct:
            alerts.append(f"{pct:.1f}% of the book sits in a single sector ({sector})")
    if risk.effective_n < min_effective_n:
        alerts.append(
            f"Concentration is equivalent to {risk.effective_n:.1f} equally-weighted positions"
        )
    if risk.diversification_ratio < 1.1:
        alerts.append(
            f"Diversification ratio {risk.diversification_ratio:.2f} — holdings move closely "
            "together, so position count overstates how spread the risk is"
        )
    return alerts
