"""Simulated user tasks: realistic journeys, not random clicking.

Phase 1 implements Task 1 (analyse a single stock) end to end — profile ->
initial state -> rendered view -> interpretation -> action intent -> semantic
event stream. The remaining tasks from the framework's list (compare, portfolio,
VaR interpretation, stress, SHAP, data-quality response, disclaimer
comprehension, ...) plug into the same ``_common_context`` + ``EventLog`` scaffold
in later phases, so their events are schema-identical and aggregate together.
"""

from __future__ import annotations

from typing import Any, Optional

from .decide import DecisionContext, decide_action
from .distributions import derive_generator
from .events import (
    ConfidenceStatus,
    EventLog,
    EventType,
    IntendedAction,
)
from .interpret import UserState, interpret_view
from .presentation import Concept, PresentationVariant, RenderedView, render_stock_view
from .profiles import UserProfile
from .sut import (
    PRODUCT_SURFACES_CONFIDENCE,
    DataQuality,
    load_scorecard,
    scorecard_data_timestamp,
)


def _common_context(
    profile: UserProfile,
    *,
    scenario_id: str,
    variant: str,
    seed: int,
    config_hash: str,
) -> dict[str, Any]:
    """The context fields every event in a run must carry (for later slicing)."""
    accessibility = (
        "+".join(sorted(n.value for n in profile.accessibility_needs)) or "none"
    )
    return {
        "simulated_user_id": profile.user_id,
        "archetype": profile.archetype.value,
        "language": profile.language.value,
        "scenario_id": scenario_id,
        "experiment_variant": variant,
        "simulation_seed": seed,
        "config_hash": config_hash,
        "accessibility_mode": accessibility,
    }


# Which noticed concept maps to which "viewed" event, so the event stream reflects
# what the user actually took in rather than merely what was on screen.
_VIEW_EVENTS: list[tuple[Concept, EventType]] = [
    (Concept.LABEL_MEANING, EventType.METHODOLOGY_VIEWED),
    (Concept.VOLATILITY, EventType.COMPONENT_VIEWED),
    (Concept.TAIL, EventType.COMPONENT_VIEWED),
    (Concept.DRAWDOWN, EventType.COMPONENT_VIEWED),
    (Concept.SENSITIVITY, EventType.COMPONENT_VIEWED),
    (Concept.LIQUIDITY, EventType.COMPONENT_VIEWED),
    (Concept.UNCERTAINTY, EventType.UNCERTAINTY_VIEWED),
    (Concept.DATA_QUALITY_WARNING, EventType.DATA_WARNING_VIEWED),
    (Concept.DISCLAIMER, EventType.DISCLAIMER_VIEWED),
    (Concept.STRESS_TEST, EventType.STRESS_TEST_VIEWED),
]


def run_single_stock_analysis(
    profile: UserProfile,
    *,
    seed: int,
    config_hash: str,
    scenario_id: str = "task1_single_stock",
    variant: PresentationVariant = PresentationVariant.AS_IS,
    ticker: str = "TSLA",
    scorecard: Optional[dict[str, Any]] = None,
    data_quality: Optional[DataQuality] = None,
    community_sentiment: float = 0.0,
    log: Optional[EventLog] = None,
) -> EventLog:
    """One user analyses one stock; returns the emitted event stream.

    ``variant`` selects the presentation (AS_IS reproduces the current product;
    SCORE_ONLY/EXPLAINED are the Scenario-A arms). ``seed`` derives an
    independent per-user RNG so the run is reproducible and order-independent.
    """
    scorecard = scorecard if scorecard is not None else load_scorecard(ticker)
    dq = data_quality or DataQuality()
    log = log or EventLog()
    rng = derive_generator(seed, _hash_user(profile.user_id), 1)

    ctx_fields = _common_context(
        profile, scenario_id=scenario_id, variant=variant.value, seed=seed, config_hash=config_hash
    )
    score = float(scorecard["risk_score"])
    data_ts = scorecard_data_timestamp(scorecard)
    intrinsic = dq.intrinsic_confidence()
    # The product surfaces no confidence flag today; record the ground-truth
    # status for analysis but flag that the user was not shown it.
    shown_status = (
        intrinsic.value if PRODUCT_SURFACES_CONFIDENCE else ConfidenceStatus.UNKNOWN.value
    )

    log.emit(
        EventType.USER_SIMULATION_STARTED,
        **ctx_fields,
        ticker=ticker,
        data_timestamp=data_ts,
        misconception_state=sorted(m.value for m in profile.initial_misconceptions),
    )

    view: RenderedView = render_stock_view(
        scorecard,
        variant=variant,
        language=profile.language,
        color_vision=profile.color_vision_mode,
        data_quality=dq,
        scenario_id=scenario_id,
    )

    state = UserState.initial(profile)
    interp = interpret_view(profile, state, view, rng)

    log.emit(
        EventType.SCORE_VIEWED,
        **ctx_fields,
        ticker=ticker,
        score=score,
        confidence_status=shown_status,
        data_timestamp=data_ts,
        detail={
            "intrinsic_confidence": intrinsic.value,
            "product_surfaced_confidence": PRODUCT_SURFACES_CONFIDENCE,
            "noticed_score": Concept.COMPOSITE_SCORE in interp.noticed,
        },
    )

    emitted: set[Concept] = set()
    for concept, event_type in _VIEW_EVENTS:
        if concept in interp.noticed and concept not in emitted:
            emitted.add(concept)
            log.emit(
                event_type,
                **ctx_fields,
                ticker=ticker,
                score=score,
                detail={"understood": concept in interp.understood},
            )

    for misc in sorted(interp.corrected, key=lambda m: m.value):
        log.emit(
            EventType.MISCONCEPTION_CORRECTED,
            **ctx_fields,
            ticker=ticker,
            detail={"misconception": misc.value},
        )
    for misc in sorted(interp.induced, key=lambda m: m.value):
        log.emit(
            EventType.MISCONCEPTION_DETECTED,
            **ctx_fields,
            ticker=ticker,
            detail={"misconception": misc.value, "origin": "induced"},
        )

    ctx = DecisionContext(
        score=score,
        community_sentiment=community_sentiment,
        warning_strength=_warning_taken_in(interp),
        market_stress=profile.current_market_stress,
    )
    decision = decide_action(profile, interp, ctx, rng)

    log.emit(
        EventType.USER_ACTION_INTENT_RECORDED,
        **ctx_fields,
        ticker=ticker,
        score=score,
        confidence_status=shown_status,
        action="single_stock_decision",
        intended_financial_action=decision.intended_action.value,
        comprehension_state={
            "actual_understanding": round(interp.actual_understanding, 3),
            "confidence_after": round(interp.confidence_after, 3),
            "calibration_gap": round(interp.calibration_gap, 3),
        },
        misconception_state=sorted(m.value for m in interp.misconceptions_after),
        detail={
            "reason": decision.reason,
            "perceived_risk": decision.perceived_risk,
            "panic_sell": decision.panic_sell,
            "overconfident_buy": decision.overconfident_buy,
            "treats_score_as_advice": decision.treats_score_as_advice,
        },
    )

    if interp.overrelied:
        log.emit(
            EventType.USER_OVERRELIANCE_DETECTED,
            **ctx_fields,
            ticker=ticker,
            score=score,
            detail={
                "confidence_after": round(interp.confidence_after, 3),
                "actual_understanding": round(interp.actual_understanding, 3),
            },
        )

    if decision.intended_action is IntendedAction.SEEK_PROFESSIONAL_ADVICE:
        log.emit(EventType.PROFESSIONAL_HELP_PROMPT_VIEWED, **ctx_fields, ticker=ticker)

    log.emit(
        EventType.SIMULATION_COMPLETED,
        **ctx_fields,
        ticker=ticker,
        score=score,
        intended_financial_action=decision.intended_action.value,
        misconception_state=sorted(m.value for m in interp.misconceptions_after),
    )
    return log


def run_comprehension_check(
    profile: UserProfile,
    *,
    seed: int,
    config_hash: str,
    scenario_id: str = "task18_comprehension",
    variant: str = "as_is",
    state: Optional[UserState] = None,
    log: Optional[EventLog] = None,
) -> tuple[EventLog, "Any"]:
    """Ask the comprehension battery; emit one answered event per question.

    ``state`` may carry understanding accrued earlier in a session (e.g. after
    viewing an explained score), so the same battery can measure whether the
    explanation improved comprehension — the core Scenario-A/I outcome.
    """
    from .comprehension import run_comprehension_battery

    log = log or EventLog()
    state = state if state is not None else UserState.initial(profile)
    rng = derive_generator(seed, _hash_user(profile.user_id), 2)
    ctx_fields = _common_context(
        profile, scenario_id=scenario_id, variant=variant, seed=seed, config_hash=config_hash
    )
    outcome = run_comprehension_battery(profile, state, rng)
    for r in outcome.results:
        log.emit(
            EventType.COMPREHENSION_ANSWERED,
            **ctx_fields,
            detail={
                "qid": r.qid,
                "concept": r.concept,
                "correct": r.correct,
                "confidence": r.confidence,
            },
        )
        if r.misconception_revealed:
            log.emit(
                EventType.MISCONCEPTION_DETECTED,
                **ctx_fields,
                detail={"misconception": r.misconception_revealed, "origin": "comprehension"},
            )
    log.emit(
        EventType.SIMULATION_COMPLETED,
        **ctx_fields,
        comprehension_state={
            "score": round(outcome.score, 3),
            "n_correct": outcome.n_correct,
            "n_total": outcome.n_total,
            "overconfident_wrong": outcome.overconfident_wrong,
        },
        misconception_state=sorted(m.value for m in state.misconceptions),
    )
    return log, outcome


def run_portfolio_concentration(
    profile: UserProfile,
    *,
    seed: int,
    config_hash: str,
    positions_spec: "list[tuple[str, float, float, float, str]]",
    show_attribution: bool = True,
    scenario_id: str = "task4_portfolio_concentration",
    log: Optional[EventLog] = None,
) -> EventLog:
    """Build a real portfolio, present it, and measure concentration recognition.

    ``show_attribution`` toggles the Scenario-B arms: generic high-risk warning
    (False) vs component-VaR + HHI attribution (True). Recognition requires the
    user to actually take in and understand the attribution — a generic warning
    only lands for the already-literate.
    """
    from .presentation import render_portfolio_view
    from .sut import build_portfolio_risk

    log = log or EventLog()
    rng = derive_generator(seed, _hash_user(profile.user_id), 3)
    variant = "attribution" if show_attribution else "generic_warning"
    ctx_fields = _common_context(
        profile, scenario_id=scenario_id, variant=variant, seed=seed, config_hash=config_hash
    )
    prisk = build_portfolio_risk(positions_spec, seed=seed)
    top = max(prisk.risk_contribution_pct, key=prisk.risk_contribution_pct.get)

    log.emit(
        EventType.PORTFOLIO_CREATED,
        **ctx_fields,
        detail={
            "n_positions": len(positions_spec),
            "effective_n": prisk.effective_n,
            "hhi": prisk.concentration_hhi,
            "true_top_contributor": top,
        },
    )

    view = render_portfolio_view(
        prisk,
        language=profile.language,
        color_vision=profile.color_vision_mode,
        show_attribution=show_attribution,
        scenario_id=scenario_id,
    )
    state = UserState.initial(profile)
    interp = interpret_view(profile, state, view, rng)

    if Concept.RISK_CONTRIBUTION in interp.noticed:
        log.emit(EventType.RISK_CONTRIBUTION_VIEWED, **ctx_fields,
                 detail={"understood": Concept.RISK_CONTRIBUTION in interp.understood})

    # Concentration recognised if the user understood the attribution, or (weaker)
    # understood a generic warning while being financially literate.
    recognised = (
        Concept.RISK_CONTRIBUTION in interp.understood
        or Concept.CONCENTRATION in interp.understood
    )
    if not show_attribution:
        recognised = Concept.RISK_LABEL in interp.understood and profile.financial_literacy > 0.6

    for misc in sorted(interp.induced, key=lambda m: m.value):
        log.emit(EventType.MISCONCEPTION_DETECTED, **ctx_fields,
                 detail={"misconception": misc.value, "origin": "induced"})

    ctx = DecisionContext(
        score=min(100.0, prisk.volatility * 100),
        warning_strength=_warning_taken_in(interp),
        market_stress=profile.current_market_stress,
    )
    decision = decide_action(profile, interp, ctx, rng)
    log.emit(
        EventType.USER_ACTION_INTENT_RECORDED,
        **ctx_fields,
        action="portfolio_decision",
        intended_financial_action=decision.intended_action.value,
        comprehension_state={"actual_understanding": round(interp.actual_understanding, 3)},
        misconception_state=sorted(m.value for m in interp.misconceptions_after),
        detail={
            "concentration_recognised": recognised,
            "true_top_contributor": top,
            "reason": decision.reason,
        },
    )
    log.emit(EventType.SIMULATION_COMPLETED, **ctx_fields,
             detail={"concentration_recognised": recognised})
    return log


def run_compare(
    profile: UserProfile,
    *,
    seed: int,
    config_hash: str,
    stock_a: "tuple[str, float]",
    stock_b: "tuple[str, float]",
    scenario_id: str = "task2_compare",
    log: Optional[EventLog] = None,
) -> EventLog:
    """Compare two stocks at different risk levels; did the user rank them right?"""
    from .sut import synthetic_scorecard

    log = log or EventLog()
    rng = derive_generator(seed, _hash_user(profile.user_id), 4)
    ctx_fields = _common_context(
        profile, scenario_id=scenario_id, variant="compare", seed=seed, config_hash=config_hash
    )
    (ta, sa), (tb, sb) = stock_a, stock_b
    card_a = synthetic_scorecard(ta, risk_score=sa)
    card_b = synthetic_scorecard(tb, risk_score=sb)

    understood = 0
    for card in (card_a, card_b):
        view = render_stock_view(
            card, variant=PresentationVariant.AS_IS, language=profile.language,
            color_vision=profile.color_vision_mode, scenario_id=scenario_id,
        )
        interp = interpret_view(profile, UserState.initial(profile), view, rng)
        if Concept.RISK_LABEL in interp.understood or Concept.COMPOSITE_SCORE in interp.understood:
            understood += 1

    # Correct ranking needs both cards' risk levels understood; else a guess.
    if understood == 2:
        correct = (sa > sb) == (card_a["risk_score"] > card_b["risk_score"])
    else:
        correct = bool(rng.random() < 0.5)

    log.emit(
        EventType.SIMULATION_COMPLETED,
        **ctx_fields,
        detail={
            "riskier_true": ta if sa > sb else tb,
            "ranked_correctly": correct,
            "both_understood": understood == 2,
        },
    )
    return log


def _warning_taken_in(interp: "Any") -> float:
    """How much caution the user actually absorbed (understood, not just shown)."""
    strength = 0.0
    if Concept.DISCLAIMER in interp.understood:
        strength += 0.5
    if (
        Concept.UNCERTAINTY in interp.understood
        or Concept.DATA_QUALITY_WARNING in interp.understood
    ):
        strength += 0.5
    return min(1.0, strength)


def _hash_user(user_id: str) -> int:
    """A small stable integer from a user id, for RNG stream derivation."""
    return int.from_bytes(user_id.encode("utf-8"), "little", signed=False) % (2**31)
