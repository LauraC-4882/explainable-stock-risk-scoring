"""Product-experience fairness: comprehension/harm disparities across segments.

This module makes NO demographic claims — there is no demographic data. It
measures *product-experience* disparities across simulated dimensions the
framework can legitimately vary: financial literacy, numeracy, language, visual
accessibility, technical experience, portfolio complexity, and data coverage.
The output is a per-segment rate for a chosen outcome plus disparity summaries
(the gap and ratio between the best- and worst-served segments).

The vocabulary is deliberately "comprehension disparity", "accessibility
disparity", "data-coverage disparity" — never a protected-attribute claim.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Callable, Iterable

from .profiles import UserProfile


def literacy_band(profile: UserProfile) -> str:
    if profile.financial_literacy < 0.33:
        return "low_literacy"
    if profile.financial_literacy < 0.66:
        return "mid_literacy"
    return "high_literacy"


def numeracy_band(profile: UserProfile) -> str:
    return "low_numeracy" if profile.numeracy < 0.5 else "high_numeracy"


def color_vision_band(profile: UserProfile) -> str:
    return "normal_vision" if profile.color_vision_mode.value == "normal" else "color_deficient"


SEGMENTERS: dict[str, Callable[[UserProfile], str]] = {
    "literacy": literacy_band,
    "numeracy": numeracy_band,
    "language": lambda p: p.language.value,
    "color_vision": color_vision_band,
    "archetype": lambda p: p.archetype.value,
}


@dataclass
class SegmentResult:
    segment_name: str
    rates: dict[str, float]           # segment value -> mean outcome
    counts: dict[str, int]

    @property
    def disparity_gap(self) -> float:
        """Best minus worst segment rate (0 = perfectly equal)."""
        if not self.rates:
            return 0.0
        return round(max(self.rates.values()) - min(self.rates.values()), 4)

    @property
    def disparity_ratio(self) -> float:
        """Worst / best rate (1.0 = equal); 0 if best rate is 0."""
        if not self.rates:
            return 1.0
        best = max(self.rates.values())
        worst = min(self.rates.values())
        return round(worst / best, 4) if best > 0 else 0.0

    @property
    def worst_segment(self) -> str | None:
        return min(self.rates, key=self.rates.get) if self.rates else None


def segment_outcome(
    population: Iterable[tuple[UserProfile, float]],
    segment_name: str,
) -> SegmentResult:
    """Mean outcome per segment value for one segmentation of a scored population.

    ``population`` is (profile, outcome) pairs — outcome is a 0/1 flag or a
    continuous score (e.g. comprehension fraction). Aggregating per user keeps the
    unit of analysis the user, never the click.
    """
    segmenter = SEGMENTERS[segment_name]
    buckets: dict[str, list[float]] = defaultdict(list)
    for profile, outcome in population:
        buckets[segmenter(profile)].append(float(outcome))
    rates = {k: round(sum(v) / len(v), 4) for k, v in buckets.items() if v}
    counts = {k: len(v) for k, v in buckets.items()}
    return SegmentResult(segment_name=segment_name, rates=rates, counts=counts)


def all_disparities(
    population: list[tuple[UserProfile, float]],
    segment_names: Iterable[str] | None = None,
) -> dict[str, SegmentResult]:
    """Compute segment results across several dimensions at once."""
    names = list(segment_names) if segment_names is not None else list(SEGMENTERS)
    return {name: segment_outcome(population, name) for name in names}


def flag_material_disparities(
    results: dict[str, SegmentResult], gap_threshold: float = 0.15
) -> list[dict]:
    """Return the dimensions whose best-vs-worst gap exceeds the threshold.

    A material comprehension/accessibility disparity is a finding to report, with
    the worst-served segment named — never a claim about a protected group.
    """
    flagged = []
    for name, res in results.items():
        if res.disparity_gap >= gap_threshold:
            flagged.append(
                {
                    "dimension": name,
                    "gap": res.disparity_gap,
                    "ratio": res.disparity_ratio,
                    "worst_segment": res.worst_segment,
                    "rates": res.rates,
                }
            )
    return sorted(flagged, key=lambda d: d["gap"], reverse=True)
