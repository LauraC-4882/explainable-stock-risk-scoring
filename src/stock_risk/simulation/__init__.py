"""Simulated-user evaluation framework for the risk platform.

This package is an **offline, deterministic evaluation harness**, not part of
the served product. It generates typed simulated users from seeded
distributions, drives them through realistic tasks against the platform's
*real* pure functions (scoring, outcomes, portfolio, tail tests) rendered into
per-screen "views", and records what each user *notices, understands,
misunderstands, and intends to do* — with a bias toward surfacing product
risks (over-trust, probability confusion, panic, concentration blindness,
accessibility and language gaps) rather than optimising engagement.

Design commitments (enforced by tests, see tests/test_sim_*.py):

* **Deterministic** — the same seed + configuration produces byte-identical
  output. No wall-clock, no unseeded randomness.
* **Offline** — never touches the network; the "system under test" is exercised
  through committed fixtures and seeded synthetic inputs, honouring the
  project's offline-gate rule (CLAUDE.md §2).
* **Honest** — simulated users are developer-encoded priors, NOT people. Every
  generated report carries the "cannot-claim-yet" banner (see report.py). The
  behavioural coefficients live in versioned config, not scattered magic
  numbers, so they can be inspected and sensitivity-tested.
* **Non-advisory** — the simulation never emits, and asserts it never emits,
  personalised buy/sell/allocation guidance, and never describes a risk score
  as a probability of loss unless it genuinely is one.
"""

from __future__ import annotations

__all__ = [
    "profiles",
    "distributions",
]
