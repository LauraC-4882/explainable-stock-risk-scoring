"""Phase 3: safety scenarios — crash, data-quality, drift, misinformation, vulnerable."""

from __future__ import annotations

from stock_risk.simulation import scenarios
from stock_risk.simulation.events import EventType, config_hash
from stock_risk.simulation.profiles import Archetype, generate_cohort, generate_user

CFG = config_hash({"phase": 3})


def _completed_rate(runner, archetype, key, *, n=60, seed0=0, **kw):
    hits = 0
    for i, u in enumerate(generate_cohort(archetype, n, seed=808)):
        log = runner(u, seed=seed0 + i, config_hash=CFG, **kw)
        if log.of_type(EventType.SIMULATION_COMPLETED)[0].detail.get(key):
            hits += 1
    return hits / n


def _intent_rate(runner, archetype, key, *, n=80, **kw):
    hits = 0
    for i, u in enumerate(generate_cohort(archetype, n, seed=808)):
        log = runner(u, seed=i, config_hash=CFG, **kw)
        ev = log.of_type(EventType.USER_ACTION_INTENT_RECORDED)[0]
        if ev.detail.get(key):
            hits += 1
    return hits / n


# ── Scenario C: market crash ────────────────────────────────────────────────
def test_crisis_safe_reduces_harmful_exit_intent():
    as_is = _completed_rate(scenarios.run_market_crash, Archetype.MARKET_CRASH_USER, "harmful_exit",
                            crisis_safe=False)
    safe = _completed_rate(scenarios.run_market_crash, Archetype.MARKET_CRASH_USER, "harmful_exit",
                           crisis_safe=True)
    assert safe < as_is


def test_crash_run_is_deterministic():
    u = generate_user(Archetype.MARKET_CRASH_USER, seed=1, index=0)
    a = scenarios.run_market_crash(u, seed=3, config_hash=CFG, crisis_safe=True)
    b = scenarios.run_market_crash(u, seed=3, config_hash=CFG, crisis_safe=True)
    assert a.to_records() == b.to_records()


# ── Scenario D: data-quality failure ────────────────────────────────────────
def test_bad_data_is_taken_at_face_value_without_a_warning():
    # With no flag, everyone takes the low-confidence score at face value.
    assert _intent_rate(scenarios.run_data_quality_failure, Archetype.FIRST_TIME_RETAIL,
                        "took_score_at_face_value", surface_warning=False) == 1.0


def test_warning_helps_the_literate_more_than_low_literacy_users():
    # A surfaced warning reduces face-value trust — but far more for professionals
    # than for low-literacy users, who mostly can't read it. This disparity is a
    # core fairness finding, not a bug.
    pro_no = _intent_rate(scenarios.run_data_quality_failure, Archetype.EXPERIENCED_INVESTOR,
                          "took_score_at_face_value", surface_warning=False)
    pro_warn = _intent_rate(scenarios.run_data_quality_failure, Archetype.EXPERIENCED_INVESTOR,
                            "took_score_at_face_value", surface_warning=True)
    low_warn = _intent_rate(scenarios.run_data_quality_failure, Archetype.LOW_FINANCIAL_LITERACY,
                            "took_score_at_face_value", surface_warning=True)
    assert pro_warn < pro_no                      # warning helps the literate
    assert (pro_no - pro_warn) > (1.0 - low_warn)  # helps them MORE than low-literacy


# ── Scenario E: model drift / demotion ──────────────────────────────────────
def _trust_counts(disclose, archetype, n=60):
    from collections import Counter
    c = Counter()
    for i, u in enumerate(generate_cohort(archetype, n, seed=5)):
        log = scenarios.run_model_degradation(u, seed=i, config_hash=CFG, disclose=disclose)
        c[log.of_type(EventType.SIMULATION_COMPLETED)[0].detail["trust_state"]] += 1
    return c


def test_disclosure_calibrates_trust_for_professionals():
    silent = _trust_counts(False, Archetype.EXPERIENCED_INVESTOR)
    disclosed = _trust_counts(True, Archetype.EXPERIENCED_INVESTOR)
    # No one calibrates when degradation is hidden; disclosure produces some.
    assert silent.get("appropriate_caution", 0) == 0
    assert disclosed.get("appropriate_caution", 0) > 0


def test_disclosure_barely_reaches_novices():
    # Novices largely don't notice/understand the degraded flag — another disparity.
    disclosed = _trust_counts(True, Archetype.FIRST_TIME_RETAIL)
    pro = _trust_counts(True, Archetype.EXPERIENCED_INVESTOR)
    assert disclosed.get("appropriate_caution", 0) < pro.get("appropriate_caution", 0)


# ── Scenario F: community misinformation ────────────────────────────────────
def test_separation_disclaimer_reduces_community_override():
    with_sep = _completed_rate(
        scenarios.run_community_misinformation, Archetype.COMMUNITY_INFLUENCED,
        "community_override_of_evidence", with_disclaimer=True,
    )
    without = _completed_rate(
        scenarios.run_community_misinformation, Archetype.COMMUNITY_INFLUENCED,
        "community_override_of_evidence", with_disclaimer=False,
    )
    assert with_sep <= without


def test_misinformation_is_sometimes_reported():
    reported = 0
    for i, u in enumerate(generate_cohort(Archetype.EXPERIENCED_INVESTOR, 60, seed=1)):
        log = scenarios.run_community_misinformation(
            u, seed=i, config_hash=CFG, is_misinformation=True
        )
        if any(e.event_type is EventType.COMMUNITY_POST_REPORTED for e in log.events):
            reported += 1
    assert reported > 0


# ── Scenario J: vulnerable context ──────────────────────────────────────────
def test_vulnerable_context_never_yields_personalized_advice():
    # Hard invariant across the whole financial-stress cohort.
    for i, u in enumerate(generate_cohort(Archetype.FINANCIAL_STRESS, 80, seed=808)):
        for reinforce in (False, True):
            log = scenarios.run_vulnerable_context(u, seed=i, config_hash=CFG,
                                           reinforce_boundaries=reinforce)
            ev = log.of_type(EventType.USER_ACTION_INTENT_RECORDED)[0]
            assert ev.detail["system_gave_personalized_advice"] is False


def test_reinforced_boundaries_increase_professional_advice_seeking():
    standard = _intent_rate(scenarios.run_vulnerable_context, Archetype.FINANCIAL_STRESS,
                            "sought_professional_advice", reinforce_boundaries=False)
    reinforced = _intent_rate(scenarios.run_vulnerable_context, Archetype.FINANCIAL_STRESS,
                              "sought_professional_advice", reinforce_boundaries=True)
    assert reinforced >= standard
