"""Phase 5 experiments: predeclared, paired, segment-aware A/B tests.

Each experiment is a within-user paired design: every simulated user experiences
BOTH arms from the same disposition, and inference is on the per-user difference
(paired bootstrap in ``stats``). Paired design is legitimate here because the arms
are counterfactual renderings of the same data to the same modelled user, and it
sharply reduces variance versus splitting the (finite) population.

An experiment declares its primary metric and MDE up front, reports the effect as
one of {positive, negative, no_effect, inconclusive}, and runs a set of
pre-named segment analyses with Benjamini-Hochberg correction — labelled
exploratory, because the framework makes no confirmatory real-world claim.

The four wired experiments map to the required scenarios:
* A  score-only vs explained            -> comprehension
* B  generic warning vs attribution     -> concentration recognition
* C  normal vs crisis-safe presentation -> harmful-exit intent (a harm; down is good)
* I  technical vs layered plain-language -> comprehension
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from .comprehension import run_comprehension_battery
from .distributions import derive_generator
from .events import EventType
from .fairness import SEGMENTERS
from .interpret import UserState, interpret_view
from .presentation import PresentationVariant, render_stock_view
from .profiles import UserProfile
from .scenarios import run_market_crash
from .stats import EffectEstimate, benjamini_hochberg, paired_bootstrap
from .sut import load_scorecard
from .tasks import _hash_user, run_portfolio_concentration

# Per-user outcome function: (profile, seed, config_hash) -> float.
OutcomeFn = Callable[[UserProfile, int, str], float]


# ── Per-user outcome adapters ────────────────────────────────────────────────
def _comprehension_after_variant(
    profile: UserProfile, seed: int, config_hash: str, *, variant: PresentationVariant,
    include_untranslated: bool = False,
) -> float:
    """View a variant, then answer the comprehension battery; return the score.

    Understanding accrued from the view carries into the battery (via UserState),
    so a better explanation can lift comprehension — the A/I primary metric.
    """
    scorecard = load_scorecard("TSLA")
    view = render_stock_view(
        scorecard, variant=variant, language=profile.language,
        color_vision=profile.color_vision_mode, include_untranslated=include_untranslated,
    )
    # _hash_user, NOT the builtin hash(): CPython salts str hashing with
    # PYTHONHASHSEED, so hash("first_time_retail-0000") differs on every process
    # start. Using it here made experiments A and I reproducible *within* a
    # process but not *across* runs — silently breaking the determinism this
    # package promises. _hash_user is a plain byte-wise fold, so it is stable.
    rng = derive_generator(seed, _hash_user(profile.user_id), 30)
    state = UserState.initial(profile)
    interpret_view(profile, state, view, rng)  # mutates state.understood_concepts
    outcome = run_comprehension_battery(profile, state, rng)
    return outcome.score


def _concentration_recognised(
    profile: UserProfile, seed: int, config_hash: str, *, show_attribution: bool,
) -> float:
    positions = [
        ("EMP", 0.70, 0.55, 1.6, "Tech"), ("A", 0.10, 0.25, 0.9, "Health"),
        ("B", 0.10, 0.22, 0.8, "Utilities"), ("C", 0.10, 0.20, 0.7, "Staples"),
    ]
    log = run_portfolio_concentration(
        profile, seed=seed, config_hash=config_hash,
        positions_spec=positions, show_attribution=show_attribution,
    )
    comp = log.of_type(EventType.SIMULATION_COMPLETED)[0]
    return 1.0 if comp.detail.get("concentration_recognised") else 0.0


def _harmful_exit(
    profile: UserProfile, seed: int, config_hash: str, *, crisis_safe: bool,
) -> float:
    log = run_market_crash(profile, seed=seed, config_hash=config_hash, crisis_safe=crisis_safe)
    comp = log.of_type(EventType.SIMULATION_COMPLETED)[0]
    return 1.0 if comp.detail.get("harmful_exit") else 0.0


# ── Experiment runner ────────────────────────────────────────────────────────
@dataclass
class ExperimentResult:
    name: str
    primary_metric: str
    mde: float
    control_arm: str
    treatment_arm: str
    effect: EffectEstimate
    control_mean: float
    treatment_mean: float
    segments: dict[str, dict] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "primary_metric": self.primary_metric,
            "mde": self.mde,
            "control_arm": self.control_arm,
            "treatment_arm": self.treatment_arm,
            "control_mean": round(self.control_mean, 4),
            "treatment_mean": round(self.treatment_mean, 4),
            "effect": self.effect.to_dict(),
            "segments": self.segments,
        }


def run_experiment(
    *,
    name: str,
    primary_metric: str,
    population: list[UserProfile],
    control_fn: OutcomeFn,
    treatment_fn: OutcomeFn,
    control_arm: str,
    treatment_arm: str,
    seed: int,
    config_hash: str,
    mde: float = 0.05,
    segment_dims: Optional[list[str]] = None,
) -> ExperimentResult:
    """Run a paired experiment over a population and analyse it, segments included."""
    control_out: list[float] = []
    treatment_out: list[float] = []
    for i, profile in enumerate(population):
        control_out.append(control_fn(profile, seed + i, config_hash))
        treatment_out.append(treatment_fn(profile, seed + 100000 + i, config_hash))

    effect = paired_bootstrap(control_out, treatment_out, seed=seed, mde=mde)

    segments: dict[str, dict] = {}
    if segment_dims:
        # Collect per-segment paired effects, then BH-correct across all segment
        # values tested (exploratory).
        seg_records: list[tuple[str, str, EffectEstimate]] = []
        for dim in segment_dims:
            segmenter = SEGMENTERS[dim]
            groups: dict[str, tuple[list[float], list[float]]] = {}
            for profile, c, t in zip(population, control_out, treatment_out):
                key = segmenter(profile)
                groups.setdefault(key, ([], []))
                groups[key][0].append(c)
                groups[key][1].append(t)
            for key, (cs, ts) in groups.items():
                if len(cs) >= 5:  # don't infer on a handful of users
                    est = paired_bootstrap(cs, ts, seed=seed + 7, mde=mde)
                    seg_records.append((dim, key, est))

        adjusted = benjamini_hochberg([e.p_value for (_, _, e) in seg_records])
        for (dim, key, est), adj_p in zip(seg_records, adjusted):
            segments.setdefault(dim, {})[key] = {
                **est.to_dict(),
                "p_value_bh": round(adj_p, 4),
                "analysis": "exploratory",
            }

    return ExperimentResult(
        name=name,
        primary_metric=primary_metric,
        mde=mde,
        control_arm=control_arm,
        treatment_arm=treatment_arm,
        effect=effect,
        control_mean=sum(control_out) / len(control_out),
        treatment_mean=sum(treatment_out) / len(treatment_out),
        segments=segments,
    )


# ── The four pre-declared experiments ────────────────────────────────────────
def experiment_a_score_only_vs_explained(
    population: list[UserProfile], *, seed: int, config_hash: str
) -> ExperimentResult:
    return run_experiment(
        name="A_score_only_vs_explained",
        primary_metric="comprehension_score",
        population=population,
        control_fn=lambda p, s, c: _comprehension_after_variant(
            p, s, c, variant=PresentationVariant.SCORE_ONLY),
        treatment_fn=lambda p, s, c: _comprehension_after_variant(
            p, s, c, variant=PresentationVariant.EXPLAINED),
        control_arm="score_only", treatment_arm="explained",
        seed=seed, config_hash=config_hash, mde=0.05,
        segment_dims=["literacy", "language"],
    )


def experiment_b_generic_vs_attribution(
    population: list[UserProfile], *, seed: int, config_hash: str
) -> ExperimentResult:
    return run_experiment(
        name="B_generic_vs_attribution",
        primary_metric="concentration_recognised",
        population=population,
        control_fn=lambda p, s, c: _concentration_recognised(p, s, c, show_attribution=False),
        treatment_fn=lambda p, s, c: _concentration_recognised(p, s, c, show_attribution=True),
        control_arm="generic_warning", treatment_arm="attribution",
        seed=seed, config_hash=config_hash, mde=0.05,
        segment_dims=["literacy"],
    )


def experiment_c_normal_vs_crisis_safe(
    population: list[UserProfile], *, seed: int, config_hash: str
) -> ExperimentResult:
    return run_experiment(
        name="C_normal_vs_crisis_safe",
        primary_metric="harmful_exit_intent",  # a HARM: a negative effect is good
        population=population,
        control_fn=lambda p, s, c: _harmful_exit(p, s, c, crisis_safe=False),
        treatment_fn=lambda p, s, c: _harmful_exit(p, s, c, crisis_safe=True),
        control_arm="normal", treatment_arm="crisis_safe",
        seed=seed, config_hash=config_hash, mde=0.05,
        segment_dims=["literacy"],
    )


def experiment_i_technical_vs_plain_language(
    population: list[UserProfile], *, seed: int, config_hash: str
) -> ExperimentResult:
    return run_experiment(
        name="I_technical_vs_plain_language",
        primary_metric="comprehension_score",
        population=population,
        control_fn=lambda p, s, c: _comprehension_after_variant(
            p, s, c, variant=PresentationVariant.EXPLAINED),
        treatment_fn=lambda p, s, c: _comprehension_after_variant(
            p, s, c, variant=PresentationVariant.PLAIN_LANGUAGE),
        control_arm="technical", treatment_arm="plain_language",
        seed=seed, config_hash=config_hash, mde=0.05,
        segment_dims=["literacy"],
    )


ALL_EXPERIMENTS = {
    "A": experiment_a_score_only_vs_explained,
    "B": experiment_b_generic_vs_attribution,
    "C": experiment_c_normal_vs_crisis_safe,
    "I": experiment_i_technical_vs_plain_language,
}
