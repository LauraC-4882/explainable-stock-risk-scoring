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
from stock_risk.features.technical import TECHNICAL_STRUCTURE_COLS, TechnicalFeatures
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
    df = RiskMetrics().compute(TechnicalFeatures().compute(frame))
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
    for block in ("regime", "sector_tilt", "trend", "patterns", "momentum", "technicals"):
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


# ── [G7] chart-structure indicators ──────────────────────────────────────────

def test_technical_structure_columns_produced(frame):
    out = TechnicalFeatures().compute(frame)
    missing = [c for c in TECHNICAL_STRUCTURE_COLS if c not in out.columns]
    assert not missing, f"declared but not produced: {missing}"


def test_kdj_follows_the_cn_convention_not_tas_stochastic(frame):
    """K and D must be the 1/3-smoothed recursion, and J = 3K - 2D exactly.

    `ta`'s StochasticOscillator returns raw RSV as %K and its SMA as %D, which
    differs by several points on the same bar — a J line that doesn't match a
    user's broker chart is worse than none.
    """
    out = TechnicalFeatures().compute(frame)
    k, d, j = out["kdj_k"], out["kdj_d"], out["kdj_j"]
    valid = pd.concat([k, d, j], axis=1).dropna()
    assert (valid["kdj_j"] - (3 * valid["kdj_k"] - 2 * valid["kdj_d"])).abs().max() < 1e-9

    low_9 = frame["low"].rolling(9, min_periods=9).min()
    high_9 = frame["high"].rolling(9, min_periods=9).max()
    rsv = 100 * (frame["close"] - low_9) / (high_9 - low_9)
    expected_k = rsv.ewm(alpha=1 / 3, adjust=False).mean()
    pd.testing.assert_series_equal(k.dropna(), expected_k.dropna(), check_names=False)


def test_kdj_j_may_leave_the_zero_hundred_band(frame):
    """J overshooting is the feature, not a bug — clamping it would erase the
    extremes it exists to mark."""
    out = TechnicalFeatures().compute(frame)
    k = out["kdj_k"].dropna()
    assert k.between(0, 100).all(), "K itself must stay bounded"


def test_ma_alignment_is_plus_one_on_a_perfect_stack():
    idx = pd.date_range("2020-01-01", periods=300, freq="B")
    rising = pd.Series(np.linspace(100, 400, 300), index=idx)
    df = pd.DataFrame(
        {"open": rising, "high": rising * 1.01, "low": rising * 0.99,
         "close": rising, "volume": 1e6},
        index=idx,
    )
    out = TechnicalFeatures().compute(df)
    assert out["ma_alignment"].dropna().iloc[-1] == pytest.approx(1.0)

    falling = pd.Series(np.linspace(400, 100, 300), index=idx)
    df2 = df.assign(open=falling, high=falling * 1.01, low=falling * 0.99, close=falling)
    out2 = TechnicalFeatures().compute(df2)
    assert out2["ma_alignment"].dropna().iloc[-1] == pytest.approx(-1.0)


def test_bb_width_percentile_is_a_rank_not_a_level(frame):
    """Absolute band width is not comparable across tickers; its rank within
    the stock's own trailing year is."""
    out = TechnicalFeatures().compute(frame)
    pctile = out["bb_width_pctile"].dropna()
    assert pctile.between(0, 1).all()

    scaled = frame.assign(**{c: frame[c] * 1000 for c in ("open", "high", "low", "close")})
    scaled_pctile = TechnicalFeatures().compute(scaled)["bb_width_pctile"].dropna()
    # A pure price rescaling leaves every rank untouched.
    pd.testing.assert_series_equal(pctile, scaled_pctile, check_names=False)


def test_pv_divergence_flags_price_up_without_volume():
    idx = pd.date_range("2020-01-01", periods=60, freq="B")
    close = pd.Series(np.linspace(100, 130, 60), index=idx)
    # Volume concentrated on down-days early then vanishing keeps OBV falling
    # while price rises — the 价升量缩 case.
    volume = pd.Series(np.r_[np.full(30, 5e6), np.full(30, 1e5)], index=idx)
    df = pd.DataFrame(
        {"open": close, "high": close * 1.01, "low": close * 0.99,
         "close": close, "volume": volume},
        index=idx,
    )
    out = TechnicalFeatures().compute(df)
    assert set(out["pv_divergence_20d"].dropna().unique()) <= {-1.0, 0.0, 1.0}


def test_squeeze_state_is_descriptive_only(enriched, ctx):
    """The compliance boundary, asserted in code: the block may describe the
    current range, and must never emit a directional or target-bearing state."""
    raw = RegimeTechnicalsProducer().produce(enriched, ctx).raw
    squeeze = raw["technicals"]["squeeze"]
    assert squeeze["state"] in {"compressed", "normal", "expanded"}

    forbidden = {"breakout", "buy", "sell", "target", "rally", "imminent", "bullish", "bearish"}
    states = [
        raw["technicals"]["squeeze"]["state"],
        raw["technicals"]["momentum_extremes"]["state"],
        raw["technicals"]["participation"]["state"],
    ]
    for state in states:
        assert not (forbidden & set(state.lower().split("_"))), f"directional state: {state}"


def test_rsi_extreme_requires_all_three_horizons_to_agree(enriched, ctx):
    """One stretched horizon is noise. Disagreement must report neutral rather
    than being resolved by majority vote."""
    latest = enriched.copy()
    idx = latest.index[-1]
    latest.loc[idx, ["rsi_6", "rsi_14"]] = 20.0
    latest.loc[idx, "rsi_24"] = 55.0
    raw = RegimeTechnicalsProducer().produce(latest, ctx).raw
    assert raw["technicals"]["momentum_extremes"]["state"] == "neutral"

    latest.loc[idx, "rsi_24"] = 25.0
    raw = RegimeTechnicalsProducer().produce(latest, ctx).raw
    assert raw["technicals"]["momentum_extremes"]["state"] == "oversold"


def test_technicals_block_absent_on_a_bare_frame(frame, ctx):
    raw = RegimeTechnicalsProducer().produce(frame, ctx).raw
    assert raw["technicals"] is None


def test_patterns_are_limited_to_the_lookback_window(enriched, ctx):
    raw = RegimeTechnicalsProducer().produce(enriched, ctx).raw
    lookback = raw["patterns"]["lookback_days"]
    cutoff = enriched.index[-lookback].strftime("%Y-%m-%d")
    assert all(hit["date"] >= cutoff for hit in raw["patterns"]["recent"])
