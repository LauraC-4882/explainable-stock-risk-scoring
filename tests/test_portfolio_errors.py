"""The portfolio endpoint answers with the same five codes as /api/score/.

Before this, every failure inside `POST /api/portfolio/risk` came out as either
a bare 404 that could not distinguish a misspelled symbol from a throttled
provider, or a 422 carrying `str(exc)` straight into the response body. The
tests here pin the mapping and the non-leak property together, in the same
shape as `tests/test_scoring_errors.py` so the two endpoints cannot drift into
different ideas of what a failure means.

They deliberately do not assert any risk number. Step 2a changed no arithmetic,
and a test that touched both would not say which half it was protecting.
"""

from __future__ import annotations

import pathlib
from unittest.mock import patch

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from stock_risk.api.app import app
from stock_risk.api.errors import ERROR_SPECS
from stock_risk.errors import (
    DelistedError,
    InsufficientDataError,
    ScoreErrorCode,
    TickerNotFoundError,
    UpstreamUnavailableError,
)

client = TestClient(app)

TWO = {"positions": [{"ticker": "AAA", "weight": 0.5}, {"ticker": "BBB", "weight": 0.5}]}

# Every failure a single holding can contribute, and the code it must produce.
# Raised from `fetch_history`, which is where all of them actually originate.
_FETCH_CASES = [
    (TickerNotFoundError("no such symbol"), ScoreErrorCode.TICKER_NOT_FOUND, 404),
    (InsufficientDataError("only 12 trading days"), ScoreErrorCode.INSUFFICIENT_DATA, 422),
    (UpstreamUnavailableError("all providers failed"), ScoreErrorCode.UPSTREAM_UNAVAILABLE, 503),
    (DelistedError("last bar 2024-01-01"), ScoreErrorCode.DELISTED, 422),
    (RuntimeError("boom"), ScoreErrorCode.CALCULATION_FAILED, 500),
]


@pytest.mark.parametrize("exc, code, status", _FETCH_CASES)
def test_each_holding_failure_maps_to_its_own_code(exc, code, status):
    """One undifferentiated 404 became five answers. The status matters as much
    as the code: a throttled provider is a 503 the caller may retry, while a
    misspelled symbol is a 404 that retrying cannot fix."""
    from stock_risk.api.app import scorer

    with patch.object(scorer.fetcher, "fetch_history", side_effect=exc):
        response = client.post("/api/portfolio/risk", json=TWO)

    assert response.status_code == status, response.text
    body = response.json()
    assert body["error"] == code.value
    assert body["status"] == status
    assert body["message"] == ERROR_SPECS[code].message
    assert body["detail"] == body["message"]


@pytest.mark.parametrize("exc, code, status", _FETCH_CASES)
def test_the_response_names_the_offending_holding(exc, code, status):
    """A book of five names failing with no indication of which one is a
    message the user cannot act on. The ticker is a structured field, never
    interpolated into prose."""
    from stock_risk.api.app import scorer

    with patch.object(scorer.fetcher, "fetch_history", side_effect=exc):
        response = client.post("/api/portfolio/risk", json=TWO)

    assert response.json()["ticker"] == "AAA", response.text


@pytest.mark.parametrize("exc, code, status", _FETCH_CASES)
def test_no_portfolio_failure_leaks_the_exception_text(exc, code, status):
    """Same assertion as tests/test_scoring_errors.py makes for /api/score/.
    An exception string can carry a filesystem path, a key in a URL or an
    internal hostname, and this endpoint used to put one in the body verbatim."""
    from stock_risk.api.app import scorer

    secret = "C:/secrets/prod-key.pem"
    leaky = type(exc)(f"failed while reading {secret}")

    with patch.object(scorer.fetcher, "fetch_history", side_effect=leaky):
        response = client.post("/api/portfolio/risk", json=TWO)

    assert secret not in response.text
    assert "Traceback" not in response.text


def test_a_cold_start_holding_fails_the_whole_portfolio():
    """A covariance matrix is a joint estimate: dropping the short-history name
    would not return this book minus one, it would return a different book
    whose weights no longer sum to what was asked about. So the whole request
    fails, and it says which holding caused it."""
    from stock_risk.api.app import scorer

    short = pd.DataFrame(
        {
            "open": [100.0] * 30, "high": [101.0] * 30, "low": [99.0] * 30,
            "close": [100.0] * 30, "volume": [1_000_000.0] * 30,
        },
        index=pd.bdate_range("2026-01-01", periods=30),
    )
    short.index.name = "date"

    with patch.object(scorer.fetcher, "fetch_history", return_value=short):
        response = client.post("/api/portfolio/risk", json=TWO)

    assert response.status_code == 422, response.text
    body = response.json()
    assert body["error"] == ScoreErrorCode.INSUFFICIENT_DATA.value
    assert body["ticker"] == "AAA"
    assert "30" not in body["message"], "the message must not echo the row count"


def test_no_overlapping_history_is_a_portfolio_level_failure():
    """The one ValueError `compute_portfolio_risk` can still raise here. It is a
    property of the COMBINATION, not of any single holding, so `ticker` is null
    — which is what lets the frontend choose portfolio-level copy over a
    per-holding message."""
    from stock_risk.api.app import scorer

    def disjoint(ticker, period="2y", **kw):
        start = "2020-01-01" if ticker == "AAA" else "2024-01-01"
        index = pd.bdate_range(start, periods=200)
        return pd.DataFrame(
            {
                "open": [100.0] * 200, "high": [101.0] * 200, "low": [99.0] * 200,
                "close": [100.0 + i * 0.01 for i in range(200)],
                "volume": [1_000_000.0] * 200,
            },
            index=index,
        ).rename_axis("date")

    with patch.object(scorer.fetcher, "fetch_history", side_effect=disjoint):
        response = client.post("/api/portfolio/risk", json=TWO)

    assert response.status_code == 422, response.text
    body = response.json()
    assert body["error"] == ScoreErrorCode.INSUFFICIENT_DATA.value
    assert body["ticker"] is None
    assert "overlap" not in response.text.lower(), "the ValueError text must not reach the body"


# ── Request-shape errors stay plain 422s ────────────────────────────────────


@pytest.mark.parametrize(
    "payload",
    [
        {"positions": [{"ticker": "AAA", "weight": 1.0}]},
        {"positions": [{"ticker": f"T{i}", "weight": 0.1} for i in range(6)]},
        {"positions": [{"ticker": "AAA", "weight": 0.5}, {"ticker": "AAA", "weight": 0.5}]},
        {"positions": [{"ticker": "AAA", "weight": 0.0}, {"ticker": "BBB", "weight": 1.0}]},
    ],
    ids=["too-few", "too-many", "duplicate", "non-positive-weight"],
)
def test_malformed_requests_are_plain_422s_without_a_score_code(payload):
    """These describe a malformed REQUEST, not a scoring outcome, so they are
    the same category as FastAPI's own body-validation errors and carry no
    ScoreErrorCode. Asserted explicitly so that a future change cannot quietly
    file them under CALCULATION_FAILED, which would report a user's typo as a
    server fault and a 500."""
    response = client.post("/api/portfolio/risk", json=payload)

    assert response.status_code == 422, response.text
    assert "error" not in response.json(), "request-shape errors must not claim a score code"


def test_the_position_cap_and_the_rate_limit_price_cannot_drift_apart():
    """They used to be two independent literal 5s. Raising the cap would then
    have widened the fan-out while leaving the request priced for the old one.

    Asserting the two are EQUAL proves nothing while they both happen to be 5 —
    a mutation putting the literal back passed that version of this test. What
    has to be shown is that the price TRACKS the cap, so the table entry is
    re-evaluated against a changed cap and the equality is re-checked. A hard
    literal fails this; a derived value survives it.
    """
    import stock_risk.api.app as app_module

    original = app_module.MAX_PORTFOLIO_POSITIONS
    try:
        app_module.MAX_PORTFOLIO_POSITIONS = original + 3
        priced_at_cap = float(app_module.MAX_PORTFOLIO_POSITIONS)
        rebuilt = [
            (prefix, priced_at_cap if prefix == "/api/portfolio" else cost)
            for prefix, cost in app_module._ENDPOINT_COSTS
        ]
        priced = dict(rebuilt)["/api/portfolio"]
        assert priced == float(original + 3), (
            "the portfolio price does not follow the cap; it is a standalone literal"
        )
    finally:
        app_module.MAX_PORTFOLIO_POSITIONS = original

    # And, today, the shipped table is already derived rather than hard-coded.
    source = (
        pathlib.Path(app_module.__file__).read_text(encoding="utf-8")
    )
    assert '("/api/portfolio", float(MAX_PORTFOLIO_POSITIONS))' in source, (
        "the rate-limit price for /api/portfolio is a literal again"
    )
    assert app_module._endpoint_cost("/api/portfolio/risk") == float(
        app_module.MAX_PORTFOLIO_POSITIONS
    )
