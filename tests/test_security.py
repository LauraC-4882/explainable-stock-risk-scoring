"""[R2] Tests for rate limiting, login lockout, cache single-flight, security
headers, CORS and the audit trail.

The threading tests here are the ones that matter most: single-flight and the
token bucket are both concurrency mechanisms, and a concurrency bug that only
appears under simultaneous load is exactly what a sequential test misses.
"""

from __future__ import annotations

import threading
import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from stock_risk.api.app import app
from stock_risk.db import get_session
from stock_risk.security.audit import AuditAction, AuditLog, record_audit
from stock_risk.security.cache import SingleFlightCache
from stock_risk.security.headers import SECURITY_HEADERS
from stock_risk.security.ratelimit import FailedLoginTracker, RateLimiter

# ── Token bucket ─────────────────────────────────────────────────────────────


def test_bucket_allows_up_to_burst_then_refuses():
    limiter = RateLimiter(rate=1.0, burst=5.0)
    for _ in range(5):
        allowed, _ = limiter.check("client")
        assert allowed
    allowed, retry_after = limiter.check("client")
    assert not allowed
    assert retry_after > 0


def test_retry_after_reflects_the_actual_wait_not_a_fixed_guess():
    """A Retry-After the client can trust: at 2 tokens/sec, needing 1 token
    means ~0.5s, not a hard-coded 60."""
    limiter = RateLimiter(rate=2.0, burst=2.0)
    limiter.check("c", cost=2.0)
    allowed, retry_after = limiter.check("c", cost=1.0)
    assert not allowed
    assert 0.4 < retry_after < 0.6


def test_bucket_refills_over_time():
    limiter = RateLimiter(rate=100.0, burst=2.0)
    assert limiter.check("c", cost=2.0)[0]
    assert not limiter.check("c", cost=1.0)[0]
    time.sleep(0.05)  # 100/s -> ~5 tokens back
    assert limiter.check("c", cost=1.0)[0]


def test_clients_are_isolated_from_each_other():
    """One abusive client must not throttle everyone else — the whole point of
    keying the bucket by client identity."""
    limiter = RateLimiter(rate=1.0, burst=2.0)
    limiter.check("noisy", cost=2.0)
    assert not limiter.check("noisy")[0]
    assert limiter.check("quiet")[0]


def test_cost_is_charged_per_endpoint():
    limiter = RateLimiter(rate=1.0, burst=10.0)
    assert limiter.check("c", cost=8.0)[0]
    assert not limiter.check("c", cost=5.0)[0]  # only 2 left
    assert limiter.check("c", cost=2.0)[0]


def test_bucket_never_exceeds_burst_after_long_idle():
    """Refill must clamp: an hour idle shouldn't bank an hour of tokens and
    permit an unbounded burst."""
    limiter = RateLimiter(rate=1000.0, burst=3.0)
    limiter.check("c", cost=3.0)
    time.sleep(0.05)
    assert limiter.check("c", cost=3.0)[0]
    assert not limiter.check("c", cost=1.0)[0]


def test_concurrent_checks_never_oversell_the_bucket():
    """Under concurrency the bucket must not hand out more than `burst`.

    A non-atomic read-modify-write would let two threads both observe 1 token
    and both spend it.
    """
    limiter = RateLimiter(rate=0.0001, burst=50.0)
    granted = []
    lock = threading.Lock()

    def worker():
        allowed, _ = limiter.check("shared")
        if allowed:
            with lock:
                granted.append(1)

    threads = [threading.Thread(target=worker) for _ in range(200)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(granted) == 50


# ── Failed-login lockout ─────────────────────────────────────────────────────


def test_lockout_after_threshold_failures():
    tracker = FailedLoginTracker(threshold=3, lockout_seconds=60)
    for _ in range(2):
        tracker.record_failure("a@example.com")
    assert tracker.is_locked("a@example.com")[0] is False
    tracker.record_failure("a@example.com")
    locked, remaining = tracker.is_locked("a@example.com")
    assert locked and remaining > 0


def test_successful_login_clears_the_streak():
    """Otherwise a user who mistyped 4 times then succeeded stays permanently
    one failure from a lockout."""
    tracker = FailedLoginTracker(threshold=3, lockout_seconds=60)
    tracker.record_failure("a@example.com")
    tracker.record_failure("a@example.com")
    tracker.clear("a@example.com")
    tracker.record_failure("a@example.com")
    assert tracker.is_locked("a@example.com")[0] is False


def test_lockout_is_per_account_not_global():
    tracker = FailedLoginTracker(threshold=2, lockout_seconds=60)
    tracker.record_failure("victim@example.com")
    tracker.record_failure("victim@example.com")
    assert tracker.is_locked("victim@example.com")[0]
    assert tracker.is_locked("bystander@example.com")[0] is False


def test_lockout_is_case_insensitive_on_email():
    """Otherwise the lockout is trivially bypassed by varying capitalisation."""
    tracker = FailedLoginTracker(threshold=2, lockout_seconds=60)
    tracker.record_failure("User@Example.com")
    tracker.record_failure("user@example.COM")
    assert tracker.is_locked("USER@EXAMPLE.COM")[0]


def test_old_failures_age_out_of_the_window():
    tracker = FailedLoginTracker(threshold=2, lockout_seconds=0.05)
    tracker.record_failure("a@example.com")
    tracker.record_failure("a@example.com")
    assert tracker.is_locked("a@example.com")[0]
    time.sleep(0.08)
    assert tracker.is_locked("a@example.com")[0] is False


# ── Single-flight cache ──────────────────────────────────────────────────────


def test_cache_returns_cached_value_without_recomputing():
    cache = SingleFlightCache(fresh_ttl=60, stale_ttl=120)
    calls = []
    cache.get_or_compute("k", lambda: calls.append(1) or "v")
    cache.get_or_compute("k", lambda: calls.append(1) or "v")
    assert len(calls) == 1


def test_concurrent_misses_compute_exactly_once():
    """The stampede guarantee.

    Twenty simultaneous requests for the same uncached ticker must produce ONE
    upstream call, not twenty. This is the test that would fail if the
    double-check inside the per-key lock were removed.
    """
    cache = SingleFlightCache(fresh_ttl=60, stale_ttl=120)
    calls = []
    lock = threading.Lock()
    start = threading.Barrier(20)

    def compute():
        with lock:
            calls.append(1)
        time.sleep(0.05)  # a slow upstream fetch
        return "value"

    results = []

    def worker():
        start.wait()
        results.append(cache.get_or_compute("AAPL", compute))

    threads = [threading.Thread(target=worker) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(calls) == 1, f"stampede: {len(calls)} concurrent computations"
    assert results == ["value"] * 20


def test_different_keys_are_not_serialised_by_one_lock():
    """Per-key locks, not a global one: AAPL must not block TSLA."""
    cache = SingleFlightCache(fresh_ttl=60, stale_ttl=120)

    def slow():
        time.sleep(0.2)
        return "v"

    started = time.monotonic()
    threads = [
        threading.Thread(target=lambda k=k: cache.get_or_compute(k, slow))
        for k in ("AAPL", "TSLA", "MSFT")
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed = time.monotonic() - started

    # Serialised would be ~0.6s; concurrent ~0.2s.
    assert elapsed < 0.45, f"keys appear serialised ({elapsed:.2f}s)"


def test_stale_value_served_when_recompute_fails():
    """Upstream outage must degrade, not 500 — the documented Yahoo-throttling
    scenario."""
    cache = SingleFlightCache(fresh_ttl=0.01, stale_ttl=60)
    cache.get_or_compute("k", lambda: "good")
    time.sleep(0.05)

    def boom():
        raise RuntimeError("upstream is throttling us")

    # Past fresh_ttl but inside stale_ttl: SWR serves the cached value and
    # refreshes in the background, so the caller never sees the failure.
    assert cache.get_or_compute("k", boom) == "good"


def test_error_propagates_when_nothing_cached_to_fall_back_to():
    cache = SingleFlightCache(fresh_ttl=60, stale_ttl=120)
    with pytest.raises(RuntimeError):
        cache.get_or_compute("cold", lambda: (_ for _ in ()).throw(RuntimeError("boom")))


def test_cache_evicts_to_stay_bounded():
    """Keys are user-supplied tickers — an unbounded dict is a memory leak
    anyone can drive by requesting garbage symbols."""
    cache = SingleFlightCache(fresh_ttl=60, stale_ttl=120, max_entries=10)
    for i in range(50):
        cache.get_or_compute(f"T{i}", lambda i=i: i)
    assert cache.stats()["entries"] <= 10


# ── HTTP surface ─────────────────────────────────────────────────────────────


@pytest.fixture()
def engine():
    eng = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(eng)
    return eng


@pytest.fixture()
def client(engine):
    def override_get_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_security_headers_present_on_responses(client):
    response = client.get("/health")
    for header in SECURITY_HEADERS:
        assert header in response.headers, f"missing {header}"
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]


def test_csp_permits_the_webfonts_the_page_actually_loads(client):
    """Regression: the first CSP silently blocked every Google font.

    The page still rendered — in fallback system fonts — which is the kind of
    breakage that passes review and fails in production. ui_shot.sh caught it
    by failing on console errors; this pins it so it can't come back.
    """
    csp = client.get("/health").headers["Content-Security-Policy"]
    style_src = next(p for p in csp.split("; ") if p.startswith("style-src"))
    font_src = next(p for p in csp.split("; ") if p.startswith("font-src"))
    assert "https://fonts.googleapis.com" in style_src
    assert "https://fonts.gstatic.com" in font_src


def test_csp_does_not_allow_inline_script(client):
    """style-src needs 'unsafe-inline' (computed gauge/chart colours);
    script-src must not — inline script is what an XSS payload needs."""
    csp = client.get("/health").headers["Content-Security-Policy"]
    script_src = next(p for p in csp.split("; ") if p.startswith("script-src"))
    assert "unsafe-inline" not in script_src
    assert "unsafe-eval" not in script_src


def test_cors_does_not_echo_arbitrary_origins(client):
    """Regression guard on the `allow_origins=["*"]` this replaced."""
    response = client.get("/health", headers={"Origin": "https://evil.example.com"})
    assert response.headers.get("access-control-allow-origin") != "https://evil.example.com"
    assert response.headers.get("access-control-allow-origin") != "*"


def test_hsts_not_sent_over_plain_http(client):
    """Sending HSTS on http://localhost pins the dev server to HTTPS in the
    developer's browser, which persists after the header is removed."""
    assert "Strict-Transport-Security" not in client.get("/health").headers


# ── Audit trail ──────────────────────────────────────────────────────────────


def test_record_audit_persists_a_row(engine):
    with Session(engine) as session:
        record_audit(
            session,
            AuditAction.USER_BANNED,
            actor_email="admin@example.com",
            target="bad@example.com",
            ip_address="203.0.113.7",
        )
    with Session(engine) as session:
        row = session.exec(select(AuditLog)).one()
        assert row.action == AuditAction.USER_BANNED
        assert row.actor_email == "admin@example.com"
        assert row.target == "bad@example.com"
        assert row.success is True


def test_record_audit_never_raises_on_a_broken_session():
    """An audit write failure must not turn a successful ban into a 500."""

    class BrokenSession:
        def add(self, _):
            raise RuntimeError("db is down")

        def commit(self):
            raise RuntimeError("db is down")

        def rollback(self):
            raise RuntimeError("still down")

    record_audit(BrokenSession(), AuditAction.LOGIN_SUCCESS, actor_email="a@example.com")


def test_failed_login_is_audited_and_locks_out(client):
    client.post(
        "/api/auth/register",
        json={
            "email": "victim@example.com",
            "password": "correct-horse",
            "nickname": "victim",
            "consent": True,
        },
    )

    statuses = [
        client.post(
            "/api/auth/login", json={"email": "victim@example.com", "password": "wrong"}
        ).status_code
        for _ in range(6)
    ]

    assert 401 in statuses, "wrong password must be rejected"
    assert 429 in statuses, "repeated failures must eventually lock out"
    assert statuses[-1] == 429


@pytest.fixture()
def tiny_bucket(monkeypatch, rate_limited):
    """Shrink the anonymous bucket so the limiter engages in a few requests.

    Two reasons not to just send a lot of real requests instead. The limiter
    runs *before* routing, so any request that gets through reaches the real
    scorer and attempts a live upstream fetch — slow and network-dependent in a
    unit test. And sizing the test to the configured burst couples it to a
    tuning value: raising `rate_limit_burst` from 40 to 120 silently turned an
    earlier version of this test from "asserts the limiter fires" into "asserts
    nothing", because the loop no longer exhausted the bucket.
    """
    from stock_risk.api import app as app_module

    monkeypatch.setattr(app_module, "_anon_limiter", RateLimiter(rate=0.5, burst=2.0))
    return app_module


def test_rate_limit_returns_429_with_retry_after(client, tiny_bucket):
    """End-to-end through the middleware, not just the bucket in isolation."""
    statuses = [client.get("/api/search?q=a").status_code for _ in range(6)]
    assert 429 in statuses, f"limiter never engaged: {statuses}"

    limited = client.get("/api/search?q=a")
    assert limited.status_code == 429
    assert int(limited.headers["Retry-After"]) >= 1
    assert "rate limit" in limited.json()["detail"].lower()


def test_health_is_never_rate_limited(client, tiny_bucket):
    """A zero-cost endpoint must stay reachable while everything else is
    throttled — otherwise the limiter takes out the platform's own liveness
    probe and gets the instance recycled mid-incident."""
    for _ in range(20):
        client.get("/api/search?q=a")
    assert client.get("/api/search?q=a").status_code == 429
    assert client.get("/health").status_code == 200


def test_static_assets_are_exempt_from_rate_limiting(client, tiny_bucket):
    """The bundle is many files fetched at once on first paint; throttling them
    would make the app fail to load for a legitimate visitor."""
    for _ in range(20):
        client.get("/api/search?q=a")
    # Not 429 — a 404 here just means the built bundle isn't present in a test
    # checkout, which is fine; what matters is that the limiter let it past.
    assert client.get("/assets/does-not-exist.js").status_code != 429


def test_login_does_not_reveal_whether_an_account_exists(client):
    """Different messages for 'no such user' vs 'wrong password' turn this
    endpoint into an account-enumeration oracle."""
    client.post(
        "/api/auth/register",
        json={
            "email": "real@example.com",
            "password": "correct-horse",
            "nickname": "realuser",
            "consent": True,
        },
    )
    wrong_password = client.post(
        "/api/auth/login", json={"email": "real@example.com", "password": "nope"}
    )
    no_such_user = client.post(
        "/api/auth/login", json={"email": "ghost@example.com", "password": "nope"}
    )
    assert wrong_password.status_code == no_such_user.status_code == 401
    assert wrong_password.json()["detail"] == no_such_user.json()["detail"]
