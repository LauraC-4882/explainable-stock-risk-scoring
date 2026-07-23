"""Phase 4: accessibility and language-parity scenarios (G, H, keyboard/SR).

These runners measure whether the product's meaning survives a change of
language or ability. They lean on the perception properties added to
``ContentUnit`` — ``english_only`` (untranslated content), ``sr_accessible``
(chart text alternatives), ``keyboard_reachable`` — and on the colour-vision
handling already in the interpreter. The point is comprehension/completion
*disparities*, which feed the fairness analysis.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Optional

from .distributions import derive_generator
from .events import EventLog, EventType
from .interpret import UserState, interpret_view
from .presentation import Concept, PresentationVariant, render_stock_view
from .profiles import AccessibilityNeed, Language, UserProfile
from .sut import load_scorecard
from .tasks import _common_context, _hash_user

# Concepts that only ever render in English on the current product (audited).
_UNTRANSLATED = (Concept.STRESS_TEST, Concept.SHAP_EXPLANATION)


def run_language_parity(
    profile: UserProfile,
    *,
    seed: int,
    config_hash: str,
    scenario_id: str = "scenarioG_language_parity",
    log: Optional[EventLog] = None,
) -> EventLog:
    """Run the SAME disposition in English and Chinese; measure the parity gap.

    Understanding of the untranslated units (stress narrative, SHAP feature names)
    should drop for the Chinese rendering — the modelled consequence of the
    audited English-only strings.
    """
    log = log or EventLog()
    scorecard = load_scorecard("TSLA")
    per_lang: dict[str, dict] = {}
    for lang in (Language.EN, Language.ZH):
        p = replace(profile, language=lang)
        lang_stream = 0 if lang is Language.EN else 1
        rng = derive_generator(seed, _hash_user(profile.user_id), 20, lang_stream)
        view = render_stock_view(
            scorecard, variant=PresentationVariant.EXPLAINED, language=lang,
            include_untranslated=True, include_chart=True, scenario_id=scenario_id,
        )
        interp = interpret_view(p, UserState.initial(p), view, rng)
        untranslated_understood = sum(1 for c in _UNTRANSLATED if c in interp.understood)
        overall = interp.actual_understanding
        per_lang[lang.value] = {
            "overall_understanding": round(overall, 3),
            "untranslated_understood": untranslated_understood,
        }
        ctx = _common_context(
            p, scenario_id=scenario_id, variant=lang.value, seed=seed, config_hash=config_hash
        )
        log.emit(EventType.SCORE_VIEWED, **ctx, ticker="TSLA",
                 detail={"language": lang.value, **per_lang[lang.value]})

    gap = (
        per_lang["en"]["untranslated_understood"] - per_lang["zh"]["untranslated_understood"]
    )
    ctx = _common_context(
        profile, scenario_id=scenario_id, variant="parity", seed=seed, config_hash=config_hash
    )
    log.emit(
        EventType.SIMULATION_COMPLETED, **ctx,
        detail={
            "en": per_lang["en"], "zh": per_lang["zh"],
            "untranslated_parity_gap": gap,
            "parity_ok": gap == 0,
        },
    )
    return log


def run_accessibility_journey(
    profile: UserProfile,
    *,
    seed: int,
    config_hash: str,
    charts_have_alt_text: bool = False,
    scenario_id: str = "scenarioH_accessibility",
    log: Optional[EventLog] = None,
) -> EventLog:
    """AS_IS card + risk chart; can this user complete the core comprehension task?

    Completion needs the risk level understood AND — for a screen-reader user —
    the chart's information reachable (which requires alt text). ``charts_have_alt_text``
    is the treatment; the audited product ships without it.
    """
    log = log or EventLog()
    rng = derive_generator(seed, _hash_user(profile.user_id), 21)
    variant = "chart_alt" if charts_have_alt_text else "chart_no_alt"
    ctx = _common_context(
        profile, scenario_id=scenario_id, variant=variant, seed=seed, config_hash=config_hash
    )
    scorecard = load_scorecard("TSLA")
    view = render_stock_view(
        scorecard, variant=PresentationVariant.AS_IS, language=profile.language,
        color_vision=profile.color_vision_mode, include_chart=True,
        charts_have_alt_text=charts_have_alt_text, scenario_id=scenario_id,
    )
    state = UserState.initial(profile)
    interp = interpret_view(profile, state, view, rng)

    got_risk = (
        Concept.RISK_LABEL in interp.understood
        or Concept.COMPOSITE_SCORE in interp.understood
    )
    uses_sr = profile.has_accessibility_need(AccessibilityNeed.SCREEN_READER)
    chart_reached = Concept.HISTORICAL_OUTCOMES in interp.noticed
    # A screen-reader user "completes" only if they also reach the chart content.
    completed = got_risk and (chart_reached if uses_sr else True)
    missed_chart = uses_sr and not chart_reached

    log.emit(
        EventType.SIMULATION_COMPLETED, **ctx, ticker="TSLA",
        detail={
            "completed": completed,
            "uses_screen_reader": uses_sr,
            "missed_chart_content": missed_chart,
            "charts_have_alt_text": charts_have_alt_text,
        },
    )
    return log


def run_color_independent(
    profile: UserProfile,
    *,
    seed: int,
    config_hash: str,
    color_only_design: bool = False,
    scenario_id: str = "scenarioH_color",
    log: Optional[EventLog] = None,
) -> EventLog:
    """Does risk meaning survive without colour? Redundant labels (AS_IS) vs colour-only."""
    log = log or EventLog()
    rng = derive_generator(seed, _hash_user(profile.user_id), 22)
    variant = "color_only" if color_only_design else "redundant_labels"
    ctx = _common_context(
        profile, scenario_id=scenario_id, variant=variant, seed=seed, config_hash=config_hash
    )
    scorecard = load_scorecard("TSLA")
    view = render_stock_view(
        scorecard, variant=PresentationVariant.AS_IS, language=profile.language,
        color_vision=profile.color_vision_mode, color_only_design=color_only_design,
        scenario_id=scenario_id,
    )
    interp = interpret_view(profile, UserState.initial(profile), view, rng)
    got_risk = (
        Concept.RISK_LABEL in interp.understood
        or Concept.COMPOSITE_SCORE in interp.understood
    )
    log.emit(
        EventType.SIMULATION_COMPLETED, **ctx, ticker="TSLA",
        detail={
            "got_risk_meaning": got_risk,
            "color_vision_mode": profile.color_vision_mode.value,
            "color_only_design": color_only_design,
        },
    )
    return log
