"""[G1] golden test: the producer-layer refactor must not change score() output.

The fixture was generated from the PRE-refactor scorer (see
tests/golden_inputs.py for why inputs are frozen rather than captured live)
and committed; this test re-runs the identical frozen scenario against the
current code and compares field by field. Any wiring mistake in the
refactor — a dropped field, a producer's raw output mapped to the wrong
key, a changed rounding — shows up as a precise per-field diff.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from stock_risk.scoring.scorer import RiskScorer

from .golden_inputs import GOLDEN_TICKER, golden_environment

FIXTURE = Path(__file__).parent / "fixtures" / "golden_score_aapl.json"

# Floats compare with a tolerance instead of exactly: the fixture may have
# been generated on a different OS/BLAS than the machine running the test,
# and GARCH MLE / XGBoost / SHAP can differ in the last few decimals across
# numeric backends. 1e-4 relative is far tighter than any real refactoring
# bug and far looser than cross-platform float noise.
_REL = 1e-4


def _assert_deep_equal(actual, expected, path=""):
    if isinstance(expected, dict):
        assert isinstance(actual, dict), f"{path}: expected dict, got {type(actual).__name__}"
        assert set(actual) == set(expected), (
            f"{path}: keys differ — extra={set(actual) - set(expected)}, "
            f"missing={set(expected) - set(actual)}"
        )
        for k in expected:
            _assert_deep_equal(actual[k], expected[k], f"{path}.{k}")
    elif isinstance(expected, list):
        assert isinstance(actual, list) and len(actual) == len(expected), (
            f"{path}: list length {len(actual) if isinstance(actual, list) else 'n/a'} "
            f"!= {len(expected)}"
        )
        for i, (a, e) in enumerate(zip(actual, expected)):
            _assert_deep_equal(a, e, f"{path}[{i}]")
    elif isinstance(expected, float) and not isinstance(expected, bool):
        assert actual == pytest.approx(expected, rel=_REL, abs=1e-9), (
            f"{path}: {actual!r} != {expected!r}"
        )
    else:
        assert actual == expected, f"{path}: {actual!r} != {expected!r}"


def test_score_matches_pre_refactor_golden_fixture():
    expected = json.loads(FIXTURE.read_text(encoding="utf-8"))

    with golden_environment():
        actual = RiskScorer().score(GOLDEN_TICKER)

    actual.pop("timestamp")  # the only intentionally non-deterministic field
    _assert_deep_equal(actual, expected)
