"""The public signal API: GET /api/v1/signal/{ticker} and the batch form.

What these pin, and why each matters to the consumer on the other end:

* the wire shape is a committed snapshot (tests/fixtures/signal_aapl.json),
  built from the same frozen scorecard the golden test uses — a renamed or
  retyped field fails here before it fails in Portfolio Lab;
* the numbers are fixed-decimal strings, so two services never disagree on
  a float's last bit;
* the optional key check, the per-IP bucket, and the daily snapshot cache
  each do what the README says they do;
* failures are the existing five-code taxonomy, with no exception text;
* the route's own copy passes the product's advice-language guard.
"""

from __future__ import annotations

import json
import re
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from stock_risk.alerts import advice_language_violations
from stock_risk.api import app as app_module
from stock_risk.api import signal as signal_module
from stock_risk.api.app import app
from stock_risk.api.errors import ERROR_SPECS
from stock_risk.api.signal import (
    MAX_BATCH_TICKERS,
    SIGNAL_SCHEMA_VERSION,
    build_signal,
    resolve_model_version,
)
from stock_risk.auth.models import SignalSnapshot
from stock_risk.config import settings
from stock_risk.data.quality import MIN_TRADING_DAYS
from stock_risk.db import get_session
from stock_risk.errors import (
    InsufficientDataError,
    ScoreErrorCode,
    TickerNotFoundError,
    UpstreamUnavailableError,
)
from stock_risk.scoring.scorer import RiskScorer
from stock_risk.security import RateLimiter

FIXTURES = Path(__file__).parent / "fixtures"
GOLDEN = FIXTURES / "golden_score_aapl.json"
SNAPSHOT = FIXTURES / "signal_aapl.json"
README = Path(__file__).parent.parent / "README.md"

# A fixed-decimal string: optional sign, digits, a point, digits. Nothing else
# — no exponent, no "nan", no bare integer.
_FIXED = re.compile(r"^-?\d+\.\d+$")

_DOCUMENTED_KEYS = {
    "schema_version", "ticker", "market", "as_of", "computed_at", "score", "regime",
    "factors", "shap", "ml_drawdown_prob_20d", "model_version", "history_days",
}
_FACTOR_KEYS = {"volatility", "tail_risk", "drawdown", "market_sensitivity", "liquidity"}


def _scorecard(ticker: str = "AAPL") -> dict:
    """The golden scorecard — a real `RiskScorer.score()` output — re-labelled.

    `timestamp` is popped by the golden test and so is absent from the file;
    it is fixed here so the snapshot below is byte-for-byte reproducible.
    """
    card = json.loads(GOLDEN.read_text(encoding="utf-8"))
    card["ticker"] = ticker
    card["timestamp"] = "2026-09-26T21:00:00Z"
    return card


@pytest.fixture()
def env(monkeypatch):
    """A client whose snapshot table lives in a throwaway in-memory database,
    and a model version that does not depend on which artefact is on disk."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)

    def override_get_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    monkeypatch.setattr(app_module, "_SIGNAL_MODEL_VERSION", "test-model")
    yield TestClient(app), engine
    app.dependency_overrides.clear()


def _by_ticker(ticker: str, failing: dict | None = None):
    """A `RiskScorer.score` stand-in that answers per ticker, or raises."""
    failing = failing or {}

    def _score(self_or_ticker, *args, **kwargs):
        # Works both bound (patch.object on the class) and unbound.
        symbol = args[0] if args else self_or_ticker
        if symbol in failing:
            raise failing[symbol]
        return _scorecard(symbol)

    return _score


# ── Wire shape ───────────────────────────────────────────────────────────────


def test_build_signal_matches_the_committed_snapshot():
    """The pure transform, against the committed file. Regenerate the file on
    purpose (and bump SIGNAL_SCHEMA_VERSION if a field changed meaning), never
    by hand-editing it to make this pass."""
    expected = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    assert build_signal(_scorecard(), model_version="test-model") == expected
    assert expected["schema_version"] == SIGNAL_SCHEMA_VERSION


def test_endpoint_returns_the_snapshot_byte_for_byte(env):
    """Same fixture, end to end: the response model must add nothing, drop
    nothing and coerce nothing on the way out."""
    client, _ = env
    expected = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    with patch.object(RiskScorer, "score", return_value=_scorecard()):
        response = client.get("/api/v1/signal/AAPL")
    assert response.status_code == 200, response.text
    assert response.json() == expected
    assert response.headers["cache-control"] == "max-age=3600"


def test_numbers_are_fixed_decimal_strings_and_counts_are_integers():
    body = build_signal(_scorecard(), model_version="v")
    for key in _FACTOR_KEYS:
        assert _FIXED.match(body["factors"][key]), (key, body["factors"][key])
        assert body["factors"][key].split(".")[1].__len__() == 2
    for key in _FACTOR_KEYS | {"other"}:
        assert _FIXED.match(body["shap"][key]), (key, body["shap"][key])
        assert len(body["shap"][key].split(".")[1]) == 4
    assert _FIXED.match(body["ml_drawdown_prob_20d"])
    assert isinstance(body["score"], int) and not isinstance(body["score"], bool)
    assert isinstance(body["history_days"], int)
    # Probability, not the percentage the UI shows.
    assert 0.0 <= float(body["ml_drawdown_prob_20d"]) <= 1.0


def test_only_the_documented_fields_and_no_var_backtest_output():
    body = build_signal(_scorecard(), model_version="v")
    assert set(body) == _DOCUMENTED_KEYS
    assert set(body["factors"]) == _FACTOR_KEYS
    assert set(body["shap"]) == _FACTOR_KEYS | {"other"}

    def walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                yield key
                yield from walk(value)

    keys = {k.lower() for k in walk(body)}
    assert not any("var" in k or "backtest" in k or "cvar" in k for k in keys), keys


def test_numpy_scalars_are_formatted_not_leaked():
    """CLAUDE.md §3.5, on this surface: a float32 out of SHAP or XGBoost must
    become a string here, not a serialisation error downstream."""
    card = _scorecard()
    card["risk_breakdown"]["tail"]["score"] = np.float32(67.3)
    card["ml_drawdown_explanation"]["category_contributions"]["tail"] = np.float32(-0.5782)
    card["ml_drawdown_probability"] = np.float32(7.6)
    body = build_signal(card, model_version="v")
    assert body["factors"]["tail_risk"] == "67.30"
    assert body["shap"]["tail_risk"] == "-0.5782"
    assert body["ml_drawdown_prob_20d"] == "0.0760"
    json.dumps(body)  # native types all the way down


@pytest.mark.parametrize(
    "internal, public",
    [("calm", "calm"), ("elevated", "elevated"), ("panic", "panic"), ("not_available", None)],
)
def test_regime_is_published_under_the_contract_names(internal, public):
    card = _scorecard()
    card["market_regime"]["regime"] = internal
    assert build_signal(card, model_version="v")["regime"] == public


def test_ml_leg_off_yields_nulls_not_zeros():
    card = _scorecard()
    card["ml_drawdown_probability"] = None
    card["ml_drawdown_explanation"] = None
    body = build_signal(card, model_version="unavailable")
    assert body["shap"] is None
    assert body["ml_drawdown_prob_20d"] is None
    assert body["factors"]["volatility"] == "79.00"  # the percentile leg is untouched


def test_shap_sums_are_the_full_decomposition_not_the_top_five():
    """The scorecard lists only the five largest features; the signal's
    per-category sums come from every feature and add up to the model's whole
    log-odds shift from its base rate."""
    card = _scorecard()
    explanation = card["ml_drawdown_explanation"]
    logit = lambda p: np.log(p / (1 - p))  # noqa: E731
    total_shift = logit(explanation["predicted_probability"]) - logit(
        explanation["base_probability"]
    )
    body = build_signal(card, model_version="v")
    assert sum(float(v) for v in body["shap"].values()) == pytest.approx(total_shift, abs=1e-3)
    top_five = sum(f["shap_contribution"] for f in explanation["top_features"])
    assert top_five != pytest.approx(total_shift, abs=1e-3)


# The structural zeros, pinned. `shap.market_sensitivity` and `shap.liquidity`
# are "0.0000" on every response because no ML feature belongs to either
# category; this is the map that makes it so. Built from the deployed model's
# own feature names through the same lookup explain.py sums with, so mapping a
# new feature (or adding a beta/liquidity input to the model) fails here and
# forces the README and docstring statements to be revisited.
_EXPECTED_FEATURE_CATEGORIES = {
    "volatility": {"vol_21d", "vol_63d"},
    "tail": {"var_95_21d", "cvar_95_21d", "skew_63d", "kurt_63d"},
    "drawdown": {"max_drawdown_63d"},
    "sensitivity": set(),
    "liquidity": set(),
    "other": {
        "rsi_14", "dist_ema_20", "dist_ema_50", "bb_pct", "volume_ratio", "atr_14",
        "vol_regime_change", "vol_of_vol_20", "drawdown_acceleration", "skew_momentum",
        "sharpe_63d", "sortino_63d",
    },
}


def test_shap_category_map_is_exactly_the_documented_one():
    from stock_risk.models import explain

    model = app_module.scorer._dr_model
    assert model is not None and model.pipeline is not None, "committed artefact not loaded"
    feature_names = list(model.pipeline.named_steps["preprocessor"].get_feature_names_out())
    assert len(feature_names) == 19

    actual = {category: set() for category in _EXPECTED_FEATURE_CATEGORIES}
    for name in feature_names:
        _, _, column = name.rpartition("__")
        actual[explain._feature_category(name)].add(column)

    assert actual == _EXPECTED_FEATURE_CATEGORIES
    assert actual["sensitivity"] == actual["liquidity"] == set()


def test_model_version_resolution(tmp_path):
    assert resolve_model_version(None, model_dir=tmp_path, repo_root=tmp_path) == "unavailable"
    assert (
        resolve_model_version(object(), model_dir=tmp_path, repo_root=tmp_path) == "unversioned"
    )
    (tmp_path / "downside_risk_xgb.joblib").write_bytes(b"not really a model")
    version = resolve_model_version(object(), model_dir=tmp_path, repo_root=tmp_path)
    assert re.fullmatch(r"sha256:[0-9a-f]{12}", version), version


# ── Auth ─────────────────────────────────────────────────────────────────────


def test_open_when_no_keys_are_configured(env, monkeypatch):
    client, _ = env
    monkeypatch.setattr(settings, "signal_api_keys", None)
    with patch.object(RiskScorer, "score", return_value=_scorecard()):
        assert client.get("/api/v1/signal/AAPL").status_code == 200


def test_key_required_when_configured(env, monkeypatch):
    client, _ = env
    monkeypatch.setattr(settings, "signal_api_keys", "first-key, second-key,")
    with patch.object(RiskScorer, "score", return_value=_scorecard()):
        missing = client.get("/api/v1/signal/AAPL")
        wrong = client.get("/api/v1/signal/AAPL", headers={"X-Api-Key": "first-ke"})
        empty = client.get("/api/v1/signal/AAPL", headers={"X-Api-Key": ""})
        right = client.get("/api/v1/signal/AAPL", headers={"X-Api-Key": "second-key"})
        batch = client.get("/api/v1/signal?tickers=AAPL", headers={"X-Api-Key": "first-key"})

    assert missing.status_code == wrong.status_code == empty.status_code == 401
    # One message for both cases, and never the configured keys.
    assert missing.json() == wrong.json()
    assert "first-key" not in missing.text and "second-key" not in missing.text
    assert right.status_code == 200
    assert batch.status_code == 200


# ── Rate limit ───────────────────────────────────────────────────────────────


@pytest.fixture()
def tiny_signal_bucket(monkeypatch, rate_limited):
    """Two requests, then dry — sized so the test asserts the limiter fires
    rather than being coupled to the configured 60/min."""
    monkeypatch.setattr(signal_module, "_signal_limiter", RateLimiter(rate=0.01, burst=2.0))


def test_rate_limit_returns_429_with_retry_after(env, tiny_signal_bucket):
    client, _ = env
    with patch.object(RiskScorer, "score", return_value=_scorecard()):
        statuses = [client.get("/api/v1/signal/AAPL").status_code for _ in range(3)]
        limited = client.get("/api/v1/signal/AAPL")
    assert statuses == [200, 200, 429], statuses
    assert limited.status_code == 429
    assert int(limited.headers["Retry-After"]) >= 1
    assert "rate limit" in limited.json()["detail"].lower()


def test_a_batch_costs_one_request_however_many_tickers(env, tiny_signal_bucket):
    client, _ = env
    with patch.object(RiskScorer, "score", side_effect=_by_ticker("x")):
        first = client.get("/api/v1/signal?tickers=AAPL,MSFT,JPM,SPY,TSLA")
        second = client.get("/api/v1/signal?tickers=AAPL")
        third = client.get("/api/v1/signal?tickers=AAPL")
    assert first.status_code == 200 and len(first.json()["results"]) == 5
    assert second.status_code == 200
    assert third.status_code == 429


def test_the_general_bucket_does_not_also_charge_this_route():
    """Two limiters on one route would make the effective limit the tighter
    of two settings nobody set together."""
    assert app_module._endpoint_cost("/api/v1/signal/AAPL") == 0.0
    assert app_module._endpoint_cost("/api/v1/signal?tickers=AAPL") == 0.0


# ── Errors: the existing taxonomy, untouched ─────────────────────────────────


def test_insufficient_history_is_a_422_with_the_taxonomy_code(env):
    """A fresh listing with 12 sessions: the symbol is real, the request is
    well-formed, and there is no honest number yet — 422, INSUFFICIENT_DATA,
    a message that names the threshold, and not a word of the exception."""
    client, _ = env
    with patch.object(RiskScorer, "score", side_effect=InsufficientDataError("only 12 rows")):
        response = client.get("/api/v1/signal/NEWIPO")
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["error"] == ScoreErrorCode.INSUFFICIENT_DATA.value
    assert body["ticker"] == "NEWIPO"
    assert body["message"] == ERROR_SPECS[ScoreErrorCode.INSUFFICIENT_DATA].message
    assert str(MIN_TRADING_DAYS) in body["message"]
    assert "12 rows" not in response.text
    assert "max-age" not in response.headers.get("cache-control", "")


@pytest.mark.parametrize(
    "exc, code, status",
    [
        (TickerNotFoundError("no such symbol"), ScoreErrorCode.TICKER_NOT_FOUND, 404),
        (UpstreamUnavailableError("all failed"), ScoreErrorCode.UPSTREAM_UNAVAILABLE, 503),
        (RuntimeError("C:/secrets/prod-key.pem"), ScoreErrorCode.CALCULATION_FAILED, 500),
    ],
)
def test_other_failures_use_their_existing_codes_and_leak_nothing(env, exc, code, status):
    client, _ = env
    with patch.object(RiskScorer, "score", side_effect=exc):
        response = client.get("/api/v1/signal/ERR")
    assert response.status_code == status, response.text
    assert response.json()["error"] == code.value
    assert str(exc) not in response.text


# ── Batch ────────────────────────────────────────────────────────────────────


def test_batch_returns_results_and_per_ticker_errors(env):
    client, _ = env
    failing = {
        "NEWIPO": InsufficientDataError("only 12 rows"),
        "NOPE": TickerNotFoundError("no data"),
    }
    with patch.object(RiskScorer, "score", side_effect=_by_ticker("x", failing)):
        response = client.get("/api/v1/signal?tickers=AAPL,NEWIPO,MSFT,NOPE")
    assert response.status_code == 200, response.text
    body = response.json()
    assert [r["ticker"] for r in body["results"]] == ["AAPL", "MSFT"]
    assert body["errors"] == [
        {"ticker": "NEWIPO", "code": "INSUFFICIENT_DATA"},
        {"ticker": "NOPE", "code": "TICKER_NOT_FOUND"},
    ]
    assert "12 rows" not in response.text
    # A transient failure must not be cached for an hour by an intermediary.
    assert response.headers["cache-control"] == "no-store"


def test_batch_of_successes_is_cacheable(env):
    client, _ = env
    with patch.object(RiskScorer, "score", side_effect=_by_ticker("x")):
        response = client.get("/api/v1/signal?tickers=aapl, msft ,AAPL")
    assert response.status_code == 200
    assert [r["ticker"] for r in response.json()["results"]] == ["AAPL", "MSFT"]
    assert response.json()["errors"] == []
    assert response.headers["cache-control"] == "max-age=3600"


def test_batch_shape_limits_are_plain_422s(env):
    client, _ = env
    too_many = ",".join(f"T{i}" for i in range(MAX_BATCH_TICKERS + 1))
    with patch.object(RiskScorer, "score", side_effect=_by_ticker("x")):
        over = client.get(f"/api/v1/signal?tickers={too_many}")
        empty = client.get("/api/v1/signal?tickers=,,")
        missing = client.get("/api/v1/signal")
        at_cap = client.get(
            "/api/v1/signal?tickers=" + ",".join(f"T{i}" for i in range(MAX_BATCH_TICKERS))
        )
    assert over.status_code == 422 and "20" in over.json()["detail"]
    assert "error" not in over.json()  # a request-shape problem, not a scoring code
    assert empty.status_code == 422
    assert missing.status_code == 422
    assert at_cap.status_code == 200 and len(at_cap.json()["results"]) == MAX_BATCH_TICKERS


# ── Daily snapshot cache ─────────────────────────────────────────────────────


def test_second_request_today_is_served_from_the_snapshot(env):
    """One computation per ticker per day. After the first call the in-process
    score cache is cleared and the scorer is made to fail, so a 200 can only
    have come from the stored row."""
    client, engine = env
    with patch.object(RiskScorer, "score", return_value=_scorecard()) as score:
        first = client.get("/api/v1/signal/AAPL")
    assert first.status_code == 200
    assert score.call_count == 1

    with Session(engine) as session:
        rows = session.exec(select(SignalSnapshot)).all()
    assert len(rows) == 1
    assert rows[0].ticker == "AAPL"
    assert rows[0].as_of.isoformat() == first.json()["as_of"]
    assert rows[0].captured_on == signal_module.utc_today()
    assert rows[0].schema_version == SIGNAL_SCHEMA_VERSION

    app_module._score_cache.clear()
    with patch.object(RiskScorer, "score", side_effect=AssertionError("must not recompute")):
        second = client.get("/api/v1/signal/AAPL")
        batch = client.get("/api/v1/signal?tickers=AAPL")
    assert second.status_code == 200
    assert second.json() == first.json()
    assert batch.json()["results"] == [first.json()]


def test_yesterdays_snapshot_is_not_served(env):
    client, engine = env
    today = signal_module.utc_today()
    stale = build_signal(_scorecard(), model_version="stale-model")
    with Session(engine) as session:
        session.add(
            SignalSnapshot(
                ticker="AAPL",
                market="US",
                as_of=today - timedelta(days=1),
                schema_version=SIGNAL_SCHEMA_VERSION,
                payload=json.dumps(stale),
                captured_on=today - timedelta(days=1),
            )
        )
        session.commit()

    with patch.object(RiskScorer, "score", return_value=_scorecard()) as score:
        response = client.get("/api/v1/signal/AAPL")
    assert response.status_code == 200
    assert score.call_count == 1
    assert response.json()["model_version"] == "test-model"

    with Session(engine) as session:
        days = sorted(r.captured_on for r in session.exec(select(SignalSnapshot)).all())
    assert days == [today - timedelta(days=1), today]


def test_a_failed_snapshot_write_does_not_fail_the_request(env):
    client, _ = env
    with (
        patch.object(RiskScorer, "score", return_value=_scorecard()),
        patch.object(app_module, "store_signal", side_effect=RuntimeError("disk full")),
    ):
        response = client.get("/api/v1/signal/AAPL")
    assert response.status_code == 200
    assert "disk full" not in response.text


# ── Copy ─────────────────────────────────────────────────────────────────────


def _readme_section(title: str) -> str:
    text = README.read_text(encoding="utf-8")
    start = text.index(f"\n## {title}\n")
    end = text.find("\n## ", start + 1)
    return text[start : end if end != -1 else len(text)]


def test_route_copy_contains_no_advice_language():
    """The same guard the alert emails are held to, over everything this route
    says in words: the OpenAPI description a consumer reads, the module and
    route docstrings, and the README section."""
    spec = app.openapi()
    surfaces = {
        "openapi:paths": json.dumps(
            {p: v for p, v in spec["paths"].items() if p.startswith("/api/v1/signal")}
        ),
        "openapi:schemas": json.dumps(
            {n: s for n, s in spec["components"]["schemas"].items() if n.startswith("Signal")}
        ),
        "module docstring": signal_module.__doc__ or "",
        "route docstrings": "\n".join(
            fn.__doc__ or ""
            for fn in (app_module.api_signal, app_module.api_signal_batch, app_module._signal_for)
        ),
        "README section": _readme_section("Public signal API"),
    }
    for name, text in surfaces.items():
        assert text.strip(), f"{name} is empty"
        assert advice_language_violations(text) == [], f"advice language in {name}"


def test_readme_documents_the_endpoint_and_the_caveat():
    section = _readme_section("Public signal API")
    assert "/api/v1/signal/{ticker}" in section
    assert "tickers=" in section
    assert "not investment advice" in section
    assert "own history" in section
    assert f'"schema_version": "{SIGNAL_SCHEMA_VERSION}"' in section
    for key in _DOCUMENTED_KEYS:
        assert f'"{key}"' in section, f"README schema is missing {key}"
    for code in ScoreErrorCode:
        assert code.value in section, f"README error table is missing {code.value}"
