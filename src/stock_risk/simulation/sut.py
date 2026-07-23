"""Adapter to the real System Under Test (the risk platform), offline.

The simulation evaluates *this* product, so it drives the platform's own pure
functions and committed fixtures rather than re-implementing risk logic. To
keep the harness within the project's offline-gate rule, the "system output" a
user sees comes from:

* committed API fixtures (``tests/fixtures/mock_api/score_<ticker>.json`` — real
  captured ``/api/score`` responses), and
* seeded synthetic ``DataQuality`` inputs for the degraded/stale/illiquid cases
  that fixtures can't represent.

Nothing here fetches from the network.

It also computes the confidence status the product *should* surface for a given
data-quality picture — and records, separately, that the product as built
surfaces no such flag. That gap (a low-confidence score shown as if normal) is
one of the product risks the framework exists to measure, so it must be modelled
explicitly, not papered over.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from .events import ConfidenceStatus

_REPO_ROOT = Path(__file__).resolve().parents[3]
_FIXTURE_DIR = _REPO_ROOT / "tests" / "fixtures" / "mock_api"

# Minimum trustworthy history, mirroring scoring/risk_categories._MIN_HISTORY.
_MIN_HISTORY_DAYS = 20
# Beyond this many trading days without a fresh bar, a daily-bar score is stale.
_STALE_DAYS = 5


def load_scorecard(ticker: str = "TSLA") -> dict[str, Any]:
    """Load a committed real ``/api/score`` response fixture for *ticker*."""
    path = _FIXTURE_DIR / f"score_{ticker.lower()}.json"
    if not path.exists():
        raise FileNotFoundError(
            f"No scorecard fixture for {ticker!r} at {path}. "
            "Available fixtures: " + ", ".join(p.name for p in _FIXTURE_DIR.glob('score_*.json'))
        )
    return json.loads(path.read_text(encoding="utf-8"))


def load_timeseries(ticker: str = "TSLA") -> list[dict[str, Any]]:
    """Load the committed real timeseries fixture for *ticker* (for outcomes)."""
    path = _FIXTURE_DIR / f"timeseries_{ticker.lower()}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    # The fixture is the API response; the rows live under a "series"/"points"
    # key in some captures and are a bare list in others — accept both.
    if isinstance(data, dict):
        for key in ("series", "points", "timeseries", "data"):
            if key in data and isinstance(data[key], list):
                return data[key]
    return data if isinstance(data, list) else []


@dataclass(frozen=True)
class DataQuality:
    """The data picture behind a score, driving the confidence it *should* carry.

    Defaults describe a healthy, liquid US equity with fresh daily bars — the
    fixture case. Degraded/stale/sparse/illiquid scenarios override these.
    """

    history_days: int = 504          # ~2y of trading days
    staleness_days: int = 0          # trading days since last bar
    missing_columns: tuple[str, ...] = ()
    illiquid: bool = False
    suspended: bool = False

    def intrinsic_confidence(self) -> ConfidenceStatus:
        """The confidence the product *should* display for this data.

        This is the ground truth the framework judges the product against. The
        product itself currently exposes no confidence field (see
        ``product_surfaces_confidence``)."""
        if self.suspended or self.history_days < _MIN_HISTORY_DAYS:
            return ConfidenceStatus.SUPPRESSED
        if (
            self.staleness_days > _STALE_DAYS
            or self.illiquid
            or self.history_days < 2 * _MIN_HISTORY_DAYS
            or self.missing_columns
        ):
            return ConfidenceStatus.LOW
        return ConfidenceStatus.NORMAL


# The current UI/API has no per-score confidence or freshness flag on the score
# response (verified in the scorer/schemas). The framework encodes that fact so
# a scenario can measure the harm of its absence rather than assume a fix.
PRODUCT_SURFACES_CONFIDENCE: bool = False
PRODUCT_SURFACES_FRESHNESS_ON_SCORE: bool = False

# The score response also carries no model_version stamp today (governance
# tracks it, but it is never threaded into the response). Recorded so events can
# reflect reality and a recommendation can target the gap.
PRODUCT_SURFACES_MODEL_VERSION: bool = False


def scorecard_composite(scorecard: dict[str, Any]) -> float:
    return float(scorecard["risk_score"])


def scorecard_label(scorecard: dict[str, Any]) -> str:
    return str(scorecard["risk_label"])


def scorecard_data_timestamp(scorecard: dict[str, Any]) -> str | None:
    """Best-available 'as of' stamp: the scoring timestamp in the response."""
    return scorecard.get("timestamp")


# ── Portfolio SUT: seeded synthetic returns -> the REAL aggregate function ──
def synthetic_returns(
    specs: "list[tuple[str, float, float]]",
    *,
    seed: int,
    n_days: int = 504,
    market_load: float = 0.6,
):
    """Seeded daily return series for each (ticker, annual_vol, sector_beta) spec.

    A shared market factor (scaled by ``market_load``) induces realistic
    cross-asset correlation, so the real ``compute_portfolio_risk`` sees genuine
    co-movement rather than independent noise. Offline and reproducible.
    Returns ``dict[ticker, pandas.Series]`` indexed by a synthetic business-day
    range — the exact input the platform's portfolio aggregator expects.
    """
    import numpy as np
    import pandas as pd

    rng = np.random.default_rng([int(seed), 7717])
    dates = pd.bdate_range("2023-01-02", periods=n_days)
    market = rng.normal(0.0002, 0.011, n_days)
    out: dict[str, "pd.Series"] = {}
    for ticker, annual_vol, load in specs:
        daily_vol = annual_vol / (252 ** 0.5)
        idio = rng.normal(0.0, daily_vol, n_days)
        series = market_load * load * market + idio
        out[ticker] = pd.Series(series, index=dates, name=ticker)
    return out


def build_portfolio_risk(
    positions_spec: "list[tuple[str, float, float, float, str]]",
    *,
    seed: int,
):
    """Compute REAL portfolio risk for a book of (ticker, weight, vol, load, sector).

    Delegates entirely to ``stock_risk.portfolio.aggregate.compute_portfolio_risk``
    — the framework evaluates the product's own attribution, it does not
    re-implement it. Returns the ``PortfolioRisk`` dataclass.
    """
    from stock_risk.portfolio.aggregate import Position, compute_portfolio_risk

    returns = synthetic_returns(
        [(t, vol, load) for (t, _w, vol, load, _sec) in positions_spec], seed=seed
    )
    positions = [Position(t, w, sec) for (t, w, _vol, _load, sec) in positions_spec]
    return compute_portfolio_risk(returns, positions)


def synthetic_scorecard(
    ticker: str,
    *,
    risk_score: float,
    template: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """A scorecard shaped exactly like a real one, at a chosen risk level.

    Used to give the compare task a second stock at a different risk level
    without a second network fixture. Derived from the committed TSLA response so
    every field the UI/renderer reads is present; the composite and label are
    overridden and category scores nudged toward the target so the card is
    internally consistent.
    """
    import copy

    base = copy.deepcopy(template if template is not None else load_scorecard("TSLA"))
    base["ticker"] = ticker
    base["name"] = ticker
    base["risk_score"] = round(float(risk_score), 1)
    base["risk_label"] = _label_for(risk_score)
    shift = (risk_score - float(base.get("risk_score", 50))) if template else 0.0
    for cat in base.get("risk_breakdown", {}).values():
        if cat.get("score") is not None:
            cat["score"] = round(min(100.0, max(0.0, cat["score"] + shift)), 1)
            if not cat.get("two_sided"):
                cat["contribution"] = cat["score"]
    return base


def _label_for(score: float) -> str:
    if score < 25:
        return "LOW"
    if score < 50:
        return "MODERATE"
    if score < 75:
        return "HIGH"
    return "EXTREME"
