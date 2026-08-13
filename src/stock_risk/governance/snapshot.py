"""Read-only governance view: what is actually deployed, and what is recorded.

The registry ([R4]) and the reproducibility manifests ([R5]) were written to be
*enforceable* — `promote_to_active` refuses a model that fails its thresholds,
`register` refuses to overwrite a version. But nothing ever read them back out,
so "which model is serving my score, and who approved it?" was still answered by
opening a JSON file in the repo. This assembles that answer for the API.

Two rules shape everything below, and they are the reason this module is more
than a `json.load`:

**Recorded and derived facts are kept apart.** A registry record is a governance
claim someone made at training time. The artefact on disk, its hash, its commit
date and its feature importances are facts about the binary that is answering
requests right now. Merging them into one flat blob would let a stale registry
entry describe a file it no longer matches — the single failure this page exists
to catch. `registry` and `artefact` are separate keys, and `artefact.sha256` is
cross-checked against the record so a mismatch surfaces instead of hiding.

**Absent is not the same as passing.** The committed champion predates the
registry: `models/registry.json` does not exist in a fresh clone, so
`registry_present` is False and every recorded field is null. That state renders
as "no governance record" rather than as a blank-but-reassuring page, and no
metric is substituted from the README to fill the hole. Same principle as the
VaR backtest panel: a governance view that always looks healthy is marketing.
Run `python scripts/train.py --version X.Y.Z` to produce a real record.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Optional

from loguru import logger

from .lineage import FEATURE_SCHEMA_VERSION
from .registry import _TRANSITIONS, ModelRegistry, ModelStatus, ValidationThresholds

# How many features the importance ranking returns. The full one-hot expanded
# schema is ~40 columns and a ranked list that long is a data dump, not a
# finding; the tail is uniformly near-zero importance.
TOP_FEATURES = 12


def _git(*args: str, cwd: Optional[Path] = None) -> Optional[str]:
    """A git query that returns None outside a checkout instead of raising.

    Deployed images frequently have no `.git` (and no `git` binary). That makes
    the commit fields genuinely unknown, which is a null — not an error worth
    500ing a read-only governance page over.
    """
    try:
        result = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
            cwd=str(cwd) if cwd else None,
        )
        return result.stdout.strip() or None
    except Exception as exc:  # noqa: BLE001 - see docstring: absence is expected
        logger.debug(f"[governance] git {' '.join(args)} unavailable: {exc}")
        return None


def _artefact_provenance(path: Path, repo_root: Path) -> dict:
    """When the deployed binary last changed, from git rather than from mtime.

    mtime is what a naive version of this used and it is wrong on every platform
    that matters: `git clone` and `pip install` both stamp mtime to the moment
    of checkout, so a two-month-old model reads as "trained today" on a fresh
    deploy. The commit that last touched the file is the real answer, and it
    survives being copied into a container.
    """
    line = _git(
        "log", "-1", "--format=%H%x1f%aI%x1f%s", "--", str(path), cwd=repo_root
    )
    if not line:
        return {"commit": None, "committed_at": None, "subject": None}
    sha, _, rest = line.partition("\x1f")
    committed_at, _, subject = rest.partition("\x1f")
    return {"commit": sha, "committed_at": committed_at or None, "subject": subject or None}


def _sha256(path: Path) -> Optional[str]:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError as exc:
        logger.warning(f"[governance] could not hash {path}: {exc}")
        return None


def artefact_snapshot(model, artefact_path: Path, repo_root: Path) -> dict:
    """Facts about the binary currently answering requests.

    `model` is the already-loaded instance the scorer is serving from, not a
    fresh load off disk — reading the deployed object is the point. The hash and
    provenance still come from the file, so a hand-edited artefact that was never
    committed shows up as a hash with no commit behind it.
    """
    importance: list[dict] = []
    feature_count: Optional[int] = None
    try:
        if model is None:
            raise RuntimeError("no model loaded (ENABLE_ML=0 or artefact missing)")
        ranked = model.feature_importance()
        # Count before truncating — the page states "top 12 of N", and taking
        # the length of the truncated list would report 12 of 12.
        feature_count = int(len(ranked))
        importance = [
            {"feature": str(name), "importance": round(float(value), 6)}
            for name, value in ranked.head(TOP_FEATURES).items()
        ]
    except Exception as exc:  # noqa: BLE001
        # Fallback/base-rate mode raises by design (downside_risk.py), and
        # ENABLE_ML=0 means there is no booster at all. Both are legitimate
        # states for a running deployment, reported as an empty ranking.
        logger.info(f"[governance] no feature importance available: {exc}")

    exists = artefact_path.exists()
    try:
        # POSIX separators regardless of host OS: this string is rendered in a
        # browser and read as a repo path, and `models\artefacts\...` from a
        # Windows dev box is not a path anyone can paste anywhere.
        display_path = artefact_path.relative_to(repo_root).as_posix()
    except ValueError:
        # Artefact outside the repo (a mounted volume, a test tmpdir) — an
        # absolute path is the honest rendering, not a ../../ climb.
        display_path = artefact_path.as_posix()

    return {
        "path": display_path,
        "exists": exists,
        # False when ENABLE_ML=0 or the load failed: the artefact can be present
        # on disk and still not be what is answering requests.
        "loaded": model is not None,
        "size_bytes": artefact_path.stat().st_size if exists else None,
        "sha256": _sha256(artefact_path) if exists else None,
        "provenance": _artefact_provenance(artefact_path, repo_root),
        "hyperparameters": dict(getattr(model, "_params", {}) or {}),
        "calibrated": getattr(model, "calibrated", None) is not None,
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "feature_count": feature_count,
        "top_features": importance,
    }


def _record_view(record) -> dict:
    """One registry record, flattened for the wire.

    History is included in full and never trimmed to the last entry: the whole
    value of an append-only lifecycle log is that you can see a model went
    active -> degraded -> validated -> active, and a view that shows only the
    current state is exactly the "read the status field" answer the registry
    replaced.
    """
    passed, failures = record.thresholds_obj().evaluate(record.metrics)
    return {
        "name": record.name,
        "version": record.version,
        "status": record.status.value,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
        "metrics": record.metrics,
        "thresholds": record.thresholds,
        "thresholds_pass": passed,
        "threshold_failures": failures,
        "dataset_hash": record.dataset_hash,
        "git_commit": record.git_commit,
        "feature_schema_version": record.feature_schema_version,
        "artefact_path": record.artefact_path,
        "manifest_path": record.manifest_path,
        "model_card": record.model_card,
        "history": record.history,
        "retirement_reason": record.retirement_reason,
        "challenger_to": record.challenger_to,
    }


def lifecycle_graph() -> dict:
    """The legal transition table, served as data.

    Rendered rather than described because the enforcement is the claim: the
    page can show that development -> active has no edge, which is the same
    table `transition()` raises on. A diagram drawn by hand in the UI would be a
    picture of the intended rules; this is the rules.
    """
    return {
        "states": [
            {"state": status.value, "to": sorted(s.value for s in allowed)}
            for status, allowed in _TRANSITIONS.items()
        ],
        "terminal": [
            status.value for status, allowed in _TRANSITIONS.items() if not allowed
        ],
    }


def governance_snapshot(
    *,
    model,
    model_name: str = "downside_risk",
    registry_path: Path,
    artefact_path: Path,
    repo_root: Path,
) -> dict:
    """Everything the governance page renders, in one read.

    Cheap enough to compute per request except for the artefact hash (~0.5 MB,
    sub-millisecond) — the caller caches it anyway because the answer only
    changes on redeploy.
    """
    artefact = artefact_snapshot(model, artefact_path, repo_root)

    registry_present = registry_path.exists()
    champion: Optional[dict] = None
    versions: list[dict] = []
    challengers: list[dict] = []
    previous: Optional[dict] = None

    if registry_present:
        registry = ModelRegistry(registry_path)
        versions = [_record_view(r) for r in registry.versions(model_name)]
        champion_record = registry.champion(model_name)
        champion = _record_view(champion_record) if champion_record else None
        challengers = [_record_view(r) for r in registry.challengers(model_name)]
        previous_record = registry.previous_champion(model_name)
        previous = _record_view(previous_record) if previous_record else None

    # The cross-check that makes the two halves worth keeping apart: a champion
    # record that points at a different file from the one being served is a
    # governance record describing a model that isn't there.
    #
    # Compared on the resolved path, not on the recorded string — `register()`
    # stores whatever path the training run was invoked with, so an absolute
    # Windows path and a repo-relative POSIX one can name the same file and must
    # not read as a mismatch. None means "no record to check against", which is
    # deliberately distinct from False.
    artefact_matches_record: Optional[bool] = None
    if champion and champion.get("artefact_path"):
        recorded = Path(champion["artefact_path"])
        if not recorded.is_absolute():
            recorded = repo_root / recorded
        try:
            artefact_matches_record = recorded.resolve() == artefact_path.resolve()
        except OSError:
            artefact_matches_record = False

    # Repo-relative and POSIX, same reasoning as the artefact path: the page
    # prints this in the "no record" copy, and an absolute
    # C:\Users\...\models\registry.json from whichever machine built the image
    # is neither pasteable nor meaningful to the reader.
    try:
        registry_display = registry_path.relative_to(repo_root).as_posix()
    except ValueError:
        registry_display = registry_path.as_posix()

    return {
        "model_name": model_name,
        "registry_present": registry_present,
        "registry_path": registry_display,
        "champion": champion,
        "challengers": challengers,
        "previous_champion": previous,
        "versions": versions,
        "artefact": artefact,
        "artefact_matches_record": artefact_matches_record,
        "lifecycle": lifecycle_graph(),
        # Served even with no records so the page can state the bar a model
        # would have to clear — the gate exists whether or not anything has been
        # put through it.
        "default_thresholds": {
            "min_roc_auc": ValidationThresholds().min_roc_auc,
            "max_brier": ValidationThresholds().max_brier,
            "max_drift_psi": ValidationThresholds().max_drift_psi,
            "require_calibration_improves_brier": (
                ValidationThresholds().require_calibration_improves_brier
            ),
        },
        "statuses": [s.value for s in ModelStatus],
    }


def load_manifest(path: Path) -> Optional[dict]:
    """Read a [R5] reproducibility manifest, or None if it isn't there."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning(f"[governance] unreadable manifest {path}: {exc}")
        return None
