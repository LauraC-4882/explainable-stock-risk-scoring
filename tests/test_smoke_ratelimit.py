"""The smoke harness's rate-limit classifier: exit 75 (skip) vs exit 1 (fail)
hinges entirely on this predicate, so each recognition path gets a test.
Loaded via importlib because scripts/ is deliberately not a package."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_SMOKE_PATH = Path(__file__).parent.parent / "scripts" / "smoke.py"
_spec = importlib.util.spec_from_file_location("smoke", _SMOKE_PATH)
smoke = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(smoke)


class YFRateLimitError(Exception):
    """Same class name as yfinance's — the classifier matches by name so it
    never needs to import yfinance internals."""


def test_recognizes_yfinance_exception_by_class_name():
    assert smoke.is_rate_limit_failure(YFRateLimitError("Too Many Requests"))


def test_recognizes_rate_limit_message_on_any_exception_type():
    assert smoke.is_rate_limit_failure(
        RuntimeError("Too Many Requests. Rate limited. Try after a while.")
    )


def test_recognizes_wrapped_cause_chain():
    try:
        try:
            raise YFRateLimitError("Too Many Requests")
        except YFRateLimitError as inner:
            raise AssertionError("GET /api/score/AAPL -> HTTP 500") from inner
    except AssertionError as outer:
        assert smoke.is_rate_limit_failure(outer)


def test_ordinary_failure_is_not_classified_as_rate_limit():
    assert not smoke.is_rate_limit_failure(
        TypeError("Object of type float32 is not JSON serializable")
    )
    assert not smoke.is_rate_limit_failure(AssertionError("GET /health -> HTTP 500"))


def test_exit_code_is_ex_tempfail():
    assert smoke.EXIT_RATE_LIMITED == 75
