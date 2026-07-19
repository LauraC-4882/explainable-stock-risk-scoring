"""[G1] Producer layer — see base.py's module docstring for the design."""

from .base import (
    ProducerOutput,
    RiskProducer,
    ScoringContext,
    fuse,
    resolve_weights,
    run_producer,
)
from .signals import (
    AltDataProducer,
    GarchVolProducer,
    MLDrawdownProducer,
    NewsRiskProducer,
    PercentileCompositeProducer,
)


def build_producers(dr_model) -> list[RiskProducer]:
    """The registered producer list, in response-assembly order."""
    return [
        PercentileCompositeProducer(),
        MLDrawdownProducer(dr_model),
        GarchVolProducer(),
        NewsRiskProducer(),
        AltDataProducer(),
    ]


__all__ = [
    "AltDataProducer",
    "GarchVolProducer",
    "MLDrawdownProducer",
    "NewsRiskProducer",
    "PercentileCompositeProducer",
    "ProducerOutput",
    "RiskProducer",
    "ScoringContext",
    "build_producers",
    "fuse",
    "resolve_weights",
    "run_producer",
]
