"""Action-intent model: from beliefs to an intended (never advised) action.

The framework models what a user *would do*, as an outcome to be measured — it
never tells a user what to do. Panic selling, overconfident buying, and blind
reliance are treated as harms to count, not conversions to maximise.

Each candidate action gets an interpretable additive utility built from the
required decision form:

    actionUtility = riskConcern·perceivedRisk
                  + socialProofSensitivity·communitySentiment
                  + confirmationBias·agreementWithPrior
                  - disclosureAttention·warningStrength
                  - frictionCost
                  + trustInAutomation·scoreSalience

with per-action sign/emphasis (a warning suppresses sell-everything and buy-more
alike; understanding pulls toward hold / research / seek-advice). A misconception
distorts *perceived* risk — e.g. a user who reads the 0-100 score as a loss
probability feels far more danger than the score warrants — which is exactly how
these misreadings turn into harmful intent. Choice is a seeded softmax so the
same user in the same context always resolves the same way.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .events import IntendedAction
from .interpret import InterpretationResult
from .profiles import Goal, Misconception, UserProfile


@dataclass(frozen=True)
class DecisionContext:
    """Everything outside the user's head that bears on the decision."""

    score: float                       # 0-100 composite
    community_sentiment: float = 0.0   # -1 (sell) .. +1 (buy)
    agreement_with_prior: float = 0.5  # 0..1, how much shown info matches prior belief
    warning_strength: float = 0.0      # 0..1, aggregate caution actually taken in
    market_stress: float = 0.0         # 0..1
    score_salience: float = 0.9        # how front-and-centre the score is


@dataclass
class DecisionResult:
    intended_action: IntendedAction
    reason: str
    utilities: dict[str, float]
    perceived_risk: float
    panic_sell: bool
    overconfident_buy: bool
    treats_score_as_advice: bool


def _perceived_risk(profile: UserProfile, result: InterpretationResult, score: float) -> float:
    """The user's *felt* risk, distorted by any live misconceptions."""
    base = score / 100.0
    m = result.misconceptions_after
    # Reading the score as P(loss) makes an 80 feel like "80% chance I lose money".
    if Misconception.SCORE_IS_PROBABILITY in m:
        base = min(1.0, base * 1.35)
    # "Low risk = safe" flattens felt risk at the low end.
    if Misconception.LOW_RISK_MEANS_SAFE in m and base < 0.5:
        base *= 0.6
    return max(0.0, min(1.0, base))


def _softmax_choice(
    utilities: dict[IntendedAction, float], rng: np.random.Generator, temperature: float
) -> IntendedAction:
    actions = list(utilities)
    xs = np.array([utilities[a] / max(temperature, 1e-6) for a in actions])
    xs = xs - xs.max()
    probs = np.exp(xs)
    probs = probs / probs.sum()
    idx = int(rng.choice(len(actions), p=probs))
    return actions[idx]


def decide_action(
    profile: UserProfile,
    result: InterpretationResult,
    ctx: DecisionContext,
    rng: np.random.Generator,
    *,
    temperature: float = 0.35,
) -> DecisionResult:
    perceived = _perceived_risk(profile, result, ctx.score)
    understanding = result.actual_understanding
    treats_as_advice = Misconception.SCORE_IS_ADVICE in result.misconceptions_after

    # Shared terms from the required utility form.
    social = profile.social_proof_sensitivity * ctx.community_sentiment
    confirm = profile.confirmation_bias * (ctx.agreement_with_prior - 0.5) * 2.0
    warning_brake = profile.disclosure_attention * ctx.warning_strength
    automation_pull = profile.trust_in_automation * ctx.score_salience
    panic_drive = profile.tendency_to_panic * (0.5 + 0.5 * ctx.market_stress)

    u: dict[IntendedAction, float] = {}

    # HOLD / do nothing — rewarded by understanding, caution, and low felt risk.
    u[IntendedAction.HOLD] = (
        0.6 + 0.8 * understanding + 0.6 * warning_brake - 0.7 * perceived * panic_drive
    )
    # RESEARCH_MORE — curiosity, disclosure attention, uncertainty tolerance.
    u[IntendedAction.RESEARCH_MORE] = (
        0.3
        + 0.7 * profile.technical_curiosity
        + 0.5 * profile.disclosure_attention
        + 0.4 * profile.uncertainty_tolerance
        - 0.5 * automation_pull  # trusting the score reduces urge to dig
    )
    # REDUCE_POSITION — a measured response to high felt risk.
    u[IntendedAction.REDUCE_POSITION] = (
        0.2 + 1.0 * perceived * profile.loss_aversion - social - 0.4 * warning_brake
    )
    # SELL_ALL — panic exit; the harm case.
    u[IntendedAction.SELL_ALL] = (
        -0.3
        + 1.4 * perceived * panic_drive * profile.loss_aversion
        - 1.1 * warning_brake
        - 0.6 * understanding
        - 0.4 * max(0.0, social)  # bullish community restrains a panic sell
    )
    # BUY / BUY_MORE — overconfident entry; the other harm case.
    buy_base = (
        -0.2
        + 1.0 * (1.0 - perceived) * profile.risk_tolerance
        + 0.8 * max(0.0, social)
        + 0.6 * confirm
        + 0.5 * automation_pull
        - 0.8 * warning_brake
    )
    if Misconception.LOW_RISK_MEANS_SAFE in result.misconceptions_after:
        buy_base += 0.5 * (1.0 - perceived)
    u[IntendedAction.BUY_MORE] = buy_base + 0.3 * profile.tendency_to_overtrade
    u[IntendedAction.BUY] = buy_base
    # SEEK_PROFESSIONAL_ADVICE — the responsible off-ramp; boosted under stress.
    u[IntendedAction.SEEK_PROFESSIONAL_ADVICE] = (
        0.1
        + 0.6 * profile.disclosure_attention
        + 0.7 * profile.current_financial_stress
        + 0.5 * warning_brake
        + (0.4 if profile.current_goal is Goal.PRESERVE_CAPITAL else 0.0)
    )
    # SHARE — driven by social sensitivity and an extreme, screenshot-worthy score.
    extremeness = abs(perceived - 0.5) * 2.0
    u[IntendedAction.SHARE] = (
        -0.2
        + 0.9 * profile.social_proof_sensitivity * extremeness
        - 0.3 * profile.disclosure_attention
    )
    # ABANDON — friction/attention exhausted before reaching a decision.
    friction = 1.0 - understanding
    u[IntendedAction.ABANDON] = (
        -0.4 + 1.0 * max(0.0, friction - profile.churn_threshold) - 0.5 * automation_pull
    )

    chosen = _softmax_choice(u, rng, temperature)

    panic_sell = chosen is IntendedAction.SELL_ALL
    overconfident_buy = chosen in {IntendedAction.BUY, IntendedAction.BUY_MORE} and (
        understanding < 0.4 or bool(result.misconceptions_after)
    )
    reason = _reason_for(chosen, perceived, result, ctx)

    return DecisionResult(
        intended_action=chosen,
        reason=reason,
        utilities={a.value: round(float(v), 4) for a, v in u.items()},
        perceived_risk=round(perceived, 4),
        panic_sell=panic_sell,
        overconfident_buy=overconfident_buy,
        treats_score_as_advice=treats_as_advice,
    )


def _reason_for(
    action: IntendedAction,
    perceived: float,
    result: InterpretationResult,
    ctx: DecisionContext,
) -> str:
    misc = ", ".join(sorted(m.value for m in result.misconceptions_after)) or "none"
    return (
        f"chose {action.value}: perceived_risk={perceived:.2f}, "
        f"understanding={result.actual_understanding:.2f}, "
        f"community_sentiment={ctx.community_sentiment:+.2f}, "
        f"warning_taken_in={ctx.warning_strength:.2f}, live_misconceptions=[{misc}]"
    )
