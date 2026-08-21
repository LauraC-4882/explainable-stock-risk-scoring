"""Shared test fixtures.

The rate limiter and login tracker introduced in [R2] are module-level state in
api/app.py — they have to be, since middleware runs outside FastAPI's
per-request dependency injection. That makes them shared across every test in a
session, which caused a real, confusing failure: an auth test that deliberately
exhausted the login lockout left the token bucket drained, and an unrelated
test several files later got a 429 instead of the 401 it asserted on.

So: rate limiting is OFF by default for tests, and the state is reset between
every test regardless. Tests that actually exercise the limiter opt in with the
`rate_limited` fixture, which turns it back on for the duration.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def reset_security_state():
    """Clear rate-limit / lockout state and disable limiting by default.

    Autouse so no test can accidentally inherit another's exhausted bucket. The
    reset runs before AND after: before so this test starts clean, after so a
    test that opted into limiting can't leave a drained bucket behind.
    """
    from stock_risk.api import app as app_module
    from stock_risk.config import settings

    def _clear():
        app_module._anon_limiter.reset()
        app_module._user_limiter.reset()
        app_module._login_tracker.reset()
        app_module._score_cache.clear()

    original = settings.rate_limit_enabled
    settings.rate_limit_enabled = False
    _clear()
    try:
        yield
    finally:
        settings.rate_limit_enabled = original
        _clear()


@pytest.fixture(autouse=True)
def hermetic_data_source_config():
    """Neutralise the developer's real .env for the duration of every test.

    Found the hard way: CLAUDE.md tells you to put TWELVE_DATA_KEY in .env (the
    US cross-sectional build and training both want it), and the moment you do,
    ten fetcher/scoring-error tests fail locally — they assert the unset-key
    routing (US tickers -> yfinance, throttle -> snapshot fallback) that CI
    sees, while your shell sees Twelve Data routing instead. A suite whose
    result depends on whether you followed the project's own setup instructions
    trains people to ignore red.

    Same design as reset_security_state above: force the neutral default here,
    and let a test that wants a key set it explicitly (test_data.py already
    does, via monkeypatch, which overrides this and restores itself).
    """
    from stock_risk.config import settings

    original = settings.twelve_data_key
    settings.twelve_data_key = None
    try:
        yield
    finally:
        settings.twelve_data_key = original


@pytest.fixture()
def rate_limited():
    """Opt back into rate limiting for a test that's exercising it."""
    from stock_risk.config import settings

    settings.rate_limit_enabled = True
    yield
    settings.rate_limit_enabled = False
