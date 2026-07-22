"""[R6] Tail-risk backtesting beyond unconditional coverage.

The existing Kupiec POF test (scripts/validate_score.py) answers one question:
does `var_95_21d` breach 5% of the time? It found that it doesn't — 9.25%
against a 5% target, LR 1160.9, p ~ 0. That is a real finding, but it is only
the *unconditional* half of VaR validation, and a VaR model can pass it while
still being unusable.

Three further tests, each catching something Kupiec structurally cannot:

* **Christoffersen independence.** Kupiec counts breaches; it cannot see when
  they happen. A model that breaches exactly 5% of the time but does so in
  three tight clusters during crises is far more dangerous than one that
  breaches 5% of the time uniformly — clustered breaches are precisely when
  losses compound and capital runs out. This tests whether a breach today
  predicts a breach tomorrow.
* **Conditional coverage.** The joint test: correct rate AND independence
  together, since passing one while failing the other is not a pass.
* **Expected Shortfall.** Basel FRTB moved the capital measure from VaR to ES
  specifically because VaR says nothing about how bad a breach is. ES is also
  not elicitable, so it cannot be backtested the same way — this uses
  Acerbi–Szekely's Z2, which conditions on the breach set rather than trying to
  score ES directly.

Everything here is descriptive of what already happened. None of it forecasts.

References:
  Kupiec (1995), "Techniques for verifying the accuracy of risk measurement models"
  Christoffersen (1998), "Evaluating interval forecasts", Int. Econ. Review 39(4)
  Acerbi & Szekely (2014), "Back-testing Expected Shortfall", Risk 27(11)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd
from scipy import stats


@dataclass
class TestResult:
    """One hypothesis test. `reject` is at the 5% level unless stated."""

    name: str
    statistic: float
    p_value: float
    reject: bool
    detail: dict

    def summary(self) -> str:
        verdict = "REJECT" if self.reject else "pass"
        return f"{self.name}: LR={self.statistic:.2f} p={self.p_value:.4g} -> {verdict}"


def _breaches(returns: pd.Series, var: pd.Series) -> pd.Series:
    """Boolean breach series: realised return below the (negative) VaR line.

    Aligned on the index and NaN-dropped first — a misalignment here silently
    compares a return to a different day's VaR, which would invalidate every
    test downstream while still producing plausible numbers.
    """
    aligned = pd.concat([returns.rename("r"), var.rename("var")], axis=1).dropna()
    return (aligned["r"] < aligned["var"]).astype(int)


def kupiec_pof(returns: pd.Series, var: pd.Series, alpha: float = 0.05) -> TestResult:
    """Unconditional coverage: is the breach RATE consistent with alpha?

    Reimplemented here (validate_score.py has its own) so the four tests share
    one aligned breach series and can be reported together.
    """
    breaches = _breaches(returns, var)
    n, x = len(breaches), int(breaches.sum())
    if n == 0:
        return TestResult("Kupiec POF", float("nan"), float("nan"), False, {"n": 0})

    rate = x / n
    if x == 0:
        lr = -2 * n * np.log(1 - alpha)
    else:
        lr = -2 * (
            (n - x) * np.log(1 - alpha)
            + x * np.log(alpha)
            - (n - x) * np.log(1 - rate)
            - x * np.log(rate)
        )
    p = 1 - stats.chi2.cdf(lr, df=1)
    return TestResult(
        "Kupiec POF (unconditional coverage)",
        float(lr),
        float(p),
        bool(p < 0.05),
        {"n": n, "breaches": x, "observed_rate": round(rate, 6), "expected_rate": alpha},
    )


def christoffersen_independence(returns: pd.Series, var: pd.Series) -> TestResult:
    """Are breaches independent, or do they cluster?

    Tests a first-order Markov chain on the breach indicator: is P(breach
    tomorrow | breach today) equal to P(breach tomorrow | no breach today)? If
    not, breaches arrive in bursts — the dangerous failure Kupiec is blind to,
    because it only ever counts them.
    """
    breaches = _breaches(returns, var).to_numpy()
    if len(breaches) < 2:
        return TestResult("Christoffersen independence", float("nan"), float("nan"), False, {})

    prev, curr = breaches[:-1], breaches[1:]
    n00 = int(np.sum((prev == 0) & (curr == 0)))
    n01 = int(np.sum((prev == 0) & (curr == 1)))
    n10 = int(np.sum((prev == 1) & (curr == 0)))
    n11 = int(np.sum((prev == 1) & (curr == 1)))

    counts = {"n00": n00, "n01": n01, "n10": n10, "n11": n11}

    # Transition probabilities out of the no-breach and breach states.
    pi01 = n01 / (n00 + n01) if (n00 + n01) else 0.0
    pi11 = n11 / (n10 + n11) if (n10 + n11) else 0.0
    pi = (n01 + n11) / len(curr)

    # Degenerate cases (no breaches at all, or every day a breach) carry no
    # information about clustering. Returning "not rejected" with the counts
    # attached is honest; computing a statistic from log(0) would not be.
    if pi in (0.0, 1.0) or (n10 + n11) == 0:
        return TestResult(
            "Christoffersen independence",
            0.0,
            1.0,
            False,
            {**counts, "note": "degenerate breach sequence — test uninformative"},
        )

    def _ll(p, k, n):
        if p <= 0 or p >= 1:
            return 0.0
        return k * np.log(p) + (n - k) * np.log(1 - p)

    ll_null = _ll(pi, n01 + n11, len(curr))
    ll_alt = _ll(pi01, n01, n00 + n01) + _ll(pi11, n11, n10 + n11)
    lr = -2 * (ll_null - ll_alt)
    p_value = 1 - stats.chi2.cdf(lr, df=1)

    return TestResult(
        "Christoffersen independence",
        float(lr),
        float(p_value),
        bool(p_value < 0.05),
        {
            **counts,
            "p_breach_after_calm": round(pi01, 6),
            "p_breach_after_breach": round(pi11, 6),
            # The interpretable number: how much more likely a breach is on the
            # day after a breach. >1 means clustering.
            "clustering_ratio": round(pi11 / pi01, 4) if pi01 else None,
        },
    )


def christoffersen_conditional_coverage(
    returns: pd.Series, var: pd.Series, alpha: float = 0.05
) -> TestResult:
    """Joint test: correct breach rate AND independent breaches.

    LR_cc = LR_uc + LR_ind, chi-square with 2 df. Reported alongside its two
    components rather than instead of them — a rejection here doesn't say
    *which* half failed, and the remedy differs completely.
    """
    uc = kupiec_pof(returns, var, alpha)
    ind = christoffersen_independence(returns, var)
    if np.isnan(uc.statistic) or np.isnan(ind.statistic):
        return TestResult(
            "Christoffersen conditional coverage", float("nan"), float("nan"), False, {}
        )

    lr = uc.statistic + ind.statistic
    p_value = 1 - stats.chi2.cdf(lr, df=2)
    return TestResult(
        "Christoffersen conditional coverage",
        float(lr),
        float(p_value),
        bool(p_value < 0.05),
        {"lr_uncond": round(uc.statistic, 4), "lr_indep": round(ind.statistic, 4)},
    )


def acerbi_szekely_z2(
    returns: pd.Series, var: pd.Series, es: pd.Series, alpha: float = 0.05
) -> TestResult:
    """Expected Shortfall backtest (Acerbi–Szekely Z2).

    ES is not elicitable — there is no scoring function it uniquely minimises —
    so it cannot be backtested the way VaR is. Z2 sidesteps that by conditioning
    on the breach set.

    **Sign convention, which is the easy thing to get wrong here.** The
    published Z2 is written with ES as a POSITIVE magnitude and returns
    negative. This codebase stores ES/CVaR as a NEGATIVE loss (`cvar_95_21d` is
    negative, consistently with `var_95_21d`), which flips the sign of the
    ratio. Computing the textbook formula against negative ES therefore yields
    the opposite sign to every published example — the first version of this
    function returned +1 where the literature says -1, and its one-sided
    p-value consequently tested the wrong tail, so an ES understating the tail
    by 2x came back "pass". The negation below restores the standard
    orientation so results are comparable to the reference:

        Z2 ~  0  ES is accurate
        Z2 <  0  breaches were WORSE than ES predicted (understates the tail —
                 the direction that matters for capital)
        Z2 >  0  ES is conservative

    p-value by bootstrap rather than from a closed form: the null distribution
    depends on the (unknown) true return distribution, and assuming normality
    here would import exactly the tail assumption the test is meant to check.
    """
    frame = pd.concat(
        [returns.rename("r"), var.rename("var"), es.rename("es")], axis=1
    ).dropna()
    if frame.empty:
        return TestResult("Acerbi-Szekely Z2 (ES)", float("nan"), float("nan"), False, {"n": 0})

    n = len(frame)
    breached = frame[frame["r"] < frame["var"]]
    if breached.empty:
        return TestResult(
            "Acerbi-Szekely Z2 (ES)",
            0.0,
            1.0,
            False,
            {"n": n, "breaches": 0, "note": "no breaches — ES untested"},
        )

    # ES is negative (a loss). Guard against a zero/positive ES, which would
    # make the ratio meaningless rather than merely large.
    valid = breached[breached["es"] < 0]
    if valid.empty:
        return TestResult(
            "Acerbi-Szekely Z2 (ES)", float("nan"), float("nan"), False,
            {"n": n, "note": "no valid (negative) ES values on breach days"},
        )

    def _z2(rows: pd.DataFrame) -> float:
        # Negated — see the sign-convention note in the docstring.
        return -float((rows["r"] / (n * alpha * rows["es"])).sum() - 1)

    z2 = _z2(valid)

    # Bootstrap over the BREACH SET, not over the full return series.
    #
    # The first version resampled returns and re-applied the same VaR/ES path.
    # That is circular: the resampled breaches inherit the very ES error being
    # tested, so the null distribution centres on the observed statistic and
    # the p-value sits near 0.5 no matter how wrong ES is. An ES understating
    # the tail by 2x scored Z2 = -1 and still came back "pass".
    #
    # H0 is "breaches were as severe as ES predicted", i.e. Z2 = 0. Resampling
    # the observed (return, ES) breach pairs gives the sampling distribution of
    # Z2, and the p-value is how much of it reaches 0 or better.
    rng = np.random.default_rng(12345)  # fixed so the p-value is reproducible
    breach_rows = valid[["r", "es"]].to_numpy()
    simulated = np.empty(2000)
    for i in range(2000):
        idx = rng.integers(0, len(breach_rows), size=len(breach_rows))
        sample = breach_rows[idx]
        simulated[i] = -float((sample[:, 0] / (n * alpha * sample[:, 1])).sum() - 1)

    # One-sided: the risk is ES understating the tail (Z2 < 0). An ES that is
    # too conservative costs money but is not a safety failure, so it is not
    # flagged. p = P(Z2* >= 0), the mass of the bootstrap distribution
    # consistent with an adequate ES.
    p_value = float(np.mean(simulated >= 0.0))

    return TestResult(
        "Acerbi-Szekely Z2 (ES)",
        z2,
        p_value,
        bool(p_value < 0.05),
        {
            "n": n,
            "breaches": len(valid),
            "mean_breach_return": round(float(valid["r"].mean()), 6),
            "mean_predicted_es": round(float(valid["es"].mean()), 6),
            # The plain-language version: how much worse the average breach was
            # than ES said it would be. >1 means ES understated severity.
            "severity_ratio": round(
                float(valid["r"].mean() / valid["es"].mean()), 4
            )
            if valid["es"].mean()
            else None,
        },
    )


def breach_clustering_profile(returns: pd.Series, var: pd.Series) -> dict:
    """Descriptive view of *when* breaches happened, not just how many.

    Complements the independence test: the LR statistic says clustering exists,
    this says what it looks like — longest run, how many arrive in multi-day
    bursts, and the worst single month.
    """
    breaches = _breaches(returns, var)
    if breaches.empty:
        return {}

    values = breaches.to_numpy()
    runs, current = [], 0
    for v in values:
        if v:
            current += 1
        elif current:
            runs.append(current)
            current = 0
    if current:
        runs.append(current)

    by_month = breaches.groupby(pd.Grouper(freq="ME")).sum() if len(breaches) else pd.Series()
    worst_month = by_month.idxmax() if len(by_month) and by_month.max() > 0 else None

    return {
        "total_breaches": int(values.sum()),
        "longest_consecutive_run": max(runs) if runs else 0,
        "runs_of_2_or_more": sum(1 for r in runs if r >= 2),
        "share_in_multiday_runs": round(
            sum(r for r in runs if r >= 2) / values.sum(), 4
        )
        if values.sum()
        else 0.0,
        "worst_month": str(worst_month.date()) if worst_month is not None else None,
        "worst_month_breaches": int(by_month.max()) if len(by_month) else 0,
    }


def run_full_suite(
    returns: pd.Series,
    var: pd.Series,
    es: Optional[pd.Series] = None,
    alpha: float = 0.05,
) -> dict:
    """All tail tests together, plus the clustering profile.

    Returned as a dict rather than printed so callers (scripts/validate_tail.py,
    tests) can assert on it.
    """
    results = {
        "kupiec_pof": kupiec_pof(returns, var, alpha),
        "christoffersen_independence": christoffersen_independence(returns, var),
        "christoffersen_conditional_coverage": christoffersen_conditional_coverage(
            returns, var, alpha
        ),
    }
    if es is not None:
        results["acerbi_szekely_z2"] = acerbi_szekely_z2(returns, var, es, alpha)
    return {
        "tests": results,
        "clustering": breach_clustering_profile(returns, var),
    }
