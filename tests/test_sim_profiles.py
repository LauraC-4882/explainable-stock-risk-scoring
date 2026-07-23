"""Phase 1: deterministic generation + meaningful within/between-group variation."""

from __future__ import annotations

import statistics as st

import pytest

from stock_risk.simulation.profiles import (
    ARCHETYPES,
    PHASE1_ARCHETYPES,
    Archetype,
    Language,
    generate_cohort,
    generate_population,
    generate_user,
)

_CONTINUOUS = (
    "financial_literacy", "numeracy", "probability_comprehension", "risk_tolerance",
    "loss_aversion", "trust_in_automation", "disclosure_attention", "attention_span",
)


def test_all_archetypes_have_a_spec():
    assert set(ARCHETYPES) == set(Archetype)
    assert len(Archetype) == 14
    assert len(PHASE1_ARCHETYPES) == 6


def test_generation_is_deterministic():
    a = generate_user(Archetype.FIRST_TIME_RETAIL, seed=42, index=3)
    b = generate_user(Archetype.FIRST_TIME_RETAIL, seed=42, index=3)
    assert a == b


def test_generation_is_order_independent():
    # Generating user 5 directly equals user 5 within a cohort of 10.
    direct = generate_user(Archetype.EXPERIENCED_INVESTOR, seed=1, index=5)
    cohort = generate_cohort(Archetype.EXPERIENCED_INVESTOR, 10, seed=1)
    assert direct == cohort[5]


def test_different_seeds_give_different_users():
    a = generate_user(Archetype.FIRST_TIME_RETAIL, seed=1, index=0)
    b = generate_user(Archetype.FIRST_TIME_RETAIL, seed=2, index=0)
    assert a.financial_literacy != b.financial_literacy


@pytest.mark.parametrize("archetype", list(Archetype))
def test_within_archetype_variation(archetype):
    cohort = generate_cohort(archetype, 40, seed=5)
    # No archetype may be a set of identical clones: at least a few continuous
    # traits must vary within the group.
    varying = 0
    for field in _CONTINUOUS:
        values = [getattr(u, field) for u in cohort]
        if st.pstdev(values) > 0.02 and len(set(round(v, 4) for v in values)) > 5:
            varying += 1
    assert varying >= 4, f"{archetype} shows too little within-group variation"


def test_no_archetype_defined_by_a_single_field():
    # Two archetypes must differ on several trait means, not just one arbitrary
    # flag — otherwise groups aren't "meaningfully different".
    novice = generate_cohort(Archetype.FIRST_TIME_RETAIL, 50, seed=9)
    pro = generate_cohort(Archetype.EXPERIENCED_INVESTOR, 50, seed=9)
    differing = 0
    for field in _CONTINUOUS:
        m1 = st.mean(getattr(u, field) for u in novice)
        m2 = st.mean(getattr(u, field) for u in pro)
        if abs(m1 - m2) > 0.1:
            differing += 1
    assert differing >= 3


def test_between_group_separation_is_directionally_correct():
    novice = generate_cohort(Archetype.FIRST_TIME_RETAIL, 60, seed=3)
    pro = generate_cohort(Archetype.EXPERIENCED_INVESTOR, 60, seed=3)
    assert st.mean(u.financial_literacy for u in novice) < st.mean(
        u.financial_literacy for u in pro
    )
    assert st.mean(u.probability_comprehension for u in novice) < st.mean(
        u.probability_comprehension for u in pro
    )
    # Professionals are less swayed by social proof and trust automation less.
    assert st.mean(u.social_proof_sensitivity for u in novice) > st.mean(
        u.social_proof_sensitivity for u in pro
    )


def test_chinese_archetype_is_always_chinese():
    cohort = generate_cohort(Archetype.CHINESE_LANGUAGE, 30, seed=11)
    assert all(u.language is Language.ZH for u in cohort)


def test_traits_are_normalised():
    population = generate_population(seed=1, per_archetype=8)
    for u in population:
        for field in _CONTINUOUS:
            assert 0.0 <= getattr(u, field) <= 1.0


def test_screen_reader_mode_implies_accessibility_need():
    from stock_risk.simulation.profiles import AccessibilityNeed, InteractionMode

    cohort = generate_cohort(Archetype.VISUAL_ACCESSIBILITY, 80, seed=2)
    for u in cohort:
        if u.preferred_interaction_mode is InteractionMode.SCREEN_READER:
            assert u.has_accessibility_need(AccessibilityNeed.SCREEN_READER)
