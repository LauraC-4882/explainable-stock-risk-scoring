"""GET /api/github-stats — server-side proxy; the browser CSP stays strict.

Network is mocked in every test: the suite is an offline gate and must stay
one. What matters is the contract — cached, degrades to {} on failure, and
never lets an upstream error surface as an HTTP error.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from stock_risk.api.app import _github_cache, app


@pytest.fixture(autouse=True)
def fresh_cache():
    _github_cache["data"] = None
    _github_cache["at"] = 0.0
    yield


class _FakeResponse:
    def __init__(self, ok=True, payload=None):
        self.ok = ok
        self._payload = payload or {}

    def json(self):
        return self._payload


def test_proxies_stars_and_push_date():
    fake = _FakeResponse(payload={"stargazers_count": 7, "pushed_at": "2026-07-23T04:00:00Z"})
    with patch("requests.get", return_value=fake) as mocked:
        res = TestClient(app).get("/api/github-stats")
    assert res.status_code == 200
    assert res.json() == {"stars": 7, "pushed_at": "2026-07-23"}
    assert "api.github.com" in mocked.call_args.args[0]


def test_upstream_failure_degrades_to_empty_not_error():
    with patch("requests.get", side_effect=OSError("offline")):
        res = TestClient(app).get("/api/github-stats")
    assert res.status_code == 200
    assert res.json() == {}


def test_result_is_cached_for_an_hour():
    fake = _FakeResponse(payload={"stargazers_count": 7, "pushed_at": "2026-07-23T04:00:00Z"})
    client = TestClient(app)
    with patch("requests.get", return_value=fake) as mocked:
        client.get("/api/github-stats")
        client.get("/api/github-stats")
    # One upstream call for two requests — the whole point of the proxy is to
    # stay far under GitHub's unauthenticated rate limit.
    assert mocked.call_count == 1
