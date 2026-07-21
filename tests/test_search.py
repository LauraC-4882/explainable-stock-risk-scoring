"""Tests for /api/search's known-symbols fallback — added after observing
live on Render that yf.Search returns an empty list for both "Tencent" and
"Apple" while yfinance is throttled there, which silently forced SearchBar's
Enter handler to add raw company-name text as a literal, invalid ticker
(e.g. "TENCENT")."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from stock_risk.api.app import app
from stock_risk.data.known_symbols import search_known_symbols

client = TestClient(app)


def test_search_known_symbols_matches_english_company_name():
    assert search_known_symbols("Tencent") == [
        {"symbol": "0700.HK", "name": "Tencent Holdings", "exchange": "HKEX", "type": "Equity"}
    ]


def test_search_known_symbols_matches_chinese_alias():
    results = search_known_symbols("茅台")
    assert results and results[0]["symbol"] == "600519.SS"


def test_search_known_symbols_is_case_insensitive():
    assert search_known_symbols("MOUTAI") == search_known_symbols("moutai")


def test_search_known_symbols_matches_by_ticker_too():
    results = search_known_symbols("aapl")
    assert results and results[0]["symbol"] == "AAPL"


def test_search_known_symbols_no_match_returns_empty():
    assert search_known_symbols("not a real company xyz") == []


def test_api_search_falls_back_to_known_symbols_when_yfinance_search_is_empty():
    """The exact scenario observed live: yf.Search(...).quotes == []."""
    with patch("stock_risk.api.app.yf.Search") as mock_search:
        mock_search.return_value.quotes = []
        response = client.get("/api/search", params={"q": "Tencent"})
    assert response.status_code == 200
    body = response.json()
    assert body and body[0]["symbol"] == "0700.HK"


def test_api_search_falls_back_when_yfinance_search_raises():
    with patch("stock_risk.api.app.yf.Search", side_effect=RuntimeError("Too Many Requests")):
        response = client.get("/api/search", params={"q": "Moutai"})
    assert response.status_code == 200
    body = response.json()
    assert body and body[0]["symbol"] == "600519.SS"


def test_api_search_prefers_live_yfinance_results_when_available():
    """The fallback must never mask a real, working live search."""
    mock_quote = {
        "symbol": "TCEHY",
        "shortname": "Tencent Holdings ADR",
        "quoteType": "EQUITY",
        "exchDisp": "OTC",
        "typeDisp": "Equity",
    }
    with patch("stock_risk.api.app.yf.Search") as mock_search:
        mock_search.return_value.quotes = [mock_quote]
        response = client.get("/api/search", params={"q": "Tencent"})
    body = response.json()
    assert body == [
        {"symbol": "TCEHY", "name": "Tencent Holdings ADR", "exchange": "OTC", "type": "Equity"}
    ]
