"""[R4] Model registry CLI — inspect and drive the model lifecycle.

    python scripts/registry.py list
    python scripts/registry.py show downside_risk 1.0.0
    python scripts/registry.py validate downside_risk 1.0.0
    python scripts/registry.py approve downside_risk 1.0.0 --actor laura
    python scripts/registry.py promote downside_risk 1.0.0 --reason "beat champion on AUC"
    python scripts/registry.py compare downside_risk 2.0.0
    python scripts/registry.py retire downside_risk 1.0.0 --reason "superseded"
    python scripts/registry.py rollback downside_risk

Transitions go through ModelRegistry, so the lifecycle rules and validation
gates apply here exactly as they do in code — this is a front-end to the state
machine, not a way around it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from stock_risk.governance import ModelRegistry, ModelStatus, TransitionError  # noqa: E402

DEFAULT_REGISTRY = Path("models/registry.json")

# Status -> a short symbol, so `list` is scannable at a glance.
_MARK = {
    ModelStatus.ACTIVE: "*",
    ModelStatus.SHADOW: "~",
    ModelStatus.DEGRADED: "!",
    ModelStatus.RETIRED: "x",
}


def _registry(args) -> ModelRegistry:
    return ModelRegistry(args.registry)


def cmd_list(args) -> int:
    registry = _registry(args)
    records = sorted(registry._records.values(), key=lambda r: (r.name, r.version))
    if not records:
        print(f"no models registered in {args.registry}")
        return 0
    print(f"{'':2s} {'MODEL':22s} {'VERSION':10s} {'STATUS':12s} {'AUC':>7s}  UPDATED")
    for record in records:
        auc = record.metrics.get("roc_auc")
        print(
            f"{_MARK.get(record.status, ' '):2s} "
            f"{record.name:22s} {record.version:10s} {record.status.value:12s} "
            f"{auc if auc is None else format(auc, '.4f'):>7} "
            f" {record.updated_at[:19]}"
        )
    print("\n* champion   ~ shadow challenger   ! degraded   x retired")
    return 0


def cmd_show(args) -> int:
    record = _registry(args).get(args.name, args.version)
    if record is None:
        print(f"{args.name} v{args.version} is not registered")
        return 1
    from dataclasses import asdict

    print(json.dumps(asdict(record), indent=2, sort_keys=True, default=str))
    return 0


def cmd_validate(args) -> int:
    try:
        record = _registry(args).validate(args.name, args.version, actor=args.actor)
    except TransitionError as exc:
        print(f"FAILED: {exc}")
        return 1
    print(f"{record.name} v{record.version} -> {record.status.value}")
    return 0


def cmd_approve(args) -> int:
    try:
        record = _registry(args).transition(
            args.name,
            args.version,
            ModelStatus.APPROVED,
            actor=args.actor,
            reason=args.reason or "approved for deployment",
        )
    except TransitionError as exc:
        print(f"FAILED: {exc}")
        return 1
    print(f"{record.name} v{record.version} -> {record.status.value}")
    return 0


def cmd_shadow(args) -> int:
    try:
        record = _registry(args).transition(
            args.name,
            args.version,
            ModelStatus.SHADOW,
            actor=args.actor,
            reason=args.reason or "running as challenger",
        )
    except TransitionError as exc:
        print(f"FAILED: {exc}")
        return 1
    print(f"{record.name} v{record.version} -> {record.status.value}")
    return 0


def cmd_promote(args) -> int:
    try:
        record = _registry(args).promote_to_active(
            args.name, args.version, actor=args.actor, reason=args.reason
        )
    except TransitionError as exc:
        print(f"FAILED: {exc}")
        return 1
    print(f"{record.name} v{record.version} is now the champion")
    return 0


def cmd_retire(args) -> int:
    try:
        record = _registry(args).retire(
            args.name, args.version, reason=args.reason, actor=args.actor
        )
    except (TransitionError, ValueError) as exc:
        print(f"FAILED: {exc}")
        return 1
    print(f"{record.name} v{record.version} retired: {record.retirement_reason}")
    return 0


def cmd_compare(args) -> int:
    result = _registry(args).compare(args.name, args.version)
    if result["champion"] is None:
        print(f"no champion registered for {args.name} — nothing to compare against")
        return 0
    print(f"champion v{result['champion']}  vs  challenger v{result['challenger']}")
    for metric, values in sorted(result["deltas"].items()):
        arrow = "better" if values["improvement"] > 0 else "worse "
        print(
            f"  {metric:20s} {values['champion']!s:>10} -> {values['challenger']!s:>10}"
            f"   {arrow} ({values['improvement']:+.6f})"
        )
    verdict = result["challenger_wins"]
    print(
        "\nverdict: challenger "
        + ("wins on ROC-AUC" if verdict else "does NOT beat the champion on ROC-AUC")
        if verdict is not None
        else "\nverdict: no comparable ROC-AUC recorded"
    )
    print("Promotion is deliberately a separate, human decision — see `promote`.")
    return 0


def cmd_rollback(args) -> int:
    """Name the rollback target after an automatic demotion.

    Prints rather than acts: rolling back is re-promoting a specific version,
    and doing that silently on a `rollback` command would skip the validation
    gate that promote_to_active enforces.
    """
    registry = _registry(args)
    previous = registry.previous_champion(args.name)
    if previous is None:
        print(f"no previous champion recorded for {args.name}")
        return 1
    current = registry.champion(args.name)
    print(f"current champion: {current.version if current else '(none — demoted)'}")
    print(f"rollback target:  v{previous.version} (status: {previous.status.value})")
    print(
        f"\nTo roll back:\n"
        f"  python scripts/registry.py approve {args.name} {previous.version}\n"
        f"  python scripts/registry.py promote {args.name} {previous.version} "
        f'--reason "rollback after breach"'
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--actor", default="cli", help="Recorded in the lifecycle history")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="All registered models and their status")

    for name, help_text in [
        ("show", "Full record as JSON"),
        ("validate", "Run the validation gate (DEVELOPMENT -> VALIDATED)"),
        ("approve", "Sign off (VALIDATED -> APPROVED)"),
        ("shadow", "Run as a challenger alongside the champion"),
        ("promote", "Make this version the champion"),
        ("retire", "Withdraw, with a recorded reason"),
        ("compare", "Compare this version against the current champion"),
    ]:
        p = sub.add_parser(name, help=help_text)
        p.add_argument("name")
        p.add_argument("version")
        if name in {"approve", "shadow", "promote", "retire"}:
            p.add_argument("--reason", default="")

    p_rollback = sub.add_parser("rollback", help="Show the rollback target after a demotion")
    p_rollback.add_argument("name")

    args = parser.parse_args()

    if args.cmd == "retire" and not args.reason:
        parser.error(
            "retire requires --reason (a retirement without a reason is not an audit trail)"
        )

    return {
        "list": cmd_list,
        "show": cmd_show,
        "validate": cmd_validate,
        "approve": cmd_approve,
        "shadow": cmd_shadow,
        "promote": cmd_promote,
        "retire": cmd_retire,
        "compare": cmd_compare,
        "rollback": cmd_rollback,
    }[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
