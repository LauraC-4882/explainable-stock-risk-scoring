"""GET /api/governance/model — the registry read back out.

The registry's own tests ([R4], tests/test_governance.py) cover what it refuses
to do. These cover the half that never existed until now: reading the recorded
state back, and — the part that actually matters for an honesty page —
reporting *absence* as absence instead of as a pass.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from stock_risk.api.app import _governance_cache, app
from stock_risk.governance import ModelRegistry, ModelStatus
from stock_risk.governance.snapshot import governance_snapshot, lifecycle_graph

GOOD_METRICS = {"roc_auc": 0.671, "brier_raw": 0.183, "brier_calibrated": 0.119}


@pytest.fixture(autouse=True)
def _clear_cache():
    """The endpoint caches for 15 minutes; without this every test after the
    first would assert against the first one's snapshot."""
    _governance_cache.update({"at": 0.0, "data": None})
    yield
    _governance_cache.update({"at": 0.0, "data": None})


class _FakeModel:
    _params = {"n_estimators": 300, "max_depth": 5}
    calibrated = object()

    def feature_importance(self):
        import pandas as pd

        return pd.Series(
            {f"f{i}": 1.0 / (i + 1) for i in range(20)}
        ).sort_values(ascending=False)


# ── The endpoint ─────────────────────────────────────────────────────────────


def test_endpoint_serves_the_real_deployed_artefact():
    res = TestClient(app).get("/api/governance/model")
    assert res.status_code == 200
    data = res.json()
    artefact = data["artefact"]
    assert artefact["exists"] is True
    # A real 64-hex digest of the committed binary, not a placeholder.
    assert artefact["sha256"] and len(artefact["sha256"]) == 64
    # Rendered for a browser, so POSIX separators on every host.
    assert "\\" not in artefact["path"]
    # Hyperparameters come off the loaded object, so they cannot drift from
    # what is actually serving.
    assert artefact["hyperparameters"]["n_estimators"] == 300
    assert artefact["feature_count"] and artefact["feature_count"] > 0
    assert len(artefact["top_features"]) <= artefact["feature_count"]
    # Ranked, descending — the page renders it as a ranking.
    weights = [f["importance"] for f in artefact["top_features"]]
    assert weights == sorted(weights, reverse=True)


def test_missing_registry_is_200_with_an_explicit_absent_flag():
    """A 404 would read as a broken endpoint and get retried; worse, an empty
    200 body with no flag would render as a reassuring blank page. The absence
    of a governance record has to be statable."""
    res = TestClient(app).get("/api/governance/model")
    data = res.json()
    if data["registry_present"]:
        pytest.skip("a registry.json exists in this checkout")
    assert data["champion"] is None
    assert data["versions"] == []
    # No metric is substituted from the README to fill the hole.
    assert data["artefact_matches_record"] is None
    # The bar is still stated even with nothing put through it.
    assert data["default_thresholds"]["min_roc_auc"] == 0.60


def test_response_is_strict_json():
    res = TestClient(app).get("/api/governance/model")
    json.dumps(res.json(), allow_nan=False)


# ── The snapshot, against a registry that actually has records ───────────────


def _registry_with_champion(tmp_path: Path) -> Path:
    path = tmp_path / "registry.json"
    registry = ModelRegistry(path)
    registry.register(
        "downside_risk",
        "1.0.0",
        metrics=dict(GOOD_METRICS),
        artefact_path=str(tmp_path / "artefacts" / "downside_risk_xgb.joblib"),
    )
    registry.validate("downside_risk", "1.0.0")
    registry.transition("downside_risk", "1.0.0", ModelStatus.APPROVED)
    registry.promote_to_active("downside_risk", "1.0.0", reason="first champion")
    return path


def test_snapshot_surfaces_the_champion_and_its_full_history(tmp_path):
    registry_path = _registry_with_champion(tmp_path)
    artefact = tmp_path / "artefacts" / "downside_risk_xgb.joblib"
    artefact.parent.mkdir(parents=True, exist_ok=True)
    artefact.write_bytes(b"not a real model")

    snap = governance_snapshot(
        model=_FakeModel(),
        registry_path=registry_path,
        artefact_path=artefact,
        repo_root=tmp_path,
    )

    assert snap["registry_present"] is True
    assert snap["champion"]["version"] == "1.0.0"
    assert snap["champion"]["status"] == "active"
    assert snap["champion"]["thresholds_pass"] is True
    # The whole lifecycle, not just the current state — the point of an
    # append-only log is that you can see the route the model took.
    route = [h["to"] for h in snap["champion"]["history"]]
    assert route == ["development", "validated", "approved", "active"]
    # Record and artefact agree, checked on the resolved path so a recorded
    # absolute path and a repo-relative one don't read as a mismatch.
    assert snap["artefact_matches_record"] is True


def test_snapshot_flags_a_record_pointing_at_a_different_artefact(tmp_path):
    """The failure this page exists to catch: a governance record describing a
    model that isn't the one being served."""
    registry_path = _registry_with_champion(tmp_path)
    served = tmp_path / "artefacts" / "some_other_model.joblib"
    served.parent.mkdir(parents=True, exist_ok=True)
    served.write_bytes(b"different binary")

    snap = governance_snapshot(
        model=_FakeModel(),
        registry_path=registry_path,
        artefact_path=served,
        repo_root=tmp_path,
    )
    assert snap["artefact_matches_record"] is False


def test_snapshot_reports_a_missing_model_without_raising(tmp_path):
    """ENABLE_ML=0 is a legitimate deployment state (the [F2/F3] memory
    toggle), not an error — the artefact can sit on disk unloaded."""
    artefact = tmp_path / "downside_risk_xgb.joblib"
    artefact.write_bytes(b"on disk but not loaded")

    snap = governance_snapshot(
        model=None,
        registry_path=tmp_path / "nope.json",
        artefact_path=artefact,
        repo_root=tmp_path,
    )
    assert snap["artefact"]["exists"] is True
    assert snap["artefact"]["loaded"] is False
    assert snap["artefact"]["top_features"] == []
    assert snap["artefact"]["feature_count"] is None


# ── The lifecycle graph ──────────────────────────────────────────────────────


def test_lifecycle_graph_is_the_enforced_table_not_a_drawing():
    """The page renders this graph as the governance claim, so it must be the
    same table `transition()` raises on — including the two edges whose absence
    is the entire control: you cannot go straight from development to active,
    and a degraded model cannot be waved back in."""
    graph = lifecycle_graph()
    edges = {s["state"]: set(s["to"]) for s in graph["states"]}
    assert "active" not in edges["development"]
    assert "active" not in edges["degraded"]
    assert edges["degraded"] == {"validated", "retired"}
    assert graph["terminal"] == ["retired"]
