"""Phase 3 safety scenarios: crash, stale data, model drift, misinformation, stress.

Each runner reuses the Phase 1/2 interpretation and decision machinery but places
the user in a hazardous context and toggles the specific safeguard under test, so
the effect of that safeguard is what the events measure. The scenarios treat
panic selling, over-reliance, community-override of evidence, and taking action on
degraded data as HARMS to count — never as engagement to maximise.

All runners are deterministic (seeded) and offline (synthetic scorecards / data
quality), and none ever produces personalised buy/sell advice.
"""

from __future__ import annotations

from typing import Optional

from .decide import DecisionContext, decide_action
from .distributions import derive_generator
from .events import EventLog, EventType, IntendedAction
from .interpret import UserState, interpret_view
from .presentation import (
    Concept,
    PresentationVariant,
    render_community_view,
    render_stock_view,
)
from .profiles import UserProfile
from .sut import DataQuality, synthetic_scorecard
from .tasks import _common_context, _hash_user, _warning_taken_in


def run_market_crash(
    profile: UserProfile,
    *,
    seed: int,
    config_hash: str,
    crisis_safe: bool = False,
    crash_score: float = 88.0,
    scenario_id: str = "scenarioC_market_crash",
    log: Optional[EventLog] = None,
) -> EventLog:
    """A stressed user sees a high, red score. Does the crisis-safe UI curb panic?"""
    log = log or EventLog()
    rng = derive_generator(seed, _hash_user(profile.user_id), 11)
    variant = PresentationVariant.CRISIS_SAFE if crisis_safe else PresentationVariant.AS_IS
    ctx_fields = _common_context(
        profile, scenario_id=scenario_id, variant=variant.value, seed=seed, config_hash=config_hash
    )
    card = synthetic_scorecard("CRSH", risk_score=crash_score)
    view = render_stock_view(
        card, variant=variant, language=profile.language,
        color_vision=profile.color_vision_mode, scenario_id=scenario_id,
    )
    state = UserState.initial(profile)
    interp = interpret_view(profile, state, view, rng)
    # Crisis-safe design curbs panic by DAMPENING felt urgency (non-alarmist
    # framing, delayed-action nudge, muted colour) rather than only by adding
    # caveats a panicked user skips — so it lowers market_stress and the bearish
    # community pull, not just warning strength.
    if crisis_safe:
        felt_stress = profile.current_market_stress * 0.5
        community = -0.2
    else:
        felt_stress = max(0.85, profile.current_market_stress)
        community = -0.5
    ctx = DecisionContext(
        score=crash_score, market_stress=felt_stress,
        community_sentiment=community, warning_strength=_warning_taken_in(interp),
        score_salience=0.6 if crisis_safe else 0.95,
    )
    decision = decide_action(profile, interp, ctx, rng)
    harmful_exit = decision.intended_action in {
        IntendedAction.SELL_ALL, IntendedAction.REDUCE_POSITION,
    }
    log.emit(
        EventType.USER_ACTION_INTENT_RECORDED, **ctx_fields, score=crash_score,
        action="crash_decision", intended_financial_action=decision.intended_action.value,
        misconception_state=sorted(m.value for m in interp.misconceptions_after),
        detail={"panic_sell": decision.panic_sell, "harmful_exit": harmful_exit,
                "reason": decision.reason},
    )
    if decision.intended_action is IntendedAction.SEEK_PROFESSIONAL_ADVICE:
        log.emit(EventType.PROFESSIONAL_HELP_PROMPT_VIEWED, **ctx_fields)
    log.emit(
        EventType.SIMULATION_COMPLETED, **ctx_fields, score=crash_score,
        intended_financial_action=decision.intended_action.value,
        detail={"panic_sell": decision.panic_sell, "harmful_exit": harmful_exit},
    )
    return log


def run_data_quality_failure(
    profile: UserProfile,
    *,
    seed: int,
    config_hash: str,
    surface_warning: bool = False,
    scenario_id: str = "scenarioD_data_quality",
    log: Optional[EventLog] = None,
) -> EventLog:
    """Stale/sparse/illiquid data. Does surfacing a warning prevent false confidence?"""
    log = log or EventLog()
    rng = derive_generator(seed, _hash_user(profile.user_id), 12)
    variant = "warning_surfaced" if surface_warning else "as_is_no_flag"
    ctx_fields = _common_context(
        profile, scenario_id=scenario_id, variant=variant, seed=seed, config_hash=config_hash
    )
    dq = DataQuality(history_days=28, staleness_days=14, illiquid=True)
    card = synthetic_scorecard("SPRS", risk_score=52.0)
    view = render_stock_view(
        card, variant=PresentationVariant.AS_IS, language=profile.language,
        color_vision=profile.color_vision_mode, data_quality=dq,
        data_warning=surface_warning, scenario_id=scenario_id,
    )
    state = UserState.initial(profile)
    interp = interpret_view(profile, state, view, rng)
    if Concept.DATA_QUALITY_WARNING in interp.noticed:
        log.emit(EventType.DATA_WARNING_VIEWED, **ctx_fields,
                 detail={"understood": Concept.DATA_QUALITY_WARNING in interp.understood})
    for misc in sorted(interp.induced, key=lambda m: m.value):
        log.emit(EventType.MISCONCEPTION_DETECTED, **ctx_fields,
                 detail={"misconception": misc.value, "origin": "induced"})

    ctx = DecisionContext(score=52.0, warning_strength=_warning_taken_in(interp))
    decision = decide_action(profile, interp, ctx, rng)
    # Correct response to bad data: don't act on it alone (hold / research / advice).
    correct_no_action = decision.intended_action in {
        IntendedAction.HOLD, IntendedAction.RESEARCH_MORE,
        IntendedAction.SEEK_PROFESSIONAL_ADVICE, IntendedAction.NONE,
    }
    took_at_face_value = (
        Concept.UNCERTAINTY not in interp.understood
        and Concept.DATA_QUALITY_WARNING not in interp.understood
    )
    log.emit(
        EventType.USER_ACTION_INTENT_RECORDED, **ctx_fields, score=52.0,
        confidence_status=dq.intrinsic_confidence().value,
        action="data_quality_decision",
        intended_financial_action=decision.intended_action.value,
        misconception_state=sorted(m.value for m in interp.misconceptions_after),
        detail={
            "intrinsic_confidence": dq.intrinsic_confidence().value,
            "warning_surfaced": surface_warning,
            "correct_no_action": correct_no_action,
            "took_score_at_face_value": took_at_face_value,
        },
    )
    log.emit(EventType.SIMULATION_COMPLETED, **ctx_fields,
             detail={"correct_no_action": correct_no_action})
    return log


def run_model_degradation(
    profile: UserProfile,
    *,
    seed: int,
    config_hash: str,
    disclose: bool = False,
    scenario_id: str = "scenarioE_model_drift",
    log: Optional[EventLog] = None,
) -> EventLog:
    """A demoted/degraded model. Does disclosing it calibrate trust vs confuse?"""
    log = log or EventLog()
    rng = derive_generator(seed, _hash_user(profile.user_id), 13)
    variant = "degradation_disclosed" if disclose else "silent_degradation"
    ctx_fields = _common_context(
        profile, scenario_id=scenario_id, variant=variant, seed=seed, config_hash=config_hash
    )
    card = synthetic_scorecard("DRFT", risk_score=61.0)
    view = render_stock_view(
        card, variant=PresentationVariant.AS_IS, language=profile.language,
        color_vision=profile.color_vision_mode, model_degraded=disclose,
        scenario_id=scenario_id,
    )
    state = UserState.initial(profile)
    interp = interpret_view(profile, state, view, rng)
    noticed_degraded = Concept.MODEL_DEGRADED in interp.noticed
    understood_degraded = Concept.MODEL_DEGRADED in interp.understood
    if noticed_degraded:
        log.emit(EventType.MODEL_CARD_VIEWED, **ctx_fields,
                 detail={"understood_degraded": understood_degraded})

    # Trust calibration. Appropriate = took in the disclosure and grew cautious.
    # Confused = saw the "degraded" flag but couldn't make sense of it (thinks the
    # product is broken) — only really bites low-literacy users. Not noticing the
    # flag (or no disclosure at all) leaves the user unaware, over-trusting if they
    # lean on automation.
    if disclose and understood_degraded:
        trust_state = "appropriate_caution"
    elif disclose and noticed_degraded and not understood_degraded:
        trust_state = "confused" if profile.financial_literacy < 0.4 else "unaffected"
    else:
        trust_state = "unaware_overtrust" if profile.trust_in_automation > 0.5 else "unaware"

    log.emit(
        EventType.USER_ACTION_INTENT_RECORDED, **ctx_fields, score=61.0,
        action="model_degradation_response",
        comprehension_state={"trust_state": trust_state},
        detail={"disclosed": disclose, "understood_degraded": understood_degraded,
                "trust_state": trust_state},
    )
    log.emit(EventType.SIMULATION_COMPLETED, **ctx_fields, detail={"trust_state": trust_state})
    return log


def run_community_misinformation(
    profile: UserProfile,
    *,
    seed: int,
    config_hash: str,
    with_disclaimer: bool = True,
    upvotes: int = 20,
    claimed_sentiment: float = 0.8,
    is_misinformation: bool = True,
    model_score: float = 78.0,
    scenario_id: str = "scenarioF_community_misinformation",
    log: Optional[EventLog] = None,
) -> EventLog:
    """A hyped, highly-upvoted misleading post vs a HIGH model score. Who wins?"""
    log = log or EventLog()
    rng = derive_generator(seed, _hash_user(profile.user_id), 14)
    variant = "with_separation" if with_disclaimer else "no_separation"
    ctx_fields = _common_context(
        profile, scenario_id=scenario_id, variant=variant, seed=seed, config_hash=config_hash
    )
    post_view = render_community_view(
        claimed_sentiment=claimed_sentiment, is_misinformation=is_misinformation,
        upvotes=upvotes, language=profile.language, with_disclaimer=with_disclaimer,
        scenario_id=scenario_id,
    )
    state = UserState.initial(profile)
    interp_post = interpret_view(profile, state, post_view, rng)
    log.emit(EventType.COMMUNITY_POST_VIEWED, **ctx_fields,
             detail={"upvotes": upvotes, "is_misinformation": is_misinformation})

    separation_understood = Concept.DISCLAIMER in interp_post.understood
    susceptibility = profile.social_proof_sensitivity * profile.trust_in_community
    adopts = rng.random() < susceptibility * (1.0 - 0.6 * (1.0 if separation_understood else 0.0))
    # Reporting misinformation: needs attention + literacy, helped by understanding
    # the separation label.
    p_report = profile.disclosure_attention * profile.financial_literacy * (
        1.2 if separation_understood else 0.7
    )
    reported = is_misinformation and rng.random() < min(1.0, p_report)
    if reported:
        log.emit(EventType.COMMUNITY_POST_REPORTED, **ctx_fields,
                 detail={"reason": "misinformation"})

    # The stock decision: community pulls bullish; a HIGH model score says risky.
    effective_sentiment = claimed_sentiment if adopts else claimed_sentiment * 0.2
    card = synthetic_scorecard("HYPE", risk_score=model_score)
    stock_view = render_stock_view(
        card, variant=PresentationVariant.AS_IS, language=profile.language,
        color_vision=profile.color_vision_mode, scenario_id=scenario_id,
    )
    interp_stock = interpret_view(profile, state, stock_view, rng)
    ctx = DecisionContext(
        score=model_score, community_sentiment=effective_sentiment,
        warning_strength=_warning_taken_in(interp_stock),
    )
    decision = decide_action(profile, interp_stock, ctx, rng)
    # Community overrides evidence if the user leans to buy a HIGH-risk name after
    # adopting the hyped sentiment.
    community_override = adopts and decision.intended_action in {
        IntendedAction.BUY, IntendedAction.BUY_MORE,
    }
    log.emit(
        EventType.USER_ACTION_INTENT_RECORDED, **ctx_fields, score=model_score,
        action="community_influenced_decision",
        intended_financial_action=decision.intended_action.value,
        detail={
            "adopted_community_sentiment": adopts,
            "separation_understood": separation_understood,
            "community_override_of_evidence": community_override,
            "reported": reported,
        },
    )
    log.emit(EventType.SIMULATION_COMPLETED, **ctx_fields,
             detail={"community_override_of_evidence": community_override, "reported": reported})
    return log


def run_vulnerable_context(
    profile: UserProfile,
    *,
    seed: int,
    config_hash: str,
    reinforce_boundaries: bool = False,
    scenario_id: str = "scenarioJ_vulnerable_context",
    log: Optional[EventLog] = None,
) -> EventLog:
    """A financially-stressed, urgency-seeking user. Boundaries must hold; no advice."""
    log = log or EventLog()
    rng = derive_generator(seed, _hash_user(profile.user_id), 15)
    variant = "boundaries_reinforced" if reinforce_boundaries else "standard"
    ctx_fields = _common_context(
        profile, scenario_id=scenario_id, variant=variant, seed=seed, config_hash=config_hash
    )
    # Reinforced = crisis-safe presentation (adds professional-help + strong caveats).
    var = PresentationVariant.CRISIS_SAFE if reinforce_boundaries else PresentationVariant.AS_IS
    card = synthetic_scorecard("URGT", risk_score=64.0)
    view = render_stock_view(
        card, variant=var, language=profile.language,
        color_vision=profile.color_vision_mode, scenario_id=scenario_id,
    )
    state = UserState.initial(profile)
    interp = interpret_view(profile, state, view, rng)
    ctx = DecisionContext(
        score=64.0, market_stress=profile.current_market_stress,
        warning_strength=_warning_taken_in(interp),
        score_salience=0.6 if reinforce_boundaries else 0.9,
    )
    decision = decide_action(profile, interp, ctx, rng)
    sought_advice = decision.intended_action is IntendedAction.SEEK_PROFESSIONAL_ADVICE
    if sought_advice or Concept.PROFESSIONAL_HELP in interp.noticed:
        log.emit(EventType.PROFESSIONAL_HELP_PROMPT_VIEWED, **ctx_fields)
    log.emit(
        EventType.USER_ACTION_INTENT_RECORDED, **ctx_fields, score=64.0,
        action="vulnerable_context_decision",
        intended_financial_action=decision.intended_action.value,
        detail={
            "sought_professional_advice": sought_advice,
            "boundaries_reinforced": reinforce_boundaries,
            # Invariant: never a personalised trade recommendation from the system.
            "system_gave_personalized_advice": False,
        },
    )
    log.emit(EventType.SIMULATION_COMPLETED, **ctx_fields,
             detail={"sought_professional_advice": sought_advice})
    return log
