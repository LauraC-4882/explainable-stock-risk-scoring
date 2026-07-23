"""Statistics for the simulated-user experiments — user-level, seeded, honest.

Design commitments the framework requires:

* **The unit of analysis is the simulated user, never the click.** Every function
  here consumes one value per user (a paired difference or a per-user outcome), so
  repeated events from one user are collapsed before inference.
* **Seeded bootstrap**, so a reported confidence interval is reproducible.
* **No-effect vs inconclusive are different verdicts.** A CI that sits entirely
  inside +/- MDE is evidence of *no meaningful effect*; a CI wider than the MDE
  that still crosses zero is *inconclusive* (underpowered). Collapsing the two is
  the classic misread this guards against.
* **Multiple comparisons are corrected** (Holm or Benjamini-Hochberg) whenever
  several segments are tested, and confirmatory vs exploratory is labelled by the
  caller.

Pure ``numpy`` — no wall clock, no global RNG.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np

Verdict = Literal["positive_effect", "negative_effect", "no_effect", "inconclusive"]


@dataclass
class EffectEstimate:
    mean_diff: float          # treatment - control (per-user paired mean)
    ci_low: float
    ci_high: float
    p_value: float
    n_users: int
    verdict: Verdict

    def to_dict(self) -> dict:
        return {
            "mean_diff": round(self.mean_diff, 4),
            "ci_low": round(self.ci_low, 4),
            "ci_high": round(self.ci_high, 4),
            "p_value": round(self.p_value, 4),
            "n_users": self.n_users,
            "verdict": self.verdict,
        }


def paired_bootstrap(
    control: list[float],
    treatment: list[float],
    *,
    seed: int,
    n_boot: int = 2000,
    alpha: float = 0.05,
    mde: float = 0.05,
) -> EffectEstimate:
    """Paired (within-user) bootstrap of the mean treatment-minus-control effect.

    ``control``/``treatment`` are aligned per-user outcomes (0/1 or continuous).
    Resamples users (not observations) with replacement, so the interval reflects
    user-level uncertainty. The two-sided p-value is the bootstrap mass on the far
    side of zero, doubled and clamped to 1.
    """
    if len(control) != len(treatment):
        raise ValueError("control and treatment must be aligned per user")
    diffs = np.asarray(treatment, dtype=float) - np.asarray(control, dtype=float)
    n = len(diffs)
    if n == 0:
        raise ValueError("need at least one user")
    rng = np.random.default_rng([int(seed), 4242, n])
    idx = rng.integers(0, n, size=(n_boot, n))
    boot_means = diffs[idx].mean(axis=1)
    observed = float(diffs.mean())
    lo = float(np.quantile(boot_means, alpha / 2))
    hi = float(np.quantile(boot_means, 1 - alpha / 2))
    # Two-sided bootstrap p: mass on the opposite side of 0 from the estimate.
    if observed >= 0:
        p = 2.0 * float((boot_means <= 0).mean())
    else:
        p = 2.0 * float((boot_means >= 0).mean())
    p = min(1.0, p)
    return EffectEstimate(observed, lo, hi, p, n, classify_effect(lo, hi, mde))


def classify_effect(ci_low: float, ci_high: float, mde: float) -> Verdict:
    """Turn a CI + MDE into one of four honest verdicts."""
    if ci_low > 0:
        return "positive_effect"
    if ci_high < 0:
        return "negative_effect"
    # CI crosses zero: is it tight enough to call "no meaningful effect"?
    if ci_low >= -mde and ci_high <= mde:
        return "no_effect"
    return "inconclusive"


def holm(p_values: list[float]) -> list[float]:
    """Holm-Bonferroni step-down adjusted p-values (family-wise error control)."""
    m = len(p_values)
    order = sorted(range(m), key=lambda i: p_values[i])
    adjusted = [0.0] * m
    running = 0.0
    for rank, i in enumerate(order):
        val = (m - rank) * p_values[i]
        running = max(running, val)
        adjusted[i] = min(1.0, running)
    return adjusted


def benjamini_hochberg(p_values: list[float]) -> list[float]:
    """Benjamini-Hochberg adjusted p-values (false-discovery-rate control)."""
    m = len(p_values)
    order = sorted(range(m), key=lambda i: p_values[i])
    adjusted = [0.0] * m
    running = 1.0
    for rank in range(m - 1, -1, -1):
        i = order[rank]
        val = p_values[i] * m / (rank + 1)
        running = min(running, val)
        adjusted[i] = min(1.0, running)
    return adjusted
