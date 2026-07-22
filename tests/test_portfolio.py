"""[R7] Tests for portfolio aggregation.

Constructed so each test has an analytically known answer — perfectly
correlated positions, perfectly uncorrelated ones, a deliberately concentrated
book — rather than asserting on whatever the code happens to produce.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from stock_risk.portfolio import (
    Position,
    compute_portfolio_risk,
    concentration_alerts,
    stress_loss_attribution,
)


def _index(n=750):
    return pd.bdate_range("2022-01-01", periods=n)


def _uncorrelated(n=750, seed=0, vol=0.01, k=3):
    rng = np.random.default_rng(seed)
    idx = _index(n)
    return {f"T{i}": pd.Series(rng.normal(0, vol, n), index=idx) for i in range(k)}


def _perfectly_correlated(n=750, seed=1, k=3):
    rng = np.random.default_rng(seed)
    idx = _index(n)
    base = rng.normal(0, 0.01, n)
    return {f"T{i}": pd.Series(base, index=idx) for i in range(k)}


# ── Diversification ──────────────────────────────────────────────────────────


def test_perfectly_correlated_book_shows_no_diversification_benefit():
    """The definitional case: identical assets can't diversify each other, so
    the ratio must be ~1.0."""
    returns = _perfectly_correlated()
    positions = [Position(t, 1 / 3) for t in returns]

    risk = compute_portfolio_risk(returns, positions)

    assert risk.diversification_ratio == pytest.approx(1.0, abs=0.02)


def test_uncorrelated_book_shows_a_real_diversification_benefit():
    """Three equally-weighted uncorrelated assets: portfolio vol is
    sigma/sqrt(3), so the ratio should be ~sqrt(3) = 1.73."""
    returns = _uncorrelated()
    positions = [Position(t, 1 / 3) for t in returns]

    risk = compute_portfolio_risk(returns, positions)

    assert risk.diversification_ratio == pytest.approx(np.sqrt(3), rel=0.12)


def test_portfolio_vol_is_below_weighted_average_when_uncorrelated():
    """The whole reason portfolio risk isn't a weighted average of scores."""
    returns = _uncorrelated()
    positions = [Position(t, 1 / 3) for t in returns]

    risk = compute_portfolio_risk(returns, positions)
    standalone = np.mean([r.std() * np.sqrt(252) for r in returns.values()])

    assert risk.volatility < standalone


# ── Risk decomposition ───────────────────────────────────────────────────────


def test_component_var_sums_to_portfolio_var():
    """The property that makes attribution meaningful (Euler allocation).

    A decomposition whose parts don't sum to the whole isn't an attribution.
    """
    returns = _uncorrelated(seed=2)
    positions = [Position("T0", 0.5), Position("T1", 0.3), Position("T2", 0.2)]

    risk = compute_portfolio_risk(returns, positions)

    # abs tolerance, not rel: the reported values are rounded (component_var to
    # 8dp, var_95 to 6dp), so three components accumulate ~1e-8 of rounding
    # against a VaR of ~0.01 — which is ~3e-6 in relative terms and would fail
    # a rel=1e-6 check for reasons that have nothing to do with the allocation.
    assert sum(risk.component_var.values()) == pytest.approx(risk.var_95, abs=1e-6)


def test_risk_contributions_sum_to_100_percent():
    returns = _uncorrelated(seed=3)
    positions = [Position("T0", 0.6), Position("T1", 0.25), Position("T2", 0.15)]

    risk = compute_portfolio_risk(returns, positions)

    assert sum(risk.risk_contribution_pct.values()) == pytest.approx(100.0, abs=0.01)


def test_a_small_high_volatility_position_can_dominate_risk():
    """The finding the decomposition exists to surface: the biggest position is
    not necessarily the biggest risk contributor."""
    rng = np.random.default_rng(4)
    idx = _index()
    returns = {
        "CALM": pd.Series(rng.normal(0, 0.004, len(idx)), index=idx),
        "WILD": pd.Series(rng.normal(0, 0.05, len(idx)), index=idx),
    }
    # WILD is only a fifth of the book by weight.
    positions = [Position("CALM", 0.8), Position("WILD", 0.2)]

    risk = compute_portfolio_risk(returns, positions)

    assert risk.risk_contribution_pct["WILD"] > risk.risk_contribution_pct["CALM"]
    assert risk.risk_contribution_pct["WILD"] > 80


def test_marginal_var_is_higher_for_the_more_volatile_asset():
    rng = np.random.default_rng(5)
    idx = _index()
    returns = {
        "CALM": pd.Series(rng.normal(0, 0.004, len(idx)), index=idx),
        "WILD": pd.Series(rng.normal(0, 0.05, len(idx)), index=idx),
    }
    risk = compute_portfolio_risk(returns, [Position("CALM", 0.5), Position("WILD", 0.5)])
    assert risk.marginal_var["WILD"] > risk.marginal_var["CALM"]


# ── Concentration ────────────────────────────────────────────────────────────


def test_effective_n_matches_an_equally_weighted_book():
    returns = _uncorrelated(k=4, seed=6)
    positions = [Position(t, 0.25) for t in returns]

    risk = compute_portfolio_risk(returns, positions)

    assert risk.effective_n == pytest.approx(4.0, abs=0.01)
    assert risk.concentration_hhi == pytest.approx(0.25, abs=0.001)


def test_effective_n_falls_when_the_book_is_concentrated():
    returns = _uncorrelated(k=4, seed=7)
    positions = [
        Position("T0", 0.85),
        Position("T1", 0.05),
        Position("T2", 0.05),
        Position("T3", 0.05),
    ]

    risk = compute_portfolio_risk(returns, positions)

    assert risk.effective_n < 1.5


def test_weights_are_normalised_rather_than_assumed_to_sum_to_one():
    returns = _uncorrelated(seed=8)
    unnormalised = [Position("T0", 20), Position("T1", 20), Position("T2", 20)]
    normalised = [Position("T0", 1 / 3), Position("T1", 1 / 3), Position("T2", 1 / 3)]

    assert compute_portfolio_risk(returns, unnormalised).volatility == pytest.approx(
        compute_portfolio_risk(returns, normalised).volatility
    )


def test_zero_or_negative_total_weight_is_rejected():
    returns = _uncorrelated(seed=9)
    with pytest.raises(ValueError, match="positive"):
        compute_portfolio_risk(returns, [Position("T0", 0.0)])


def test_sector_exposure_aggregates_positions():
    returns = _uncorrelated(k=3, seed=10)
    positions = [
        Position("T0", 0.5, sector="Technology"),
        Position("T1", 0.3, sector="Technology"),
        Position("T2", 0.2, sector="Utilities"),
    ]

    risk = compute_portfolio_risk(returns, positions)

    assert risk.sector_exposure["Technology"] == pytest.approx(80.0, abs=0.01)
    assert risk.sector_exposure["Utilities"] == pytest.approx(20.0, abs=0.01)


def test_positions_without_a_sector_are_labelled_not_dropped():
    """Silently omitting them would make sector exposure sum to less than 100%
    and look like a bug in the arithmetic."""
    returns = _uncorrelated(k=2, seed=11)
    risk = compute_portfolio_risk(
        returns, [Position("T0", 0.5, sector="Technology"), Position("T1", 0.5)]
    )
    assert risk.sector_exposure["unclassified"] == pytest.approx(50.0, abs=0.01)


# ── Data alignment ───────────────────────────────────────────────────────────


def test_non_overlapping_history_is_intersected_not_zero_filled():
    """Zero-filling a gap reads as "this asset didn't move", understating both
    its volatility and its correlation — the two inputs everything rests on."""
    idx_a = pd.bdate_range("2022-01-01", periods=500)
    idx_b = pd.bdate_range("2022-06-01", periods=500)
    rng = np.random.default_rng(12)
    returns = {
        "A": pd.Series(rng.normal(0, 0.01, 500), index=idx_a),
        "B": pd.Series(rng.normal(0, 0.01, 500), index=idx_b),
    }

    risk = compute_portfolio_risk(returns, [Position("A", 0.5), Position("B", 0.5)])

    assert risk.n_observations < 500
    assert risk.n_observations == len(idx_a.intersection(idx_b))


def test_completely_disjoint_history_raises_rather_than_returning_nonsense():
    returns = {
        "A": pd.Series([0.01] * 50, index=pd.bdate_range("2020-01-01", periods=50)),
        "B": pd.Series([0.01] * 50, index=pd.bdate_range("2024-01-01", periods=50)),
    }
    with pytest.raises(ValueError, match="no overlapping"):
        compute_portfolio_risk(returns, [Position("A", 0.5), Position("B", 0.5)])


# ── Stress attribution ───────────────────────────────────────────────────────


def test_stress_loss_is_attributed_across_positions_and_sums_to_the_total():
    returns = _uncorrelated(seed=13)
    positions = [Position("T0", 0.5), Position("T1", 0.3), Position("T2", 0.2)]

    result = stress_loss_attribution(returns, positions, market_shock=-0.20)

    assert sum(result["per_position_loss"].values()) == pytest.approx(
        result["portfolio_loss"], rel=1e-6
    )
    assert sum(result["loss_share_pct"].values()) == pytest.approx(100.0, abs=0.01)


def test_stress_uses_beta_scaling_not_a_flat_shock():
    """A market-wide drawdown doesn't hit a defensive and an aggressive name
    equally; a flat shock would report a loss no plausible scenario produces."""
    returns = _uncorrelated(k=2, seed=14)
    positions = [Position("T0", 0.5), Position("T1", 0.5)]

    result = stress_loss_attribution(
        returns, positions, market_shock=-0.20, betas={"T0": 0.4, "T1": 1.8}
    )

    assert abs(result["per_position_loss"]["T1"]) > abs(result["per_position_loss"]["T0"])
    assert result["per_position_loss"]["T0"] == pytest.approx(0.5 * 0.4 * -0.20)


# ── Alerts ───────────────────────────────────────────────────────────────────


def test_concentration_alerts_fire_on_a_dominant_risk_contributor():
    rng = np.random.default_rng(15)
    idx = _index()
    returns = {
        "CALM": pd.Series(rng.normal(0, 0.004, len(idx)), index=idx),
        "WILD": pd.Series(rng.normal(0, 0.05, len(idx)), index=idx),
    }
    risk = compute_portfolio_risk(
        returns, [Position("CALM", 0.8, "Utilities"), Position("WILD", 0.2, "Tech")]
    )

    alerts = concentration_alerts(risk)

    assert any("WILD" in a for a in alerts)


def test_alerts_are_descriptive_and_never_instruct_a_trade():
    """The product's advice boundary applies here too: describing a measurement
    is not recommending a position change."""
    returns = _uncorrelated(seed=16)
    risk = compute_portfolio_risk(returns, [Position("T0", 0.9), Position("T1", 0.1)])

    alerts = concentration_alerts(risk)

    banned = ("reduce", "sell", "buy", "trim", "should", "recommend", "you must")
    for alert in alerts:
        assert not any(word in alert.lower() for word in banned), alert


def test_equally_weighted_diversified_book_produces_no_alerts():
    """Regression: a flat 25% position threshold fired on every equally-weighted
    four-position book, where each holding contributes ~25% of risk by
    construction. An alert that goes off on a textbook-diversified portfolio
    trains people to ignore alerts, so the bar is now relative to fair share.
    """
    returns = _uncorrelated(k=4, seed=17)
    risk = compute_portfolio_risk(
        returns, [Position(t, 0.25, f"S{i}") for i, t in enumerate(returns)]
    )
    assert concentration_alerts(risk) == []


def test_alert_still_fires_when_one_position_far_exceeds_its_fair_share():
    """The relative bar must not become so permissive that nothing trips it."""
    rng = np.random.default_rng(18)
    idx = _index()
    returns = {f"T{i}": pd.Series(rng.normal(0, 0.004, len(idx)), index=idx) for i in range(4)}
    returns["WILD"] = pd.Series(rng.normal(0, 0.06, len(idx)), index=idx)
    positions = [Position(t, 0.2, f"S{i}") for i, t in enumerate(returns)]

    alerts = concentration_alerts(compute_portfolio_risk(returns, positions))

    assert any("WILD" in a for a in alerts)
