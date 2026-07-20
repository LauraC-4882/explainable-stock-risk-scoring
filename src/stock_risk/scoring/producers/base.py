"""[G1] RiskProducer abstraction: the contract every risk-signal producer obeys.

Five signals used to live as five hand-rolled, mutually-unaware code paths
inside RiskScorer.score() (percentile composite, ML drawdown, GARCH vol,
news risk, alt-data) — each with its own copy-pasted try/except degradation
block, and only the first one actually feeding risk_score. This module makes
the three things they all share declarative instead of implicit:

  - weight   — each producer carries its fusion weight (0.0 = display-only);
  - unit     — `score` is always 0-100 risk units or None ("no defensible
               mapping to risk units" is an honest, explicit state — e.g.
               GARCH emits absolute volatility, and inventing a 0-100 mapping
               without validation would be pseudo-rigor);
  - validation — machine-readable record of whether/how this producer was
               backtested. The fusion guard is typed on this: an unvalidated
               producer with a nonzero weight is forced to 0 with a warning,
               so "never average noise into the signal" is enforced in code,
               not by convention.

This issue is refactor-only by design: weights ship as
{percentile_composite: 1.0, everything else: 0.0}, so fuse() reproduces the
pre-refactor risk_score exactly. Changing weights is a separate,
behavior-changing step gated on validation results — see README.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd
from loguru import logger


@dataclass
class ScoringContext:
    """Shared inputs fetched once by RiskScorer — producers never fetch data
    themselves, so adding a producer can't add hidden network calls."""

    ticker: str
    market: str
    benchmark_ticker: str
    category_weights: dict[str, float]
    vix: Optional[float] = None
    vix3m: Optional[float] = None  # [G4] 3-month VIX for the term-structure signal
    regime: str = "not_available"
    info: dict = field(default_factory=dict)
    iv: Optional[float] = None
    options_signals: dict = field(default_factory=dict)  # [G4] atm_iv/otm_put_iv/put_skew/expiry
    news_articles: list[dict] = field(default_factory=list)
    analyst_activity: dict = field(default_factory=dict)
    insider_activity: dict = field(default_factory=dict)


@dataclass
class ProducerOutput:
    score: Optional[float]  # 0-100 risk units; None = not usable for fusion
    raw: dict = field(default_factory=dict)  # producer-native output (probability/σ/counts)
    detail: dict = field(default_factory=dict)  # explanatory breakdown (categories, SHAP, ...)


class RiskProducer(ABC):
    name: str
    default_weight: float = 0.0
    # Machine-readable validation record (method/metrics/date/reference), or
    # None when the producer has never been backtested. fuse()'s guard keys
    # off this — see resolve_weights().
    validation: Optional[dict] = None
    # required=True: a failure here is a scoring failure (exception propagates,
    # matching the pre-refactor behavior where composite_score was never
    # wrapped in a degradation block). required=False: failure degrades to
    # None and the response ships without this signal.
    required: bool = False

    @abstractmethod
    def produce(self, df: pd.DataFrame, ctx: ScoringContext) -> Optional[ProducerOutput]:
        """Compute this producer's signal. May return None for a clean
        "not available this run" (e.g. no model artefact loaded)."""


def run_producer(
    producer: RiskProducer, df: pd.DataFrame, ctx: ScoringContext
) -> Optional[ProducerOutput]:
    """The single degradation point that replaced the per-signal copy-pasted
    try/except blocks in score(): optional producers fail soft (logged, signal
    omitted), required producers fail the request like they always did."""
    if producer.required:
        return producer.produce(df, ctx)
    try:
        return producer.produce(df, ctx)
    except Exception as exc:
        logger.warning(f"{producer.name} producer failed for {ctx.ticker} (degrading): {exc}")
        return None


def resolve_weights(producers: list[RiskProducer]) -> dict[str, float]:
    """Effective fusion weights, with the validation guard applied: a producer
    that has never been validated cannot carry a nonzero weight — misconfiguring
    one logs a warning and forces it to 0 instead of silently averaging noise
    into risk_score."""
    weights: dict[str, float] = {}
    for p in producers:
        w = p.default_weight
        if w > 0 and p.validation is None:
            logger.warning(
                f"Producer '{p.name}' has weight {w} but no validation record — "
                "forcing weight to 0 (unvalidated signals must not enter risk_score)"
            )
            w = 0.0
        weights[p.name] = w
    return weights


def fuse_with_composition(
    outputs: dict[str, Optional[ProducerOutput]], weights: dict[str, float]
) -> tuple[Optional[float], list[dict]]:
    """Σ wᵢ·sᵢ / Σ wᵢ over producers that actually delivered a score and carry
    a positive weight — the same renormalise-over-what's-available pattern as
    risk_categories.composite_score. Also returns the composition (producer,
    score, normalized weight actually used) so the API can show exactly what
    the headline number is made of — a fused score that can't explain itself
    would undercut the whole point of this project. (None, []) if nothing
    usable contributed.

    The renormalisation doubles as graceful degradation for the fusion gate:
    with weights {percentile: 0.85, ml_drawdown: 0.15}, a request where the
    ML leg is unavailable (no artefact / ENABLE_ML=0 / prediction failure)
    renormalises to the percentile alone — bit-identical to the
    pre-fusion-gate score, with the composition saying so.
    """
    contributions: list[tuple[str, float, float]] = []
    weighted_sum = 0.0
    weight_total = 0.0
    for name, out in outputs.items():
        w = weights.get(name, 0.0)
        if out is None or out.score is None or w <= 0:
            continue
        contributions.append((name, out.score, w))
        weighted_sum += out.score * w
        weight_total += w
    if weight_total == 0:
        return None, []
    composition = [
        {"producer": name, "score": round(score, 1), "weight": round(w / weight_total, 3)}
        for name, score, w in contributions
    ]
    return weighted_sum / weight_total, composition


def fuse(
    outputs: dict[str, Optional[ProducerOutput]], weights: dict[str, float]
) -> Optional[float]:
    """The fused score alone — see fuse_with_composition."""
    return fuse_with_composition(outputs, weights)[0]
