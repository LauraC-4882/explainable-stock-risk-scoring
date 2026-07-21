"""[G6] Tests for MomentumRiskFeatures and the RegimeTechnicalsProducer.

The governing property, asserted first and directly: this producer must NOT be
able to move `risk_score`. Everything else here is about the block degrading
one leg at a time instead of all-or-nothing.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from stock_risk.features.candlestick import CandlestickFeatures
from stock_risk.features.momentum_risk import MOMENTUM_COLS, MomentumRiskFeatures
from stock_risk.features.regime import RegimeFeatures
from stock_risk.features.risk_metrics import RiskMetrics
from stock_risk.features.sector_rotation import SectorRotationFeatures
from stock_risk.features.sma_search import OptimizedSMAFeatures
from stock_risk.scoring.producers import (
    RegimeTechnicalsProducer,
    ScoringContext,
    build_producers,
    fuse_with_composition,
    resolve_weights,
)
from stock_risk.scoring.producers.base import ProducerOutput


@pytest.fixture
def frame() -> pd.DataFrame:
    idx = pd.date_range("2022-01-03", periods=700, freq="B")
    rng = np.random.default_rng(11)
    close = 100 * np.exp(rng.normal(0.0004, 0.013, 700).cumsum())
    df = pd.DataFrame(
        {
            "open": close * 0.997,
            "high": close * 1.013,
            "low": close * 0.988,
            "close": close,
            "volume": rng.integers(1_000_000, 6_000_000, 700).astype(float),
        },
        index=idx,
    )
    df["log_return"] = np.log(df["close"] / df["close"].shift(1))
    return df


@pytest.fixture
def enriched(frame) -> pd.DataFrame:
    df = RiskMetrics().compute(frame)
    df = CandlestickFeatures().compute(df)
    df = MomentumRiskFeatures().compute(df)
    df = OptimizedSMAFeatures().compute(df)
    vix = pd.Series(np.random.default_rng(3).uniform(12, 30, len(df)), index=df.index)
    df = RegimeFeatures().compute(df, vix)
    r = df["log_return"]
    noise = np.random.default_rng(5).normal(0, 0.005, len(df))
    df = SectorRotationFeatures().compute(
        df, r * 1.3 + noise, pd.Series(r.to_numpy() * 0.4 + noise, index=df.index)
    )
    return df


@pytest.fixture
def ctx() -> ScoringContext:
    return ScoringContext(
        ticker="TEST", market="us", benchmark_ticker="SPY",
        category_weights={"volatility": 1.0},
    )


# ── Momentum features ────────────────────────────────────────────────────────

def test_momentum_columns_produced(frame):
    out = MomentumRiskFeatures().compute(frame)
    missing = [c for c in MOMENTUM_COLS if c not in out.columns]
    assert not missing, f"declared but not produced: {missing}"


def test_momentum_matches_manual_pct_change(frame):
    out = MomentumRiskFeatures().compute(frame)
    expected = frame["close"].iloc[-1] / frame["close"].iloc[-1 - 21] - 1
    assert out["momentum_1m"].iloc[-1] == pytest.approx(expected)


def test_crash_risk_is_bounded_and_needs_both_legs(frame):
    """The interaction, not either component: a stock can only score high when
    momentum AND volatility are both high in its own history."""
    out = RiskMetrics().compute(frame)
    out = MomentumRiskFeatures().compute(out)
    crash = out["momentum_crash_risk"].dropna()
    assert crash.between(0, 1).all()

    mom_rank = out["momentum_3m"].expanding(min_periods=63).apply(
        lambda w: (w <= w[-1]).mean(), raw=True
    )
    # Wherever momentum sits in its own bottom decile, the product cannot be high
    # no matter how volatile the stock is.
    low_momentum = mom_rank < 0.1
    assert (out.loc[low_momentum, "momentum_crash_risk"].dropna() <= 0.1).all()


def test_expanding_rank_has_no_lookahead(frame):
    """Appending future rows must not change any earlier crash-risk value — the
    same guard the walk-forward SMA search carries."""
    baseline = MomentumRiskFeatures().compute(frame.iloc[:500])["momentum_crash_risk"]
    full = MomentumRiskFeatures().compute(frame)["momentum_crash_risk"]
    pd.testing.assert_series_equal(baseline, full.iloc[:500])


def test_52w_position_is_zero_to_one(frame):
    out = MomentumRiskFeatures().compute(frame)
    pos = out["pct_of_52w_range"].dropna()
    assert pos.between(0, 1).all()
    # At the 52-week high, distance-from-high is 0 and range position is 1.
    assert out["price_vs_52w_high"].dropna().max() == pytest.approx(0.0, abs=1e-9)


def test_momentum_works_without_risk_metrics_columns(frame):
    """Standalone call contract: the class computes its own volatility leg when
    the frame has never been through RiskMetrics."""
    out = MomentumRiskFeatures().compute(frame)
    assert out["momentum_crash_risk"].notna().sum() > 0


# ── Producer contract ────────────────────────────────────────────────────────

def test_producer_cannot_contribute_to_risk_score(enriched, ctx):
    """The load-bearing guarantee. Unvalidated signals must not move the
    headline number, and this is enforced by the weight guard rather than by
    anyone remembering to keep the weight at zero."""
    producer = RegimeTechnicalsProducer()
    assert producer.validation is None
    assert producer.default_weight == 0.0

    weights = resolve_weights([producer])
    assert weights["regime_technicals"] == 0.0

    out = producer.produce(enriched, ctx)
    assert out.score is None
    fused, composition = fuse_with_composition({"regime_technicals": out}, weights)
    assert fused is None
    assert composition == []


def test_producer_is_registered_with_zero_weight():
    producers = build_producers(None)
    names = [p.name for p in producers]
    assert "regime_technicals" in names
    assert resolve_weights(producers)["regime_technicals"] == 0.0


def test_a_forced_nonzero_weight_is_refused():
    """Even a misconfiguration cannot launder it into the score."""
    producer = RegimeTechnicalsProducer()
    producer.default_weight = 0.5
    assert resolve_weights([producer])["regime_technicals"] == 0.0


def test_all_blocks_present_on_a_fully_enriched_frame(enriched, ctx):
    raw = RegimeTechnicalsProducer().produce(enriched, ctx).raw
    for block in ("regime", "sector_tilt", "trend", "patterns", "momentum"):
        assert raw[block] is not None, f"{block} missing"
    assert raw["regime"]["state"] in {"risk_on", "risk_off"}
    assert raw["sector_tilt"]["reading"] in {"cyclical", "defensive", "balanced"}
    assert raw["trend"]["state"] in {"above", "below"}


def test_blocks_degrade_independently(frame, ctx):
    """A throttled VIX/sector fetch must empty only its own block — the pure
    price blocks need no network and must survive."""
    df = CandlestickFeatures().compute(RiskMetrics().compute(frame))
    df = MomentumRiskFeatures().compute(df)
    df = OptimizedSMAFeatures().compute(df)
    df = RegimeFeatures().compute(df, None)          # no VIX
    df = SectorRotationFeatures().compute(df, None, None)  # no baskets

    raw = RegimeTechnicalsProducer().produce(df, ctx).raw
    assert raw["regime"] is None
    assert raw["sector_tilt"] is None
    assert raw["patterns"] is not None
    assert raw["momentum"] is not None
    assert raw["trend"] is not None


def test_producer_survives_a_bare_ohlcv_frame(frame, ctx):
    """No feature class run at all: every block reports unavailable instead of
    raising a KeyError into a user-facing request."""
    raw = RegimeTechnicalsProducer().produce(frame, ctx).raw
    assert all(v is None for v in raw.values())


def test_output_carries_no_numpy_scalars(enriched, ctx):
    """CLAUDE.md rule 4 — this block is serialized straight into the API
    response, where a numpy scalar raises inside json.dumps."""
    out: ProducerOutput = RegimeTechnicalsProducer().produce(enriched, ctx)

    leaks = []

    def walk(obj, path=""):
        if isinstance(obj, dict):
            for k, v in obj.items():
                walk(v, f"{path}.{k}")
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                walk(v, f"{path}[{i}]")
        elif type(obj).__module__ == "numpy":
            leaks.append(f"{path} = {type(obj).__name__}")

    walk(out.raw)
    assert not leaks, f"numpy scalars leaked: {leaks}"


def test_tilt_deadband_reports_balanced_rather_than_a_direction(enriched, ctx):
    """A tilt inside the estimation-noise band must not be reported as a
    cyclical or defensive finding."""
    latest = enriched.copy()
    latest.loc[latest.index[-1], "risk_on_tilt"] = 0.05
    raw = RegimeTechnicalsProducer().produce(latest, ctx).raw
    assert raw["sector_tilt"]["reading"] == "balanced"


def test_patterns_are_limited_to_the_lookback_window(enriched, ctx):
    raw = RegimeTechnicalsProducer().produce(enriched, ctx).raw
    lookback = raw["patterns"]["lookback_days"]
    cutoff = enriched.index[-lookback].strftime("%Y-%m-%d")
    assert all(hit["date"] >= cutoff for hit in raw["patterns"]["recent"])
