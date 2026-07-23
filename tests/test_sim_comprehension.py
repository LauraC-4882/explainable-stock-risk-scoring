"""Phase 2: comprehension battery, literacy gradient, and misconception detection."""

from __future__ import annotations

import statistics as st
from dataclasses import replace

from stock_risk.simulation.comprehension import (
    QUESTION_BANK,
    answer_question,
    run_comprehension_battery,
)
from stock_risk.simulation.distributions import derive_generator
from stock_risk.simulation.interpret import UserState
from stock_risk.simulation.profiles import Archetype, Misconception, generate_cohort, generate_user


def _battery_mean(archetype, n=40, seed=55):
    scores = []
    for i, u in enumerate(generate_cohort(archetype, n, seed=seed)):
        state = UserState.initial(u)
        out = run_comprehension_battery(u, state, derive_generator(200 + i, 0))
        scores.append(out.score)
    return st.mean(scores)


def test_bank_covers_the_ten_core_items():
    assert len(QUESTION_BANK) == 10
    assert all(q.prompt_en and q.prompt_zh for q in QUESTION_BANK)


def test_comprehension_is_deterministic():
    u = generate_user(Archetype.FIRST_TIME_RETAIL, seed=1, index=0)
    a = run_comprehension_battery(u, UserState.initial(u), derive_generator(3, 0))
    b = run_comprehension_battery(u, UserState.initial(u), derive_generator(3, 0))
    assert [r.correct for r in a.results] == [r.correct for r in b.results]


def test_literacy_gradient():
    novice = _battery_mean(Archetype.LOW_FINANCIAL_LITERACY)
    pro = _battery_mean(Archetype.EXPERIENCED_INVESTOR)
    assert pro > novice + 0.2


def test_holding_a_misconception_produces_a_wrong_revealing_answer():
    # A user who believes the score is a probability answers the trap wrong, and
    # the wrong answer is recorded as that misconception.
    profile = replace(
        generate_user(Archetype.EXPERIENCED_INVESTOR, seed=1, index=0),
        initial_misconceptions=frozenset({Misconception.SCORE_IS_PROBABILITY}),
    )
    q = next(q for q in QUESTION_BANK if q.qid == "q_score_probability")
    wrong_and_revealed = 0
    for i in range(40):
        state = UserState.initial(profile)
        r = answer_question(profile, state, q, derive_generator(9, i))
        if not r.correct:
            assert r.misconception_revealed == Misconception.SCORE_IS_PROBABILITY.value
            wrong_and_revealed += 1
    assert wrong_and_revealed > 25  # mostly wrong when the misconception is held


def test_chinese_user_gets_chinese_prompts():
    u = generate_user(Archetype.CHINESE_LANGUAGE, seed=1, index=0)
    state = UserState.initial(u)
    out = run_comprehension_battery(u, state, derive_generator(1, 0))
    # zh prompts contain CJK characters.
    assert any(any("一" <= ch <= "鿿" for ch in r.prompt) for r in out.results)


def test_overconfident_wrong_is_counted():
    # Low-literacy users holding misconceptions should sometimes be sure and wrong.
    total = 0
    for i, u in enumerate(generate_cohort(Archetype.LOW_FINANCIAL_LITERACY, 40, seed=2)):
        state = UserState.initial(u)
        out = run_comprehension_battery(u, state, derive_generator(400 + i, 0))
        total += out.overconfident_wrong
    assert total > 0
