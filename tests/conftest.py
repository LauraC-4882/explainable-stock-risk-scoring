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

import atexit
import shutil
import socket
import tempfile
from pathlib import Path

import pytest

# ── Database isolation: MODULE-LEVEL on purpose, not a fixture ───────────────
#
# api/app.py calls init_db() at module level, so the baseline migration runs
# the moment any test module does `TestClient(app)` at import — during
# COLLECTION, before any fixture (session-scoped included) gets a chance to
# run. A fixture therefore cannot redirect it; only code in this conftest,
# which pytest imports before every test module, runs early enough. (Moving
# init_db out of module scope is the deferred "Plan D" architecture item —
# when that lands, this block can become an ordinary session fixture.)
#
# Two problems this solves, both demonstrated before the fix:
#   * Two concurrent pytest processes shared data/app.db and raced its
#     import-time migration — reproduced: one process died at collection
#     with "sqlite3.OperationalError: table pageview already exists".
#     tempfile.mkdtemp is per-process unique, so each run now migrates its
#     own file.
#   * DATABASE_URL from a developer's .env would point the whole suite at a
#     real external database. Neutralised here exactly like TWELVE_DATA_KEY
#     in hermetic_data_source_config below, and for the same reason: the
#     suite's result must not depend on whether you followed the project's
#     own setup instructions.
#
# Rebinding db.engine here is sufficient for every consumer: get_session()
# and run_migrations() read the module global at call time, and the two
# `from ..db import engine` sites (api/app.py, alerts/checker.py) are only
# imported after this conftest has run.
from stock_risk import db as _db  # noqa: E402
from stock_risk.config import settings as _settings  # noqa: E402

_TEST_DB_DIR = Path(tempfile.mkdtemp(prefix="stock_risk_test_db_"))
atexit.register(shutil.rmtree, _TEST_DB_DIR, ignore_errors=True)

_settings.database_url = None
_settings.db_path = _TEST_DB_DIR / "app.db"
_db.engine.dispose()
_test_db_url = _db.resolve_db_url(_settings.database_url, _settings.db_path)
_db.engine = _db.create_engine(
    _test_db_url, connect_args=_db.connect_args_for(_test_db_url)
)

_LOOPBACK_HOSTS = ("127.0.0.1", "::1", "localhost", "")


@pytest.fixture(autouse=True, scope="session")
def block_external_network():
    """Structural hermeticity: any external connect() or DNS lookup fails loudly.

    The suite's offline-ness used to be a behavioural side effect — it held
    only while TWELVE_DATA_KEY happened to be unset. Probed 2026-08-24: with
    a key in .env and no neutralising fixture, two tests issued real HTTPS
    requests to api.twelvedata.com (and a key-set run also rewrites tracked
    snapshot files). This guard makes the guarantee structural instead: a
    future test that reaches for the network raises immediately and locally,
    rather than passing here and failing intermittently in CI.

    Loopback stays allowed (anyio/TestClient event-loop plumbing needs it on
    Windows). getaddrinfo is patched alongside connect so DNS itself cannot
    leak. Adopted with ZERO interceptions across the full suite — current
    hermeticity is proven, not assumed — so any future trip of this guard is
    a new network dependency, never a pre-existing one.
    """
    real_connect = socket.socket.connect
    real_getaddrinfo = socket.getaddrinfo

    def _host_of(address):
        return address[0] if isinstance(address, tuple) else address

    def guarded_connect(self, address, *args, **kwargs):
        host = _host_of(address)
        if isinstance(host, str) and host not in _LOOPBACK_HOSTS:
            raise RuntimeError(f"[socket guard] external connect blocked: {address!r}")
        return real_connect(self, address, *args, **kwargs)

    def guarded_getaddrinfo(host, *args, **kwargs):
        if isinstance(host, str) and host not in _LOOPBACK_HOSTS:
            raise RuntimeError(f"[socket guard] DNS lookup blocked: {host!r}")
        return real_getaddrinfo(host, *args, **kwargs)

    socket.socket.connect = guarded_connect
    socket.getaddrinfo = guarded_getaddrinfo
    try:
        yield
    finally:
        socket.socket.connect = real_connect
        socket.getaddrinfo = real_getaddrinfo


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
