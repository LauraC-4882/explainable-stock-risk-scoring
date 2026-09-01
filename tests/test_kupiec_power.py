"""The power analysis, and the document that quotes it, must agree.

Two things are pinned here:

* the arithmetic — the power routine reproduces the suite's own decision rule,
  and the structural-zero claim in Part 2 is checked rather than asserted;
* the document — every power figure in KUPIEC_POWER_ANALYSIS.md is recomputed
  and compared, so the prose cannot drift away from the script that produced it.

The second is the reason the numbers are not hardcoded anywhere: a figure typed
into a document is a figure nobody re-derives.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_REPO = Path(__file__).resolve().parents[1]
_SCRIPT = _REPO / "scripts" / "kupiec_power.py"
_DOC = _REPO / "docs_internal" / "KUPIEC_POWER_ANALYSIS.md"


def _module():
    spec = importlib.util.spec_from_file_location("_kupiec_power", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ── the statistic matches the one the suite actually uses ────────────────────


def test_power_routine_reproduces_the_suites_statistic():
    """A power analysis of a re-derived statistic measures a different test."""
    from stock_risk.validation.tail_tests import kupiec_pof

    module = _module()
    import pandas as pd

    n, breach_count = 400, 30
    returns = np.full(n, -0.001)
    returns[:breach_count] = -0.10
    var = np.full(n, -0.05)
    result = kupiec_pof(pd.Series(returns), pd.Series(var), alpha=module.ALPHA)

    mine = module.kupiec_lr(n, np.array([breach_count]), module.ALPHA)[0]
    assert mine == pytest.approx(result.statistic, rel=1e-12)


def test_zero_breaches_uses_the_same_special_case():
    module = _module()
    n = 300
    assert module.kupiec_lr(n, np.array([0]), 0.05)[0] == pytest.approx(
        -2 * n * np.log(0.95), rel=1e-12
    )


# ── Part 1: the power figures ────────────────────────────────────────────────


def test_power_at_the_null_equals_the_significance_level():
    """Sanity floor: at a true rate of exactly 5% the rejection probability is
    the test's size, not something else."""
    module = _module()
    n = 429
    mask = module.rejection_mask_chi2(n)
    assert module.power(n, module.ALPHA, mask) == pytest.approx(0.05, abs=0.02)


def test_power_increases_with_the_size_of_the_miss():
    module = _module()
    n = 429
    mask = module.rejection_mask_chi2(n)
    curve = [module.power(n, r, mask) for r in (0.06, 0.07, 0.08, 0.09, 0.10)]
    assert curve == sorted(curve)


def test_six_percent_power_is_below_one_fifth_at_this_sample_size():
    """The headline of Part 1, pinned so it cannot quietly stop being true.

    If a future change to the estimator window moves n far enough that this
    passes comfortably, the document's central claim needs rewriting — and this
    going red is the notification.
    """
    module = _module()
    for n in (428, 429, 478):
        mask = module.rejection_mask_chi2(n)
        assert module.power(n, 0.06, mask) < 0.20


def test_the_two_decision_rules_agree():
    module = _module()
    n = 429
    chi2_mask = module.rejection_mask_chi2(n)
    exact_mask = module.rejection_mask_exact(n)
    for rate in (0.06, 0.07, 0.08):
        gap = abs(module.power(n, rate, chi2_mask) - module.power(n, rate, exact_mask))
        assert gap < 0.01


# ── Part 2: the structural-zero claim, checked not asserted ──────────────────


def test_the_statistic_ignores_breach_magnitude():
    """Part 2's premise: LR_uc reads the count, never the sizes.

    Two return series with identical breach counts and wildly different loss
    magnitudes must produce the identical statistic — which is what makes the
    power against a fatter tail structurally zero rather than merely small.
    """
    import pandas as pd

    from stock_risk.validation.tail_tests import kupiec_pof

    n = 400
    var = pd.Series(np.full(n, -0.05))

    mild = np.full(n, -0.001)
    mild[:25] = -0.06  # 25 breaches, only just past the line
    severe = np.full(n, -0.001)
    severe[:25] = -0.60  # same 25 breaches, ten times the loss

    a = kupiec_pof(pd.Series(mild), var, alpha=0.05)
    b = kupiec_pof(pd.Series(severe), var, alpha=0.05)

    assert a.statistic == pytest.approx(b.statistic, rel=1e-12)
    assert a.p_value == pytest.approx(b.p_value, rel=1e-12)


def test_the_statistic_ignores_breach_order():
    """The clustering half of the same argument."""
    import pandas as pd

    from stock_risk.validation.tail_tests import kupiec_pof

    n = 400
    var = pd.Series(np.full(n, -0.05))

    clustered = np.full(n, -0.001)
    clustered[:25] = -0.10  # all 25 breaches consecutive
    spread = np.full(n, -0.001)
    spread[:: n // 25][:25] = -0.10  # the same 25, evenly spaced

    a = kupiec_pof(pd.Series(clustered), var, alpha=0.05)
    b = kupiec_pof(pd.Series(spread), var, alpha=0.05)

    assert a.detail["breaches"] == b.detail["breaches"] == 25
    assert a.statistic == pytest.approx(b.statistic, rel=1e-12)


def test_christoffersen_does_see_the_order_kupiec_ignores():
    """The control for the pair above: if no test in the suite noticed the
    difference, "each test is blind to what the others measure" would be an
    excuse rather than a division of labour."""
    import pandas as pd

    from stock_risk.validation.tail_tests import christoffersen_independence

    n = 400
    var = pd.Series(np.full(n, -0.05))

    clustered = np.full(n, -0.001)
    clustered[:25] = -0.10
    spread = np.full(n, -0.001)
    spread[:: n // 25][:25] = -0.10

    a = christoffersen_independence(pd.Series(clustered), var)
    b = christoffersen_independence(pd.Series(spread), var)

    assert a.statistic != pytest.approx(b.statistic, rel=1e-6)


# ── the document quotes the script ───────────────────────────────────────────


def test_the_documents_sample_sizes_match_the_current_snapshots():
    """The document's `n` column must be today's data, not the day it was written.

    This is the check the first version of this file was missing, and the miss
    is instructive: power was recomputed from the *document's own* n, so when a
    daily snapshot refresh moved n from 429 to 428 the quoted power (0.169) and
    the recomputed power (0.169, from 429) still agreed. The table was
    internally consistent and externally stale, and every test stayed green.

    A guard anchored to a document's self-consistency verifies nothing about the
    world. Anchor it to the world.
    """
    module = _module()
    text = _DOC.read_text(encoding="utf-8")

    actual = {}
    for path in module.tracked_snapshots():
        ticker = path.name.replace("_2y_1d.parquet", "")
        actual[ticker] = module.usable_n(pd.read_parquet(path))

    row = re.compile(r"^\|\s*(?:\*\*)?([A-Z0-9_]+)(?:\*\*)?\s*\|\s*(\d+)\s*\|", re.M)
    quoted = {
        m.group(1): int(m.group(2))
        for m in row.finditer(text)
        if m.group(1) != "POOLED"
    }

    assert quoted, "no per-snapshot rows parsed from the document"
    for ticker, n in quoted.items():
        assert ticker in actual, f"document quotes {ticker}, which is not a tracked snapshot"
        assert n == actual[ticker], (
            f"{ticker}: document says n={n}, the snapshots now give n={actual[ticker]}. "
            "Re-run scripts/kupiec_power.py and update the table."
        )


def test_every_power_figure_in_the_document_is_reproducible():
    """No figure in the analysis may be hand-typed.

    Parses the per-snapshot table and recomputes each cell. A number that drifts
    from the script — because the estimator window moved, or because someone
    edited the prose — fails here rather than being quietly wrong.

    Note this recomputes from the document's own `n`, so it catches a mistyped
    power value but NOT a stale sample size; that is
    test_the_documents_sample_sizes_match_the_current_snapshots' job. The two
    together are what bind the table to reality.
    """
    module = _module()
    text = _DOC.read_text(encoding="utf-8")

    alternatives = [0.06, 0.07, 0.08, 0.09, 0.10]
    row = re.compile(
        r"^\|\s*(?:\*\*)?([A-Z0-9_]+)(?:\*\*)?\s*\|\s*(\d+)\s*\|(.+)\|\s*$", re.M
    )

    checked = 0
    for match in row.finditer(text):
        ticker, n_text, cells = match.groups()
        if ticker == "POOLED":
            continue
        n = int(n_text)
        values = [
            float(c.strip().replace("**", ""))
            for c in cells.split("|")
            if c.strip().replace("**", "").replace(".", "").isdigit()
        ]
        if len(values) != len(alternatives):
            continue
        mask = module.rejection_mask_chi2(n)
        for rate, quoted in zip(alternatives, values):
            assert module.power(n, rate, mask) == pytest.approx(quoted, abs=5e-4), (
                f"{ticker} at {rate:.0%}: document says {quoted}, script computes "
                f"{module.power(n, rate, mask):.4f}"
            )
        checked += 1

    assert checked >= 6, f"only {checked} snapshot rows parsed from the document"


def test_the_document_marks_the_pooled_row_as_a_bound():
    text = _DOC.read_text(encoding="utf-8")
    assert "upper bound" in text.lower()
    assert "independent" in text.lower()


def test_the_document_does_not_call_the_structural_zero_low_power():
    """Wording matters here: "low" implies more data would fix it, and no
    amount would. Guarded because it is an easy edit to make by accident."""
    text = _DOC.read_text(encoding="utf-8")
    part_two = text[text.index("## Part 2"):].lower()

    assert "zero power" in part_two

    # Not a blanket ban on the phrase: the document contrasts the two
    # explicitly ("that is not low power, it is zero power"), and forbidding the
    # words outright would forbid the very sentence that draws the distinction.
    # What must not appear is the phrase used as the *description*.
    for claim in (
        "has low power",
        "power is low",
        "low power against",
        "limited power against",
    ):
        assert claim not in part_two, f"structural zero described as {claim!r}"
