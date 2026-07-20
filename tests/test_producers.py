"""[G1] Producer-layer tests: per-producer contracts, fusion math, and the
unvalidated-weight guard. All offline — synthetic data, no network."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from loguru import logger

from stock_risk.data.preprocessor import DataPreprocessor
from stock_risk.features.risk_metrics import RiskMetrics
from stock_risk.features.technical import TechnicalFeatures
from stock_risk.scoring import risk_categories
from stock_risk.scoring.producers import (
    AltDataProducer,
    GarchVolProducer,
    MLDrawdownProducer,
    NewsRiskProducer,
    PercentileCompositeProducer,
    ProducerOutput,
    RiskProducer,
    ScoringContext,
    build_producers,
    fuse,
    resolve_weights,
    run_producer,
)


def _feature_df(n: int = 400, seed: int = 5) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.standard_normal(n) * 0.01))
    dates = pd.bdate_range("2024-01-01", periods=n)
    raw = pd.DataFrame({
        "open": close * 0.99, "high": close * 1.01,
        "low": close * 0.98, "close": close,
        "volume": rng.integers(1_000_000, 5_000_000, n).astype(float),
    }, index=dates)
    raw.index.name = "date"
    return RiskMetrics().compute(TechnicalFeatures().compute(DataPreprocessor().process(raw)))


def _ctx(**overrides) -> ScoringContext:
    defaults = dict(
        ticker="TEST",
        market="us",
        benchmark_ticker="SPY",
        category_weights=dict(risk_categories.CATEGORY_WEIGHTS),
        news_articles=[{"title": "Some headline", "summary": "s"}],
        analyst_activity={"downgrade_count": 1, "upgrade_count": 0},
        insider_activity={"sale_count": 2, "purchase_count": 0, "net_transaction_count": -2},
    )
    defaults.update(overrides)
    return ScoringContext(**defaults)


# ── Per-producer contracts ───────────────────────────────────────────────────


def test_percentile_producer_contract():
    out = PercentileCompositeProducer().produce(_feature_df(), _ctx())
    assert out is not None
    assert 0 <= out.score <= 100
    assert set(out.detail["categories"]) == set(risk_categories.CATEGORY_WEIGHTS)


def test_percentile_producer_is_required_and_validated_with_full_weight():
    p = PercentileCompositeProducer()
    assert p.required is True
    assert p.default_weight == 1.0
    assert p.validation is not None


def test_ml_producer_returns_none_without_model():
    assert MLDrawdownProducer(None).produce(_feature_df(), _ctx()) is None


def test_ml_producer_is_validated_with_the_default_fusion_share():
    """Validated (walk-forward AUC 0.671); since the fusion gate opened its
    class default matches the settings default (0.15). build_producers
    overrides per-instance from ML_FUSION_WEIGHT."""
    p = MLDrawdownProducer(None)
    assert p.validation is not None
    assert p.default_weight == pytest.approx(0.15)


def test_garch_producer_emits_raw_forecast_but_no_score():
    out = GarchVolProducer().produce(_feature_df(), _ctx())
    assert out.score is None  # absolute σ has no validated 0-100 mapping
    assert set(out.raw) == {"vol_1d", "vol_30d"}
    assert out.raw["vol_1d"] > 0


def test_news_producer_summarizes_context_articles():
    out = NewsRiskProducer().produce(_feature_df(), _ctx())
    assert out.score is None
    assert out.raw["llm_configured"] is False
    assert len(out.raw["articles"]) == 1


def test_alt_data_producer_passes_through_context():
    ctx = _ctx()
    out = AltDataProducer().produce(_feature_df(), ctx)
    assert out.score is None
    assert out.raw == {
        "analyst_activity": ctx.analyst_activity,
        "insider_activity": ctx.insider_activity,
    }


# ── run_producer degradation policy ──────────────────────────────────────────


class _ExplodingProducer(RiskProducer):
    name = "exploding"
    default_weight = 0.0
    validation = None

    def produce(self, df, ctx):
        raise RuntimeError("boom")


def test_optional_producer_failure_degrades_to_none():
    assert run_producer(_ExplodingProducer(), _feature_df(), _ctx()) is None


def test_required_producer_failure_propagates():
    """Pre-refactor, a composite_score failure was a scoring failure (no
    degradation block around it) — required=True preserves exactly that."""
    p = _ExplodingProducer()
    p.required = True
    with pytest.raises(RuntimeError, match="boom"):
        run_producer(p, _feature_df(), _ctx())


# ── Fusion ───────────────────────────────────────────────────────────────────


class _StubProducer(RiskProducer):
    def __init__(self, name, weight, validation=None):
        self.name = name
        self.default_weight = weight
        self.validation = validation

    def produce(self, df, ctx):  # pragma: no cover — never called in these tests
        return None


def test_fuse_renormalizes_over_available_scores():
    outputs = {
        "a": ProducerOutput(score=80.0),
        "b": ProducerOutput(score=40.0),
        "c": None,  # failed producer — excluded
        "d": ProducerOutput(score=None),  # no risk-unit mapping — excluded
    }
    weights = {"a": 0.6, "b": 0.2, "c": 0.2, "d": 0.5}
    # (80*0.6 + 40*0.2) / (0.6+0.2) = 56/0.8 = 70
    assert fuse(outputs, weights) == pytest.approx(70.0)


def test_fuse_returns_none_when_nothing_contributes():
    assert fuse({"a": None, "b": ProducerOutput(score=None)}, {"a": 1.0, "b": 1.0}) is None


def test_unvalidated_nonzero_weight_is_forced_to_zero_with_warning():
    """The fusion gate: a producer with no validation record must never carry
    weight into risk_score, even if misconfigured with one."""
    captured: list[str] = []
    sink_id = logger.add(lambda msg: captured.append(str(msg)), level="WARNING")
    try:
        weights = resolve_weights([
            _StubProducer("validated", 0.7, validation={"method": "backtest"}),
            _StubProducer("unvalidated_misconfigured", 0.3, validation=None),
        ])
    finally:
        logger.remove(sink_id)

    assert weights == {"validated": 0.7, "unvalidated_misconfigured": 0.0}
    assert any("unvalidated_misconfigured" in m and "forcing weight to 0" in m for m in captured)


def test_registry_weights_reflect_the_opened_fusion_gate():
    """Post-[A1]/[A2] the gate is open: percentile 0.85 / ml 0.15 by default
    (both validated — the resolve_weights guard only zeroes unvalidated
    producers), everything else still 0."""
    weights = resolve_weights(build_producers(dr_model=None))
    assert weights["percentile_composite"] == pytest.approx(0.85)
    assert weights["ml_drawdown"] == pytest.approx(0.15)
    assert all(
        w == 0.0 for name, w in weights.items()
        if name not in ("percentile_composite", "ml_drawdown")
    )


def test_ml_fusion_weight_zero_reproduces_pure_percentile(monkeypatch):
    from stock_risk.config import settings
    monkeypatch.setattr(settings, "ml_fusion_weight", 0.0)
    weights = resolve_weights(build_producers(dr_model=None))
    assert weights["percentile_composite"] == 1.0
    assert weights["ml_drawdown"] == 0.0


def test_fuse_with_composition_reports_normalized_shares():
    from stock_risk.scoring.producers import fuse_with_composition
    outputs = {
        "percentile_composite": ProducerOutput(score=70.0),
        "ml_drawdown": ProducerOutput(score=10.0),
    }
    weights = {"percentile_composite": 0.85, "ml_drawdown": 0.15}
    fused, comp = fuse_with_composition(outputs, weights)
    assert fused == pytest.approx(0.85 * 70 + 0.15 * 10)
    shares = {c["producer"]: c["weight"] for c in comp}
    assert shares == {"percentile_composite": 0.85, "ml_drawdown": 0.15}


def test_fusion_renormalizes_to_percentile_when_ml_unavailable():
    """The graceful-degradation contract of the opened gate: no ML output ->
    exact pre-fusion score, and the composition says only percentile fed it."""
    from stock_risk.scoring.producers import fuse_with_composition
    outputs = {"percentile_composite": ProducerOutput(score=70.0), "ml_drawdown": None}
    weights = {"percentile_composite": 0.85, "ml_drawdown": 0.15}
    fused, comp = fuse_with_composition(outputs, weights)
    assert fused == pytest.approx(70.0)
    assert comp == [{"producer": "percentile_composite", "score": 70.0, "weight": 1.0}]
