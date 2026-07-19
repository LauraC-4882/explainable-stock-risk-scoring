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
    dates = pd.bdate_range("2023-06-01", periods=n)
    df = pd.DataFrame({
        "open": close * 0.995, "high": close * 1.012,
        "low": close * 0.987, "close": close,
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
GOLDEN_IV = 0.31


@contextmanager
def golden_environment():
    """Patch every network-touching fetcher call with the frozen inputs."""
    df = golden_ohlcv()
    with (
        patch(f"{_FETCH}.fetch_history", return_value=df),
        patch(f"{_FETCH}.fetch_info", return_value=dict(GOLDEN_INFO)),
        patch(f"{_FETCH}.fetch_options_iv", return_value=GOLDEN_IV),
        patch(f"{_FETCH}.fetch_vix", return_value=GOLDEN_VIX),
        patch(f"{_FETCH}.fetch_news", return_value=[dict(a) for a in GOLDEN_NEWS]),
        patch(f"{_FETCH}.fetch_analyst_activity", return_value=dict(GOLDEN_ANALYST)),
        patch(f"{_FETCH}.fetch_insider_activity", return_value=dict(GOLDEN_INSIDER)),
    ):
        yield
