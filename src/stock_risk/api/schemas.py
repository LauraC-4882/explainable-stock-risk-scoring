"""Pydantic response models for the scoring API.

Declaring these as FastAPI's `response_model` gets two things at once: free
OpenAPI docs, and — the actual reason this file exists — type sanitization
at the response boundary. Pydantic's numeric validators coerce anything
`float`-like (including a stray `numpy.float32`, which isn't a `float`
subclass and is exactly what broke `json.dumps` in ModelMonitor.record())
into a native Python `float` before FastAPI serializes the response.

This does NOT cover `ModelMonitor.record()` — it receives the raw dict
`RiskScorer.score()` returns, before FastAPI ever applies this model, so a
leak there still needs its own defense (see api/app.py: monitor.record is
wrapped in its own try/except so a monitoring failure can't 500 the
request; and monitoring/metrics.py's own json.dumps is a second, narrower
backstop). This model is the response-boundary half of that defense, not
a substitute for it.

Nested shapes that are inherently loosely-typed (news article extractions,
which can come from an LLM; stress-test per-scenario category breakdowns,
which reuse the same variable-keyed metrics dict as risk_breakdown) are
typed as `dict`/`list[dict]` rather than fully pinned down — the numpy-leak
risk lives in the named numeric fields, not in those free-form blobs, and
over-specifying them would add schema-mismatch risk for no real benefit.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel


class RiskCategoryMetric(BaseModel):
    score: Optional[float] = None
    weight: float
    metrics: dict[str, float]


class FusionComponent(BaseModel):
    producer: str
    score: float
    weight: float  # normalized share actually used in this response


class MarketRegime(BaseModel):
    vix: Optional[float] = None
    regime: str
    market: str
    benchmark: str


class MLExplanationFeature(BaseModel):
    feature: str
    raw_value: Optional[float] = None
    shap_contribution: float


class MLDrawdownExplanation(BaseModel):
    base_probability: float
    predicted_probability: float
    calibrated_probability: Optional[float] = None
    top_features: list[MLExplanationFeature]
    note: str


class GarchForecast(BaseModel):
    vol_1d: float
    vol_30d: float


class NewsRisk(BaseModel):
    llm_configured: bool
    max_severity: float
    negative_count: int
    articles: list[dict[str, Any]]


class AnalystActivity(BaseModel):
    downgrade_count: int
    upgrade_count: int


class InsiderActivity(BaseModel):
    sale_count: int
    purchase_count: int
    net_transaction_count: int


class AltData(BaseModel):
    analyst_activity: AnalystActivity
    insider_activity: InsiderActivity


class StressScenario(BaseModel):
    label: str
    baseline_score: float
    stressed_score: float
    delta: float
    narrative: str
    stressed_categories: dict[str, RiskCategoryMetric]


class StressTest(BaseModel):
    live_score: float
    scenarios: dict[str, StressScenario]


class VixTermStructure(BaseModel):
    vix: float
    vix3m: float
    ratio: float
    backwardation: bool


class OptionsImplied(BaseModel):
    atm_iv: Optional[float] = None
    put_skew: Optional[float] = None
    iv_hv_ratio: Optional[float] = None
    vix_term_structure: Optional[VixTermStructure] = None
    expiry: Optional[str] = None


class Indicators(BaseModel):
    rsi_14: Optional[float] = None
    bb_pct: Optional[float] = None
    atr_14: Optional[float] = None


class Fundamentals(BaseModel):
    sector: Optional[str] = None
    market_cap: Optional[float] = None
    trailing_pe: Optional[float] = None


class ScoreResponse(BaseModel):
    ticker: str
    timestamp: str
    risk_score: float
    risk_label: str
    risk_note: str
    risk_score_composition: Optional[list[FusionComponent]] = None
    risk_breakdown: dict[str, RiskCategoryMetric]
    market_regime: MarketRegime
    ml_drawdown_probability: Optional[float] = None
    ml_drawdown_explanation: Optional[MLDrawdownExplanation] = None
    garch_volatility_forecast: Optional[GarchForecast] = None
    har_volatility_forecast: Optional[GarchForecast] = None  # same {vol_1d, vol_30d} shape
    options_implied: Optional[OptionsImplied] = None
    news_risk: NewsRisk
    alt_data: AltData
    stress_test: Optional[StressTest] = None
    volatility_30d: Optional[float] = None
    var_95: Optional[float] = None
    cvar_95: Optional[float] = None
    max_drawdown_90d: Optional[float] = None
    beta: Optional[float] = None
    implied_volatility: Optional[float] = None
    name: str
    indicators: Indicators
    fundamentals: Fundamentals
