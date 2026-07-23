"""Seeded, inspectable distributions for drawing simulated-user traits.

Every trait an archetype declares is a *distribution*, not a constant — that is
the whole point of the "variation within the group" requirement: two first-time
retail investors sampled from the same archetype must be able to behave
differently (one happens to read disclaimers, one doesn't), while still being
recognisably that archetype on average.

Two primitives cover every field:

* ``Trait`` — a bounded continuous value in [0, 1], drawn from a truncated
  normal (mean +/- sd, clamped). Truncated-normal rather than Beta on purpose:
  ``mean`` and ``sd`` map directly onto "where this archetype centres and how
  spread out it is", which is exactly the knob a reviewer wants to reason about
  and sensitivity-test. ``sd == 0`` yields a constant (used sparingly).
* ``Choice`` — a categorical draw over typed options with weights.

All randomness flows through a ``numpy.random.Generator`` the caller owns, so
the stream is reproducible and — critically — *independent per user* when the
caller derives one generator per (seed, archetype, index) tuple. Nothing here
reads the wall clock or a global RNG.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, Sequence, TypeVar

import numpy as np

T = TypeVar("T")


@dataclass(frozen=True)
class Trait:
    """A bounded continuous trait ~ TruncNormal(mean, sd) clamped to [lo, hi].

    ``sd`` is the *spread* of the archetype on this trait; a larger value means
    more within-group variation. ``sd == 0`` collapses to a constant ``mean``.
    """

    mean: float
    sd: float = 0.15
    lo: float = 0.0
    hi: float = 1.0

    def __post_init__(self) -> None:
        if self.sd < 0:
            raise ValueError("Trait.sd must be non-negative")
        if not (self.lo <= self.mean <= self.hi):
            raise ValueError(f"Trait.mean {self.mean} outside [{self.lo}, {self.hi}]")

    def sample(self, rng: np.random.Generator) -> float:
        if self.sd == 0:
            return float(self.mean)
        value = rng.normal(self.mean, self.sd)
        return float(min(max(value, self.lo), self.hi))


@dataclass(frozen=True)
class Choice(Generic[T]):
    """A categorical trait: draw one option with the given (auto-normalised) weights."""

    options: Sequence[T]
    weights: Sequence[float]

    def __post_init__(self) -> None:
        if len(self.options) != len(self.weights):
            raise ValueError("Choice.options and weights must be the same length")
        if not self.options:
            raise ValueError("Choice needs at least one option")
        if any(w < 0 for w in self.weights):
            raise ValueError("Choice.weights must be non-negative")
        if sum(self.weights) <= 0:
            raise ValueError("Choice.weights must sum to a positive number")

    def sample(self, rng: np.random.Generator) -> T:
        total = float(sum(self.weights))
        probs = [w / total for w in self.weights]
        idx = int(rng.choice(len(self.options), p=probs))
        return self.options[idx]


@dataclass(frozen=True)
class Subset(Generic[T]):
    """Draw an independent yes/no for each option; returns those that came up true.

    Used for multi-valued fields such as accessibility needs, where a user may
    have none, one, or several. ``per_option_prob`` is the marginal probability
    of each option being present.
    """

    options: Sequence[T]
    per_option_prob: Sequence[float]

    def __post_init__(self) -> None:
        if len(self.options) != len(self.per_option_prob):
            raise ValueError("Subset.options and per_option_prob must be the same length")
        if any(not (0.0 <= p <= 1.0) for p in self.per_option_prob):
            raise ValueError("Subset.per_option_prob entries must be in [0, 1]")

    def sample(self, rng: np.random.Generator) -> tuple[T, ...]:
        return tuple(
            opt for opt, p in zip(self.options, self.per_option_prob) if rng.random() < p
        )


def derive_generator(seed: int, *stream: int) -> np.random.Generator:
    """A reproducible Generator for one independent stream.

    The stream key (e.g. ``(archetype_ordinal, user_index)``) is folded into the
    seed so that user 3 of archetype 2 always draws the same trait vector,
    independent of how many other users were generated first or in what order.
    """
    return np.random.default_rng([int(seed), *(int(s) for s in stream)])
