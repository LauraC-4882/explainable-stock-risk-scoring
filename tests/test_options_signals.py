"""[G4] Options-implied signal tests: synthetic chain fixtures for the skew
math and moneyness selection, None-safety on thin/missing chains, producer
unit handling, and graceful degradation through a full score(). Offline."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from stock_risk.api.schemas import ScoreResponse
from stock_risk.data.fetcher import MarketDataFetcher
from stock_risk.scoring.producers import OptionsImpliedProducer, ScoringContext
from stock_risk.scoring.scorer import RiskScorer

from .golden_inputs import GOLDEN_TICKER, golden_environment


def _chain(calls: pd.DataFrame, puts: pd.DataFrame):
    return SimpleNamespace(calls=calls, puts=puts)


def _side(strikes: list[float], ivs: list[float]) -> pd.DataFrame:
    return pd.DataFrame({"strike": strikes, "impliedVolatility": ivs})


def _mock_ticker(spot: float, expirations, chain) -> MagicMock:
    tk = MagicMock()
    tk.options = expirations
    tk.option_chain.return_value = chain
    tk.fast_info.last_price = spot
    return tk


def test_put_skew_and_moneyness_selection():
    """spot=100: ATM = median(call IV@100, put IV@100); OTM put = strike
    nearest 95 (moneyness 0.95) — NOT the nearest-to-spot put."""
    calls = _side([90, 95, 100, 105], [0.40, 0.35, 0.30, 0.28])
    puts = _side([90, 95, 100, 105], [0.42, 0.38, 0.32, 0.30])
    tk = _mock_ticker(100.0, ["2026-08-21"], _chain(calls, puts))
    with patch("stock_risk.data.fetcher.yf.Ticker", return_value=tk):
        sig = MarketDataFetcher().fetch_options_signals("XYZ")

    assert sig["atm_iv"] == pytest.approx(np.median([0.30, 0.32]))
    assert sig["otm_put_iv"] == pytest.approx(0.38)  # the strike-95 put
    assert sig["put_skew"] == pytest.approx(0.38 - 0.31)
    assert sig["expiry"] == "2026-08-21"


def test_no_options_ticker_returns_all_none_without_raising():
    tk = _mock_ticker(100.0, [], None)
    with patch("stock_risk.data.fetcher.yf.Ticker", return_value=tk):
        sig = MarketDataFetcher().fetch_options_signals("NOOPT")
    assert sig == {"atm_iv": None, "otm_put_iv": None, "put_skew": None, "expiry": None}


def test_one_sided_chain_gives_atm_from_calls_but_no_skew():
    calls = _side([100], [0.30])
    puts = _side([], [])
    tk = _mock_ticker(100.0, ["2026-08-21"], _chain(calls, puts))
    with patch("stock_risk.data.fetcher.yf.Ticker", return_value=tk):
        sig = MarketDataFetcher().fetch_options_signals("XYZ")
    assert sig["atm_iv"] == pytest.approx(0.30)
    assert sig["otm_put_iv"] is None
    assert sig["put_skew"] is None


def test_junk_iv_treated_as_missing():
    calls = _side([100], [float("nan")])
    puts = _side([100, 95], [0.0, -1.0])  # non-positive IVs are junk
    tk = _mock_ticker(100.0, ["2026-08-21"], _chain(calls, puts))
    with patch("stock_risk.data.fetcher.yf.Ticker", return_value=tk):
        sig = MarketDataFetcher().fetch_options_signals("XYZ")
    assert sig["atm_iv"] is None and sig["put_skew"] is None


def test_chain_exception_degrades_to_none():
    with patch("stock_risk.data.fetcher.yf.Ticker", side_effect=RuntimeError("boom")):
        sig = MarketDataFetcher().fetch_options_signals("XYZ")
    assert sig["atm_iv"] is None and sig["expiry"] is None


def test_fetch_options_iv_compat_view():
    calls = _side([100], [0.30])
    puts = _side([100], [0.32])
    tk = _mock_ticker(100.0, ["2026-08-21"], _chain(calls, puts))
    with patch("stock_risk.data.fetcher.yf.Ticker", return_value=tk):
        assert MarketDataFetcher().fetch_options_iv("XYZ") == pytest.approx(0.31)


# ── Producer-level unit handling ─────────────────────────────────────────────


def _df_with_vol(vol_21d: float) -> pd.DataFrame:
    return pd.DataFrame({"vol_21d": [vol_21d]}, index=pd.bdate_range("2024-01-01", periods=1))


def _base_ctx(**overrides) -> ScoringContext:
    defaults = dict(ticker="XYZ", market="us", benchmark_ticker="SPY", category_weights={})
    defaults.update(overrides)
    return ScoringContext(**defaults)


def test_producer_iv_hv_and_term_structure():
    ctx = _base_ctx(
        vix=25.0, vix3m=20.0,
        options_signals={"atm_iv": 0.42, "otm_put_iv": 0.50, "put_skew": 0.08, "expiry": "e"},
    )
    out = OptionsImpliedProducer().produce(_df_with_vol(0.30), ctx)
    assert out.raw["iv_hv_ratio"] == pytest.approx(1.4)
    ts = out.raw["vix_term_structure"]
    assert ts["ratio"] == pytest.approx(1.25)
    assert ts["backwardation"] is True  # near fear above 3m fear


def test_producer_none_paths():
    # no options signals + no vix3m + NaN HV -> every derived field None
    out = OptionsImpliedProducer().produce(
        _df_with_vol(float("nan")), _base_ctx(vix=20.0, vix3m=None, options_signals={})
    )
    assert out.raw["atm_iv"] is None
    assert out.raw["iv_hv_ratio"] is None
    assert out.raw["vix_term_structure"] is None
    assert out.score is None


# ── Graceful degradation through the full pipeline ───────────────────────────


def test_score_survives_optionless_ticker_and_passes_schema():
    """A ticker with no options must produce a complete scorecard with the
    options_implied fields None — and the response must still validate
    against the API's response_model (the HTTP-200 guarantee)."""
    none_signals = {"atm_iv": None, "otm_put_iv": None, "put_skew": None, "expiry": None}
    with golden_environment():
        with (
            patch(
                "stock_risk.scoring.scorer.MarketDataFetcher.fetch_options_signals",
                return_value=none_signals,
            ),
            patch("stock_risk.scoring.scorer.MarketDataFetcher.fetch_vix3m", return_value=None),
        ):
            result = RiskScorer().score(GOLDEN_TICKER)

    assert result["risk_score"] is not None
    block = result["options_implied"]
    assert block["atm_iv"] is None and block["put_skew"] is None
    assert block["vix_term_structure"] is None
    assert result["implied_volatility"] is None  # compat field follows atm_iv
    ScoreResponse(**result)  # response-model validation must accept the Nones
