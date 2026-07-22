"""[R2] Score cache: single-flight, stale-while-revalidate, stale-on-error.

The problem this solves is specific. `/api/score/{ticker}` is public and takes
~2.7s on a miss because it makes live upstream calls. Without coordination:

* **Cache stampede.** AAPL's entry expires; twenty in-flight requests all miss
  simultaneously and all launch their own upstream fetch. Twenty identical
  round trips for one answer, twenty workers blocked, and twenty hits against
  an upstream that throttles by IP. The more popular the ticker, the worse it
  gets — load spikes exactly where caching was supposed to help most.
* **Latency cliff on expiry.** Whoever arrives first after expiry eats the full
  2.7s, even though a 60-second-old score is a perfectly good answer for a
  metric computed from daily bars.
* **Upstream outage = total outage.** Yahoo throttles the egress IP (routine on
  shared datacenter IPs) and every request 500s, despite a slightly stale
  answer sitting right there in memory.

Three mechanisms, one per problem:

1. **Single-flight** — one computation per key at a time. Concurrent callers
   for the same ticker wait on the first one's result instead of duplicating
   it. Per-key locks, not one global lock, so AAPL and TSLA still compute
   concurrently.
2. **Stale-while-revalidate** — past `fresh_ttl` but within `stale_ttl`, serve
   the cached value immediately and refresh in the background. Nobody waits at
   the expiry boundary.
3. **Stale-on-error** — if the refresh raises, keep serving the stale value
   until `stale_ttl` and log. Degraded beats down.

In-process, like ratelimit.py, and for the same reason: this deployment is a
single instance, and a shared cache would put a network hop in the hot path.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Generic, Optional, TypeVar

from loguru import logger

T = TypeVar("T")


@dataclass
class _Entry(Generic[T]):
    value: T
    stored_at: float
    refreshing: bool = False


@dataclass
class SingleFlightCache(Generic[T]):
    """TTL cache where a miss is computed exactly once per key.

    *fresh_ttl*: serve straight from cache, no refresh.
    *stale_ttl*: past fresh_ttl but under this, serve the cached value AND
    kick off a background refresh. Past stale_ttl, callers block on a fresh
    computation.
    """

    fresh_ttl: float = 300.0
    stale_ttl: float = 3600.0
    max_entries: int = 512

    _entries: dict[str, _Entry[T]] = field(default_factory=dict)
    _key_locks: dict[str, threading.Lock] = field(default_factory=dict)
    _guard: threading.Lock = field(default_factory=threading.Lock)
    hits: int = 0
    misses: int = 0
    stale_hits: int = 0
    stale_on_error: int = 0

    def _lock_for(self, key: str) -> threading.Lock:
        with self._guard:
            lock = self._key_locks.get(key)
            if lock is None:
                lock = threading.Lock()
                self._key_locks[key] = lock
            return lock

    def _evict_if_needed(self) -> None:
        """Drop the oldest entries past max_entries.

        Bounded because the key space is user-supplied ticker strings — an
        unbounded dict keyed on those is a memory leak anyone can drive by
        requesting garbage symbols.
        """
        if len(self._entries) <= self.max_entries:
            return
        oldest = sorted(self._entries.items(), key=lambda kv: kv[1].stored_at)
        for key, _ in oldest[: len(self._entries) - self.max_entries]:
            self._entries.pop(key, None)
            self._key_locks.pop(key, None)

    def _spawn_refresh(self, key: str, compute: Callable[[], T]) -> None:
        entry = self._entries.get(key)
        if entry is None or entry.refreshing:
            return
        entry.refreshing = True

        def _refresh() -> None:
            try:
                value = compute()
                with self._guard:
                    self._entries[key] = _Entry(value=value, stored_at=time.monotonic())
                logger.debug(f"[cache] background refresh ok: {key}")
            except Exception as exc:
                # Deliberately swallowed after logging: this runs on a
                # background thread with no caller to propagate to, and the
                # stale value is still being served. Re-raising would only kill
                # the thread silently.
                with self._guard:
                    stale = self._entries.get(key)
                    if stale is not None:
                        stale.refreshing = False
                self.stale_on_error += 1
                logger.warning(f"[cache] background refresh failed for {key}, serving stale: {exc}")

        threading.Thread(target=_refresh, name=f"cache-refresh-{key}", daemon=True).start()

    def get_or_compute(self, key: str, compute: Callable[[], T]) -> T:
        now = time.monotonic()

        with self._guard:
            entry = self._entries.get(key)
            if entry is not None:
                age = now - entry.stored_at
                if age < self.fresh_ttl:
                    self.hits += 1
                    return entry.value
                if age < self.stale_ttl:
                    self.stale_hits += 1
                    self._spawn_refresh(key, compute)
                    return entry.value

        # Past stale_ttl (or never cached): compute, but only once per key.
        lock = self._lock_for(key)
        with lock:
            # Re-check under the per-key lock — whoever held it before us may
            # have just populated the entry, which is the entire point of
            # single-flight. Without this second check every queued caller
            # would recompute in turn, serialised instead of deduplicated.
            with self._guard:
                entry = self._entries.get(key)
                if entry is not None and (time.monotonic() - entry.stored_at) < self.fresh_ttl:
                    self.hits += 1
                    return entry.value

            self.misses += 1
            try:
                value = compute()
            except Exception:
                with self._guard:
                    entry = self._entries.get(key)
                    if entry is not None and (time.monotonic() - entry.stored_at) < self.stale_ttl:
                        self.stale_on_error += 1
                        logger.warning(f"[cache] compute failed for {key}, serving stale value")
                        return entry.value
                raise

            with self._guard:
                self._entries[key] = _Entry(value=value, stored_at=time.monotonic())
                self._evict_if_needed()
            return value

    def peek(self, key: str) -> Optional[T]:
        with self._guard:
            entry = self._entries.get(key)
            return entry.value if entry else None

    def invalidate(self, key: str) -> None:
        with self._guard:
            self._entries.pop(key, None)

    def clear(self) -> None:
        with self._guard:
            self._entries.clear()
            self._key_locks.clear()
            self.hits = self.misses = self.stale_hits = self.stale_on_error = 0

    def stats(self) -> dict:
        total = self.hits + self.stale_hits + self.misses
        return {
            "entries": len(self._entries),
            "hits": self.hits,
            "stale_hits": self.stale_hits,
            "misses": self.misses,
            "stale_on_error": self.stale_on_error,
            "hit_rate": round((self.hits + self.stale_hits) / total, 4) if total else None,
        }
