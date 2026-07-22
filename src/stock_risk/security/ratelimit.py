"""[R2] Token-bucket rate limiting, per client and per endpoint cost.

Why this exists: `/api/score/{ticker}` is unauthenticated, public, and on a
cache miss makes a live upstream call (yfinance/akshare/Twelve Data) that takes
~2.7s. Before this, a single client in a loop could saturate the worker pool
*and* burn the upstream quota — and Yahoo throttles by egress IP, so one
abusive caller gets the whole deployment throttled for everyone. That failure
mode is documented in README "Deployment"; this is the inbound half of the fix
(the outbound half is cache.py's single-flight + snapshot fallback).

Token bucket rather than a fixed window, because a fixed window lets a client
spend its entire allowance in the last instant of one window and again in the
first instant of the next — a 2x burst at the boundary. A bucket refills
continuously, so `burst` is an explicit, bounded parameter rather than an
artifact of where the window edges happen to fall.

Costs are per-endpoint: a cached `/health` is cheap, a cold score is not.
Charging every route the same either throttles trivial requests pointlessly or
lets expensive ones through freely.

In-process and per-worker on purpose. A shared Redis counter would be exact
across replicas, but this deployment is a single small instance, and adding a
network dependency to the request hot path — one that fails *open* or *closed*,
both bad — is a worse trade than a limiter that is approximate across workers.
Documented rather than silently assumed: with N workers the effective limit is
N x the configured rate.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

from loguru import logger


@dataclass
class _Bucket:
    tokens: float
    last_refill: float


@dataclass
class RateLimiter:
    """Token bucket keyed by an arbitrary client identity.

    *rate* is sustained tokens per second; *burst* is the bucket capacity, i.e.
    how many tokens can be spent at once after an idle period.
    """

    rate: float
    burst: float
    _buckets: dict[str, _Bucket] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    # Buckets for one-off clients would otherwise accumulate forever — an
    # unbounded dict keyed by client IP is a slow memory leak, and a trivially
    # triggerable one on a public endpoint (spoofed X-Forwarded-For values).
    _last_sweep: float = 0.0
    _sweep_interval: float = 300.0

    def _refill(self, bucket: _Bucket, now: float) -> None:
        elapsed = now - bucket.last_refill
        if elapsed > 0:
            bucket.tokens = min(self.burst, bucket.tokens + elapsed * self.rate)
            bucket.last_refill = now

    def _sweep(self, now: float) -> None:
        """Drop buckets that have been full (i.e. idle) long enough to be
        indistinguishable from a client that never existed."""
        if now - self._last_sweep < self._sweep_interval:
            return
        self._last_sweep = now
        idle_cutoff = self.burst / self.rate if self.rate > 0 else 0
        stale = [
            key
            for key, bucket in self._buckets.items()
            if now - bucket.last_refill > max(idle_cutoff, self._sweep_interval)
        ]
        for key in stale:
            del self._buckets[key]
        if stale:
            logger.debug(f"[ratelimit] swept {len(stale)} idle buckets")

    def check(self, key: str, cost: float = 1.0) -> tuple[bool, float]:
        """Try to spend *cost* tokens for *key*.

        Returns (allowed, retry_after_seconds). retry_after is 0 when allowed,
        and otherwise how long until enough tokens exist — a real number the
        caller can put in a Retry-After header, not a fixed guess.
        """
        now = time.monotonic()
        with self._lock:
            self._sweep(now)
            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = _Bucket(tokens=self.burst, last_refill=now)
                self._buckets[key] = bucket
            self._refill(bucket, now)

            if bucket.tokens >= cost:
                bucket.tokens -= cost
                return True, 0.0

            deficit = cost - bucket.tokens
            retry_after = deficit / self.rate if self.rate > 0 else 60.0
            return False, retry_after

    def reset(self) -> None:
        """Drop all state. For tests, and for an admin-triggered clear."""
        with self._lock:
            self._buckets.clear()


@dataclass
class FailedLoginTracker:
    """Progressive lockout for repeated failed logins against one account.

    Keyed by email, NOT by IP: an attacker spraying one password across many
    accounts from one IP is caught by the IP limiter, while an attacker
    rotating IPs against one account is caught here. Both are needed; either
    alone leaves an obvious hole.

    The lockout is time-based rather than permanent so a legitimate user who
    mistypes their password a few times is delayed, not locked out of their own
    account until an admin intervenes — which is a denial-of-service anyone
    could trigger against any known email address.
    """

    threshold: int = 5
    lockout_seconds: float = 900.0  # 15 minutes
    _failures: dict[str, list[float]] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def _prune(self, key: str, now: float) -> list[float]:
        recent = [t for t in self._failures.get(key, []) if now - t < self.lockout_seconds]
        if recent:
            self._failures[key] = recent
        else:
            self._failures.pop(key, None)
        return recent

    def is_locked(self, key: str) -> tuple[bool, float]:
        """(locked, seconds_remaining) for *key*."""
        now = time.monotonic()
        with self._lock:
            recent = self._prune(key.lower(), now)
            if len(recent) < self.threshold:
                return False, 0.0
            # Unlocks once the oldest counted failure ages out of the window.
            remaining = self.lockout_seconds - (now - recent[0])
            return True, max(remaining, 0.0)

    def record_failure(self, key: str) -> int:
        now = time.monotonic()
        with self._lock:
            key = key.lower()
            recent = self._prune(key, now)
            recent.append(now)
            self._failures[key] = recent
            return len(recent)

    def clear(self, key: str) -> None:
        """Called on a successful login — a correct password ends the streak."""
        with self._lock:
            self._failures.pop(key.lower(), None)

    def reset(self) -> None:
        with self._lock:
            self._failures.clear()


def client_key(request) -> str:
    """Identity to rate-limit on: the authenticated user if there is one, else
    the client IP.

    Preferring the user means a signed-in user on a shared/NAT'd IP isn't
    throttled by strangers' traffic, and that a user cannot multiply their own
    quota just by rotating IPs.

    `X-Forwarded-For` is trusted ONLY when `settings.trust_proxy_headers` is on
    (true behind Render's proxy, false for a directly-exposed server). Trusting
    it unconditionally would make the IP limiter useless — the header is
    attacker-controlled, so anyone could send a fresh value per request and get
    a fresh bucket every time.
    """
    from ..auth.security import decode_access_token
    from ..config import settings

    authorization = request.headers.get("authorization", "")
    if authorization.startswith("Bearer "):
        subject = decode_access_token(authorization.removeprefix("Bearer "))
        if subject:
            return f"user:{subject}"

    if settings.trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            # Left-most entry is the original client; the rest are proxies.
            return f"ip:{forwarded.split(',')[0].strip()}"

    client = getattr(request, "client", None)
    return f"ip:{client.host if client else 'unknown'}"
