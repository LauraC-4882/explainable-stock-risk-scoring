"""[G1] Producer layer — see base.py's module docstring for the design."""

from .base import (
    ProducerOutput,
    RiskProducer,
    ScoringContext,
    fuse,
    fuse_with_composition,
    resolve_weights,
    run_producer,
)
from .regime_technicals import RegimeTechnicalsProducer
from .signals import (
    AltDataProducer,
    GarchVolProducer,
    HarVolProducer,
    MLDrawdownProducer,
    NewsRiskProducer,
    OptionsImpliedProducer,
    PercentileCompositeProducer,
)


def build_producers(dr_model) -> list[RiskProducer]:
    """The registered producer list, in response-assembly order.

    Fusion gate ([G1] roadmap: "#8/#9 validation results open the gate"):
    after [A1] validated the percentile composite and [A2] validated the ML
    leg (walk-forward AUC 0.671), the ML producer carries a real fusion
    share, configurable via ML_FUSION_WEIGHT (default 0.15; 0 reproduces the
    pure-percentile score). resolve_weights' unvalidated-producer guard
    still applies to everything else.
    """
    from ...config import settings

    ml_share = max(0.0, min(1.0, settings.ml_fusion_weight))
    percentile = PercentileCompositeProducer()
    percentile.default_weight = 1.0 - ml_share
    ml = MLDrawdownProducer(dr_model)
    ml.default_weight = ml_share
    return [
        percentile,
        ml,
        GarchVolProducer(),
        HarVolProducer(),
        OptionsImpliedProducer(),
        NewsRiskProducer(),
        AltDataProducer(),
        # [G6] display-only (weight 0, validation None — see its docstring).
        # Last in the list so response-assembly order puts the newest,
        # lowest-authority block after the established signals.
        RegimeTechnicalsProducer(),
    ]


__all__ = [
    "AltDataProducer",
    "GarchVolProducer",
    "HarVolProducer",
    "MLDrawdownProducer",
    "NewsRiskProducer",
    "OptionsImpliedProducer",
    "PercentileCompositeProducer",
    "ProducerOutput",
    "RegimeTechnicalsProducer",
    "RiskProducer",
    "ScoringContext",
    "build_producers",
    "fuse",
    "fuse_with_composition",
    "resolve_weights",
    "run_producer",
]
