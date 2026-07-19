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
from ...models.har_volatility import HarVolatilityModel
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


class HarVolProducer(RiskProducer):
    """[G5] HAR(1,5,22) on daily Garman-Klass realized vol — the modern
    consensus baseline for vol forecasting, shipped ALONGSIDE the GJR leg
    (not replacing it) until scripts/compare_vol_models.py's QLIKE shootout
    picks a default on evidence. score=None for the same reason as GarchVol:
    absolute sigma has no validated 0-100 mapping yet."""

    name = "har_vol"
    default_weight = 0.0
    validation = None

    def produce(self, df: pd.DataFrame, ctx: ScoringContext) -> ProducerOutput:
        har = HarVolatilityModel().fit(df)
        forecast = har.predict(df)
        return ProducerOutput(
            score=None,
            raw={
                "vol_1d": round(float(forecast["har_vol_1d"]), 4),
                "vol_30d": round(float(forecast["har_vol_30d"]), 4),
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


class OptionsImpliedProducer(RiskProducer):
    """[G4] The system's only FORWARD-looking signal family — everything else
    is derived from historical prices. Option prices encode what participants
    are paying today for protection against tomorrow: put skew (crash-
    insurance demand, Xing-Zhang-Zhao 2010 at the stock level), IV/HV (the
    fear premium: expected future vol over realized), and the VIX/VIX3M term
    structure (backwardation = fear concentrated in the immediate future).

    score=None + weight 0.0: yfinance provides only a current-chain snapshot,
    no IV history, so skew/IV-HV cannot be walk-forward validated yet — the
    daily snapshot collector (scripts/collect_iv_snapshots.py) is building
    the history that unlocks IV rank + a real backtest after ~252 sessions.
    The one immediately backtestable piece (VIX term structure, full history
    on both legs) gets its verdict from scripts/validate_vix_structure.py.
    """

    name = "options_implied"
    default_weight = 0.0
    validation = None

    def produce(self, df: pd.DataFrame, ctx: ScoringContext) -> ProducerOutput:
        sig = ctx.options_signals or {}
        atm_iv = sig.get("atm_iv")

        # IV/HV: both legs annualized (yfinance IV is annualized; vol_21d is
        # annualized by RiskMetrics), so the ratio is unit-consistent.
        iv_hv_ratio = None
        hv = df.iloc[-1].get("vol_21d")
        if atm_iv is not None and hv is not None and pd.notna(hv) and hv > 0:
            iv_hv_ratio = round(float(atm_iv) / float(hv), 4)

        vix_term = None
        if ctx.vix is not None and ctx.vix3m is not None and ctx.vix3m > 0:
            ratio = ctx.vix / ctx.vix3m
            vix_term = {
                "vix": round(float(ctx.vix), 2),
                "vix3m": round(float(ctx.vix3m), 2),
                "ratio": round(float(ratio), 4),
                "backwardation": bool(ratio > 1.0),
            }

        return ProducerOutput(
            score=None,
            raw={
                "atm_iv": round(atm_iv, 4) if atm_iv is not None else None,
                "put_skew": round(sig["put_skew"], 4) if sig.get("put_skew") is not None else None,
                "iv_hv_ratio": iv_hv_ratio,
                "vix_term_structure": vix_term,
                "expiry": sig.get("expiry"),
            },
        )


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
