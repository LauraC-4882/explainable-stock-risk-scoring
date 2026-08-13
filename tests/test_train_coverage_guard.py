"""scripts/train.py's universe-coverage guard.

Regression test for a real incident, reproduced here because the failure was
silent and expensive: a rate-limited training run reached 1 of 56 requested
tickers, trained on that one stock, overwrote the deployed 56-ticker champion,
scored 0.609 mean walk-forward AUC — and CLEARED the registry's 0.60 validation
gate, because that gate grades metrics and has nothing to say about whether the
data behind them was adequate.

Loaded via importlib because scripts/ is not an installed package (same
approach as test_cn_names.py).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_TRAIN = Path(__file__).resolve().parents[1] / "scripts" / "train.py"


def _load():
    spec = importlib.util.spec_from_file_location("train_script", _TRAIN)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


train_script = _load()

UNIVERSE = [f"T{i}" for i in range(56)]


def _usable(n: int) -> dict:
    return {ticker: object() for ticker in UNIVERSE[:n]}


def test_the_incident_is_blocked():
    """1 of 56 — the exact shape of the run that replaced the champion."""
    with pytest.raises(train_script.InsufficientUniverseError) as exc:
        train_script._require_universe_coverage(UNIVERSE, _usable(1), min_coverage=0.8)
    message = str(exc.value)
    # The message has to name the numbers and say nothing was written, because
    # the failure mode it replaces was a run that looked like a success.
    assert "1/56" in message
    assert "Nothing was written" in message


def test_it_raises_rather_than_warning():
    """A warning is what the original run effectively had — 55 'Skipping X'
    lines in a log nobody reads until the model is already replaced."""
    with pytest.raises(train_script.InsufficientUniverseError):
        train_script._require_universe_coverage(UNIVERSE, _usable(30), min_coverage=0.8)


def test_full_coverage_passes():
    train_script._require_universe_coverage(UNIVERSE, _usable(56), min_coverage=0.8)


def test_a_couple_of_legitimate_dropouts_still_pass():
    """Delistings and symbol changes are normal in a large universe. A guard
    that fails the run for one missing name is a guard people switch off."""
    train_script._require_universe_coverage(UNIVERSE, _usable(50), min_coverage=0.8)


def test_the_floor_is_overridable_for_a_deliberately_small_run():
    """--min-coverage exists so training on a handful of names on purpose is
    still possible; the default just stops it happening by accident."""
    train_script._require_universe_coverage(UNIVERSE, _usable(1), min_coverage=0.0)


def test_default_tickers_run_is_unaffected():
    """The 3-ticker default must not trip its own guard when all three work."""
    tickers = ["AAPL", "MSFT", "GOOGL"]
    train_script._require_universe_coverage(
        tickers, {t: object() for t in tickers}, min_coverage=0.8
    )
