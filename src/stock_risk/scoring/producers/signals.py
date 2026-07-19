"""[G1] The five concrete producers — algorithms moved verbatim from
RiskScorer.score(), zero behavior change. Only the percentile composite has a
nonzero fusion weight; the ML leg is validated (see its metadata) but turning
its weight on is a deliberate future behavior change, not part of this
refactor. GARCH/news/alt-data emit score=None: absolute volatility, mock
severity labels, and raw counts have no defensible 0-100 risk-unit mapping
today, and pretending otherwise would launder unvalidated numbers into
risk_score.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

from ...llm.news_risk import extract_news_risk, summarize_news_risk
from ...models.volatility import VolatilityModel
from .. import risk_categories
from .base import ProducerOutput, RiskProducer, ScoringContext


class PercentileCompositeProducer(RiskProducer):
    """The explainable baseline — sole contributor to risk_score today."""

    name = "percentile_composite"
    default_weight = 1.0
    required = True  # its failure is a scoring failure, exactly as pre-refactor
    validation = {
        "method": "quintile backtest + Kupiec POF test (36 tickers, 5y, 37,869 obs)",
        "result": (
            "forward 20d max-drawdown and realized vol both monotonic across "
            "score quintiles; var_95_21d breach rate 9.25% vs claimed 5% "
            "(documented miscalibration, see README)"
        ),
        "date": "2026-07-17",
        "reference": "scripts/validate_score.py; README 'Score Validation'",
    }

    def produce(self, df: pd.DataFrame, ctx: ScoringContext) -> ProducerOutput:
        scorecard = risk_categories.composite_score(df, weights=ctx.category_weights)
        return ProducerOutput(
            score=scorecard["composite_score"],
            detail={"categories": scorecard["categories"]},
        )


class MLDrawdownProducer(RiskProducer):
    """XGBoost 20-day severe-drawdown probability + SHAP explanation.

    Validated (walk-forward AUC 0.671) but still weight 0.0: granting it a
    share of risk_score would change every API response, which is exactly the
    behavior change this refactor-only issue defers. When that step happens,
    only this default_weight (and the README weight table) should move.
    """

    name = "ml_drawdown"
    default_weight = 0.0
    validation = {
        "method": "walk-forward TimeSeriesSplit (gap=20), 56 tickers x 5y, 68,430 rows",
        "roc_auc": 0.671,
        "result": "mean AUC 0.671 (every fold >0.6); precision 0.41, recall 0.11 (low, documented)",
        "date": "2026-07-17",
        "reference": "README 'Does the XGBoost signal actually work?'",
    }

    def __init__(self, model):
        self._model = model  # DownsideRiskModel or None (no artefact / ENABLE_ML=0)

    def produce(self, df: pd.DataFrame, ctx: ScoringContext) -> Optional[ProducerOutput]:
        if self._model is None:
            return None
        from ...models.explain import explain_prediction  # deferred — see [F1]

        probability = round(float(self._model.predict(df)["downside_risk_score"]), 1)
        return ProducerOutput(
            score=probability,  # already 0-100 (probability x 100)
            raw={"probability": probability},
            detail={"explanation": explain_prediction(self._model, df)},
        )


class GarchVolProducer(RiskProducer):
    """GARCH(1,1) 1d/30d volatility forecast — fit live per ticker (vol
    clustering parameters are instrument-specific, unlike the pretrained
    classifier). score=None: output is absolute annualized σ, and no
    validated σ→0-100 mapping exists; it's the future 'absolute anchor'
    for cross-ticker comparability once such a mapping is built and tested.
    """

    name = "garch_vol"
    default_weight = 0.0
    validation = None

    def produce(self, df: pd.DataFrame, ctx: ScoringContext) -> ProducerOutput:
        garch = VolatilityModel().fit(df)
        forecast = garch.predict(df)
        return ProducerOutput(
            score=None,
            raw={
                "vol_1d": round(float(forecast["garch_vol_1d"]), 4),
                "vol_30d": round(float(forecast["garch_vol_30d"]), 4),
            },
        )


class NewsRiskProducer(RiskProducer):
    """Headline risk extraction — currently a labeled mock (no live LLM call),
    so score=None and validation=None until a real extractor is wired in."""

    name = "news_risk"
    default_weight = 0.0
    validation = None

    def produce(self, df: pd.DataFrame, ctx: ScoringContext) -> ProducerOutput:
        extractions = [extract_news_risk(a) for a in ctx.news_articles]
        summary = summarize_news_risk(extractions)
        summary["llm_configured"] = False
        return ProducerOutput(score=None, raw=summary)


class AltDataProducer(RiskProducer):
    """Analyst rating changes + insider transactions — informational counts,
    deliberately not folded into risk_score (fundamentals aren't
    point-in-time; see README 'Data Quality & Limitations')."""

    name = "alt_data"
    default_weight = 0.0
    validation = None

    def produce(self, df: pd.DataFrame, ctx: ScoringContext) -> ProducerOutput:
        return ProducerOutput(
            score=None,
            raw={
                "analyst_activity": ctx.analyst_activity,
                "insider_activity": ctx.insider_activity,
            },
        )
