"""[R4][R5] Tests for the model registry, lifecycle gating, and lineage.

The tests that matter here are the *refusals*: a governance control is only
worth anything if it blocks the thing it claims to block. Most of this file is
therefore about what the registry will not let you do.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from stock_risk.governance import (
    DataQualityReport,
    ModelCard,
    ModelRegistry,
    ModelStatus,
    ReproducibilityManifest,
    TransitionError,
    ValidationThresholds,
    build_manifest,
    dataset_hash,
)

GOOD_METRICS = {"roc_auc": 0.671, "brier_raw": 0.183, "brier_calibrated": 0.119}
WEAK_METRICS = {"roc_auc": 0.56, "brier_raw": 0.30, "brier_calibrated": 0.28}


@pytest.fixture()
def registry(tmp_path):
    return ModelRegistry(tmp_path / "registry.json")


def _register(registry, version="1.0.0", metrics=None, name="downside_risk"):
    return registry.register(name, version, metrics=metrics or dict(GOOD_METRICS))


# ── Lifecycle gating ─────────────────────────────────────────────────────────


def test_new_models_start_in_development_regardless_of_metrics(registry):
    """Even excellent metrics don't grant a starting state — the state machine
    decides eligibility, not the caller."""
    record = _register(registry, metrics={"roc_auc": 0.99, "brier_calibrated": 0.01})
    assert record.status is ModelStatus.DEVELOPMENT


def test_cannot_skip_validation_and_go_straight_to_active(registry):
    """The single most important refusal in this module."""
    _register(registry)
    with pytest.raises(TransitionError, match="not a legal transition"):
        registry.transition("downside_risk", "1.0.0", ModelStatus.ACTIVE)


def test_validation_rejects_a_model_below_the_auc_floor(registry):
    """0.56 mean AUC is the coin-flip result this project actually got on its
    first attempt (README). It must not pass."""
    _register(registry, metrics=WEAK_METRICS)
    with pytest.raises(TransitionError, match="roc_auc"):
        registry.validate("downside_risk", "1.0.0")
    assert registry.get("downside_risk", "1.0.0").status is ModelStatus.DEVELOPMENT


def test_validation_rejects_a_model_with_no_recorded_metrics(registry):
    """Absent evidence must fail, not pass — treating "no AUC recorded" as
    satisfied is exactly how ungated models reach production."""
    registry.register("downside_risk", "1.0.0", metrics={})
    with pytest.raises(TransitionError, match="not recorded"):
        registry.validate("downside_risk", "1.0.0")


def test_validation_rejects_calibration_that_made_brier_worse(registry):
    """If isotonic calibration degraded Brier, the calibration slice is wrong —
    a real failure this project's own walk-forward output could produce."""
    _register(
        registry,
        metrics={"roc_auc": 0.68, "brier_raw": 0.15, "brier_calibrated": 0.46},
    )
    with pytest.raises(TransitionError, match="calibration made Brier worse"):
        registry.validate("downside_risk", "1.0.0")


def test_full_happy_path_to_champion(registry):
    _register(registry)
    registry.validate("downside_risk", "1.0.0")
    registry.transition("downside_risk", "1.0.0", ModelStatus.APPROVED, reason="signed off")
    registry.promote_to_active("downside_risk", "1.0.0")

    champion = registry.champion("downside_risk")
    assert champion.version == "1.0.0"
    assert champion.status is ModelStatus.ACTIVE


def test_promotion_refuses_a_model_that_fails_its_thresholds(registry):
    """Belt and braces: even if a model reached APPROVED somehow, promotion
    re-checks. A gate you only pass once is a gate you can walk around."""
    _register(registry, metrics=WEAK_METRICS)
    registry.transition("downside_risk", "1.0.0", ModelStatus.VALIDATED, force=True)
    registry.transition("downside_risk", "1.0.0", ModelStatus.APPROVED)
    with pytest.raises(TransitionError, match="refusing to promote"):
        registry.promote_to_active("downside_risk", "1.0.0")


def test_registering_the_same_version_twice_is_refused(registry):
    """Governance records are immutable — silently overwriting one destroys the
    evidence it exists to preserve."""
    _register(registry)
    with pytest.raises(ValueError, match="immutable"):
        _register(registry)


def test_retirement_requires_a_reason(registry):
    _register(registry)
    with pytest.raises(ValueError, match="reason is required"):
        registry.retire("downside_risk", "1.0.0", reason="   ")


def test_retired_is_terminal(registry):
    _register(registry)
    registry.retire("downside_risk", "1.0.0", reason="superseded by a different approach")
    with pytest.raises(TransitionError):
        registry.transition("downside_risk", "1.0.0", ModelStatus.VALIDATED)


def test_degraded_cannot_go_straight_back_to_active(registry):
    """A model that breached its bar must re-validate, not get waved through
    because the metric happened to recover."""
    _promote(registry, "1.0.0")
    registry.demote("downside_risk", "1.0.0", reason="drift")
    with pytest.raises(TransitionError):
        registry.transition("downside_risk", "1.0.0", ModelStatus.ACTIVE)


# ── Champion / challenger ────────────────────────────────────────────────────


def _promote(registry, version, metrics=None):
    registry.register("downside_risk", version, metrics=metrics or dict(GOOD_METRICS))
    registry.validate("downside_risk", version)
    registry.transition("downside_risk", version, ModelStatus.APPROVED)
    return registry.promote_to_active("downside_risk", version)


def test_only_one_champion_at_a_time(registry):
    """Two ACTIVE versions means "which model produced this score?" has no
    answer, which invalidates every downstream record."""
    _promote(registry, "1.0.0")
    _promote(registry, "2.0.0")

    actives = [r for r in registry.versions("downside_risk") if r.status is ModelStatus.ACTIVE]
    assert len(actives) == 1
    assert actives[0].version == "2.0.0"
    assert registry.get("downside_risk", "1.0.0").status is ModelStatus.RETIRED


def test_superseded_champion_records_why_it_was_retired(registry):
    _promote(registry, "1.0.0")
    _promote(registry, "2.0.0")
    assert "2.0.0" in registry.get("downside_risk", "1.0.0").retirement_reason


def test_compare_ranks_challenger_against_champion(registry):
    _promote(registry, "1.0.0", metrics={"roc_auc": 0.65, "brier_calibrated": 0.15})
    registry.register(
        "downside_risk", "2.0.0", metrics={"roc_auc": 0.71, "brier_calibrated": 0.12}
    )

    result = registry.compare("downside_risk", "2.0.0")

    assert result["challenger_wins"] is True
    assert result["deltas"]["roc_auc"]["improvement"] == pytest.approx(0.06)
    # Brier is lower-is-better: a DECREASE must register as an improvement.
    assert result["deltas"]["brier_calibrated"]["improvement"] == pytest.approx(0.03)


def test_compare_does_not_promote(registry):
    """Promotion stays a human decision — automating it removes the only step
    where someone checks whether the improvement is real."""
    _promote(registry, "1.0.0", metrics={"roc_auc": 0.60, "brier_calibrated": 0.15})
    registry.register("downside_risk", "2.0.0", metrics={"roc_auc": 0.90, "brier_calibrated": 0.05})

    registry.compare("downside_risk", "2.0.0")

    assert registry.champion("downside_risk").version == "1.0.0"
    assert registry.get("downside_risk", "2.0.0").status is ModelStatus.DEVELOPMENT


# ── Automatic demotion and rollback ──────────────────────────────────────────


def test_live_drift_breach_demotes_the_champion(registry):
    _promote(registry, "1.0.0")
    demoted = registry.check_for_breach("downside_risk", {"max_drift_psi": 0.42})

    assert demoted is not None
    assert demoted.status is ModelStatus.DEGRADED
    assert "drift PSI" in demoted.history[-1]["reason"]
    assert registry.champion("downside_risk") is None


def test_healthy_champion_is_not_demoted(registry):
    _promote(registry, "1.0.0")
    assert registry.check_for_breach("downside_risk", {"max_drift_psi": 0.05}) is None
    assert registry.champion("downside_risk").version == "1.0.0"


def test_previous_champion_is_available_as_a_rollback_target(registry):
    _promote(registry, "1.0.0")
    _promote(registry, "2.0.0")
    registry.check_for_breach("downside_risk", {"roc_auc": 0.20})

    previous = registry.previous_champion("downside_risk")
    assert previous is not None
    assert previous.version in {"1.0.0", "2.0.0"}


def test_history_is_append_only_and_records_actor_and_reason(registry):
    _promote(registry, "1.0.0")
    registry.demote("downside_risk", "1.0.0", reason="AUC fell below floor", actor="monitor")

    history = registry.get("downside_risk", "1.0.0").history
    assert [h["to"] for h in history] == [
        "development",
        "validated",
        "approved",
        "active",
        "degraded",
    ]
    assert history[-1]["actor"] == "monitor"
    assert history[-1]["reason"] == "AUC fell below floor"


# ── Persistence ──────────────────────────────────────────────────────────────


def test_registry_round_trips_through_disk(tmp_path):
    """The registry is a reviewable file, so it has to survive a reload
    unchanged — including enum-valued status fields."""
    path = tmp_path / "registry.json"
    first = ModelRegistry(path)
    first.register(
        "downside_risk",
        "1.0.0",
        metrics=dict(GOOD_METRICS),
        model_card=ModelCard(
            intended_use="Secondary drawdown-risk signal",
            limitations=["Recall is low (0.11 mean)"],
        ),
    )
    first.validate("downside_risk", "1.0.0")

    reloaded = ModelRegistry(path)
    record = reloaded.get("downside_risk", "1.0.0")
    assert record.status is ModelStatus.VALIDATED
    assert record.model_card["limitations"] == ["Recall is low (0.11 mean)"]


def test_custom_thresholds_are_stored_per_model(registry):
    """A challenger with a different objective can carry a different bar, and
    tightening the bar later must not retroactively invalidate old records."""
    registry.register(
        "experimental",
        "0.1.0",
        metrics={"roc_auc": 0.55, "brier_calibrated": 0.2},
        thresholds=ValidationThresholds(min_roc_auc=0.50),
    )
    registry.validate("experimental", "0.1.0")
    assert registry.get("experimental", "0.1.0").status is ModelStatus.VALIDATED


# ── [R5] Lineage ─────────────────────────────────────────────────────────────


def _frame(seed=0, n=50):
    rng = np.random.default_rng(seed)
    return pd.DataFrame(
        {"vol_21d": rng.normal(size=n), "rsi_14": rng.normal(size=n)},
        index=pd.bdate_range("2024-01-01", periods=n),
    )


def test_dataset_hash_is_stable_for_identical_data():
    assert dataset_hash(_frame()) == dataset_hash(_frame())


def test_dataset_hash_changes_when_a_value_changes():
    """The whole point: a restated price must change the hash even though the
    filename, shape and column names are identical."""
    a = _frame()
    b = a.copy()
    b.iloc[0, 0] += 0.001
    assert dataset_hash(a) != dataset_hash(b)


def test_dataset_hash_ignores_column_order():
    """Column order is an artifact of how the frame was assembled, not a
    property of the data — it must not read as drift."""
    a = _frame()
    assert dataset_hash(a) == dataset_hash(a[["rsi_14", "vol_21d"]])


def test_dataset_hash_is_insensitive_to_float_noise_below_tolerance():
    """Cross-platform BLAS noise in the last bits must not flag drift that
    isn't there — otherwise every hash comparison is useless."""
    a = _frame()
    b = a.copy()
    b.iloc[0, 0] += 1e-15
    assert dataset_hash(a) == dataset_hash(b)


def test_data_quality_report_captures_missingness_and_staleness():
    df = _frame()
    df.loc[df.index[:5], "vol_21d"] = np.nan

    report = DataQualityReport.from_frame(df)

    assert report.rows == 50
    assert report.missing_by_column["vol_21d"] == pytest.approx(10.0)
    assert "rsi_14" not in report.missing_by_column
    assert report.staleness_days is not None and report.staleness_days > 0


def test_manifest_records_everything_needed_to_explain_a_rerun(tmp_path):
    manifest = build_manifest(
        model_name="downside_risk",
        model_version="1.0.0",
        features=_frame(),
        feature_names=["vol_21d", "rsi_14"],
        universe=["AAPL", "MSFT"],
        excluded_tickers={"XYZ": "delisted mid-window"},
        hyperparameters={"n_estimators": 300},
        metrics=dict(GOOD_METRICS),
        random_seed=42,
        label_definition="forward 20d max drawdown <= -10%",
    )
    path = manifest.write(tmp_path / "manifest.json")

    reloaded = ReproducibilityManifest.load(path)
    assert reloaded.dataset_hash == manifest.dataset_hash
    assert reloaded.excluded_tickers == {"XYZ": "delisted mid-window"}
    assert reloaded.random_seed == 42
    assert reloaded.feature_schema_version


def test_manifest_diff_isolates_what_changed():
    """The triage tool: when a metric moves, this says whether the data moved,
    the code moved, or neither (which means the run is nondeterministic — itself
    the finding)."""
    common = dict(
        model_name="downside_risk",
        model_version="1.0.0",
        feature_names=["vol_21d", "rsi_14"],
        universe=["AAPL"],
        metrics=dict(GOOD_METRICS),
    )
    first = build_manifest(features=_frame(seed=1), **common)
    second = build_manifest(features=_frame(seed=2), **common)

    diffs = second.differences_from(first)

    assert "dataset_hash" in diffs, "different data must show as a dataset_hash diff"
    assert "universe" not in diffs
    assert "feature_names" not in diffs
