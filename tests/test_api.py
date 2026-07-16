"""Tests for FastAPI endpoints (uses httpx test client)."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from stock_risk.api.app import app

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
