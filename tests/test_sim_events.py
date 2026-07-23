"""Phase 1: event schema, JSONL round-trip, task determinism, and replays."""

from __future__ import annotations

import json

from stock_risk.simulation.events import EventType, IntendedAction, config_hash
from stock_risk.simulation.presentation import PresentationVariant
from stock_risk.simulation.profiles import Archetype, generate_cohort, generate_user
from stock_risk.simulation.replay import build_replay, render_markdown, write_replay
from stock_risk.simulation.sut import DataQuality
from stock_risk.simulation.tasks import run_single_stock_analysis

CFG = config_hash({"phase": 1})


def test_config_hash_is_stable_and_order_independent():
    a = config_hash({"a": 1, "b": 2})
    b = config_hash({"b": 2, "a": 1})
    assert a == b and len(a) == 12


def test_single_stock_run_is_deterministic():
    user = generate_user(Archetype.FIRST_TIME_RETAIL, seed=1, index=0)
    a = run_single_stock_analysis(user, seed=7, config_hash=CFG)
    b = run_single_stock_analysis(user, seed=7, config_hash=CFG)
    assert a.to_records() == b.to_records()


def test_run_emits_required_lifecycle_events():
    user = generate_user(Archetype.FIRST_TIME_RETAIL, seed=1, index=0)
    log = run_single_stock_analysis(user, seed=7, config_hash=CFG)
    types = {e.event_type for e in log.events}
    assert EventType.USER_SIMULATION_STARTED in types
    assert EventType.SCORE_VIEWED in types
    assert EventType.USER_ACTION_INTENT_RECORDED in types
    assert EventType.SIMULATION_COMPLETED in types


def test_every_event_carries_required_context_fields():
    user = generate_user(Archetype.CHINESE_LANGUAGE, seed=2, index=0)
    log = run_single_stock_analysis(
        user, seed=3, config_hash=CFG, variant=PresentationVariant.AS_IS
    )
    for e in log.events:
        rec = e.to_dict()
        for key in (
            "simulated_user_id", "archetype", "language", "scenario_id",
            "experiment_variant", "simulation_seed", "config_hash", "accessibility_mode",
        ):
            assert rec[key] not in (None, ""), f"{e.event_type} missing {key}"


def test_intended_actions_are_within_the_enum_and_never_advice():
    # Acceptance invariant: the simulation records a user's own intent, never a
    # system recommendation. No event may carry a buy/sell *recommendation* field.
    users = generate_cohort(Archetype.YOUNG_HIGH_RISK_TRADER, 20, seed=5)
    valid = {a.value for a in IntendedAction}
    for i, u in enumerate(users):
        log = run_single_stock_analysis(u, seed=100 + i, config_hash=CFG)
        for e in log.events:
            if e.intended_financial_action is not None:
                assert e.intended_financial_action in valid
            rec = e.to_dict()
            assert "recommendation" not in rec
            assert "advice" not in rec


def test_score_viewed_never_labels_the_score_a_probability():
    # The framework must never describe the 0-100 score as a probability of loss.
    user = generate_user(Archetype.LOW_FINANCIAL_LITERACY, seed=1, index=0)
    log = run_single_stock_analysis(user, seed=8, config_hash=CFG)
    score_events = log.of_type(EventType.SCORE_VIEWED)
    assert score_events
    for e in score_events:
        # confidence_status is a data-confidence label, not a probability; the
        # score value is a plain number, never expressed as P(loss).
        assert e.confidence_status in {"normal", "low", "suppressed", "unknown"}
        assert "probability_of_loss" not in e.detail


def test_bad_data_run_records_the_unshown_confidence_gap():
    # AS_IS + low-quality data: the event records the true (low) confidence AND
    # that the product surfaced none — the measurable product-risk signal.
    user = generate_user(Archetype.ILLIQUID_DATA_SPARSE, seed=1, index=0)
    log = run_single_stock_analysis(
        user, seed=9, config_hash=CFG, variant=PresentationVariant.AS_IS,
        data_quality=DataQuality(history_days=25, staleness_days=15, illiquid=True),
    )
    sv = log.of_type(EventType.SCORE_VIEWED)[0]
    assert sv.detail["intrinsic_confidence"] in {"low", "suppressed"}
    assert sv.detail["product_surfaced_confidence"] is False
    assert sv.confidence_status == "unknown"  # user shown nothing


def test_jsonl_round_trip(tmp_path):
    user = generate_user(Archetype.EXPERIENCED_INVESTOR, seed=1, index=0)
    log = run_single_stock_analysis(user, seed=7, config_hash=CFG)
    path = log.write_jsonl(tmp_path / "events.jsonl")
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == len(log.events)
    reparsed = [json.loads(line) for line in lines]
    assert reparsed == log.to_records()


def test_replay_build_and_markdown(tmp_path):
    user = generate_user(Archetype.FIRST_TIME_RETAIL, seed=1, index=0)
    log = run_single_stock_analysis(user, seed=7, config_hash=CFG)
    replay = build_replay(log)
    assert replay["user_id"] == user.user_id
    assert replay["summary"]["final_intended_action"] is not None
    md = render_markdown(replay)
    assert "User journey replay" in md
    assert "not evidence about a real person" in md  # honesty banner present
    json_path, md_path = write_replay(log, tmp_path / "replays", "u0")
    assert json_path.exists() and md_path.exists()


def test_groups_behave_differently_in_aggregate():
    # Acceptance invariant: distinct archetypes produce distinct behaviour.
    def overreliance_rate(archetype):
        cohort = generate_cohort(archetype, 60, seed=21)
        flagged = 0
        for i, u in enumerate(cohort):
            log = run_single_stock_analysis(u, seed=500 + i, config_hash=CFG)
            if log.of_type(EventType.USER_OVERRELIANCE_DETECTED):
                flagged += 1
        return flagged / len(cohort)

    novice = overreliance_rate(Archetype.FIRST_TIME_RETAIL)
    pro = overreliance_rate(Archetype.EXPERIENCED_INVESTOR)
    assert novice > pro
