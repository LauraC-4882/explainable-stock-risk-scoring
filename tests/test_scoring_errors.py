"""Every way a score can fail, and what the user is told about it.

Before the taxonomy, `/api/score/{ticker}` had two answers for five different
problems: a 404 echoing `str(exc)`, or a 500 saying "Internal scoring error".
These tests pin the replacement contract — one code per failure mode, a safe
message, and no raw exception text on the wire — end to end, because that
contract spans the fetcher, the scorer, the classifier and the HTTP layer, and
a unit test of any one of them would not have caught the old bug.
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
import requests
from fastapi.testclient import TestClient
from loguru import logger

from stock_risk.api.app import app
from stock_risk.api.errors import ERROR_SPECS
from stock_risk.data.fetcher import MarketDataFetcher
from stock_risk.data.quality import (
    MIN_TRADING_DAYS,
    SOURCE_ATTR,
    STALE_AFTER_DAYS,
    check_history_scorable,
)
from stock_risk.data.validation import DataValidationError
from stock_risk.errors import (
    DelistedError,
    InsufficientDataError,
    ScoreErrorCode,
    TickerNotFoundError,
    UpstreamUnavailableError,
    classify_scoring_error,
)
from stock_risk.scoring.scorer import RiskScorer

client = TestClient(app)


# ── The classifier ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "exc, expected",
    [
        (TickerNotFoundError("nothing came back"), ScoreErrorCode.TICKER_NOT_FOUND),
        (InsufficientDataError("only 12 rows"), ScoreErrorCode.INSUFFICIENT_DATA),
        (DelistedError("last bar 2024-01-01"), ScoreErrorCode.DELISTED),
        (UpstreamUnavailableError("every source failed"), ScoreErrorCode.UPSTREAM_UNAVAILABLE),
        # A transport failure that escaped the fetcher's own handling is an
        # outage, not a bug in this code.
        (requests.exceptions.Timeout(), ScoreErrorCode.UPSTREAM_UNAVAILABLE),
        (requests.exceptions.ConnectionError(), ScoreErrorCode.UPSTREAM_UNAVAILABLE),
        # A malformed OHLCV frame means the symbol is fine and the *data* is
        # not — telling the user to check their spelling would be a lie.
        (DataValidationError("AAPL: high < low"), ScoreErrorCode.CALCULATION_FAILED),
        # The arithmetic failure modes the issue called out by name.
        (ZeroDivisionError("float division by zero"), ScoreErrorCode.CALCULATION_FAILED),
        (FloatingPointError("invalid value encountered"), ScoreErrorCode.CALCULATION_FAILED),
        # Preserved from the pre-taxonomy behaviour: a bare ValueError reaches
        # the API only from the fetch boundary, where it means "no such symbol".
        (ValueError("No data returned for ticker 'ZZZZ'"), ScoreErrorCode.TICKER_NOT_FOUND),
    ],
)
def test_every_failure_mode_gets_its_own_code(exc, expected):
    assert classify_scoring_error(exc) is expected


def test_an_unrecognised_exception_defaults_to_calculation_failed():
    """The default must be the code that logs a traceback and blames us. An
    unanticipated exception rebranded as UPSTREAM_UNAVAILABLE would hide a real
    bug behind "try again later" — forever, since retrying never fixes it."""

    class SomethingNobodyAnticipatedError(Exception):
        pass

    unknown = SomethingNobodyAnticipatedError()
    assert classify_scoring_error(unknown) is ScoreErrorCode.CALCULATION_FAILED


# ── The HTTP contract ────────────────────────────────────────────────────────

# Distinct tickers per case: [R2]'s score cache serves stale-on-failure, so
# reusing one symbol would let an earlier case's fixture answer a later one.
_HTTP_CASES = [
    ("ERRNOTFOUND", TickerNotFoundError("no data"), ScoreErrorCode.TICKER_NOT_FOUND, 404),
    ("ERRTHIN", InsufficientDataError("only 12 rows"), ScoreErrorCode.INSUFFICIENT_DATA, 422),
    (
        "ERRTHROTTLED",
        UpstreamUnavailableError("all failed"),
        ScoreErrorCode.UPSTREAM_UNAVAILABLE,
        503,
    ),
    ("ERRBUG", RuntimeError("boom"), ScoreErrorCode.CALCULATION_FAILED, 500),
    ("ERRGONE", DelistedError("last bar 2024-01-01"), ScoreErrorCode.DELISTED, 422),
]


@pytest.mark.parametrize("ticker, exc, code, status", _HTTP_CASES)
def test_score_endpoint_returns_a_specific_code_per_failure(ticker, exc, code, status):
    with patch.object(RiskScorer, "score", side_effect=exc):
        response = client.get(f"/api/score/{ticker}")

    assert response.status_code == status, response.text
    body = response.json()
    assert body["error"] == code.value
    assert body["status"] == status
    assert body["ticker"] == ticker
    # `message` is the user-facing copy and `detail` is the legacy field every
    # existing client already reads; they must not drift apart.
    assert body["message"] == ERROR_SPECS[code].message
    assert body["detail"] == body["message"]


@pytest.mark.parametrize("ticker, exc, code, status", _HTTP_CASES)
def test_no_failure_mode_leaks_the_exception_text(ticker, exc, code, status):
    """The whole point of routing through a code table: `str(exc)` can carry a
    filesystem path, an API key in a URL or an internal hostname, and none of
    that may reach a browser. Same assertion for all five so a future code
    added without a table entry cannot quietly fall back to echoing."""
    secret = "C:/secrets/prod-key.pem"
    leaky = type(exc)(f"failed while reading {secret}")

    with patch.object(RiskScorer, "score", side_effect=leaky):
        response = client.get(f"/api/score/LEAK{ticker}")

    assert secret not in response.text
    assert "Traceback" not in response.text


def test_a_genuine_bug_is_logged_with_its_traceback_while_the_user_sees_nothing():
    """The two halves of CALCULATION_FAILED, asserted together: the operator
    gets everything, the user gets a sentence. Testing only one half is how a
    "safe message" ends up silently swallowing the incident report too."""
    log_sink = []
    handler_id = logger.add(lambda msg: log_sink.append(str(msg)), level="ERROR")
    try:
        with patch.object(RiskScorer, "score", side_effect=RuntimeError("segfault in leg 3")):
            response = client.get("/api/score/ERRLOGGED")
    finally:
        logger.remove(handler_id)

    assert response.status_code == 500
    assert response.json()["error"] == "CALCULATION_FAILED"
    assert "segfault in leg 3" not in response.text
    logged = "\n".join(log_sink)
    assert "segfault in leg 3" in logged
    assert "ERRLOGGED" in logged
    assert "CALCULATION_FAILED" in logged


def test_an_expected_upstream_outage_is_not_logged_as_an_error():
    """A throttled provider is an operating condition, not an incident. If it
    logged at ERROR with a traceback, the log would be all outage and the real
    bugs would be invisible in it — which is what makes the ERROR-level assert
    below the useful half of this test."""
    log_sink = []
    handler_id = logger.add(lambda msg: log_sink.append(str(msg)), level="ERROR")
    try:
        with patch.object(
            RiskScorer, "score", side_effect=UpstreamUnavailableError("rate limited")
        ):
            response = client.get("/api/score/ERRQUIET")
    finally:
        logger.remove(handler_id)

    assert response.status_code == 503
    assert log_sink == []


@pytest.mark.parametrize("path", ["/api/score/{t}/timeseries", "/api/score/{t}/outcomes"])
@pytest.mark.parametrize(
    "exc, code, status",
    [
        (TickerNotFoundError("no data"), ScoreErrorCode.TICKER_NOT_FOUND, 404),
        (UpstreamUnavailableError("all failed"), ScoreErrorCode.UPSTREAM_UNAVAILABLE, 503),
        (RuntimeError("boom"), ScoreErrorCode.CALCULATION_FAILED, 500),
    ],
)
def test_chart_endpoints_share_the_same_taxonomy(path, exc, code, status):
    """The three scoring endpoints used to have three different error ladders,
    which is exactly how they drifted. One funnel now, so one test shape."""
    ticker = f"TS{code.value[:4]}{path.rsplit('/', 1)[-1][:3]}".upper()
    with patch.object(RiskScorer, "score_timeseries", side_effect=exc):
        response = client.get(path.format(t=ticker))

    assert response.status_code == status, response.text
    assert response.json()["error"] == code.value


def test_the_legacy_score_route_answers_identically():
    """/score/{ticker} shares _score_ticker with /api/score/{ticker}; the [C1]
    postmortem was caused by exactly this pair drifting apart."""
    with patch.object(RiskScorer, "score", side_effect=DelistedError("gone")):
        new = client.get("/api/score/ERRLEGACY")
        old = client.get("/score/ERRLEGACY")
    assert new.status_code == old.status_code == 422
    assert new.json() == old.json()


def test_only_the_upstream_outage_is_advertised_as_retryable():
    """The frontend derives its retry button from the code alone, so the
    property has to hold in the status codes too: 503 is the retryable one and
    every other failure is a 4xx/500 the same request cannot recover from."""
    retryable = {c for c, spec in ERROR_SPECS.items() if spec.status == 503}
    assert retryable == {ScoreErrorCode.UPSTREAM_UNAVAILABLE}


def test_every_code_has_a_spec():
    """A code with no table entry would raise a KeyError *inside the error
    handler* — turning a handled failure into an unhandled one."""
    assert set(ERROR_SPECS) == set(ScoreErrorCode)


def test_the_insufficient_data_copy_states_the_real_threshold_in_every_language():
    """"Not enough data" tells a user nothing they can act on; "at least 60
    trading days" tells them the answer is "wait" and roughly how long. The
    number is therefore load-bearing copy, and it is written out by hand in
    three locale files that cannot import MIN_TRADING_DAYS — so raising the
    threshold without retranslating would leave three screens quoting a figure
    the backend no longer enforces. This is the only thing that would catch it.
    """
    locales = Path(__file__).resolve().parents[1] / "ui" / "web" / "src" / "i18n" / "locales"
    threshold = str(MIN_TRADING_DAYS)

    assert threshold in ERROR_SPECS[ScoreErrorCode.INSUFFICIENT_DATA].message

    for name in ("en.json", "zh-CN.json", "zh-TW.json"):
        catalog = json.loads((locales / name).read_text(encoding="utf-8"))
        copy = catalog["errors"]["insufficientData"]
        assert threshold in copy, f"{name} does not name the {threshold}-day threshold: {copy}"


# ── Which history is scorable ────────────────────────────────────────────────


def _history(n: int, *, end: datetime, source: str | None = None) -> pd.DataFrame:
    idx = pd.bdate_range(end=pd.Timestamp(end.date()), periods=n)
    df = pd.DataFrame({"close": [100.0] * n}, index=idx)
    if source is not None:
        df.attrs[SOURCE_ATTR] = source
    return df


def test_a_short_history_is_insufficient_data_not_a_neutral_fifty():
    """A 20-row IPO used to score: every percentile collapsed toward 50 and the
    card showed a confident MODERATE built on almost no information."""
    now = datetime.now(timezone.utc)
    df = _history(MIN_TRADING_DAYS - 1, end=now, source="live")
    with pytest.raises(InsufficientDataError) as excinfo:
        check_history_scorable(df, "IPO")
    assert classify_scoring_error(excinfo.value) is ScoreErrorCode.INSUFFICIENT_DATA


def test_exactly_the_minimum_is_enough():
    now = datetime.now(timezone.utc)
    check_history_scorable(_history(MIN_TRADING_DAYS, end=now, source="live"), "OK")


def test_history_that_stops_months_ago_is_delisted():
    now = datetime.now(timezone.utc)
    stale = now - timedelta(days=STALE_AFTER_DAYS + 5)
    with pytest.raises(DelistedError, match="suspended or delisted"):
        check_history_scorable(_history(200, end=stale, source="live"), "GONE")


def test_a_stale_snapshot_is_not_blamed_on_the_stock():
    """The regression this guard exists to prevent: under an upstream outage
    every ticker is served from a snapshot, and an unqualified staleness check
    would stamp "may be delisted" across a board of perfectly healthy names."""
    now = datetime.now(timezone.utc)
    stale = now - timedelta(days=STALE_AFTER_DAYS + 5)
    check_history_scorable(_history(200, end=stale, source="snapshot"), "HEALTHY")


def test_a_frame_with_no_provenance_is_not_judged_on_staleness():
    """Frames that never came through MarketDataFetcher (fixtures, test
    doubles, the simulation harness) carry no stamp, and guessing "live" would
    make every one of them look delisted."""
    df = _history(200, end=datetime(2024, 1, 1, tzinfo=timezone.utc))
    check_history_scorable(df, "FIXTURE")


def test_the_row_count_floor_applies_to_snapshots_too():
    """Staleness is excused for a snapshot; thinness is not — a 30-row snapshot
    cannot support a percentile no matter where it came from."""
    now = datetime.now(timezone.utc)
    with pytest.raises(InsufficientDataError):
        check_history_scorable(_history(30, end=now, source="snapshot"), "THIN")


# ── Provenance actually gets stamped ─────────────────────────────────────────


@pytest.fixture(autouse=True)
def _isolated_snapshot_dir(tmp_path, monkeypatch):
    from stock_risk.config import settings

    monkeypatch.setattr(settings, "snapshot_dir", tmp_path / "snapshots")


def _yf_frame(n: int = 200) -> pd.DataFrame:
    idx = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n)
    close = pd.Series([100.0 + i * 0.1 for i in range(n)], index=idx)
    return pd.DataFrame(
        {
            "Open": close * 0.99,
            "High": close * 1.01,
            "Low": close * 0.98,
            "Close": close,
            "Volume": [1_000_000.0] * n,
        },
        index=idx,
    )


def test_a_live_fetch_is_stamped_live():
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = _yf_frame()
    fetcher = MarketDataFetcher()
    with patch("stock_risk.data.fetcher.yf.Ticker", return_value=mock_ticker):
        df = fetcher.fetch_history("AAPL", period="1y")
    assert df.attrs[SOURCE_ATTR] == "live"


def test_a_snapshot_fallback_is_stamped_snapshot():
    """The stamp is what keeps a throttled deploy from reporting every ticker
    as delisted, so it has to survive the fallback path specifically."""
    fetcher = MarketDataFetcher()
    saved = _yf_frame()
    saved.columns = [c.lower() for c in saved.columns]
    fetcher._save_snapshot("AAPL", "1y", "1d", saved)

    with patch(
        "stock_risk.data.fetcher.yf.Ticker",
        side_effect=RuntimeError("Too Many Requests. Rate limited."),
    ):
        df = fetcher.fetch_history("AAPL", period="1y")
    assert df.attrs[SOURCE_ATTR] == "snapshot"


def test_an_empty_upstream_result_raises_the_typed_not_found_error():
    """Still a ValueError subclass, so `except ValueError` elsewhere (portfolio
    aggregation, the backtest endpoint) behaves exactly as it did — but now it
    also carries the code that turns it into a 404 with real copy."""
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = pd.DataFrame()
    fetcher = MarketDataFetcher()
    with patch("stock_risk.data.fetcher.yf.Ticker", return_value=mock_ticker):
        with pytest.raises(TickerNotFoundError, match="No data returned") as excinfo:
            fetcher.fetch_history("NOTAREALTICKER", period="1y")
    assert isinstance(excinfo.value, ValueError)
    assert classify_scoring_error(excinfo.value) is ScoreErrorCode.TICKER_NOT_FOUND
