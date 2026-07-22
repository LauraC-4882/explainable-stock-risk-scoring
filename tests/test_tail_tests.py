"""[R6] Tests for tail-risk backtesting.

These are statistical tests, so "it ran without raising" proves nothing. Each
test below constructs data with a KNOWN answer — a correctly-calibrated VaR, a
deliberately under-stated one, breaches forced into clusters — and asserts the
statistic reaches the right verdict. A test suite that only checks the plumbing
would pass just as happily with the log-likelihood inverted.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from stock_risk.validation import (
    acerbi_szekely_z2,
    breach_clustering_profile,
    christoffersen_conditional_coverage,
    christoffersen_independence,
    kupiec_pof,
    run_full_suite,
)

ALPHA = 0.05


def _index(n):
    return pd.bdate_range("2020-01-01", periods=n)


def _well_calibrated(n=2000, seed=0):
    """Returns whose true 5% quantile is exactly the stated VaR line."""
    rng = np.random.default_rng(seed)
    returns = pd.Series(rng.normal(0, 0.01, n), index=_index(n))
    var_level = float(np.quantile(rng.normal(0, 0.01, 200_000), ALPHA))
    var = pd.Series(var_level, index=returns.index)
    return returns, var


# ── Kupiec: unconditional coverage ───────────────────────────────────────────


def test_kupiec_passes_a_correctly_calibrated_var():
    returns, var = _well_calibrated()
    result = kupiec_pof(returns, var, ALPHA)
    assert not result.reject, f"correct VaR wrongly rejected: {result.summary()}"
    assert result.detail["observed_rate"] == pytest.approx(0.05, abs=0.015)


def test_kupiec_rejects_a_var_that_understates_risk():
    """The real finding this project already has: var_95_21d breaches 9.25% of
    the time against a 5% claim. A VaR set too close to zero must be caught."""
    rng = np.random.default_rng(1)
    returns = pd.Series(rng.normal(0, 0.01, 2000), index=_index(2000))
    too_shallow = pd.Series(-0.008, index=returns.index)  # ~21% breach rate

    result = kupiec_pof(returns, too_shallow, ALPHA)

    assert result.reject
    assert result.detail["observed_rate"] > 0.10


def test_kupiec_rejects_an_overly_conservative_var():
    """Both directions matter: a VaR that never breaches is also miscalibrated,
    and over-reserving has a real cost."""
    rng = np.random.default_rng(2)
    returns = pd.Series(rng.normal(0, 0.01, 2000), index=_index(2000))
    far_too_deep = pd.Series(-0.20, index=returns.index)

    result = kupiec_pof(returns, far_too_deep, ALPHA)

    assert result.reject
    assert result.detail["breaches"] == 0


# ── Christoffersen: independence ─────────────────────────────────────────────


def test_independence_passes_when_breaches_are_scattered():
    returns, var = _well_calibrated(seed=3)
    result = christoffersen_independence(returns, var)
    assert not result.reject, f"iid breaches wrongly flagged as clustered: {result.summary()}"


def test_independence_rejects_clustered_breaches():
    """The failure Kupiec structurally cannot see.

    Breach rate is held at ~5% — Kupiec is satisfied — but every breach is
    packed into a handful of consecutive-day bursts, which is exactly the
    pattern that destroys capital in a crisis.
    """
    n = 1000
    returns = np.full(n, 0.001)
    # 50 breaches (5%), in 5 blocks of 10 consecutive days.
    for start in (100, 300, 500, 700, 900):
        returns[start : start + 10] = -0.05
    series = pd.Series(returns, index=_index(n))
    var = pd.Series(-0.02, index=series.index)

    kupiec = kupiec_pof(series, var, ALPHA)
    independence = christoffersen_independence(series, var)

    assert not kupiec.reject, "the breach RATE is correct — Kupiec should be satisfied"
    assert independence.reject, "clustered breaches must be rejected by the independence test"
    assert independence.detail["clustering_ratio"] > 1


def test_independence_is_uninformative_with_no_breaches_rather_than_crashing():
    """A degenerate sequence carries no clustering information. Reporting that
    honestly beats computing a statistic from log(0)."""
    series = pd.Series(np.full(500, 0.01), index=_index(500))
    var = pd.Series(-0.5, index=series.index)

    result = christoffersen_independence(series, var)

    assert not result.reject
    assert "degenerate" in result.detail.get("note", "")


# ── Conditional coverage ─────────────────────────────────────────────────────


def test_conditional_coverage_is_the_sum_of_its_two_components():
    """LR_cc = LR_uc + LR_ind, on 2 df. Pinned because a wrong df or a wrong
    sum would still produce a plausible-looking p-value."""
    returns, var = _well_calibrated(seed=4)

    uc = kupiec_pof(returns, var, ALPHA)
    ind = christoffersen_independence(returns, var)
    cc = christoffersen_conditional_coverage(returns, var, ALPHA)

    assert cc.statistic == pytest.approx(uc.statistic + ind.statistic, rel=1e-9)
    assert cc.detail["lr_uncond"] == pytest.approx(round(uc.statistic, 4))


def test_conditional_coverage_rejects_when_only_independence_fails():
    """Correct rate, clustered timing — the joint test must still reject, which
    is the entire reason to run it alongside Kupiec."""
    n = 1000
    returns = np.full(n, 0.001)
    for start in (100, 300, 500, 700, 900):
        returns[start : start + 10] = -0.05
    series = pd.Series(returns, index=_index(n))
    var = pd.Series(-0.02, index=series.index)

    assert christoffersen_conditional_coverage(series, var, ALPHA).reject


# ── Expected Shortfall ───────────────────────────────────────────────────────


def test_es_backtest_accepts_an_accurate_expected_shortfall():
    rng = np.random.default_rng(5)
    n = 3000
    returns = pd.Series(rng.normal(0, 0.01, n), index=_index(n))
    var_level = float(np.quantile(returns, ALPHA))
    # True ES: the mean of returns at or below the VaR line.
    es_level = float(returns[returns <= var_level].mean())

    result = acerbi_szekely_z2(
        returns,
        pd.Series(var_level, index=returns.index),
        pd.Series(es_level, index=returns.index),
        ALPHA,
    )

    assert not result.reject, f"accurate ES wrongly rejected: {result.summary()}"
    assert abs(result.statistic) < 0.35


def test_es_backtest_rejects_an_es_that_understates_tail_severity():
    """The direction that matters for capital: breaches were worse than ES said.

    ES is deliberately set to half its true magnitude, so realised breaches
    average about twice what was predicted.
    """
    rng = np.random.default_rng(6)
    n = 3000
    returns = pd.Series(rng.normal(0, 0.01, n), index=_index(n))
    var_level = float(np.quantile(returns, ALPHA))
    true_es = float(returns[returns <= var_level].mean())

    result = acerbi_szekely_z2(
        returns,
        pd.Series(var_level, index=returns.index),
        pd.Series(true_es / 2, index=returns.index),  # far too shallow
        ALPHA,
    )

    assert result.reject, f"understated ES not caught: {result.summary()}"
    assert result.statistic < 0, "Z2 must be negative when breaches beat the ES estimate"
    assert result.detail["severity_ratio"] > 1.5


def test_es_z2_sign_convention_matches_the_literature():
    """Regression: Z2's sign was inverted.

    The published Z2 is written with ES as a positive magnitude; this codebase
    stores ES as a negative loss, which flips the ratio. The first version
    computed the textbook formula directly against negative ES and returned +1
    where the reference says -1 — and since the p-value is one-sided, an ES
    understating the tail by 2x came back as "pass". This pins both directions
    so the sign can't silently flip back.
    """
    rng = np.random.default_rng(11)
    n = 3000
    returns = pd.Series(rng.normal(0, 0.01, n), index=_index(n))
    var = pd.Series(float(np.quantile(returns, ALPHA)), index=returns.index)
    true_es = float(returns[returns <= var.iloc[0]].mean())

    understated = acerbi_szekely_z2(
        returns, var, pd.Series(true_es / 2, index=returns.index), ALPHA
    )
    conservative = acerbi_szekely_z2(
        returns, var, pd.Series(true_es * 2, index=returns.index), ALPHA
    )

    assert understated.statistic < 0, "ES too shallow must give Z2 < 0"
    assert conservative.statistic > 0, "ES too deep must give Z2 > 0"
    # Only the understating direction is a safety failure worth rejecting.
    assert understated.reject
    assert not conservative.reject


def test_es_backtest_reports_honestly_when_there_are_no_breaches():
    series = pd.Series(np.full(500, 0.01), index=_index(500))
    result = acerbi_szekely_z2(
        series,
        pd.Series(-0.5, index=series.index),
        pd.Series(-0.6, index=series.index),
        ALPHA,
    )
    assert not result.reject
    assert result.detail["breaches"] == 0
    assert "untested" in result.detail["note"]


def test_es_p_value_is_reproducible():
    """A bootstrapped p-value that changes between runs can't be cited in a
    validation report — the RNG is seeded for exactly this reason."""
    rng = np.random.default_rng(7)
    returns = pd.Series(rng.normal(0, 0.01, 1500), index=_index(1500))
    var = pd.Series(float(np.quantile(returns, ALPHA)), index=returns.index)
    es = pd.Series(float(returns[returns <= var.iloc[0]].mean()), index=returns.index)

    first = acerbi_szekely_z2(returns, var, es, ALPHA)
    second = acerbi_szekely_z2(returns, var, es, ALPHA)

    assert first.p_value == second.p_value
    assert first.statistic == second.statistic


# ── Clustering profile & suite ───────────────────────────────────────────────


def test_clustering_profile_measures_run_length():
    n = 200
    returns = np.full(n, 0.01)
    returns[50:57] = -0.1  # one 7-day run
    returns[120] = -0.1  # one isolated breach
    series = pd.Series(returns, index=_index(n))
    var = pd.Series(-0.05, index=series.index)

    profile = breach_clustering_profile(series, var)

    assert profile["total_breaches"] == 8
    assert profile["longest_consecutive_run"] == 7
    assert profile["runs_of_2_or_more"] == 1
    assert profile["share_in_multiday_runs"] == pytest.approx(7 / 8)


def test_full_suite_runs_every_test_and_is_serialisable():
    returns, var = _well_calibrated(seed=8)
    es = var * 1.3

    output = run_full_suite(returns, var, es, ALPHA)

    assert set(output["tests"]) == {
        "kupiec_pof",
        "christoffersen_independence",
        "christoffersen_conditional_coverage",
        "acerbi_szekely_z2",
    }
    assert output["clustering"]["total_breaches"] > 0
    for result in output["tests"].values():
        assert isinstance(result.summary(), str)


def test_misaligned_series_are_aligned_not_silently_compared():
    """A shifted index would otherwise compare a return to a different day's
    VaR — plausible numbers, meaningless test."""
    returns, var = _well_calibrated(n=500, seed=9)
    shifted = var.iloc[100:]

    result = kupiec_pof(returns, shifted, ALPHA)

    assert result.detail["n"] == len(shifted)
