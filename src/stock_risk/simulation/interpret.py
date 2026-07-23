"""Interpretation model: what a user notices, understands, and misbelieves.

Given a user, their evolving cognitive state, and a ``RenderedView``, this
models three separate things the framework needs to keep distinct (the required
"content shown / noticed / understood / misunderstood" chain):

1. **Noticing** — a function of a unit's salience and the user's attention (and,
   for warnings, their disclosure attention). A colour-only unit is effectively
   invisible to a colour-deficient user.
2. **Understanding** — a logistic function of the gap between the user's ability
   (a concept-weighted blend of financial literacy, numeracy and probability
   comprehension) and the concept's difficulty.
3. **Misbelief dynamics** — understanding the right concept can *correct* a
   misconception; failing to see a needed cue can *induce* one. The headline
   case: when the data behind a score is actually low-confidence but the product
   surfaces no confidence flag (a verified gap), a user with low disclosure
   attention forms the "ignores data quality" misconception — the harm is caused
   by the missing cue, exactly as in the real product.

Every stochastic step draws from a caller-owned seeded generator, so a run is
reproducible. All coefficients are transparent priors, tuned to be plausible and
directionally defensible — NOT measured human parameters (see the cannot-claim
list).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .presentation import Concept, ContentUnit, Modality, RenderedView
from .profiles import ColorVisionMode, Misconception, UserProfile

# Which misconceptions understanding a concept can correct.
CORRECTS: dict[Concept, frozenset[Misconception]] = {
    Concept.LABEL_MEANING: frozenset(
        {Misconception.SCORE_IS_PROBABILITY, Misconception.LOW_RISK_MEANS_SAFE}
    ),
    Concept.DISCLAIMER: frozenset(
        {
            Misconception.SCORE_IS_ADVICE,
            Misconception.SCORE_IS_PROBABILITY,
            Misconception.HISTORY_GUARANTEES_FUTURE,
        }
    ),
    Concept.UNCERTAINTY: frozenset({Misconception.IGNORES_DATA_QUALITY}),
    Concept.DATA_QUALITY_WARNING: frozenset({Misconception.IGNORES_DATA_QUALITY}),
    Concept.STRESS_TEST: frozenset(
        {Misconception.HISTORY_GUARANTEES_FUTURE, Misconception.LOW_VOL_CANNOT_FALL}
    ),
    Concept.HISTORICAL_OUTCOMES: frozenset(
        {Misconception.SCORE_IS_PROBABILITY, Misconception.HISTORY_GUARANTEES_FUTURE}
    ),
    Concept.CONCENTRATION: frozenset({Misconception.DIVERSIFIED_IF_MANY_NAMES}),
    Concept.RISK_CONTRIBUTION: frozenset({Misconception.DIVERSIFIED_IF_MANY_NAMES}),
    Concept.VAR: frozenset({Misconception.VAR_IS_MAX_LOSS}),
}

# Ability blend per concept: (financial_literacy, numeracy, probability_comprehension).
# Probability-flavoured concepts lean on probability comprehension; the rest lean
# on general financial literacy.
_PROB_CONCEPTS = {
    Concept.COMPOSITE_SCORE,
    Concept.VAR,
    Concept.CVAR,
    Concept.ML_DRAWDOWN_PROB,
    Concept.HISTORICAL_OUTCOMES,
    Concept.UNCERTAINTY,
}


def _ability_for(profile: UserProfile, concept: Concept) -> float:
    if concept in _PROB_CONCEPTS:
        w = (0.30, 0.25, 0.45)
    else:
        w = (0.60, 0.20, 0.20)
    return (
        w[0] * profile.financial_literacy
        + w[1] * profile.numeracy
        + w[2] * profile.probability_comprehension
    )


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def notice_prob(profile: UserProfile, unit: ContentUnit) -> float:
    """Probability the user attends to this unit at all."""
    from .profiles import AccessibilityNeed

    if (
        unit.color_only
        and unit.modality is Modality.COLOR
        and profile.color_vision_mode is not ColorVisionMode.NORMAL
    ):
        return 0.02  # meaning carried by colour alone is lost to this user
    if (
        not unit.sr_accessible
        and profile.has_accessibility_need(AccessibilityNeed.SCREEN_READER)
    ):
        return 0.02  # a chart with no text alternative is invisible to a screen reader
    if (
        not unit.keyboard_reachable
        and profile.has_accessibility_need(AccessibilityNeed.KEYBOARD_ONLY)
    ):
        return 0.05  # a mouse-only control (unfocusable modal) is largely unreachable
    attention = 0.4 + 0.6 * profile.attention_span
    p = unit.salience * attention
    if unit.warning_strength > 0:
        # Warnings/caveats are only seen by users who pay disclosure attention.
        p *= 0.35 + 0.65 * profile.disclosure_attention
    return _clamp(p)


def understand_prob(profile: UserProfile, unit: ContentUnit) -> float:
    """Probability the user correctly understands a unit they've noticed."""
    ability = _ability_for(profile, unit.concept)
    gap = ability - unit.difficulty()
    p = _sigmoid(6.0 * gap)  # steepness 6: above-difficulty ~ high, below ~ low
    if unit.english_only and profile.language.value == "zh":
        # Content that never translated: a Chinese-reading user gets far less from
        # it. This is the modelled consequence of the audited untranslated strings.
        p *= 0.35
    return _clamp(p)


def _correction_prob(profile: UserProfile) -> float:
    return _clamp(
        0.25 + 0.6 * (0.5 * profile.disclosure_attention + 0.5 * profile.probability_comprehension)
    )


@dataclass
class UserState:
    """Evolving cognitive state, distinct from the frozen disposition profile."""

    misconceptions: set[Misconception]
    understood_concepts: set[Concept] = field(default_factory=set)
    subjective_confidence: float = 0.5
    prior_actions: list[str] = field(default_factory=list)

    @classmethod
    def initial(cls, profile: UserProfile) -> "UserState":
        prior_conf = _clamp(
            0.3 + 0.4 * profile.trust_in_automation + 0.2 * (1.0 - profile.uncertainty_tolerance)
        )
        return cls(
            misconceptions=set(profile.initial_misconceptions),
            subjective_confidence=prior_conf,
        )


@dataclass
class InterpretationResult:
    noticed: set[Concept]
    understood: set[Concept]
    misunderstood: set[Concept]
    corrected: set[Misconception]
    induced: set[Misconception]
    misconceptions_after: frozenset[Misconception]
    confidence_before: float
    confidence_after: float
    actual_understanding: float     # fraction of noticed concepts truly understood
    calibration_gap: float          # subjective - actual (positive = over-trust)
    overrelied: bool

    def concept_understood(self, concept: Concept) -> bool:
        return concept in self.understood


def _induce_misconceptions(
    profile: UserProfile,
    view: RenderedView,
    noticed: set[Concept],
    understood: set[Concept],
    state: UserState,
    rng: np.random.Generator,
) -> set[Concept]:
    """Form new misconceptions from missing/misread cues. Returns induced set."""
    induced: set[Misconception] = set()

    # (a) Score-as-probability: saw the 0-100 number, didn't grasp its self-
    # relative meaning, and has weak probability sense.
    if (
        Concept.COMPOSITE_SCORE in noticed
        and Concept.LABEL_MEANING not in understood
        and Misconception.SCORE_IS_PROBABILITY not in state.misconceptions
    ):
        p = 0.7 * (1.0 - profile.probability_comprehension)
        if rng.random() < p:
            state.misconceptions.add(Misconception.SCORE_IS_PROBABILITY)
            induced.add(Misconception.SCORE_IS_PROBABILITY)

    # (b) Score-as-advice: saw a score, never took in the disclaimer, and is here
    # to make a decision.
    decision_goal = profile.current_goal.value in {"speculate", "urgent_decision", "check_holding"}
    if (
        Concept.COMPOSITE_SCORE in noticed
        and Concept.DISCLAIMER not in understood
        and decision_goal
        and Misconception.SCORE_IS_ADVICE not in state.misconceptions
    ):
        p = 0.5 * (1.0 - profile.disclosure_attention)
        if rng.random() < p:
            state.misconceptions.add(Misconception.SCORE_IS_ADVICE)
            induced.add(Misconception.SCORE_IS_ADVICE)

    # (c) Ignores data quality: the data is genuinely low-confidence, but no
    # confidence/warning cue was understood — the score is taken at face value.
    intrinsic = view.meta.get("intrinsic_confidence", "normal")
    quality_cue_understood = (
        Concept.UNCERTAINTY in understood or Concept.DATA_QUALITY_WARNING in understood
    )
    if (
        intrinsic in {"low", "suppressed"}
        and not quality_cue_understood
        and Concept.COMPOSITE_SCORE in noticed
        and Misconception.IGNORES_DATA_QUALITY not in state.misconceptions
    ):
        p = 0.6 + 0.3 * (1.0 - profile.disclosure_attention)
        if rng.random() < _clamp(p):
            state.misconceptions.add(Misconception.IGNORES_DATA_QUALITY)
            induced.add(Misconception.IGNORES_DATA_QUALITY)

    return induced


def interpret_view(
    profile: UserProfile,
    state: UserState,
    view: RenderedView,
    rng: np.random.Generator,
) -> InterpretationResult:
    """Run the notice -> understand -> (correct|induce) chain over one view."""
    confidence_before = state.subjective_confidence
    noticed: set[Concept] = set()
    understood: set[Concept] = set()
    misunderstood: set[Concept] = set()

    for unit in view.units:
        if rng.random() < notice_prob(profile, unit):
            noticed.add(unit.concept)
            if rng.random() < understand_prob(profile, unit):
                understood.add(unit.concept)
                state.understood_concepts.add(unit.concept)
            else:
                misunderstood.add(unit.concept)

    # Correct existing misconceptions from understood corrective concepts.
    corrected: set[Misconception] = set()
    for concept in understood:
        for misc in CORRECTS.get(concept, frozenset()):
            if misc in state.misconceptions and rng.random() < _correction_prob(profile):
                state.misconceptions.discard(misc)
                corrected.add(misc)

    induced = _induce_misconceptions(profile, view, noticed, understood, state, rng)

    actual = len(understood) / max(1, len(noticed))
    # Over-trust grows with automation trust and understanding felt; misconceptions
    # inflate felt-but-false confidence.
    misbelief_penalty = 0.15 if state.misconceptions else 0.0
    subjective_after = _clamp(
        0.25
        + 0.4 * profile.trust_in_automation
        + 0.35 * actual
        + misbelief_penalty  # believing you "get it" while holding a misconception
    )
    state.subjective_confidence = subjective_after
    calibration_gap = subjective_after - actual
    overrelied = (
        subjective_after > 0.6
        and profile.trust_in_automation > 0.5
        and (bool(state.misconceptions) or actual < 0.4)
    )

    return InterpretationResult(
        noticed=noticed,
        understood=understood,
        misunderstood=misunderstood,
        corrected=corrected,
        induced=induced,
        misconceptions_after=frozenset(state.misconceptions),
        confidence_before=confidence_before,
        confidence_after=subjective_after,
        actual_understanding=actual,
        calibration_gap=calibration_gap,
        overrelied=overrelied,
    )
