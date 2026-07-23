"""The perception bridge: real scorecard -> what a screen actually presents.

The served UI is React and can't be rendered headlessly here, so the framework
models the *information content* of a screen as an ordered list of typed
``ContentUnit``s — each with the concept it conveys, the modality it uses
(number / label / colour / text / chart / warning), how salient it is, how
strong any warning is, and whether it carries uncertainty or freshness cues.
Crucially, a unit records whether its meaning is carried by colour ALONE, so the
colour-vision scenarios can measure what a user with a colour deficiency would
miss.

Experiment variants are different *projections of the same real data*: the
score-only control strips everything but the number and label; the explained
treatment adds the component breakdown, uncertainty, freshness and plain
language; the ``AS_IS`` variant reproduces what the current product actually
shows today — which, per the audit, is a rich card that still lacks any explicit
confidence or freshness flag on the score. Keeping ``AS_IS`` honest is what lets
a scenario attribute a harm to a real gap rather than an invented one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from .profiles import ColorVisionMode, Language
from .sut import (
    PRODUCT_SURFACES_CONFIDENCE,
    PRODUCT_SURFACES_FRESHNESS_ON_SCORE,
    DataQuality,
)


class Modality(str, Enum):
    NUMBER = "number"
    LABEL = "label"
    COLOR = "color"
    TEXT = "text"
    CHART = "chart"
    WARNING = "warning"
    ICON = "icon"


class Concept(str, Enum):
    COMPOSITE_SCORE = "composite_score"
    RISK_LABEL = "risk_label"
    RISK_COLOR = "risk_color"
    LABEL_MEANING = "label_meaning"           # plain-language "what HIGH means"
    VOLATILITY = "volatility"
    TAIL = "tail"
    DRAWDOWN = "drawdown"
    SENSITIVITY = "sensitivity"
    LIQUIDITY = "liquidity"
    VAR = "var_95"
    CVAR = "cvar_95"
    BETA = "beta"
    ML_DRAWDOWN_PROB = "ml_drawdown_probability"
    SHAP_EXPLANATION = "shap_explanation"
    STRESS_TEST = "stress_test"
    HISTORICAL_OUTCOMES = "historical_outcomes"
    CONCENTRATION = "concentration"
    RISK_CONTRIBUTION = "risk_contribution"
    DATA_FRESHNESS = "data_freshness"
    UNCERTAINTY = "uncertainty"
    DATA_QUALITY_WARNING = "data_quality_warning"
    MODEL_VERSION = "model_version"
    MODEL_DEGRADED = "model_degraded"
    DISCLAIMER = "disclaimer"
    PROFESSIONAL_HELP = "professional_help"
    COMMUNITY_OPINION = "community_opinion"


# How much financial literacy/numeracy a concept demands before a user can read
# it correctly. Used by the interpretation model. Values are deliberate priors,
# not measurements — they live here so a reviewer can see and adjust them.
CONCEPT_DIFFICULTY: dict[Concept, float] = {
    Concept.COMPOSITE_SCORE: 0.35,      # "higher = riskier vs its own history" is subtle
    Concept.RISK_LABEL: 0.15,
    Concept.RISK_COLOR: 0.05,
    Concept.LABEL_MEANING: 0.25,
    Concept.VOLATILITY: 0.45,
    Concept.TAIL: 0.70,
    Concept.DRAWDOWN: 0.45,
    Concept.SENSITIVITY: 0.60,
    Concept.LIQUIDITY: 0.60,
    Concept.VAR: 0.72,
    Concept.CVAR: 0.78,
    Concept.BETA: 0.62,
    Concept.ML_DRAWDOWN_PROB: 0.65,
    Concept.SHAP_EXPLANATION: 0.82,
    Concept.STRESS_TEST: 0.50,
    Concept.HISTORICAL_OUTCOMES: 0.55,
    Concept.CONCENTRATION: 0.55,
    Concept.RISK_CONTRIBUTION: 0.68,
    Concept.DATA_FRESHNESS: 0.30,
    Concept.UNCERTAINTY: 0.45,
    Concept.DATA_QUALITY_WARNING: 0.30,
    Concept.MODEL_VERSION: 0.55,
    Concept.MODEL_DEGRADED: 0.50,
    Concept.DISCLAIMER: 0.30,
    Concept.PROFESSIONAL_HELP: 0.20,
    Concept.COMMUNITY_OPINION: 0.25,
}


@dataclass(frozen=True)
class ContentUnit:
    """One piece of information a screen presents to the user."""

    concept: Concept
    modality: Modality
    salience: float                 # 0-1, how visually/attentionally prominent
    warning_strength: float = 0.0   # 0-1, how strongly this cautions the user
    carries_uncertainty: bool = False
    carries_freshness: bool = False
    color_only: bool = False        # meaning conveyed by colour with NO text/label backup
    text_key: Optional[str] = None  # i18n key when this unit renders copy
    value: Optional[Any] = None     # the underlying datum (score, metric, %, ...)
    # Accessibility / i18n properties of the RENDERED unit (audited from the real
    # UI): English-only content that never translates, whether a screen reader can
    # reach it, and whether it is keyboard-reachable.
    english_only: bool = False      # renders English even in zh mode (P4 gap)
    sr_accessible: bool = True       # exposed to a screen reader (charts often aren't)
    keyboard_reachable: bool = True  # reachable without a mouse (modals often aren't)

    def difficulty(self) -> float:
        return CONCEPT_DIFFICULTY.get(self.concept, 0.5)


class PresentationVariant(str, Enum):
    SCORE_ONLY = "score_only"     # Scenario A control: number + label only
    EXPLAINED = "explained"       # Scenario A treatment: + components/uncertainty/freshness/plain
    AS_IS = "as_is"               # what the current product actually renders today
    CRISIS_SAFE = "crisis_safe"   # Scenario C treatment: freshness, uncertainty, delayed-action
    PLAIN_LANGUAGE = "plain_language"  # Scenario I treatment: layered plain-language first


@dataclass(frozen=True)
class RenderedView:
    """The full set of content a screen shows, for one variant/language/vision."""

    variant: PresentationVariant
    language: Language
    color_vision: ColorVisionMode
    units: tuple[ContentUnit, ...]
    ticker: Optional[str] = None
    scenario_id: str = "unspecified"
    meta: dict[str, Any] = field(default_factory=dict)

    def concepts(self) -> set[Concept]:
        return {u.concept for u in self.units}

    def unit_for(self, concept: Concept) -> Optional[ContentUnit]:
        for u in self.units:
            if u.concept is concept:
                return u
        return None

    def has(self, concept: Concept) -> bool:
        return self.unit_for(concept) is not None


# ── Renderers ───────────────────────────────────────────────────────────────
def _score_and_label_units(scorecard: dict[str, Any]) -> list[ContentUnit]:
    """The hero: the number, the label, and the colour cue.

    The colour unit is NOT ``color_only``: the audit found the real UI always
    pairs the gauge colour with the numeric score and a text label, so a
    colour-deficient user still gets the meaning. Scenario H can flip this to
    test a hypothetical colour-only design.
    """
    return [
        ContentUnit(
            concept=Concept.COMPOSITE_SCORE,
            modality=Modality.NUMBER,
            salience=0.95,
            value=float(scorecard["risk_score"]),
        ),
        ContentUnit(
            concept=Concept.RISK_LABEL,
            modality=Modality.LABEL,
            salience=0.8,
            text_key=f"riskLabel.{str(scorecard['risk_label']).lower()}",
            value=scorecard["risk_label"],
        ),
        ContentUnit(
            concept=Concept.RISK_COLOR,
            modality=Modality.COLOR,
            salience=0.7,
            color_only=False,
            value=scorecard["risk_label"],
        ),
    ]


def _breakdown_units(scorecard: dict[str, Any]) -> list[ContentUnit]:
    units: list[ContentUnit] = []
    breakdown = scorecard.get("risk_breakdown", {})
    concept_map = {
        "volatility": Concept.VOLATILITY,
        "tail": Concept.TAIL,
        "drawdown": Concept.DRAWDOWN,
        "sensitivity": Concept.SENSITIVITY,
        "liquidity": Concept.LIQUIDITY,
    }
    for cat, concept in concept_map.items():
        info = breakdown.get(cat)
        if not info:
            continue
        units.append(
            ContentUnit(
                concept=concept,
                modality=Modality.NUMBER,
                salience=0.4,
                text_key=f"categories.{cat}",
                value=info.get("score"),
            )
        )
    return units


def _metric_tile_units(scorecard: dict[str, Any]) -> list[ContentUnit]:
    tiles = [
        (Concept.VAR, "var_95"),
        (Concept.CVAR, "cvar_95"),
        (Concept.BETA, "beta"),
        (Concept.VOLATILITY, "volatility_30d"),
    ]
    units: list[ContentUnit] = []
    for concept, key in tiles:
        if scorecard.get(key) is not None:
            units.append(
                ContentUnit(
                    concept=concept,
                    modality=Modality.NUMBER,
                    salience=0.35,
                    text_key=f"metrics.{key}",
                    value=scorecard.get(key),
                )
            )
    return units


def _plain_language_unit() -> ContentUnit:
    return ContentUnit(
        concept=Concept.LABEL_MEANING,
        modality=Modality.TEXT,
        salience=0.6,
        text_key="labelExplanation",
    )


def _disclaimer_unit(scorecard: dict[str, Any]) -> ContentUnit:
    return ContentUnit(
        concept=Concept.DISCLAIMER,
        modality=Modality.TEXT,
        salience=0.25,             # architecturally present but low-prominence (a footnote)
        warning_strength=0.5,
        text_key="footer.disclaimerBody1",
        value=scorecard.get("risk_note"),
    )


def _freshness_unit(scorecard: dict[str, Any]) -> ContentUnit:
    return ContentUnit(
        concept=Concept.DATA_FRESHNESS,
        modality=Modality.TEXT,
        salience=0.3,
        carries_freshness=True,
        text_key="card.dataAsOf",
        value=scorecard.get("timestamp"),
    )


def _uncertainty_unit(dq: DataQuality) -> ContentUnit:
    status = dq.intrinsic_confidence().value
    return ContentUnit(
        concept=Concept.UNCERTAINTY,
        modality=Modality.WARNING,
        salience=0.4,
        warning_strength=0.4 if status == "low" else 0.2,
        carries_uncertainty=True,
        text_key="card.confidence",
        value=status,
    )


def render_stock_view(
    scorecard: dict[str, Any],
    *,
    variant: PresentationVariant,
    language: Language,
    color_vision: ColorVisionMode = ColorVisionMode.NORMAL,
    data_quality: Optional[DataQuality] = None,
    scenario_id: str = "unspecified",
    model_degraded: bool = False,
    data_warning: bool = False,
    include_untranslated: bool = False,
    color_only_design: bool = False,
    include_chart: bool = False,
    charts_have_alt_text: bool = False,
) -> RenderedView:
    """Project a real scorecard into the content a given variant/language shows.

    ``model_degraded`` / ``data_warning`` add the governance and data-quality cues
    that a *fixed* product would surface — the Scenario D/E treatments. They are
    off by default, matching the audited AS_IS product which shows neither.

    Accessibility / i18n toggles (Scenario G/H), all off by default so the base
    renders are unchanged: ``include_untranslated`` adds the audited English-only
    units (stress narrative, SHAP feature names); ``color_only_design`` models a
    hypothetical UI where the label is dropped and only colour carries risk;
    ``include_chart`` adds the risk chart, whose ``sr_accessible`` follows
    ``charts_have_alt_text`` (the audited product has none).
    """
    dq = data_quality or DataQuality()
    if color_only_design:
        # Hypothetical inaccessible design: colour is the ONLY risk cue (no label).
        units: list[ContentUnit] = [
            ContentUnit(concept=Concept.COMPOSITE_SCORE, modality=Modality.NUMBER, salience=0.95,
                        value=float(scorecard["risk_score"])),
            ContentUnit(concept=Concept.RISK_COLOR, modality=Modality.COLOR, salience=0.8,
                        color_only=True, value=scorecard["risk_label"]),
        ]
    else:
        units = list(_score_and_label_units(scorecard))

    if variant is PresentationVariant.SCORE_ONLY:
        pass  # number + label + colour only, by design

    elif variant is PresentationVariant.CRISIS_SAFE:
        # Non-alarmist: plain language, freshness, uncertainty, a delayed-action
        # nudge and a professional-help off-ramp; the raw colour is de-emphasised
        # so a red gauge doesn't drive the response on its own.
        units[2] = ContentUnit(  # dampen the colour hero
            concept=Concept.RISK_COLOR, modality=Modality.COLOR, salience=0.35, value="muted"
        )
        units.append(_plain_language_unit())
        units.append(_freshness_unit(scorecard))
        units.append(_uncertainty_unit(dq))
        units.append(
            ContentUnit(
                concept=Concept.PROFESSIONAL_HELP, modality=Modality.TEXT, salience=0.5,
                warning_strength=0.4, text_key="crisis.delayAndConsult",
            )
        )
        units.append(_disclaimer_unit(scorecard))

    elif variant is PresentationVariant.PLAIN_LANGUAGE:
        # Layered: one strong plain-language sentence first, then optional depth.
        units.append(
            ContentUnit(
                concept=Concept.LABEL_MEANING, modality=Modality.TEXT, salience=0.85,
                text_key="labelExplanation",
            )
        )
        units.extend(_breakdown_units(scorecard))
        units.append(_disclaimer_unit(scorecard))

    elif variant is PresentationVariant.EXPLAINED:
        units.append(_plain_language_unit())
        units.extend(_breakdown_units(scorecard))
        units.extend(_metric_tile_units(scorecard))
        units.append(_freshness_unit(scorecard))
        units.append(_uncertainty_unit(dq))
        units.append(_disclaimer_unit(scorecard))

    elif variant is PresentationVariant.AS_IS:
        # What the current product actually renders: rich card + plain language +
        # breakdown + metric tiles + disclaimer — but NO explicit confidence and
        # NO freshness flag on the score (both verified absent in the audit).
        units.append(_plain_language_unit())
        units.extend(_breakdown_units(scorecard))
        units.extend(_metric_tile_units(scorecard))
        if PRODUCT_SURFACES_FRESHNESS_ON_SCORE:  # currently False
            units.append(_freshness_unit(scorecard))
        if PRODUCT_SURFACES_CONFIDENCE:          # currently False
            units.append(_uncertainty_unit(dq))
        units.append(_disclaimer_unit(scorecard))

    if include_untranslated:
        # Audited English-only content that renders untranslated even in zh mode:
        # the stress-scenario narrative and the ML SHAP feature names.
        units.append(
            ContentUnit(
                concept=Concept.STRESS_TEST, modality=Modality.TEXT, salience=0.45,
                text_key="stressTest.narrative", english_only=True,
                value=scorecard.get("stress_test"),
            )
        )
        units.append(
            ContentUnit(
                concept=Concept.SHAP_EXPLANATION, modality=Modality.TEXT, salience=0.35,
                english_only=True, value=scorecard.get("ml_drawdown_explanation"),
            )
        )
    if include_chart:
        units.append(
            ContentUnit(
                concept=Concept.HISTORICAL_OUTCOMES, modality=Modality.CHART, salience=0.5,
                sr_accessible=charts_have_alt_text, text_key="chart.risk",
            )
        )
    if data_warning:
        units.append(
            ContentUnit(
                concept=Concept.DATA_QUALITY_WARNING, modality=Modality.WARNING, salience=0.55,
                warning_strength=0.7, carries_uncertainty=True, text_key="card.dataWarning",
                value=dq.intrinsic_confidence().value,
            )
        )
    if model_degraded:
        units.append(
            ContentUnit(
                concept=Concept.MODEL_DEGRADED, modality=Modality.WARNING, salience=0.5,
                warning_strength=0.6, text_key="card.modelDegraded",
                value="degraded",
            )
        )

    # A monochrome / colour-deficient viewer loses meaning only from color_only
    # units; the framework marks (does not delete) them so interpret.py can model
    # the loss. Nothing to strip here for the current non-color_only design.
    return RenderedView(
        variant=variant,
        language=language,
        color_vision=color_vision,
        units=tuple(units),
        ticker=scorecard.get("ticker"),
        scenario_id=scenario_id,
        meta={
            "intrinsic_confidence": dq.intrinsic_confidence().value,
            "model_degraded": model_degraded,
            "data_warning_shown": data_warning,
        },
    )


def render_community_view(
    *,
    claimed_sentiment: float,
    is_misinformation: bool,
    upvotes: int,
    language: Language,
    with_disclaimer: bool = True,
    color_vision: ColorVisionMode = ColorVisionMode.NORMAL,
    scenario_id: str = "community",
) -> RenderedView:
    """A community post as content: an opinion cue plus the (real) separation label.

    The current product renders a permanent, non-dismissible ``CommunityDisclaimer``
    that labels posts as opinion, not model output; ``with_disclaimer=False`` models
    a hypothetical UI that drops it, to measure the separation's value.
    """
    salience = min(0.9, 0.45 + 0.02 * min(upvotes, 25))  # popularity raises prominence
    units: list[ContentUnit] = [
        ContentUnit(
            concept=Concept.COMMUNITY_OPINION, modality=Modality.TEXT, salience=salience,
            value={
                "claimed_sentiment": claimed_sentiment,
                "is_misinformation": is_misinformation,
                "upvotes": upvotes,
            },
        )
    ]
    if with_disclaimer:
        units.append(
            ContentUnit(
                concept=Concept.DISCLAIMER, modality=Modality.TEXT, salience=0.4,
                warning_strength=0.5, text_key="community.disclaimer",
            )
        )
    return RenderedView(
        variant=PresentationVariant.AS_IS,
        language=language,
        color_vision=color_vision,
        units=tuple(units),
        scenario_id=scenario_id,
        meta={"is_misinformation": is_misinformation, "upvotes": upvotes},
    )


def render_portfolio_view(
    portfolio_risk: Any,
    *,
    language: Language,
    color_vision: ColorVisionMode = ColorVisionMode.NORMAL,
    show_attribution: bool = True,
    scenario_id: str = "unspecified",
) -> RenderedView:
    """Project a real ``PortfolioRisk`` into what a concentration view presents.

    ``show_attribution=False`` reproduces a generic "high risk" warning (the
    Scenario-B control); ``True`` adds component-VaR contribution, HHI /
    effective-N concentration and the top contributor (the treatment).
    """
    top_ticker = None
    contrib = getattr(portfolio_risk, "risk_contribution_pct", {}) or {}
    if contrib:
        top_ticker = max(contrib, key=contrib.get)
    units: list[ContentUnit] = [
        ContentUnit(
            concept=Concept.COMPOSITE_SCORE,
            modality=Modality.NUMBER,
            salience=0.9,
            value=round(float(portfolio_risk.volatility), 4),
            text_key="portfolio.risk",
        )
    ]
    if show_attribution:
        units.append(
            ContentUnit(
                concept=Concept.CONCENTRATION,
                modality=Modality.NUMBER,
                salience=0.6,
                text_key="portfolio.concentration",
                value={
                    "hhi": portfolio_risk.concentration_hhi,
                    "effective_n": portfolio_risk.effective_n,
                },
            )
        )
        units.append(
            ContentUnit(
                concept=Concept.RISK_CONTRIBUTION,
                modality=Modality.TEXT,
                salience=0.55,
                text_key="portfolio.topContributor",
                value={"top": top_ticker, "contribution_pct": contrib},
            )
        )
    else:
        units.append(
            ContentUnit(
                concept=Concept.RISK_LABEL,
                modality=Modality.LABEL,
                salience=0.7,
                warning_strength=0.3,
                text_key="portfolio.genericHighRisk",
                value="HIGH",
            )
        )
    units.append(
        ContentUnit(
            concept=Concept.DISCLAIMER,
            modality=Modality.TEXT,
            salience=0.25,
            warning_strength=0.5,
            text_key="footer.disclaimerBody1",
        )
    )
    return RenderedView(
        variant=(
            PresentationVariant.EXPLAINED if show_attribution else PresentationVariant.SCORE_ONLY
        ),
        language=language,
        color_vision=color_vision,
        units=tuple(units),
        ticker=None,
        scenario_id=scenario_id,
        meta={"top_contributor": top_ticker, "effective_n": portfolio_risk.effective_n},
    )
