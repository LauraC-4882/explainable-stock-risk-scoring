"""Power of the Kupiec POF test at this repository's actual sample sizes.

Answers one question and refuses another.

**Answers**: if the true breach rate is not 5%, how often does this test say so?
That is the alternative Kupiec is built for — it is a likelihood-ratio test on a
binomial count — and the answer turns out to be "less often than the word
'passed' suggests" at n ~ 430.

**Refuses**: how much power it has against a fatter left tail, or against
clustered breaches. Neither is a power question. `LR_uc` is a function of the
breach *count* alone, so its distribution is pointwise identical under any
alternative that leaves the count distribution alone. That is structural, not a
sample-size problem, and `power_report` states it as a result rather than a
caveat. Those alternatives are what the other three tests in the suite are for.

Power is computed by exact enumeration over the binomial distribution, not by
simulation: n is at most a few thousand, so every possible breach count can be
visited and the answer is deterministic. Two decision rules are evaluated —
the chi-square asymptotic one the suite actually uses, and an exact binomial
rule — because a test whose power depends on which critical region you assume
should say so.

    python scripts/kupiec_power.py
    python scripts/kupiec_power.py --json out.json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy import stats  # noqa: E402

from stock_risk.data.preprocessor import DataPreprocessor  # noqa: E402
from stock_risk.features.risk_metrics import RiskMetrics  # noqa: E402

SNAPSHOT_DIR = Path("snapshots")
ALPHA = 0.05  # the coverage level under test
SIGNIFICANCE = 0.05  # the level at which the suite rejects
ALTERNATIVES = (0.06, 0.07, 0.08, 0.09, 0.10)
CURVE = np.round(np.arange(0.050, 0.1001, 0.0025), 4)


def kupiec_lr(n: int, x: np.ndarray, alpha: float = ALPHA) -> np.ndarray:
    """The suite's LR statistic, vectorised over every possible breach count.

    Mirrors validation/tail_tests.py exactly, including its x == 0 branch. A
    power analysis of a re-derived statistic would be a power analysis of a
    different test.
    """
    x = np.asarray(x, dtype=float)
    rate = x / n
    with np.errstate(divide="ignore", invalid="ignore"):
        lr = -2.0 * (
            (n - x) * np.log(1 - alpha)
            + x * np.log(alpha)
            - (n - x) * np.log1p(-rate)
            - x * np.log(rate)
        )
    lr = np.where(x == 0, -2.0 * n * np.log(1 - alpha), lr)
    return lr


def rejection_mask_chi2(n: int, alpha: float = ALPHA) -> np.ndarray:
    """Which breach counts the suite rejects: 1 - chi2.cdf(LR, 1) < 0.05."""
    x = np.arange(n + 1)
    p = 1.0 - stats.chi2.cdf(kupiec_lr(n, x, alpha), df=1)
    return p < SIGNIFICANCE


def rejection_mask_exact(n: int, alpha: float = ALPHA) -> np.ndarray:
    """An exact two-sided binomial rule, for comparison.

    Not what the suite does — included because if the two rules disagree about
    a snapshot's power, the reported number depends on an implementation
    choice, and that has to be visible rather than buried.
    """
    x = np.arange(n + 1)
    pmf = stats.binom.pmf(x, n, alpha)
    # Two-sided by the "at most as probable" convention.
    tol = 1e-12
    return np.array([pmf[pmf <= pmf[k] + tol].sum() < SIGNIFICANCE for k in x])


def power(n: int, true_rate: float, mask: np.ndarray) -> float:
    """P(reject | true breach rate), by exact enumeration."""
    return float(stats.binom.pmf(np.arange(n + 1), n, true_rate)[mask].sum())


def usable_n(raw: pd.DataFrame) -> int:
    """Rows the tail suite actually grades, matching _prepare's alignment."""
    df = RiskMetrics().compute(DataPreprocessor().process(raw))
    out = pd.DataFrame(
        {
            "return": df["log_return"],
            "var": df["var_95_100d"].shift(1),
            "es": df["cvar_95_100d"].shift(1),
        }
    )
    return len(out.dropna())


def tracked_snapshots() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "snapshots/"], capture_output=True, text=True, check=True
    ).stdout.split()
    return sorted(Path(p) for p in out if p.endswith(".parquet"))


def build_report() -> dict:
    samples = {}
    for path in tracked_snapshots():
        samples[path.name.replace("_2y_1d.parquet", "")] = usable_n(pd.read_parquet(path))
    pooled_n = sum(samples.values())

    report = {"significance": SIGNIFICANCE, "coverage": ALPHA, "per_snapshot": {}}
    for ticker, n in samples.items():
        chi2_mask = rejection_mask_chi2(n)
        exact_mask = rejection_mask_exact(n)
        report["per_snapshot"][ticker] = {
            "n": n,
            "power_chi2": {str(r): power(n, r, chi2_mask) for r in ALTERNATIVES},
            "power_exact": {str(r): power(n, r, exact_mask) for r in ALTERNATIVES},
            "curve_chi2": {str(r): power(n, r, chi2_mask) for r in CURVE},
        }

    chi2_mask = rejection_mask_chi2(pooled_n)
    exact_mask = rejection_mask_exact(pooled_n)
    report["pooled"] = {
        "n": pooled_n,
        "is_upper_bound": True,
        "power_chi2": {str(r): power(pooled_n, r, chi2_mask) for r in ALTERNATIVES},
        "power_exact": {str(r): power(pooled_n, r, exact_mask) for r in ALTERNATIVES},
        "curve_chi2": {str(r): power(pooled_n, r, chi2_mask) for r in CURVE},
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args()

    report = build_report()

    print("Kupiec POF power — exact enumeration, chi-square decision rule")
    print(f"coverage under test: {ALPHA:.0%}   reject when p < {SIGNIFICANCE}")
    print()
    header = f"{'ticker':13s} {'n':>5s} " + " ".join(f"{r:>7.0%}" for r in ALTERNATIVES)
    print(header)
    print("-" * len(header))
    for ticker, block in report["per_snapshot"].items():
        row = " ".join(f"{block['power_chi2'][str(r)]:7.3f}" for r in ALTERNATIVES)
        print(f"{ticker:13s} {block['n']:5d} {row}")

    pooled = report["pooled"]
    row = " ".join(f"{pooled['power_chi2'][str(r)]:7.3f}" for r in ALTERNATIVES)
    print(f"{'POOLED*':13s} {pooled['n']:5d} {row}")
    print()
    print("* upper bound only. The six series are four A-shares, a CSI 300 ETF and")
    print("  one US name; breaches co-occur on shared market days, while the binomial")
    print("  likelihood behind Kupiec assumes independent observations. Treating a")
    print("  correlated panel as 2,622 independent trials overstates the effective")
    print("  sample size, and therefore the power.")
    print()

    print("Decision-rule sensitivity (chi-square vs exact binomial)")
    worst = 0.0
    for ticker, block in report["per_snapshot"].items():
        for r in ALTERNATIVES:
            gap = abs(block["power_chi2"][str(r)] - block["power_exact"][str(r)])
            worst = max(worst, gap)
    print(f"  largest |chi2 - exact| across all snapshots and alternatives: {worst:.4f}")
    print()

    print("WHAT THIS TEST CANNOT SEE")
    print("  LR_uc is a function of the breach COUNT alone. Any alternative that")
    print("  leaves the count distribution unchanged leaves the statistic's")
    print("  distribution pointwise unchanged, so the rejection probability stays")
    print("  at the significance level for every n. Power against a fatter left")
    print("  tail at unchanged coverage, and against clustered breaches, is not")
    print("  low — it is zero, and no sample size changes that.")

    if args.json:
        args.json.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nWrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
