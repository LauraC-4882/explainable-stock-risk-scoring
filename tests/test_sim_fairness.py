"""Phase 4: language parity, accessibility, colour-independence, and disparities."""

from __future__ import annotations

from dataclasses import replace

from stock_risk.simulation import accessibility as acc
from stock_risk.simulation import fairness
from stock_risk.simulation.comprehension import run_comprehension_battery
from stock_risk.simulation.distributions import derive_generator
from stock_risk.simulation.events import EventType, config_hash
from stock_risk.simulation.interpret import UserState, understand_prob
from stock_risk.simulation.presentation import Concept, ContentUnit, Modality
from stock_risk.simulation.profiles import (
    Archetype,
    ColorVisionMode,
    Language,
    generate_cohort,
    generate_population,
    generate_user,
)

CFG = config_hash({"phase": 4})


# ── Language parity (Scenario G) ─────────────────────────────────────────────
def test_english_only_unit_understood_less_in_chinese():
    unit = ContentUnit(Concept.STRESS_TEST, Modality.TEXT, salience=0.5, english_only=True)
    pro_en = generate_user(Archetype.EXPERIENCED_INVESTOR, seed=1, index=0)
    pro_zh = replace(pro_en, language=Language.ZH)
    assert understand_prob(pro_zh, unit) < understand_prob(pro_en, unit)


def test_language_parity_gap_is_positive_for_untranslated_content():
    gaps = []
    for i, u in enumerate(generate_cohort(Archetype.EXPERIENCED_INVESTOR, 50, seed=42)):
        log = acc.run_language_parity(u, seed=i, config_hash=CFG)
        gaps.append(log.of_type(EventType.SIMULATION_COMPLETED)[0].detail["untranslated_parity_gap"])
    assert sum(gaps) / len(gaps) > 0.1   # zh loses ground on untranslated units
    assert any(g > 0 for g in gaps)


def test_language_parity_run_is_deterministic():
    u = generate_user(Archetype.CHINESE_LANGUAGE, seed=1, index=0)
    a = acc.run_language_parity(u, seed=3, config_hash=CFG)
    b = acc.run_language_parity(u, seed=3, config_hash=CFG)
    assert a.to_records() == b.to_records()


# ── Accessibility (Scenario H) ───────────────────────────────────────────────
def _accessibility_stats(alt, n=60):
    completed = missed = sr = 0
    for i, u in enumerate(generate_cohort(Archetype.VISUAL_ACCESSIBILITY, n, seed=7)):
        d = acc.run_accessibility_journey(
            u, seed=i, config_hash=CFG, charts_have_alt_text=alt
        ).of_type(EventType.SIMULATION_COMPLETED)[0].detail
        completed += d["completed"]
        missed += d["missed_chart_content"]
        sr += d["uses_screen_reader"]
    return completed / n, missed, sr


def test_chart_alt_text_improves_screen_reader_completion():
    no_alt_completed, no_alt_missed, sr = _accessibility_stats(False)
    alt_completed, alt_missed, _ = _accessibility_stats(True)
    assert sr > 0                          # the cohort actually contains SR users
    assert alt_completed > no_alt_completed
    assert alt_missed < no_alt_missed      # fewer SR users miss the chart with alt text


def test_color_only_design_hurts_color_deficient_users():
    def deficient_got_risk(color_only, n=80):
        hits = total = 0
        for i, u in enumerate(generate_cohort(Archetype.VISUAL_ACCESSIBILITY, n, seed=3)):
            if u.color_vision_mode is ColorVisionMode.NORMAL:
                continue
            d = acc.run_color_independent(
                u, seed=i, config_hash=CFG, color_only_design=color_only
            ).of_type(EventType.SIMULATION_COMPLETED)[0].detail
            total += 1
            hits += d["got_risk_meaning"]
        return hits / total if total else 0.0

    redundant = deficient_got_risk(False)
    color_only = deficient_got_risk(True)
    assert redundant > color_only   # redundant labels protect colour-deficient users


# ── Fairness disparities ─────────────────────────────────────────────────────
def _comprehension_population(per_archetype=12, seed=11):
    pop = []
    for u in generate_population(seed=seed, per_archetype=per_archetype):
        state = UserState.initial(u)
        out = run_comprehension_battery(u, state, derive_generator(seed, len(pop)))
        pop.append((u, out.score))
    return pop


def test_literacy_is_the_dominant_comprehension_disparity():
    pop = _comprehension_population()
    results = fairness.all_disparities(pop, ["literacy", "language", "color_vision"])
    assert results["literacy"].disparity_gap > 0.2
    assert results["literacy"].worst_segment == "low_literacy"
    flagged = {d["dimension"] for d in fairness.flag_material_disparities(results)}
    assert "literacy" in flagged


def test_segment_outcome_aggregates_per_user():
    pop = _comprehension_population(per_archetype=6)
    res = fairness.segment_outcome(pop, "archetype")
    # One count per user, summing to the population size.
    assert sum(res.counts.values()) == len(pop)
    # Professionals comprehend more than low-literacy users.
    assert res.rates["experienced_investor"] > res.rates["low_financial_literacy"]
