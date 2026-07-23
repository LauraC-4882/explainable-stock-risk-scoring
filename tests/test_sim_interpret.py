"""Phase 1: interpretation, misconception dynamics, and action-intent logic."""

from __future__ import annotations

from dataclasses import replace

from stock_risk.simulation.decide import DecisionContext, decide_action
from stock_risk.simulation.distributions import derive_generator
from stock_risk.simulation.events import IntendedAction
from stock_risk.simulation.interpret import (
    UserState,
    interpret_view,
    notice_prob,
    understand_prob,
)
from stock_risk.simulation.presentation import (
    Concept,
    ContentUnit,
    Modality,
    PresentationVariant,
    render_stock_view,
)
from stock_risk.simulation.profiles import (
    Archetype,
    ColorVisionMode,
    Misconception,
    generate_user,
)
from stock_risk.simulation.sut import DataQuality, load_scorecard


def _novice():
    return generate_user(Archetype.FIRST_TIME_RETAIL, seed=1, index=0)


def _pro():
    return generate_user(Archetype.EXPERIENCED_INVESTOR, seed=1, index=0)


def test_higher_ability_understands_harder_concepts():
    var_unit = ContentUnit(Concept.VAR, Modality.NUMBER, salience=0.4)
    assert understand_prob(_pro(), var_unit) > understand_prob(_novice(), var_unit)


def test_color_only_unit_is_lost_to_color_deficient_user():
    unit = ContentUnit(Concept.RISK_COLOR, Modality.COLOR, salience=0.9, color_only=True)
    normal = replace(_novice(), color_vision_mode=ColorVisionMode.NORMAL)
    deutan = replace(_novice(), color_vision_mode=ColorVisionMode.DEUTERANOPIA)
    assert notice_prob(normal, unit) > 0.3
    assert notice_prob(deutan, unit) < 0.05


def test_low_data_confidence_without_a_flag_can_induce_ignore_quality():
    # AS_IS shows no confidence cue; with genuinely low-quality data a low-
    # disclosure user forms the "ignores data quality" misconception.
    profile = replace(
        _novice(),
        disclosure_attention=0.1,
        initial_misconceptions=frozenset(),
        probability_comprehension=0.2,
    )
    scorecard = load_scorecard("TSLA")
    view = render_stock_view(
        scorecard,
        variant=PresentationVariant.AS_IS,
        language=profile.language,
        data_quality=DataQuality(history_days=25, staleness_days=15, illiquid=True),
    )
    induced_any = False
    for i in range(40):
        state = UserState.initial(profile)
        res = interpret_view(profile, state, view, derive_generator(7, i))
        if Misconception.IGNORES_DATA_QUALITY in res.induced:
            induced_any = True
            break
    assert induced_any


def test_explained_variant_can_correct_a_probability_misconception():
    # A reasonably literate user who takes in the plain-language meaning should
    # sometimes shed the score-as-probability misconception under EXPLAINED.
    profile = replace(
        _pro(),
        initial_misconceptions=frozenset({Misconception.SCORE_IS_PROBABILITY}),
        disclosure_attention=0.9,
    )
    scorecard = load_scorecard("TSLA")
    view = render_stock_view(
        scorecard, variant=PresentationVariant.EXPLAINED, language=profile.language
    )
    corrected_any = False
    for i in range(40):
        state = UserState.initial(profile)
        res = interpret_view(profile, state, view, derive_generator(3, i))
        if Misconception.SCORE_IS_PROBABILITY in res.corrected:
            corrected_any = True
            break
    assert corrected_any


def test_score_only_leaves_probability_misconception_uncorrected():
    # No plain-language / disclaimer unit is shown, so it can never be corrected.
    profile = replace(
        _pro(), initial_misconceptions=frozenset({Misconception.SCORE_IS_PROBABILITY})
    )
    scorecard = load_scorecard("TSLA")
    view = render_stock_view(
        scorecard, variant=PresentationVariant.SCORE_ONLY, language=profile.language
    )
    for i in range(30):
        state = UserState.initial(profile)
        res = interpret_view(profile, state, view, derive_generator(4, i))
        assert Misconception.SCORE_IS_PROBABILITY not in res.corrected
        assert Misconception.SCORE_IS_PROBABILITY in res.misconceptions_after


def test_interpretation_is_deterministic_under_same_seed():
    profile = _novice()
    scorecard = load_scorecard("TSLA")
    view = render_stock_view(
        scorecard, variant=PresentationVariant.AS_IS, language=profile.language
    )
    a = interpret_view(profile, UserState.initial(profile), view, derive_generator(9, 0))
    b = interpret_view(profile, UserState.initial(profile), view, derive_generator(9, 0))
    assert a.noticed == b.noticed and a.understood == b.understood
    assert a.misconceptions_after == b.misconceptions_after


def _fake_interpretation(perceived_understanding: float, misconceptions=frozenset()):
    from stock_risk.simulation.interpret import InterpretationResult

    return InterpretationResult(
        noticed=set(),
        understood=set(),
        misunderstood=set(),
        corrected=set(),
        induced=set(),
        misconceptions_after=misconceptions,
        confidence_before=0.5,
        confidence_after=0.5,
        actual_understanding=perceived_understanding,
        calibration_gap=0.0,
        overrelied=False,
    )


def test_panic_utility_rises_with_perceived_risk_and_panic():
    from stock_risk.simulation.decide import _perceived_risk  # noqa

    panicky = replace(
        _novice(), tendency_to_panic=0.95, loss_aversion=0.9, disclosure_attention=0.1
    )
    interp = _fake_interpretation(0.1)
    rng = derive_generator(1, 0)
    low = decide_action(panicky, interp, DecisionContext(score=15.0), rng)
    high = decide_action(
        panicky, interp, DecisionContext(score=95.0, market_stress=0.9), derive_generator(1, 0)
    )
    assert high.utilities["sell_all"] > low.utilities["sell_all"]


def test_warning_suppresses_panic_selling():
    panicky = replace(
        _novice(), tendency_to_panic=0.95, loss_aversion=0.9, disclosure_attention=0.9
    )
    interp = _fake_interpretation(0.2)
    no_warn = decide_action(
        panicky, interp, DecisionContext(score=90.0, market_stress=0.8, warning_strength=0.0),
        derive_generator(2, 0),
    )
    warned = decide_action(
        panicky, interp, DecisionContext(score=90.0, market_stress=0.8, warning_strength=1.0),
        derive_generator(2, 0),
    )
    assert warned.utilities["sell_all"] < no_warn.utilities["sell_all"]


def test_decision_never_emits_an_action_outside_the_intent_enum():
    profile = _novice()
    scorecard = load_scorecard("TSLA")
    view = render_stock_view(
        scorecard, variant=PresentationVariant.AS_IS, language=profile.language
    )
    for i in range(50):
        state = UserState.initial(profile)
        res = interpret_view(profile, state, view, derive_generator(5, i))
        decision = decide_action(profile, res, DecisionContext(score=66.5), derive_generator(6, i))
        assert isinstance(decision.intended_action, IntendedAction)
