"""Both sides of a tail comparison must come from one return convention.

Conflict 1 in docs_internal/RETURN_CONVENTION_AUDIT.md: `validate_tail.py`
graded a forecast derived from `log_return` against realised losses read from
`pct_return`. The two differ by r - log(1+r) ~ r^2/2, always in the direction
that understates a loss, so breaches were undercounted.

These tests are behavioural — constructed frames go in and results are
asserted — rather than source-text checks, so they survive any refactor that
keeps the behaviour and fail on any that does not.
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_REPO = Path(__file__).resolve().parents[1]
_SCRIPT = _REPO / "scripts" / "validate_tail.py"


def _module():
    spec = importlib.util.spec_from_file_location("_validate_tail_conv", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _ohlcv(n: int = 400, seed: int = 3, scale: float = 0.02) -> pd.DataFrame:
    """A frame volatile enough that the two conventions differ measurably."""
    rng = np.random.default_rng(seed)
    close = 100.0 * np.exp(np.cumsum(rng.normal(0.0, scale, n)))
    idx = pd.bdate_range("2023-01-02", periods=n)
    frame = pd.DataFrame(
        {
            "open": close * 0.999,
            "high": close * 1.004,
            "low": close * 0.996,
            "close": close,
            "volume": np.full(n, 1_000_000.0),
        },
        index=idx,
    )
    frame.index.name = "date"
    return frame


# ── the pairing itself ───────────────────────────────────────────────────────


def test_realised_losses_use_the_forecast_convention():
    """The fix, stated as a value comparison rather than a column name.

    The prepared realised series must equal the log returns of the same frame,
    not its simple returns — checked against independently recomputed values so
    that renaming a column cannot make this pass vacuously.
    """
    module = _module()
    raw = _ohlcv()
    prepared = module._prepare(raw)

    from stock_risk.data.preprocessor import DataPreprocessor

    processed = DataPreprocessor().process(raw)
    expected_log = processed["log_return"].reindex(prepared.index)
    expected_simple = processed["pct_return"].reindex(prepared.index)

    pd.testing.assert_series_equal(
        prepared["return"], expected_log, check_names=False
    )
    # And is measurably NOT the simple series — otherwise the assertion above
    # would also pass on a frame where the two happen to coincide.
    assert not np.allclose(prepared["return"], expected_simple)


def test_the_prepared_frame_states_its_convention():
    module = _module()
    prepared = module._prepare(_ohlcv())
    assert prepared.attrs["return_convention"] == module.RETURN_CONVENTION
    assert prepared.attrs["forecast_convention"] == module.RETURN_CONVENTION


def test_a_mismatched_pairing_is_refused():
    """The guard, exercised on a deliberately mismatched frame.

    This is the acceptance criterion: feed in two sides with different
    conventions and the behaviour must fail. A source-text assertion could not
    express this.
    """
    module = _module()
    mismatched = module._prepare(_ohlcv(), return_column="pct_return")

    with pytest.raises(ValueError, match="pct_return"):
        module._assert_conventions_agree(mismatched, "TEST")


def test_the_guard_passes_the_matched_pairing():
    """Control: the guard must not fire on the correct pairing, or it would be
    indistinguishable from an unconditional failure."""
    module = _module()
    module._assert_conventions_agree(module._prepare(_ohlcv()), "TEST")


def test_the_simple_convention_undercounts_breaches():
    """Why the mismatch mattered, measured rather than argued.

    Simple returns exceed log returns for every non-zero move, so a realised
    series read from `pct_return` sits above the true loss and crosses the VaR
    line less often. The direction of the error is what makes this a defect
    rather than a wash.
    """
    module = _module()
    # scale/n chosen so the frame HAS near-boundary observations. A quieter
    # fixture gives zero, and the test would then pass while exercising
    # nothing — the same near-boundary mechanic measured on the real
    # snapshots, where four of six moved not at all.
    raw = _ohlcv(n=500, seed=0, scale=0.05)

    matched = module._prepare(raw)
    mismatched = module._prepare(raw, return_column="pct_return")

    breaches_log = int((matched["return"] < matched["var"]).sum())
    breaches_simple = int((mismatched["return"] < mismatched["var"]).sum())

    assert breaches_simple <= breaches_log
    assert breaches_log > breaches_simple, (
        "this fixture was chosen to have near-boundary observations; if the two "
        "agree, it no longer exercises the difference"
    )


# ── pct_return has no consumers ──────────────────────────────────────────────


def test_pct_return_has_no_consumers():
    """`pct_return` is kept but is now read by nothing.

    Deliberately not deleted (that would touch DataPreprocessor and the
    inventory pins in PR #39), so this records the fact instead. If code starts
    reading it again, that is a convention decision someone should make
    explicitly — and this test turning red is the prompt to make it.
    """
    tracked = subprocess.run(
        ["git", "ls-files", "src/", "scripts/"],
        cwd=_REPO, capture_output=True, text=True, check=True,
    ).stdout.split()

    offenders = []
    for rel in tracked:
        if not rel.endswith(".py"):
            continue
        text = (_REPO / rel).read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), 1):
            if "pct_return" not in line:
                continue
            stripped = line.strip()
            # Writes are not consumers. The column is deliberately still
            # produced — by DataPreprocessor and by validate_score.py's own
            # frame builder — and this test is about whether anything READS it.
            if re.match(r"^\w+\[[\"']pct_return[\"']\]\s*=", stripped):
                continue
            # Prose is not a consumer. Comments and docstring lines naming the
            # column — including the ones explaining why it is no longer read —
            # must not register, or documenting the decision would break this.
            if stripped.startswith("#") or stripped.startswith('"""') or '"""' in stripped:
                continue
            if not any(
                token in line
                for token in ('["pct_return"]', "['pct_return']", ".pct_return")
            ):
                continue
            offenders.append(f"{rel}:{lineno}: {stripped}")

    assert offenders == [], (
        "pct_return has acquired consumers; decide the convention deliberately:\n"
        + "\n".join(offenders)
    )
