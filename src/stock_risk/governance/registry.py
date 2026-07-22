"""[R4] Model registry: lifecycle, validation gating, champion–challenger.

The project already had the *ingredients* of model governance — walk-forward
validation, isotonic calibration, drift monitoring, and a rule that unvalidated
signals ship at zero weight. What it lacked was a place where any of that was
recorded. "Is this model approved?" was answered by reading a README section;
"which version is deployed?" by looking at a file's mtime; "why was the old one
retired?" by nothing at all.

This makes those answerable and enforceable:

* **Explicit lifecycle.** A model is in exactly one state, and the legal
  transitions are declared rather than implied. You cannot promote straight
  from `development` to `active` — validation is a state you must pass
  *through*, which is the whole point of having states.
* **Validation gating with teeth.** `promote_to_active` refuses a model whose
  recorded metrics fail the registered thresholds. The gate is data, not a
  code review convention someone can forget.
* **Champion–challenger.** Exactly one `active` champion per model name; any
  number of `shadow` challengers scored against it. Promotion is a comparison,
  not a vibe.
* **Automatic demotion.** A champion breaching its drift or performance
  thresholds is demoted to `degraded` and the previous champion is available
  for rollback — the failure mode this whole module exists for.
* **Retirement with a reason.** A retired model keeps its record and states why
  it went. "We turned that off at some point, I think because it wasn't
  working" is not an audit trail.

Deliberately a JSON-file registry rather than a database table. It has to be
readable and diffable in a pull request — a governance record whose history
lives only in a database is one nobody reviews — and it must work in the
training script, in CI, and inside a Docker image with no database attached.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

from loguru import logger


class ModelStatus(str, Enum):
    """Lifecycle states, in the order a model normally travels through them."""

    DEVELOPMENT = "development"  # trained, nothing claimed about it
    VALIDATED = "validated"  # passed walk-forward; not yet approved for use
    APPROVED = "approved"  # signed off; eligible to be deployed
    SHADOW = "shadow"  # scored live alongside the champion, not served
    ACTIVE = "active"  # the champion; its output is served
    DEGRADED = "degraded"  # breached a threshold; auto-demoted, needs review
    RETIRED = "retired"  # withdrawn, with a recorded reason


# Legal transitions. Declared as data so an illegal one is a raised error and
# not a silently-accepted string assignment — the reason `status` is not just a
# free-text field.
#
# DEVELOPMENT -> ACTIVE is deliberately absent: skipping validation is exactly
# what this table exists to prevent. DEGRADED -> ACTIVE is also absent; a model
# that breached a threshold goes back through validation, it does not get
# waved through because the metric recovered on its own.
_TRANSITIONS: dict[ModelStatus, set[ModelStatus]] = {
    ModelStatus.DEVELOPMENT: {ModelStatus.VALIDATED, ModelStatus.RETIRED},
    ModelStatus.VALIDATED: {ModelStatus.APPROVED, ModelStatus.DEVELOPMENT, ModelStatus.RETIRED},
    ModelStatus.APPROVED: {ModelStatus.SHADOW, ModelStatus.ACTIVE, ModelStatus.RETIRED},
    ModelStatus.SHADOW: {ModelStatus.ACTIVE, ModelStatus.APPROVED, ModelStatus.RETIRED},
    ModelStatus.ACTIVE: {ModelStatus.DEGRADED, ModelStatus.RETIRED},
    ModelStatus.DEGRADED: {ModelStatus.VALIDATED, ModelStatus.RETIRED},
    ModelStatus.RETIRED: set(),  # terminal; register a new version instead
}


class TransitionError(RuntimeError):
    """An illegal lifecycle transition, or one blocked by a validation gate."""


@dataclass
class ValidationThresholds:
    """The bar a model must clear to be served, recorded with the model.

    Stored per-model rather than as a global constant so a challenger with a
    different objective can carry a different bar, and so tightening the bar for
    a new model doesn't retroactively invalidate an old record.

    Defaults come from what this project has actually measured: the production
    downside-risk model reached 0.671 mean walk-forward AUC (README "Does the
    XGBoost signal actually work?"), so 0.60 is a floor that a genuinely
    uninformative model — the 0.56 first attempt, essentially a coin flip —
    would not clear.
    """

    min_roc_auc: float = 0.60
    max_brier: float = 0.25
    # PSI > 0.2 is the conventional "significant population shift" line, and is
    # what monitoring/drift.py already alerts on.
    max_drift_psi: float = 0.20
    # Calibration must not be worse than the uncalibrated model — if isotonic
    # calibration made Brier worse, something is wrong with the calibration
    # slice, not with the metric.
    require_calibration_improves_brier: bool = True

    def evaluate(self, metrics: dict) -> tuple[bool, list[str]]:
        """(passed, reasons_it_failed). Missing metrics fail rather than pass.

        A model with no recorded AUC is not a model that passed — treating
        absent evidence as satisfied is precisely how ungated models reach
        production.
        """
        failures: list[str] = []

        auc = metrics.get("roc_auc")
        if auc is None:
            failures.append("roc_auc not recorded")
        elif auc < self.min_roc_auc:
            failures.append(f"roc_auc {auc:.4f} < required {self.min_roc_auc}")

        brier = metrics.get("brier_calibrated", metrics.get("brier"))
        if brier is None:
            failures.append("brier not recorded")
        elif brier > self.max_brier:
            failures.append(f"brier {brier:.4f} > allowed {self.max_brier}")

        if self.require_calibration_improves_brier:
            raw = metrics.get("brier_raw")
            calibrated = metrics.get("brier_calibrated")
            if raw is not None and calibrated is not None and calibrated > raw:
                failures.append(
                    f"calibration made Brier worse ({raw:.4f} -> {calibrated:.4f})"
                )

        psi = metrics.get("max_drift_psi")
        if psi is not None and psi > self.max_drift_psi:
            failures.append(f"drift PSI {psi:.4f} > allowed {self.max_drift_psi}")

        return (not failures), failures


@dataclass
class ModelCard:
    """Human-readable documentation, kept with the model rather than in a wiki.

    Structured after the Mitchell et al. (2019) model-card framing, trimmed to
    the fields this project can actually fill in honestly. `limitations` and
    `ethical_considerations` are required-by-convention: a model card whose
    weaknesses section is empty is marketing, and this project's whole posture
    is that the weaknesses are stated (see README's "What's still weak, stated
    plainly").
    """

    intended_use: str
    out_of_scope_uses: list[str] = field(default_factory=list)
    training_data: str = ""
    evaluation_data: str = ""
    limitations: list[str] = field(default_factory=list)
    ethical_considerations: list[str] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)


@dataclass
class ModelRecord:
    """One version of one model, and everything governance needs to know."""

    name: str
    version: str
    status: ModelStatus
    created_at: str
    updated_at: str
    # Path to the serialised artefact, relative to the repo root.
    artefact_path: Optional[str] = None
    # Path to the [R5] reproducibility manifest for the run that produced it.
    manifest_path: Optional[str] = None
    dataset_hash: Optional[str] = None
    git_commit: Optional[str] = None
    feature_schema_version: Optional[str] = None
    metrics: dict = field(default_factory=dict)
    thresholds: dict = field(default_factory=lambda: asdict(ValidationThresholds()))
    model_card: Optional[dict] = None
    # Append-only lifecycle history: (timestamp, from, to, actor, reason).
    history: list[dict] = field(default_factory=list)
    retirement_reason: Optional[str] = None
    # For a challenger: which champion version it is being compared against.
    challenger_to: Optional[str] = None
    notes: Optional[str] = None

    def thresholds_obj(self) -> ValidationThresholds:
        return ValidationThresholds(**self.thresholds)


class ModelRegistry:
    """JSON-backed registry of model versions and their lifecycle state."""

    def __init__(self, path: Path | str = Path("models/registry.json")):
        self.path = Path(path)
        self._records: dict[tuple[str, str], ModelRecord] = {}
        self._load()

    # ── persistence ──────────────────────────────────────────────────────────

    def _load(self) -> None:
        if not self.path.exists():
            return
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        for entry in raw.get("models", []):
            entry["status"] = ModelStatus(entry["status"])
            record = ModelRecord(**entry)
            self._records[(record.name, record.version)] = record

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": "1.0",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            # Sorted so the file diffs cleanly in review — an unordered dump
            # produces spurious churn that hides the real change.
            "models": [
                asdict(record) for _, record in sorted(self._records.items())
            ],
        }
        self.path.write_text(
            json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8"
        )

    # ── queries ──────────────────────────────────────────────────────────────

    def get(self, name: str, version: str) -> Optional[ModelRecord]:
        return self._records.get((name, version))

    def versions(self, name: str) -> list[ModelRecord]:
        return [r for (n, _), r in sorted(self._records.items()) if n == name]

    def champion(self, name: str) -> Optional[ModelRecord]:
        """The single ACTIVE version, or None."""
        for record in self.versions(name):
            if record.status == ModelStatus.ACTIVE:
                return record
        return None

    def challengers(self, name: str) -> list[ModelRecord]:
        return [r for r in self.versions(name) if r.status == ModelStatus.SHADOW]

    def previous_champion(self, name: str) -> Optional[ModelRecord]:
        """Most recently demoted/retired version that was once ACTIVE.

        This is the rollback target. Derived from history rather than stored as
        a pointer, so it stays correct no matter how the transitions happened.
        """
        candidates = [
            r
            for r in self.versions(name)
            if r.status in {ModelStatus.DEGRADED, ModelStatus.RETIRED, ModelStatus.APPROVED}
            and any(h.get("from") == ModelStatus.ACTIVE.value for h in r.history)
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda r: r.updated_at)

    # ── mutations ────────────────────────────────────────────────────────────

    def register(
        self,
        name: str,
        version: str,
        *,
        artefact_path: Optional[str] = None,
        manifest_path: Optional[str] = None,
        dataset_hash: Optional[str] = None,
        git_commit: Optional[str] = None,
        feature_schema_version: Optional[str] = None,
        metrics: Optional[dict] = None,
        thresholds: Optional[ValidationThresholds] = None,
        model_card: Optional[ModelCard] = None,
        notes: Optional[str] = None,
    ) -> ModelRecord:
        """Register a newly trained model in DEVELOPMENT.

        Every model starts here regardless of how good its metrics look — the
        state machine, not the caller, decides what it's eligible for.
        """
        key = (name, version)
        if key in self._records:
            raise ValueError(
                f"{name} v{version} is already registered. Model versions are immutable — "
                "register a new version rather than overwriting a governance record."
            )
        now = datetime.now(timezone.utc).isoformat()
        record = ModelRecord(
            name=name,
            version=version,
            status=ModelStatus.DEVELOPMENT,
            created_at=now,
            updated_at=now,
            artefact_path=artefact_path,
            manifest_path=manifest_path,
            dataset_hash=dataset_hash,
            git_commit=git_commit,
            feature_schema_version=feature_schema_version,
            metrics=metrics or {},
            thresholds=asdict(thresholds or ValidationThresholds()),
            model_card=asdict(model_card) if model_card else None,
            notes=notes,
            history=[
                {
                    "at": now,
                    "from": None,
                    "to": ModelStatus.DEVELOPMENT.value,
                    "actor": "system",
                    "reason": "registered",
                }
            ],
        )
        self._records[key] = record
        self.save()
        logger.info(f"[registry] registered {name} v{version} (development)")
        return record

    def transition(
        self,
        name: str,
        version: str,
        to: ModelStatus,
        *,
        actor: str = "system",
        reason: str = "",
        force: bool = False,
    ) -> ModelRecord:
        """Move a model to a new lifecycle state, enforcing the legal graph."""
        record = self._require(name, version)
        if to != record.status and to not in _TRANSITIONS[record.status] and not force:
            allowed = ", ".join(sorted(s.value for s in _TRANSITIONS[record.status])) or "(none)"
            raise TransitionError(
                f"{name} v{version}: {record.status.value} -> {to.value} is not a legal "
                f"transition. Allowed from {record.status.value}: {allowed}."
            )

        now = datetime.now(timezone.utc).isoformat()
        record.history.append(
            {
                "at": now,
                "from": record.status.value,
                "to": to.value,
                "actor": actor,
                "reason": reason or None,
                "forced": force or None,
            }
        )
        record.status = to
        record.updated_at = now
        self.save()
        logger.info(f"[registry] {name} v{version}: -> {to.value} ({reason or 'no reason given'})")
        return record

    def validate(self, name: str, version: str, *, actor: str = "system") -> ModelRecord:
        """Move DEVELOPMENT -> VALIDATED, but only if the metrics clear the bar.

        This is the gate. Failing it raises rather than warning — a validation
        step that can be ignored is documentation, not a control.
        """
        record = self._require(name, version)
        passed, failures = record.thresholds_obj().evaluate(record.metrics)
        if not passed:
            raise TransitionError(
                f"{name} v{version} failed validation: " + "; ".join(failures)
            )
        return self.transition(
            name, version, ModelStatus.VALIDATED, actor=actor, reason="passed validation thresholds"
        )

    def promote_to_active(
        self, name: str, version: str, *, actor: str = "system", reason: str = ""
    ) -> ModelRecord:
        """Make this version the champion, demoting the incumbent.

        Enforces one champion per model name. Two ACTIVE versions is not a
        harmless bookkeeping slip — it means "which model produced this score?"
        has no answer, which invalidates every downstream record.
        """
        record = self._require(name, version)
        passed, failures = record.thresholds_obj().evaluate(record.metrics)
        if not passed:
            raise TransitionError(
                f"refusing to promote {name} v{version}: " + "; ".join(failures)
            )

        incumbent = self.champion(name)
        if incumbent and incumbent.version != version:
            self.transition(
                name,
                incumbent.version,
                ModelStatus.RETIRED,
                actor=actor,
                reason=f"superseded by v{version}",
            )
            incumbent.retirement_reason = f"superseded by v{version}"

        promoted = self.transition(
            name, version, ModelStatus.ACTIVE, actor=actor, reason=reason or "promoted to champion"
        )
        self.save()
        return promoted

    def demote(
        self, name: str, version: str, *, reason: str, actor: str = "monitor"
    ) -> ModelRecord:
        """Mark a champion DEGRADED. Called by the automatic breach check."""
        return self.transition(
            name, version, ModelStatus.DEGRADED, actor=actor, reason=reason
        )

    def retire(
        self, name: str, version: str, *, reason: str, actor: str = "system"
    ) -> ModelRecord:
        """Withdraw a model, recording why.

        The reason is required, not optional: "we turned that off at some point,
        I think because it wasn't working" is not an audit trail.
        """
        if not reason.strip():
            raise ValueError("a retirement reason is required")
        record = self.transition(name, version, ModelStatus.RETIRED, actor=actor, reason=reason)
        record.retirement_reason = reason
        self.save()
        return record

    def check_for_breach(
        self, name: str, live_metrics: dict, *, actor: str = "monitor"
    ) -> Optional[ModelRecord]:
        """Demote the champion if live metrics breach its registered thresholds.

        This is the automatic half of governance. A champion whose live AUC or
        drift has crossed its own recorded bar is demoted without waiting for
        someone to notice — and `previous_champion()` then names the rollback
        target.

        Returns the demoted record, or None if the champion is fine (or there
        isn't one).
        """
        champion = self.champion(name)
        if champion is None:
            return None
        passed, failures = champion.thresholds_obj().evaluate(
            {**champion.metrics, **live_metrics}
        )
        if passed:
            return None
        return self.demote(
            name, champion.version, reason="threshold breach: " + "; ".join(failures), actor=actor
        )

    def compare(self, name: str, challenger_version: str) -> dict:
        """Champion vs. challenger on their recorded metrics.

        Returns the per-metric deltas plus a `challenger_wins` verdict. It does
        NOT promote — the point of champion–challenger is that promotion is a
        decision someone makes on evidence, and automating it away would remove
        the only step where a human looks at whether the improvement is real.
        """
        challenger = self._require(name, challenger_version)
        champion = self.champion(name)
        if champion is None:
            return {"champion": None, "challenger": challenger_version, "challenger_wins": None}

        # Lower-is-better metrics, so a naive "bigger delta wins" is wrong.
        lower_is_better = {"brier", "brier_raw", "brier_calibrated", "max_drift_psi"}
        deltas = {}
        for key in set(champion.metrics) | set(challenger.metrics):
            a, b = champion.metrics.get(key), challenger.metrics.get(key)
            if isinstance(a, (int, float)) and isinstance(b, (int, float)):
                improvement = (a - b) if key in lower_is_better else (b - a)
                deltas[key] = {"champion": a, "challenger": b, "improvement": round(improvement, 6)}

        primary = deltas.get("roc_auc")
        return {
            "champion": champion.version,
            "challenger": challenger_version,
            "deltas": deltas,
            "challenger_wins": (primary["improvement"] > 0) if primary else None,
        }

    def _require(self, name: str, version: str) -> ModelRecord:
        record = self.get(name, version)
        if record is None:
            raise KeyError(f"{name} v{version} is not registered")
        return record
