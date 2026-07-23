"""CLI: run the simulated-user evaluation and write the report artifacts.

    python -m stock_risk.simulation --out simulation_reports --seed 2026 --per-archetype 12
    python -m stock_risk.simulation replay --archetype first_time_retail

Deterministic: the same --seed and --per-archetype reproduce byte-identical output.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m stock_risk.simulation",
        description="Simulated-user evaluation harness (offline, seeded).",
    )
    sub = parser.add_subparsers(dest="command")

    run_p = sub.add_parser("run", help="run the full evaluation and write all artifacts")
    run_p.add_argument("--out", default="simulation_reports", type=Path)
    run_p.add_argument("--seed", default=2026, type=int)
    run_p.add_argument("--per-archetype", default=12, type=int)

    rep_p = sub.add_parser("replay", help="print one human-readable journey replay")
    rep_p.add_argument("--archetype", default="first_time_retail")
    rep_p.add_argument("--seed", default=7, type=int)

    # Default to `run` when no subcommand is given.
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    if args.command is None:
        args = parser.parse_args(["run", *(argv if argv is not None else sys.argv[1:])])

    if args.command == "run":
        from .report import generate_all

        manifest = generate_all(args.out, seed=args.seed, per_archetype=args.per_archetype)
        print(f"Wrote {len(manifest.files)} artifacts to {args.out}/")
        for f in sorted(manifest.files):
            print(f"  {f}")
        return 0

    if args.command == "replay":
        from .events import config_hash
        from .presentation import PresentationVariant
        from .profiles import Archetype, generate_population
        from .replay import build_replay, render_markdown
        from .tasks import run_single_stock_analysis

        archetype = Archetype(args.archetype)
        user = generate_population(seed=2026, per_archetype=1, archetypes=(archetype,))[0]
        log = run_single_stock_analysis(
            user, seed=args.seed, config_hash=config_hash({"cli": "replay"}),
            variant=PresentationVariant.AS_IS,
        )
        print(render_markdown(build_replay(log)))
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
