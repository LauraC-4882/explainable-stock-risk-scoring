"""Semantic event schema for the simulation and a deterministic JSONL log.

The served product only records coarse HTTP telemetry (a ``PageView`` per
request) and security/audit rows — there is no event that captures what a user
*noticed, understood, or intended*. This module supplies that missing semantic
layer, but scoped to the simulation: events are written to run-scoped JSONL
files under the reports directory, never into the production database (that was
an explicit scope decision — keep simulated data out of real analytics).

Every event carries the full context needed to slice results later (archetype,
language, scenario, experiment variant, seed, config hash, comprehension and
misconception state, the intended financial action, accessibility mode, and the
model/data provenance stamps). "Time" is a monotonic integer step, not a wall
clock, so a run is byte-reproducible.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class EventType(str, Enum):
    USER_SIMULATION_STARTED = "user_simulation_started"
    TICKER_SEARCHED = "ticker_searched"
    PORTFOLIO_CREATED = "portfolio_created"
    SCORE_VIEWED = "score_viewed"
    COMPONENT_VIEWED = "component_viewed"
    UNCERTAINTY_VIEWED = "uncertainty_viewed"
    METHODOLOGY_VIEWED = "methodology_viewed"
    MODEL_CARD_VIEWED = "model_card_viewed"
    DATA_WARNING_VIEWED = "data_warning_viewed"
    DISCLAIMER_VIEWED = "disclaimer_viewed"
    DISCLAIMER_ACKNOWLEDGED = "disclaimer_acknowledged"
    COMPREHENSION_ANSWERED = "comprehension_answered"
    MISCONCEPTION_DETECTED = "misconception_detected"
    MISCONCEPTION_CORRECTED = "misconception_corrected"
    STRESS_TEST_VIEWED = "stress_test_viewed"
    RISK_CONTRIBUTION_VIEWED = "risk_contribution_viewed"
    COMMUNITY_POST_VIEWED = "community_post_viewed"
    COMMUNITY_POST_REPORTED = "community_post_reported"
    SHARE_ATTEMPTED = "share_attempted"
    PROFESSIONAL_HELP_PROMPT_VIEWED = "professional_help_prompt_viewed"
    USER_ACTION_INTENT_RECORDED = "user_action_intent_recorded"
    USER_OVERRELIANCE_DETECTED = "user_overreliance_detected"
    WORKFLOW_ABANDONED = "workflow_abandoned"
    SIMULATION_COMPLETED = "simulation_completed"


class ConfidenceStatus(str, Enum):
    """The system's data/model confidence for a score, as surfaced to the user.

    Note: the *current product has no such field* — the simulation derives this
    from data-quality inputs precisely so it can test the "silent neutral 50"
    product risk (a score shown at NORMAL confidence when it should be LOW)."""

    NORMAL = "normal"
    LOW = "low"
    SUPPRESSED = "suppressed"
    UNKNOWN = "unknown"


class IntendedAction(str, Enum):
    """A user's intended *financial* action. Deliberately coarse and never a
    recommendation FROM the system — this is what the simulated user says they
    would do, an outcome to be measured (panic-sell intent is a harm, not a KPI).
    """

    NONE = "none"
    HOLD = "hold"
    RESEARCH_MORE = "research_more"
    REDUCE_POSITION = "reduce_position"
    SELL_ALL = "sell_all"           # panic / full exit
    BUY = "buy"
    BUY_MORE = "buy_more"
    SEEK_PROFESSIONAL_ADVICE = "seek_professional_advice"
    SHARE = "share"
    ABANDON = "abandon"


@dataclass(frozen=True)
class SimEvent:
    """One semantic event. Field names mirror the framework's required schema."""

    event_type: EventType
    step: int                       # monotonic "simulated time"
    simulated_user_id: str
    archetype: str
    language: str
    scenario_id: str
    experiment_variant: str
    simulation_seed: int
    config_hash: str
    accessibility_mode: str
    model_version: Optional[str] = None
    data_timestamp: Optional[str] = None
    ticker: Optional[str] = None
    score: Optional[float] = None
    confidence_status: str = ConfidenceStatus.UNKNOWN.value
    action: Optional[str] = None                 # UI-level action (what screen/thing)
    intended_financial_action: Optional[str] = None
    comprehension_state: dict[str, Any] = field(default_factory=dict)
    misconception_state: list[str] = field(default_factory=list)
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["event_type"] = self.event_type.value
        return d


def config_hash(config: dict[str, Any]) -> str:
    """Stable short hash of a run configuration (sorted-keys JSON, sha256[:12])."""
    blob = json.dumps(config, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:12]


@dataclass
class EventLog:
    """Accumulates events in memory and can flush them to JSONL.

    Holding in memory first keeps the run deterministic and lets tests assert on
    the event stream without touching disk; ``write_jsonl`` is the only I/O.
    """

    events: list[SimEvent] = field(default_factory=list)
    _step: int = 0

    def emit(self, event_type: EventType, **kwargs: Any) -> SimEvent:
        event = SimEvent(event_type=event_type, step=self._step, **kwargs)
        self._step += 1
        self.events.append(event)
        return event

    def of_type(self, event_type: EventType) -> list[SimEvent]:
        return [e for e in self.events if e.event_type is event_type]

    def to_records(self) -> list[dict[str, Any]]:
        return [e.to_dict() for e in self.events]

    def write_jsonl(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fh:
            for event in self.events:
                fh.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")
        return path
