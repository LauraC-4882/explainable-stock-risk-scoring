"""Frozen, deterministic inputs for the [G1] golden test.

The issue asked for a golden fixture of RiskScorer().score("AAPL") captured
against live data — but live yfinance data changes every trading day, so a
live-capture fixture would go stale (and falsely fail) within a day. The
refactor-safety intent is preserved by freezing the *inputs* instead: every
fetcher call is mocked with fixed values / a fixed-seed synthetic series, so
pre- and post-refactor outputs are comparable indefinitely. Shared between
the one-off fixture generation and the ongoing golden test so both always
run the exact same scenario.
"""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import patch

import numpy as np
import pandas as pd

GOLDEN_TICKER = "AAPL"

_FETCH = "stock_risk.scoring.scorer.MarketDataFetcher"


def golden_ohlcv(n: int = 600, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.standard_normal(n) * 0.012))
    # Intraday ranges VARY day to day (real markets never have a constant
    # relative range): a constant-multiple high/low made Garman-Klass daily
    # vol a constant series, whose perfectly-collinear HAR design matrix
    # either pseudo-solved or raised "Singular matrix" depending on the
    # numpy version — an environment-dependent golden input is exactly what
    # this fixture must never be.
    width = 0.012 * rng.uniform(0.4, 1.8, n)
    dates = pd.bdate_range("2023-06-01", periods=n)
    df = pd.DataFrame({
        "open": close * (1 - width * 0.3),
        "high": close * (1 + width),
        "low": close * (1 - width * 0.9),
        "close": close,
        "volume": rng.integers(2_000_000, 8_000_000, n).astype(float),
    }, index=dates)
    df.index.name = "date"
    return df


GOLDEN_INFO = {
    "shortName": "Apple Inc.", "sector": "Technology", "industry": "Consumer Electronics",
    "marketCap": 3.0e12, "beta": 1.2, "trailingPE": 28.5, "forwardPE": 25.0,
    "dividendYield": 0.005, "52WeekChange": 0.12,
    "sharesOutstanding": 1.5e10, "floatShares": 1.49e10,
}

GOLDEN_NEWS = [
    {"title": "Company reports quarterly results", "summary": "Revenue in line with expectations.",
     "publisher": "TestWire", "published_at": "2026-07-01T12:00:00Z", "link": "https://example.com/a"},
    {"title": "Analysts weigh in on product launch", "summary": "Mixed early reviews.",
     "publisher": "TestWire", "published_at": "2026-07-02T09:00:00Z", "link": "https://example.com/b"},
]

GOLDEN_ANALYST = {"downgrade_count": 2, "upgrade_count": 1}
GOLDEN_INSIDER = {"sale_count": 3, "purchase_count": 1, "net_transaction_count": -2}
GOLDEN_VIX = 22.5  # "elevated" regime — exercises the regime-adjusted weights branch
GOLDEN_VIX3M = 24.0  # contango (vix < vix3m) — the calm-market term structure
GOLDEN_IV = 0.31
GOLDEN_OPTIONS_SIGNALS = {
    "atm_iv": GOLDEN_IV, "otm_put_iv": 0.36, "put_skew": 0.05, "expiry": "2026-08-21",
}


def golden_vix_history(n: int = 600, seed: int = 7) -> pd.DataFrame:
    """[G6] A frozen ^VIX series for the realised-vs-implied regime leg.

    Needed because that leg reads VIX *history* via fetch_history, not the
    single current level GOLDEN_VIX provides. Without a symbol-aware mock the
    scorer would receive the equity frame for ^VIX and compare an equity price
    level (~100) against an annualised volatility in percentage points — a
    deterministic fixture, but one that exercises the arithmetic on nonsense
    and would mask a units bug. Range 12-30 keeps it in real VIX territory,
    straddling the calm/elevated boundary.
    """
    rng = np.random.default_rng(seed)
    level = 12 + 18 * rng.beta(2, 3, n)
    return pd.DataFrame(
        {"open": level, "high": level * 1.05, "low": level * 0.95,
         "close": level, "volume": np.zeros(n)},
        index=pd.bdate_range("2023-06-01", periods=n),
    )


def golden_sector_ohlcv(ticker: str, n: int = 600) -> pd.DataFrame:
    """[G6] Distinct frozen frames for the XLY/XLP sector-tilt proxies.

    Seeded per ticker so the two sides are genuinely different series — a
    shared frame would make both betas identical and the tilt exactly 0,
    silently passing whatever the tilt arithmetic does.
    """
    seed = {"XLY": 101, "XLP": 202}.get(ticker.upper(), 303)
    return golden_ohlcv(n=n, seed=seed)


# Symbols the [G6] legs fetch beyond the equity/benchmark pair. Everything not
# listed here (AAPL and the SPY benchmark) still gets the same golden_ohlcv
# frame the pre-[G6] fixture was generated from, so the scored metrics — and
# therefore risk_score — are unchanged by this routing.
_SPECIAL_HISTORY = {"^VIX": golden_vix_history}


def _golden_history(ticker: str, *_args, **_kwargs) -> pd.DataFrame:
    symbol = ticker.upper()
    if symbol in _SPECIAL_HISTORY:
        return _SPECIAL_HISTORY[symbol]()
    if symbol in {"XLY", "XLP"}:
        return golden_sector_ohlcv(symbol)
    return golden_ohlcv()


@contextmanager
def golden_environment():
    """Patch every network-touching fetcher call with the frozen inputs."""
    with (
        patch(f"{_FETCH}.fetch_history", side_effect=_golden_history),
        patch(f"{_FETCH}.fetch_info", return_value=dict(GOLDEN_INFO)),
        patch(f"{_FETCH}.fetch_options_signals",
              return_value=dict(GOLDEN_OPTIONS_SIGNALS)),
        patch(f"{_FETCH}.fetch_vix", return_value=GOLDEN_VIX),
        patch(f"{_FETCH}.fetch_vix3m", return_value=GOLDEN_VIX3M),
        patch(f"{_FETCH}.fetch_news", return_value=[dict(a) for a in GOLDEN_NEWS]),
        patch(f"{_FETCH}.fetch_analyst_activity", return_value=dict(GOLDEN_ANALYST)),
        patch(f"{_FETCH}.fetch_insider_activity", return_value=dict(GOLDEN_INSIDER)),
    ):
        yield
