"""Tests for FastAPI endpoints (uses httpx test client)."""

import json
from unittest.mock import patch

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient
from loguru import logger

from stock_risk.api import app as app_module
from stock_risk.api.app import app
from stock_risk.data.fetcher import MarketDataFetcher
from stock_risk.models.downside_risk import DownsideRiskModel
from stock_risk.models.feature_sets import build_dataset
from stock_risk.monitoring.metrics import ModelMonitor
from stock_risk.scoring.scorer import RiskScorer

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_score_invalid_ticker():
    with patch(
        "stock_risk.scoring.scorer.MarketDataFetcher.fetch_history",
        side_effect=ValueError("No data"),
    ):
        response = client.get("/score/INVALID_TICKER_XYZ")
    assert response.status_code == 404


def _fake_scorecard(ticker: str = "AAPL") -> dict:
    """Minimal dict satisfying every required field of api.schemas.ScoreResponse."""
    return {
        "ticker": ticker,
        "timestamp": "2026-07-17T00:00:00Z",
        "risk_score": 42.0,
        "risk_label": "MODERATE",
        "risk_note": "test note",
        "risk_breakdown": {
            "volatility": {"score": 50.0, "weight": 0.25, "metrics": {"vol_21d": 50.0}},
        },
        "market_regime": {"vix": 15.0, "regime": "calm", "market": "us", "benchmark": "SPY"},
        "ml_drawdown_probability": None,
        "ml_drawdown_explanation": None,
        "garch_volatility_forecast": None,
        "har_volatility_forecast": None,
        "options_implied": None,
        "news_risk": {
            "llm_configured": False, "max_severity": 0, "negative_count": 0, "articles": [],
        },
        "alt_data": {
            "analyst_activity": {"downgrade_count": 0, "upgrade_count": 0},
            "insider_activity": {"sale_count": 0, "purchase_count": 0, "net_transaction_count": 0},
        },
        "stress_test": None,
        "volatility_30d": 0.3,
        "var_95": -0.02,
        "cvar_95": -0.03,
        "max_drawdown_90d": -0.1,
        "beta": 1.1,
        "implied_volatility": None,
        "name": "Apple Inc.",
        "indicators": {"rsi_14": 55.0, "bb_pct": 0.5, "atr_14": 2.0},
        "fundamentals": {"sector": "Technology", "market_cap": 1_000_000, "trailing_pe": 25.0},
    }


def test_legacy_and_new_score_endpoints_behave_identically():
    """/score/{ticker} and /api/score/{ticker} now share one implementation
    (_score_ticker) instead of two copy-pasted bodies that silently drifted
    apart (see the [C1] postmortem: only one of them used to log exceptions).
    Covers the three cases that matter: an unexpected error (500, logged),
    a ValueError (404), and success (200, byte-for-byte identical bodies)."""
    log_sink = []
    handler_id = logger.add(lambda msg: log_sink.append(str(msg)), level="ERROR")
    try:
        with patch.object(RiskScorer, "score", side_effect=RuntimeError("boom")):
            r_new = client.get("/api/score/AAPL")
            r_old = client.get("/score/AAPL")
        assert r_new.status_code == r_old.status_code == 500
        assert r_new.json() == r_old.json()
        assert any("boom" in m for m in log_sink), "the 500 must be logged with context, not silent"

        with patch.object(RiskScorer, "score", side_effect=ValueError("no data for XYZ")):
            r_new = client.get("/api/score/XYZ")
            r_old = client.get("/score/XYZ")
        assert r_new.status_code == r_old.status_code == 404
        assert r_new.json() == r_old.json()

        fake = _fake_scorecard()
        with patch.object(RiskScorer, "score", return_value=fake):
            r_new = client.get("/api/score/AAPL")
            r_old = client.get("/score/AAPL")
        assert r_new.status_code == r_old.status_code == 200
        assert r_new.json() == r_old.json() == fake
    finally:
        logger.remove(handler_id)


def _synthetic_raw_ohlcv(n: int = 400, seed: int = 3) -> pd.DataFrame:
    """Matches MarketDataFetcher.fetch_history's output contract, with a
    forced drawdown window so DownsideRiskModel has both classes to fit on."""
    rng = np.random.default_rng(seed)
    rets = rng.standard_normal(n) * 0.01 + 0.0002
    rets[150:170] = rng.standard_normal(20) * 0.04 - 0.02
    close = 100 * np.exp(np.cumsum(rets))
    dates = pd.bdate_range("2023-01-01", periods=n)
    df = pd.DataFrame({
        "open": close * 0.99, "high": close * 1.01,
        "low": close * 0.98, "close": close,
        "volume": rng.integers(1_000_000, 5_000_000, n).astype(float),
    }, index=dates)
    df.index.name = "date"
    return df


def _mock_fetcher(monkeypatch, raw_df: pd.DataFrame) -> None:
    """Patch every MarketDataFetcher method RiskScorer.score() calls, so the
    test never touches the network — matches the existing
    test_scorer.py::_synthetic_ohlcv pattern, extended to the full set of
    calls score() makes (not just fetch_history)."""
    monkeypatch.setattr(MarketDataFetcher, "fetch_history", lambda self, ticker, **kw: raw_df)
    monkeypatch.setattr(MarketDataFetcher, "fetch_info", lambda self, ticker: {"beta": 1.1})
    monkeypatch.setattr(MarketDataFetcher, "fetch_vix", lambda self: 15.0)
    monkeypatch.setattr(MarketDataFetcher, "fetch_news", lambda self, ticker, limit=8: [])
    monkeypatch.setattr(
        MarketDataFetcher, "fetch_analyst_activity",
        lambda self, ticker, lookback_days=90: {"downgrade_count": 0, "upgrade_count": 0},
    )
    monkeypatch.setattr(
        MarketDataFetcher, "fetch_insider_activity",
        lambda self, ticker: {"sale_count": 0, "purchase_count": 0, "net_transaction_count": 0},
    )
    monkeypatch.setattr(MarketDataFetcher, "fetch_options_iv", lambda self, ticker: None)


def _fit_and_save_tiny_model(model_dir, raw_df: pd.DataFrame) -> None:
    from stock_risk.data.preprocessor import DataPreprocessor
    from stock_risk.features.risk_metrics import RiskMetrics
    from stock_risk.features.technical import TechnicalFeatures

    df = RiskMetrics().compute(TechnicalFeatures().compute(DataPreprocessor().process(raw_df)))
    dataset = build_dataset({"AAPL": df})
    model = DownsideRiskModel()
    model.fit_calibrated(dataset)
    model.save(model_dir)


def test_score_endpoint_with_real_trained_model_returns_valid_json(monkeypatch, tmp_path):
    """End-to-end regression test for the numpy.float32 JSON-serialization
    crash (see CLAUDE.md hard rule #4 / models/explain.py). Every *other*
    test's RiskScorer has no model loaded, so ml_drawdown_explanation is
    always None and never gets near json.dumps or ScoreResponse — this is
    the one test that actually loads a real fitted DownsideRiskModel and
    drives the request through TestClient + the real FastAPI response
    pipeline, which is the exact path that broke in production.

    Red/green-verified manually: `git stash -- src/stock_risk/models/explain.py`
    (restoring the pre-fix `values.sum()` without `float()`) makes this test
    fail with the real `Object of type float32 is not JSON serializable`
    TypeError; `git stash pop` restores the fix and it passes again.
    """
    raw_df = _synthetic_raw_ohlcv()
    _mock_fetcher(monkeypatch, raw_df)
    _fit_and_save_tiny_model(tmp_path, raw_df)

    monitor_dir = tmp_path / "monitoring"
    monkeypatch.setattr(app_module, "scorer", RiskScorer(model_dir=tmp_path))
    monkeypatch.setattr(app_module, "monitor", ModelMonitor(monitor_dir))

    response = TestClient(app_module.app).get("/api/score/AAPL")

    assert response.status_code == 200
    body = response.json()  # already proves FastAPI's own json encoding succeeded
    json.dumps(body)  # explicit belt-and-suspenders check per the issue's acceptance criteria
    assert body["ml_drawdown_explanation"] is not None, (
        "test is only meaningful if the real-model path actually ran"
    )

    # Prove ModelMonitor.record()'s *own* json.dumps succeeded too — not just
    # that the call-site try/except silently swallowed a failure there.
    log_path = monitor_dir / "AAPL.jsonl"
    assert log_path.exists()
    logged = json.loads(log_path.read_text().strip().splitlines()[-1])
    assert logged["ticker"] == "AAPL"


def test_monitor_failure_does_not_fail_the_request(monkeypatch):
    """A monitoring failure (disk full, bad data, whatever) must never turn a
    successful score into a 500 — see ModelMonitor.record's own try/except
    and the isolated try/except around its call site in api_score."""
    raw_df = _synthetic_raw_ohlcv(seed=4)
    _mock_fetcher(monkeypatch, raw_df)

    def _boom(self, scorecard):
        raise RuntimeError("disk full (simulated)")

    monkeypatch.setattr(ModelMonitor, "record", _boom)

    log_sink = []
    handler_id = logger.add(lambda msg: log_sink.append(msg), level="ERROR")
    try:
        response = client.get("/api/score/AAPL")
    finally:
        logger.remove(handler_id)

    assert response.status_code == 200
    assert response.json()["ticker"] == "AAPL"
    assert any("disk full (simulated)" in str(m) for m in log_sink), (
        "the monitoring failure must be logged even though the request still succeeds"
    )
