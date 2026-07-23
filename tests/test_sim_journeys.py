"""Phase 2: portfolio-concentration and compare journeys over the real aggregator."""

from __future__ import annotations

from stock_risk.simulation.events import EventType, config_hash
from stock_risk.simulation.profiles import Archetype, generate_cohort, generate_user
from stock_risk.simulation.sut import build_portfolio_risk
from stock_risk.simulation.tasks import run_compare, run_portfolio_concentration

CFG = config_hash({"phase": 2})

# One dominant high-vol employer stock + three small diversifiers.
CONCENTRATED = [
    ("EMP", 0.70, 0.55, 1.6, "Tech"),
    ("A", 0.10, 0.25, 0.9, "Health"),
    ("B", 0.10, 0.22, 0.8, "Utilities"),
    ("C", 0.10, 0.20, 0.7, "Staples"),
]


def _recognition_rate(archetype, show_attribution, n=40, seed=77):
    hits = 0
    for i, u in enumerate(generate_cohort(archetype, n, seed=seed)):
        log = run_portfolio_concentration(
            u, seed=300 + i, config_hash=CFG,
            positions_spec=CONCENTRATED, show_attribution=show_attribution,
        )
        comp = log.of_type(EventType.SIMULATION_COMPLETED)[0]
        hits += 1 if comp.detail["concentration_recognised"] else 0
    return hits / n


def test_real_aggregator_flags_the_dominant_name():
    prisk = build_portfolio_risk(CONCENTRATED, seed=1)
    top = max(prisk.risk_contribution_pct, key=prisk.risk_contribution_pct.get)
    assert top == "EMP"
    assert prisk.risk_contribution_pct["EMP"] > 80.0   # dominant contributor
    assert prisk.effective_n < 2.5                     # genuinely concentrated
    # Euler allocation: contributions sum to ~100%.
    assert abs(sum(prisk.risk_contribution_pct.values()) - 100.0) < 1.0


def test_portfolio_run_records_true_top_contributor():
    u = generate_user(Archetype.CONCENTRATED_EMPLOYER_STOCK, seed=1, index=0)
    log = run_portfolio_concentration(u, seed=5, config_hash=CFG, positions_spec=CONCENTRATED)
    created = log.of_type(EventType.PORTFOLIO_CREATED)[0]
    assert created.detail["true_top_contributor"] == "EMP"


def test_attribution_helps_more_than_generic_warning():
    # Professionals recognise concentration far more often with attribution than
    # novices do with either arm — the Scenario-B hypothesis, directionally.
    pro_attr = _recognition_rate(Archetype.EXPERIENCED_INVESTOR, True)
    novice_attr = _recognition_rate(Archetype.FIRST_TIME_RETAIL, True)
    novice_generic = _recognition_rate(Archetype.FIRST_TIME_RETAIL, False)
    assert pro_attr > novice_attr
    assert pro_attr > novice_generic
    assert novice_attr >= novice_generic  # attribution never worse than generic


def test_portfolio_run_is_deterministic():
    u = generate_user(Archetype.FIRST_TIME_RETAIL, seed=9, index=0)
    a = run_portfolio_concentration(u, seed=5, config_hash=CFG, positions_spec=CONCENTRATED)
    b = run_portfolio_concentration(u, seed=5, config_hash=CFG, positions_spec=CONCENTRATED)
    assert a.to_records() == b.to_records()


def test_compare_ranks_correctly_for_literate_users():
    # A financially literate professional should reliably rank a high-risk stock
    # above a low-risk one.
    correct = 0
    for i, u in enumerate(generate_cohort(Archetype.EXPERIENCED_INVESTOR, 40, seed=3)):
        log = run_compare(
            u, seed=100 + i, config_hash=CFG,
            stock_a=("HIVOL", 84.0), stock_b=("LOVOL", 16.0),
        )
        comp = log.of_type(EventType.SIMULATION_COMPLETED)[0]
        if comp.detail["ranked_correctly"]:
            correct += 1
    assert correct / 40 > 0.7


def test_compare_is_deterministic():
    u = generate_user(Archetype.EXPERIENCED_INVESTOR, seed=1, index=0)
    a = run_compare(u, seed=1, config_hash=CFG, stock_a=("X", 80.0), stock_b=("Y", 20.0))
    b = run_compare(u, seed=1, config_hash=CFG, stock_a=("X", 80.0), stock_b=("Y", 20.0))
    assert a.to_records() == b.to_records()
