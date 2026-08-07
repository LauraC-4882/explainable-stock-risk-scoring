"""The offline A-share name table and its fetch_info fallback."""

import importlib.util
import json
from pathlib import Path
from unittest.mock import Mock, PropertyMock, patch

import pytest

from stock_risk.data.cn_names import _NAMES_PATH, cn_name
from stock_risk.data.fetcher import MarketDataFetcher

_GENERATOR = Path(__file__).resolve().parents[1] / "scripts" / "fetch_cn_names.py"


def _load_generator():
    """Import scripts/fetch_cn_names.py by path — scripts/ isn't a package."""
    spec = importlib.util.spec_from_file_location("fetch_cn_names", _GENERATOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ── the committed table ───────────────────────────────────────────────────────

def test_cn_name_resolves_an_a_share():
    assert cn_name("301189.SZ") == "奥尼电子"
    assert cn_name("600519.SS") == "贵州茅台"


def test_cn_name_is_case_and_whitespace_insensitive():
    assert cn_name("  301189.sz  ") == cn_name("301189.SZ")


def test_cn_name_returns_none_outside_the_table():
    assert cn_name("AAPL") is None
    assert cn_name("999999.SZ") is None


def test_committed_table_is_well_formed():
    """Guards the generator's output shape, which the read side trusts blindly.

    A malformed entry here would surface as a wrong or blank company name on a
    real card, and nothing downstream re-validates it.
    """
    table = json.loads(_NAMES_PATH.read_text(encoding="utf-8"))
    # The A-share market has been >4k listings for years; a table that shrank
    # below that means a truncated upstream response got committed.
    assert len(table) > 4000
    for symbol, name in table.items():
        code, _, suffix = symbol.partition(".")
        assert suffix in ("SS", "SZ"), symbol
        assert len(code) == 6 and code.isdigit(), symbol
        # .SS is Yahoo's spelling for Shanghai and the only one _is_cn_ticker
        # accepts; 6xxxxx is Shanghai, everything else Shenzhen.
        assert suffix == ("SS" if code.startswith("6") else "SZ"), symbol
        assert isinstance(name, str) and name.strip(), symbol


def test_a_missing_table_degrades_to_no_names_instead_of_raising():
    """Scoring a ticker whose price data is fine must not break on a bad file."""
    from stock_risk.data import cn_names as module

    module._names.cache_clear()
    try:
        with patch.object(Path, "open", side_effect=FileNotFoundError):
            assert cn_name("301189.SZ") is None
    finally:
        module._names.cache_clear()


# ── the generator's symbol mapping ────────────────────────────────────────────

def test_generator_maps_sina_codes_to_yahoo_symbols():
    to_yahoo = _load_generator()._to_yahoo_symbol
    assert to_yahoo("sz301189") == "301189.SZ"
    assert to_yahoo("sh600519") == "600519.SS"


def test_generator_drops_symbols_outside_the_supported_universe():
    to_yahoo = _load_generator()._to_yahoo_symbol
    assert to_yahoo("bj430047") is None  # Beijing Stock Exchange — unsupported
    assert to_yahoo("sz30118") is None  # not a 6-digit code
    assert to_yahoo("") is None


# ── the fetch_info fallback ───────────────────────────────────────────────────

def _throttled_ticker():
    """A yf.Ticker whose .info raises, which is what a real throttle does."""
    ticker = Mock()
    type(ticker).info = PropertyMock(side_effect=RuntimeError("Too Many Requests"))
    return ticker


def test_fetch_info_serves_the_offline_name_when_yahoo_throttles_a_cn_ticker():
    with patch("stock_risk.data.fetcher.yf.Ticker", return_value=_throttled_ticker()):
        info = MarketDataFetcher().fetch_info("301189.SZ")
    assert info["shortName"] == "奥尼电子"
    # Only the name — no live fundamental may be invented from a static file.
    assert info["sector"] is None
    assert info["beta"] is None


def test_fetch_info_still_raises_for_a_non_cn_ticker():
    """Unchanged behaviour everywhere the offline table can't help."""
    with patch("stock_risk.data.fetcher.yf.Ticker", return_value=_throttled_ticker()):
        with pytest.raises(RuntimeError):
            MarketDataFetcher().fetch_info("AAPL")


def test_fetch_info_still_raises_for_a_cn_ticker_with_no_offline_name():
    with patch("stock_risk.data.fetcher.yf.Ticker", return_value=_throttled_ticker()):
        with pytest.raises(RuntimeError):
            MarketDataFetcher().fetch_info("999999.SZ")


def test_fetch_info_never_overwrites_a_live_yahoo_name():
    ticker = Mock()
    ticker.info = {"shortName": "Aoni Electronic Co Ltd", "sector": "Technology"}
    with patch("stock_risk.data.fetcher.yf.Ticker", return_value=ticker):
        info = MarketDataFetcher().fetch_info("301189.SZ")
    assert info["shortName"] == "Aoni Electronic Co Ltd"


def test_fetch_info_fills_the_name_when_yahoo_answers_without_one():
    """Yahoo's A-share coverage is thin even when it isn't throttling."""
    ticker = Mock()
    ticker.info = {"sector": "Technology", "beta": 1.4}
    with patch("stock_risk.data.fetcher.yf.Ticker", return_value=ticker):
        info = MarketDataFetcher().fetch_info("301189.SZ")
    assert info["shortName"] == "奥尼电子"
    assert info["sector"] == "Technology"


def test_a_name_only_result_is_not_cached():
    """Otherwise the degraded answer pins every fundamental as None for a full
    slow-cache TTL, long after Yahoo recovers."""
    fetcher = MarketDataFetcher()
    with patch("stock_risk.data.fetcher.yf.Ticker", return_value=_throttled_ticker()):
        fetcher.fetch_info("301189.SZ")

    live = Mock()
    live.info = {"shortName": "Aoni", "sector": "Technology"}
    with patch("stock_risk.data.fetcher.yf.Ticker", return_value=live) as mock_cls:
        info = fetcher.fetch_info("301189.SZ")
    mock_cls.assert_called_once()  # refetched, not served from cache
    assert info["sector"] == "Technology"


def test_a_complete_result_is_still_cached():
    fetcher = MarketDataFetcher()
    ticker = Mock()
    ticker.info = {"shortName": "Aoni", "sector": "Technology", "beta": 1.4}
    with patch("stock_risk.data.fetcher.yf.Ticker", return_value=ticker) as mock_cls:
        fetcher.fetch_info("301189.SZ")
        fetcher.fetch_info("301189.SZ")
    mock_cls.assert_called_once()
