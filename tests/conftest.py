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

import socket

import pytest

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


@pytest.fixture(autouse=True)
def isolated_snapshot_dir(tmp_path, monkeypatch):
    """Redirect snapshot persistence to a per-test temp dir, for EVERY test.

    Promoted from a test_data.py module-local fixture: the protection lived
    only where the danger was first noticed, while `fetch_history` persists
    every successful fetch into the TRACKED snapshots/ directory from any
    caller. The failure shape is demonstrated, not hypothetical (2026-08-26,
    key-set run: AAPL parquet silently modified, SPY created — one
    `git add -A` from being committed). The socket guard blocks *live*
    fetches suite-wide, but a mocked-success fetch outside test_data.py
    would still write tracked files. tests/test_data.py's
    test_snapshot_persistence_is_redirected_away_from_the_tracked_dir is the
    canary that goes red if this fixture is ever disabled or skipped.
    """
    from stock_risk.config import settings

    monkeypatch.setattr(settings, "snapshot_dir", tmp_path / "snapshots")


@pytest.fixture()
def rate_limited():
    """Opt back into rate limiting for a test that's exercising it."""
    from stock_risk.config import settings

    settings.rate_limit_enabled = True
    yield
    settings.rate_limit_enabled = False
