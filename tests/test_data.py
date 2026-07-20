"""Tests for data fetching and preprocessing."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest
import requests
from cachetools import TTLCache

from stock_risk.data.fetcher import MarketDataFetcher, _TimeoutSession
from stock_risk.data.preprocessor import DataPreprocessor
from stock_risk.data.validation import DataValidationError, validate_ohlcv


class _FakeTimer:
    """Deterministic stand-in for cachetools' default time.monotonic timer —
    lets TTL-expiry tests advance time exactly, without a real time.sleep()
    (flaky under load) or monkeypatching the time module globally."""

    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds

FIXTURES_DIR = Path(__file__).parent / "fixtures"


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


def test_preprocessor_survives_dst_mixed_timestamps():
    """Regression test: real yfinance timestamps carry a time-of-day (market
    close in UTC) that shifts by an hour across DST transitions, e.g.
    04:00:00 vs 05:00:00 within the same fetch. asfreq("B") reindexes against
    midnight-aligned dates, so without normalizing the index first, almost
    every row silently fails to match the new index and gets dropped instead
    of forward-filled — this used to shrink a 123-row real fetch to 40 rows."""
    import numpy as np

    n = 120
    dates = pd.bdate_range("2024-01-01", periods=n)
    # Half the timestamps carry a 04:00 time-of-day, half 05:00 — like a real
    # EST/EDT DST split within one fetch.
    times = [pd.Timedelta(hours=4) if i < n // 2 else pd.Timedelta(hours=5) for i in range(n)]
    index = dates + pd.TimedeltaIndex(times)
    close = 100 * (1 + np.random.randn(n).cumsum() * 0.01)
    df = pd.DataFrame({
        "open": close * 0.99, "high": close * 1.01,
        "low": close * 0.98, "close": close,
        "volume": np.random.randint(1_000_000, 10_000_000, n),
    }, index=index)

    result = DataPreprocessor().process(df)
    # Allow a little loss to gap-filling/outlier removal, but not the ~65%
    # collapse the unnormalized-index bug caused.
    assert len(result) >= n - 5


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


def test_validate_ohlcv_accepts_clean_data():
    df = _make_ohlcv()
    result = validate_ohlcv(df, "TEST")
    assert result is df


def test_validate_ohlcv_rejects_negative_price():
    df = _make_ohlcv()
    df.loc[df.index[5], "close"] = -5.0
    with pytest.raises(DataValidationError, match="close"):
        validate_ohlcv(df, "TEST")


def test_validate_ohlcv_rejects_zero_price():
    df = _make_ohlcv()
    df.loc[df.index[5], "close"] = 0.0
    with pytest.raises(DataValidationError, match="close"):
        validate_ohlcv(df, "TEST")


def test_validate_ohlcv_rejects_high_below_low():
    df = _make_ohlcv()
    df.loc[df.index[5], "high"] = df.loc[df.index[5], "low"] - 1.0
    with pytest.raises(DataValidationError, match=r"high.*low"):
        validate_ohlcv(df, "TEST")


def test_validate_ohlcv_rejects_out_of_order_dates():
    df = _make_ohlcv()
    idx = list(df.index)
    idx[5], idx[6] = idx[6], idx[5]
    df.index = pd.DatetimeIndex(idx)
    with pytest.raises(DataValidationError, match="strictly increasing"):
        validate_ohlcv(df, "TEST")


def test_validate_ohlcv_rejects_gap_too_large():
    df = _make_ohlcv()
    idx = list(df.index)
    # push everything from row 20 onward out by 30 calendar days — stays
    # monotonic, but blows well past MAX_GAP_TRADING_DAYS between rows 19/20
    idx = idx[:20] + [d + pd.Timedelta(days=30) for d in idx[20:]]
    df.index = pd.DatetimeIndex(idx)
    assert df.index.is_monotonic_increasing
    with pytest.raises(DataValidationError, match="gap"):
        validate_ohlcv(df, "TEST")


def test_validate_ohlcv_rejects_negative_volume():
    df = _make_ohlcv()
    df.loc[df.index[5], "volume"] = -100.0
    with pytest.raises(DataValidationError, match="volume"):
        validate_ohlcv(df, "TEST")


def test_validate_ohlcv_tolerates_nan_only_on_final_incomplete_session():
    """A still-open "today" session legitimately comes back from yfinance as
    a partial bar with NaN OHLC — not bad data, just incomplete data that
    DataPreprocessor.process() already drops via dropna(). Only the *last*
    row gets this pass; NaN anywhere else is still rejected."""
    df = _make_ohlcv()
    df.loc[df.index[-1], ["open", "high", "low", "close"]] = float("nan")
    result = validate_ohlcv(df, "TEST")
    assert result is df  # accepted, not stripped — preprocessing handles the drop


def test_validate_ohlcv_rejects_nan_mid_history():
    df = _make_ohlcv()
    df.loc[df.index[5], "close"] = float("nan")
    with pytest.raises(DataValidationError):
        validate_ohlcv(df, "TEST")


def test_validate_ohlcv_reproduces_issue_repro_case():
    """The exact malformed data from the issue's repro: high < low, a zero
    close, and negative volume — must raise with the violating column names
    visible in the error message, not pass through silently."""
    dates = pd.bdate_range("2024-01-01", periods=10)
    df = pd.DataFrame({
        "open": 100.0, "high": 99.0, "low": 101.0,  # high < low, physically impossible
        "close": [100.0, 0.0] + [100.0] * 8,          # close = 0
        "volume": -1.0,                                # negative volume
    }, index=dates)
    with pytest.raises(DataValidationError) as excinfo:
        validate_ohlcv(df, "BADTICKER")
    assert "BADTICKER" in str(excinfo.value)


def test_outlier_filter_preserves_real_historic_event():
    """Regression test: a pure `|log return| > 6 sigma` amplitude filter
    deleted real market history, not just bad ticks — verified live against
    SPY's real 2025-04-09 close (+9.99%, the tariff-pause rally, one of the
    largest single-day gains since 2008). For a tail-risk scorer, silently
    deleting the tail events it exists to measure is self-defeating.

    Fixture is a real 2-year SPY OHLCV pull (tests/fixtures/
    spy_2025_04_tariff_rally.csv) so this runs offline — no network, and no
    dependency on yfinance still returning the same window by the time
    someone runs this later. The next day (2025-04-10) was -4.48%, a ~45%
    reversal of the move, well under a bad tick's near-total round-trip, so
    the fixed filter (spike AND >50% next-day reversal) must keep the row
    while a naive amplitude-only filter deletes it.
    """
    raw = pd.read_csv(
        FIXTURES_DIR / "spy_2025_04_tariff_rally.csv", index_col="date", parse_dates=True
    )

    # Sanity-check the fixture itself still represents the real bug trigger
    # before trusting the assertion below to mean anything. Compares on the
    # date component since the raw fixture keeps its real yfinance
    # time-of-day (e.g. 04:00:00) — preprocessing normalizes that away (see
    # _fill_gaps), but the pre-preprocessing sanity check needs to too.
    log_ret = np.log(raw["close"] / raw["close"].shift(1))
    naive_mask = (log_ret - log_ret.mean()).abs() > 6 * log_ret.std()
    assert pd.Timestamp("2025-04-09") in raw.index[naive_mask].normalize(), (
        "fixture no longer reproduces the naive 6-sigma trigger this test exists to guard against"
    )

    result = DataPreprocessor().process(raw)
    assert pd.Timestamp("2025-04-09") in result.index, (
        "a real historic rally day was deleted by the outlier filter — "
        "amplitude alone can't distinguish a real event from a bad tick"
    )


# ── [C3] TTL cache + timeout ─────────────────────────────────────────────────


def test_fetch_vix_cache_hit_avoids_second_network_call():
    mock_ticker = MagicMock()
    mock_ticker.fast_info.last_price = 20.0
    fetcher = MarketDataFetcher()
    with patch("stock_risk.data.fetcher.yf.Ticker", return_value=mock_ticker) as mock_cls:
        assert fetcher.fetch_vix() == 20.0
        assert fetcher.fetch_vix() == 20.0
    assert mock_cls.call_count == 1  # second call served from cache


def test_fetch_vix_cache_expires_after_ttl():
    mock_ticker = MagicMock()
    mock_ticker.fast_info.last_price = 20.0
    fetcher = MarketDataFetcher()
    timer = _FakeTimer()
    fetcher._fast_cache = TTLCache(maxsize=256, ttl=900, timer=timer)  # 15 min, same as prod
    with patch("stock_risk.data.fetcher.yf.Ticker", return_value=mock_ticker) as mock_cls:
        fetcher.fetch_vix()
        timer.advance(901)  # just past the TTL
        fetcher.fetch_vix()
    assert mock_cls.call_count == 2  # cache expired -> refetched


def test_fetch_vix_failure_is_not_cached():
    """Exceptions/empty results must not be cached — a transient failure
    should be retried on the next request, not pinned as a false "down for
    15 minutes" result for the rest of the TTL window."""
    fetcher = MarketDataFetcher()
    with patch("stock_risk.data.fetcher.yf.Ticker", side_effect=RuntimeError("boom")) as mock_cls:
        assert fetcher.fetch_vix() is None
        assert fetcher.fetch_vix() is None
    assert mock_cls.call_count == 2  # not cached — both calls actually attempted


def test_fetch_analyst_activity_empty_result_is_not_cached():
    fetcher = MarketDataFetcher()
    mock_ticker = MagicMock()
    mock_ticker.upgrades_downgrades = pd.DataFrame()
    with patch("stock_risk.data.fetcher.yf.Ticker", return_value=mock_ticker) as mock_cls:
        fetcher.fetch_analyst_activity("XYZ")
        fetcher.fetch_analyst_activity("XYZ")
    assert mock_cls.call_count == 2  # empty result not cached — retried both times


def test_fetch_history_cache_hit_avoids_second_network_call():
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = _make_ohlcv(50)
    fetcher = MarketDataFetcher()
    with patch("stock_risk.data.fetcher.yf.Ticker", return_value=mock_ticker):
        fetcher.fetch_history("AAPL", period="1y")
        fetcher.fetch_history("AAPL", period="1y")
    assert mock_ticker.history.call_count == 1


def test_fetch_history_cache_key_includes_period():
    """Different params must be different cache entries — caching by ticker
    alone would silently serve a 1y fetch's data to a 2y request."""
    mock_ticker = MagicMock()
    mock_ticker.history.side_effect = [_make_ohlcv(50), _make_ohlcv(50)]
    fetcher = MarketDataFetcher()
    with patch("stock_risk.data.fetcher.yf.Ticker", return_value=mock_ticker):
        fetcher.fetch_history("AAPL", period="1y")
        fetcher.fetch_history("AAPL", period="2y")
    assert mock_ticker.history.call_count == 2


def test_fetch_history_cache_expires_after_ttl():
    mock_ticker = MagicMock()
    mock_ticker.history.side_effect = [_make_ohlcv(50), _make_ohlcv(50)]
    fetcher = MarketDataFetcher()
    timer = _FakeTimer()
    fetcher._fast_cache = TTLCache(maxsize=256, ttl=900, timer=timer)
    with patch("stock_risk.data.fetcher.yf.Ticker", return_value=mock_ticker):
        fetcher.fetch_history("AAPL", period="1y")
        timer.advance(901)
        fetcher.fetch_history("AAPL", period="1y")
    assert mock_ticker.history.call_count == 2


def test_fetch_history_passes_configured_timeout():
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = _make_ohlcv(50)
    fetcher = MarketDataFetcher(timeout=7)
    with patch("stock_risk.data.fetcher.yf.Ticker", return_value=mock_ticker):
        fetcher.fetch_history("AAPL", period="1y")
    assert mock_ticker.history.call_args.kwargs["timeout"] == 7


def test_timeout_session_injects_default_timeout_when_unset():
    session = _TimeoutSession(timeout=12)
    with patch.object(requests.Session, "request", return_value=None) as base_request:
        session.request("GET", "https://example.com")
    assert base_request.call_args.kwargs["timeout"] == 12


def test_timeout_session_respects_explicit_timeout():
    session = _TimeoutSession(timeout=12)
    with patch.object(requests.Session, "request", return_value=None) as base_request:
        session.request("GET", "https://example.com", timeout=3)
    assert base_request.call_args.kwargs["timeout"] == 3


# ── [IP-block resilience] snapshot fallback ──────────────────────────────────


@pytest.fixture(autouse=True)
def _isolated_snapshot_dir(tmp_path, monkeypatch):
    """Redirect snapshot persistence to a temp dir so tests never write into
    the repo's tracked snapshots/ directory."""
    from stock_risk.config import settings
    monkeypatch.setattr(settings, "snapshot_dir", tmp_path / "snapshots")


def test_fetch_history_success_persists_snapshot():
    df = _make_ohlcv(60)
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = df
    fetcher = MarketDataFetcher()
    with patch("stock_risk.data.fetcher.yf.Ticker", return_value=mock_ticker):
        fetcher.fetch_history("AAPL", period="1y")
    assert fetcher._snapshot_path("AAPL", "1y", "1d").exists()


def test_fetch_history_falls_back_to_snapshot_when_throttled():
    """The chronic-throttling scenario: live fetch fails, but a snapshot from
    an earlier successful fetch exists — serve it instead of 500ing."""
    df = _make_ohlcv(60)
    fetcher = MarketDataFetcher()
    fetcher._save_snapshot("AAPL", "1y", "1d", df)

    with patch(
        "stock_risk.data.fetcher.yf.Ticker",
        side_effect=RuntimeError("Too Many Requests. Rate limited."),
    ):
        result = fetcher.fetch_history("AAPL", period="1y")
    # check_freq=False: the parquet round-trip drops the BusinessDay freq
    # attribute from the index; the data itself must be identical.
    pd.testing.assert_frame_equal(result, df, check_freq=False)


def test_fetch_history_still_raises_without_snapshot():
    fetcher = MarketDataFetcher()
    with patch(
        "stock_risk.data.fetcher.yf.Ticker",
        side_effect=RuntimeError("Too Many Requests. Rate limited."),
    ):
        with pytest.raises(RuntimeError, match="Rate limited"):
            fetcher.fetch_history("NOSNAP", period="1y")
