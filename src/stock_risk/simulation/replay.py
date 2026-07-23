"""Human-readable journey replays, derived entirely from the event stream.

A replay reconstructs one user's session as a numbered story — what they viewed,
how they interpreted it, which misconceptions formed or were corrected, what they
intended to do, any safety intervention, and the residual risk — so a reviewer
can audit a single journey without reading raw JSONL. Because it is built only
from ``SimEvent``s, the JSONL log is the single source of truth; the Markdown and
JSON forms are two renderings of it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .events import EventLog, EventType, SimEvent


def build_replay(log: EventLog) -> dict[str, Any]:
    """Structured replay object for one user's event stream (JSON-serialisable)."""
    events = log.events
    if not events:
        return {"steps": [], "summary": {}}

    head = events[0]
    start = next((e for e in events if e.event_type is EventType.USER_SIMULATION_STARTED), head)
    completed = next(
        (e for e in reversed(events) if e.event_type is EventType.SIMULATION_COMPLETED), events[-1]
    )
    intent = next(
        (e for e in reversed(events) if e.event_type is EventType.USER_ACTION_INTENT_RECORDED),
        None,
    )

    steps: list[dict[str, Any]] = []
    for e in events:
        steps.append(
            {
                "step": e.step,
                "event": e.event_type.value,
                "score": e.score,
                "confidence_status": e.confidence_status,
                "intended_financial_action": e.intended_financial_action,
                "misconceptions": e.misconception_state,
                "detail": e.detail,
            }
        )

    initial_misc = set(start.misconception_state or [])
    final_misc = set(completed.misconception_state or [])
    return {
        "user_id": head.simulated_user_id,
        "archetype": head.archetype,
        "language": head.language,
        "scenario_id": head.scenario_id,
        "experiment_variant": head.experiment_variant,
        "accessibility_mode": head.accessibility_mode,
        "simulation_seed": head.simulation_seed,
        "config_hash": head.config_hash,
        "steps": steps,
        "summary": {
            "final_intended_action": (
                intent.intended_financial_action if intent else None
            ),
            "initial_misconceptions": sorted(initial_misc),
            "final_misconceptions": sorted(final_misc),
            "corrected": sorted(initial_misc - final_misc),
            "remaining": sorted(final_misc),
            "overreliance_detected": any(
                e.event_type is EventType.USER_OVERRELIANCE_DETECTED for e in events
            ),
        },
    }


def render_markdown(replay: dict[str, Any]) -> str:
    """A plain-language Markdown replay, in the style of the framework's example."""
    if not replay.get("steps"):
        return "# Replay\n\n(empty)\n"

    s = replay["summary"]
    lines: list[str] = []
    lines.append(f"# User journey replay — {replay['user_id']}")
    lines.append("")
    lines.append(
        f"**Archetype:** {replay['archetype']} | **Language:** {replay['language']} | "
        f"**Variant:** {replay['experiment_variant']} | "
        f"**Accessibility:** {replay['accessibility_mode']}"
    )
    lines.append(
        f"**Scenario:** {replay['scenario_id']} | **Seed:** {replay['simulation_seed']} | "
        f"**Config:** `{replay['config_hash']}`"
    )
    lines.append("")

    label = {
        EventType.SCORE_VIEWED.value: "Viewed score",
        EventType.COMPONENT_VIEWED.value: "Read a component breakdown",
        EventType.METHODOLOGY_VIEWED.value: "Read the plain-language meaning",
        EventType.UNCERTAINTY_VIEWED.value: "Saw an uncertainty cue",
        EventType.DATA_WARNING_VIEWED.value: "Saw a data-quality warning",
        EventType.DISCLAIMER_VIEWED.value: "Saw the disclaimer",
        EventType.MISCONCEPTION_DETECTED.value: "Formed a misconception",
        EventType.MISCONCEPTION_CORRECTED.value: "Corrected a misconception",
        EventType.USER_ACTION_INTENT_RECORDED.value: "Decided on an action",
        EventType.USER_OVERRELIANCE_DETECTED.value: "Over-relied on the score",
        EventType.PROFESSIONAL_HELP_PROMPT_VIEWED.value: "Considered professional advice",
        EventType.SIMULATION_COMPLETED.value: "Finished",
        EventType.USER_SIMULATION_STARTED.value: "Started",
    }

    n = 0
    for step in replay["steps"]:
        ev = step["event"]
        text = label.get(ev, ev)
        extra = ""
        if step.get("score") is not None and ev == EventType.SCORE_VIEWED.value:
            conf = step.get("confidence_status")
            shown = step["detail"].get("product_surfaced_confidence")
            intr = step["detail"].get("intrinsic_confidence")
            extra = f" — score {step['score']}/100 (shown confidence: {conf}"
            if shown is False and intr in {"low", "suppressed"}:
                extra += f"; true data confidence was **{intr}**, not shown to user)"
            else:
                extra += ")"
        if ev == EventType.MISCONCEPTION_DETECTED.value:
            extra = f" — {step['detail'].get('misconception')}"
        if ev == EventType.MISCONCEPTION_CORRECTED.value:
            extra = f" — {step['detail'].get('misconception')}"
        if ev == EventType.USER_ACTION_INTENT_RECORDED.value:
            extra = f" — intends to **{step['intended_financial_action']}**"
            reason = step["detail"].get("reason")
            if reason:
                extra += f"\n     _{reason}_"
        n += 1
        lines.append(f"{n}. {text}{extra}")

    lines.append("")
    lines.append("## Outcome")
    lines.append(f"- **Intended action:** {s['final_intended_action']}")
    lines.append(f"- **Misconceptions corrected:** {', '.join(s['corrected']) or 'none'}")
    lines.append(f"- **Misconceptions remaining:** {', '.join(s['remaining']) or 'none'}")
    lines.append(f"- **Over-relied on score:** {'yes' if s['overreliance_detected'] else 'no'}")
    lines.append("")
    lines.append(
        "> This is a simulated journey produced by developer-encoded behavioural "
        "priors. It is a hypothesis about a product risk, not evidence about a real person."
    )
    return "\n".join(lines) + "\n"


def write_replay(log: EventLog, out_dir: Path, stem: str) -> tuple[Path, Path]:
    """Write both JSON and Markdown replays; return their paths."""
    replay = build_replay(log)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"{stem}.json"
    md_path = out_dir / f"{stem}.md"
    json_path.write_text(json.dumps(replay, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(replay), encoding="utf-8")
    return json_path, md_path


def _find(events: list[SimEvent], event_type: EventType) -> SimEvent | None:
    return next((e for e in events if e.event_type is event_type), None)
