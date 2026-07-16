"""Tests for data fetching and preprocessing."""

from unittest.mock import MagicMock, patch

import pandas as pd

from stock_risk.data.fetcher import MarketDataFetcher
from stock_risk.data.preprocessor import DataPreprocessor


def _make_ohlcv(n: int = 100) -> pd.DataFrame:
    import numpy as np
    dates = pd.bdate_range("2024-01-01", periods=n)
    close = 100 * (1 + np.random.randn(n).cumsum() * 0.01)
    return pd.DataFrame({
        "open": close * 0.99,
        "high": close * 1.01,
        "low": close * 0.98,
        "close": close,
        "volume": np.random.randint(1_000_000, 10_000_000, n),
    }, index=dates)


def test_preprocessor_adds_returns():
    df = _make_ohlcv()
    result = DataPreprocessor().process(df)
    assert "log_return" in result.columns
    assert "pct_return" in result.columns


def test_preprocessor_no_nans_in_close():
    df = _make_ohlcv()
    result = DataPreprocessor().process(df)
    assert result["close"].isnull().sum() == 0


def test_fetch_news_parses_yfinance_content_shape():
    mock_ticker = MagicMock()
    mock_ticker.news = [
        {
            "content": {
                "title": "Company X faces lawsuit",
                "summary": "A regulator filed suit against Company X.",
                "provider": {"displayName": "Reuters"},
                "pubDate": "2026-07-01T12:00:00Z",
                "canonicalUrl": {"url": "https://example.com/article"},
            }
        },
        {"content": {"title": ""}},  # no title -> should be dropped
    ]
    with patch("stock_risk.data.fetcher.yf.Ticker", return_value=mock_ticker):
        articles = MarketDataFetcher().fetch_news("XYZ", limit=8)

    assert len(articles) == 1
    assert articles[0]["title"] == "Company X faces lawsuit"
    assert articles[0]["publisher"] == "Reuters"
    assert articles[0]["link"] == "https://example.com/article"


def test_fetch_news_returns_empty_list_on_error():
    with patch("stock_risk.data.fetcher.yf.Ticker", side_effect=RuntimeError("boom")):
        articles = MarketDataFetcher().fetch_news("XYZ")
    assert articles == []


def test_fetch_analyst_activity_counts_recent_actions_only():
    now = pd.Timestamp.now()
    idx = pd.DatetimeIndex(
        [now - pd.Timedelta(days=5), now - pd.Timedelta(days=10), now - pd.Timedelta(days=200)],
        name="GradeDate",
    )
    df = pd.DataFrame(
        {"Firm": ["A", "B", "C"], "Action": ["downgrade", "upgrade", "downgrade"]}, index=idx
    )
    mock_ticker = MagicMock()
    mock_ticker.upgrades_downgrades = df
    with patch("stock_risk.data.fetcher.yf.Ticker", return_value=mock_ticker):
        result = MarketDataFetcher().fetch_analyst_activity("XYZ", lookback_days=90)
    # the 200-day-old downgrade falls outside the lookback window
    assert result == {"downgrade_count": 1, "upgrade_count": 1}


def test_fetch_analyst_activity_empty_dataframe():
    mock_ticker = MagicMock()
    mock_ticker.upgrades_downgrades = pd.DataFrame()
    with patch("stock_risk.data.fetcher.yf.Ticker", return_value=mock_ticker):
        result = MarketDataFetcher().fetch_analyst_activity("XYZ")
    assert result == {"downgrade_count": 0, "upgrade_count": 0}


def test_fetch_insider_activity_counts_transactions():
    df = pd.DataFrame({"Transaction": ["Sale", "Sale", "Purchase", "Option Exercise"]})
    mock_ticker = MagicMock()
    mock_ticker.insider_transactions = df
    with patch("stock_risk.data.fetcher.yf.Ticker", return_value=mock_ticker):
        result = MarketDataFetcher().fetch_insider_activity("XYZ")
    assert result == {"sale_count": 2, "purchase_count": 1, "net_transaction_count": -1}


def test_fetch_vix_returns_float():
    mock_ticker = MagicMock()
    mock_ticker.fast_info.last_price = 18.5
    with patch("stock_risk.data.fetcher.yf.Ticker", return_value=mock_ticker):
        vix = MarketDataFetcher().fetch_vix()
    assert vix == 18.5


def test_fetch_vix_returns_none_on_error():
    with patch("stock_risk.data.fetcher.yf.Ticker", side_effect=RuntimeError("boom")):
        assert MarketDataFetcher().fetch_vix() is None
