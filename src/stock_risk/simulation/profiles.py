"""Typed simulated-user profiles and seeded, per-archetype generation.

A ``UserProfile`` is a frozen, strongly-typed vector of *dispositions* (all
continuous traits normalised to [0, 1], all categorical traits typed enums).
Behaviour code elsewhere reads ONLY these fields — there are deliberately no
``if archetype == FIRST_TIME_RETAIL`` branches downstream. An archetype is
nothing more than a named ``ArchetypeSpec``: a distribution over the profile
fields. That is what makes "meaningful differences between groups" and
"variation within a group" both true and testable:

* between groups — the specs centre different means (a professional's
  ``financialLiteracy`` centres high, a first-timer's low);
* within a group — every trait has non-zero spread, so two users of the same
  archetype differ.

Evolving state (what the user has come to understand, which misconceptions they
still hold, what they have done) is NOT stored here — the profile is the static
disposition. That mutable state lives in ``UserState`` so the profile can stay
frozen and hashable, and so a single profile can be replayed through several
scenarios from a clean slate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .distributions import Choice, Subset, Trait, derive_generator


# ── Typed categorical dimensions ────────────────────────────────────────────
class Archetype(str, Enum):
    FIRST_TIME_RETAIL = "first_time_retail"
    YOUNG_HIGH_RISK_TRADER = "young_high_risk_trader"
    CAUTIOUS_RETIREMENT_SAVER = "cautious_retirement_saver"
    LOW_FINANCIAL_LITERACY = "low_financial_literacy"
    EXPERIENCED_INVESTOR = "experienced_investor"
    FINANCIAL_ADVISOR = "financial_advisor"
    CONCENTRATED_EMPLOYER_STOCK = "concentrated_employer_stock"
    MARKET_CRASH_USER = "market_crash_user"
    VISUAL_ACCESSIBILITY = "visual_accessibility"
    CHINESE_LANGUAGE = "chinese_language"
    ILLIQUID_DATA_SPARSE = "illiquid_data_sparse"
    COMMUNITY_INFLUENCED = "community_influenced"
    FINANCIAL_STRESS = "financial_stress"
    ADVERSARIAL_MISUSE = "adversarial_misuse"


class Language(str, Enum):
    EN = "en"
    ZH = "zh"


class ColorVisionMode(str, Enum):
    NORMAL = "normal"
    DEUTERANOPIA = "deuteranopia"
    PROTANOPIA = "protanopia"
    TRITANOPIA = "tritanopia"
    MONOCHROME = "monochrome"


class AccessibilityNeed(str, Enum):
    KEYBOARD_ONLY = "keyboard_only"
    SCREEN_READER = "screen_reader"
    LOW_VISION_ZOOM = "low_vision_zoom"
    REDUCED_MOTION = "reduced_motion"


class ExplanationDepth(str, Enum):
    """How far a user is willing to drill into an explanation before disengaging."""

    GLANCE = "glance"          # score + label only
    PLAIN = "plain"            # one-sentence plain-language meaning
    COMPONENT = "component"    # per-category breakdown
    TECHNICAL = "technical"    # full methodology / raw metrics


class InteractionMode(str, Enum):
    VISUAL = "visual"
    KEYBOARD = "keyboard"
    SCREEN_READER = "screen_reader"


class InvestmentHorizon(str, Enum):
    SHORT = "short"     # weeks-months
    MEDIUM = "medium"   # 1-5 years
    LONG = "long"       # 5+ years / retirement


class Goal(str, Enum):
    """The user's own framing of why they are here (a scenario input, not advice)."""

    UNDERSTAND_RISK = "understand_risk"
    CHECK_HOLDING = "check_holding"
    SPECULATE = "speculate"
    PRESERVE_CAPITAL = "preserve_capital"
    URGENT_DECISION = "urgent_decision"
    EVALUATE_CLIENT_PORTFOLIO = "evaluate_client_portfolio"
    RESEARCH_METHODOLOGY = "research_methodology"
    FOLLOW_COMMUNITY = "follow_community"
    MANIPULATE = "manipulate"


class Misconception(str, Enum):
    """Named financial misconceptions the framework can detect and track.

    Kept as an enum (not free text) so misconception *rates* aggregate cleanly
    across users, languages and segments, and so a corrected misconception is an
    exact set-membership change rather than a fuzzy match.
    """

    SCORE_IS_PROBABILITY = "score_is_probability"          # "80/100 => 80% chance of loss"
    LOW_RISK_MEANS_SAFE = "low_risk_means_safe"      # "low risk => cannot fall / is profitable"
    SCORE_IS_ADVICE = "score_is_advice"                    # "the score tells me to buy/sell"
    VAR_IS_MAX_LOSS = "var_is_max_loss"                    # "losses can't exceed the 5% VaR"
    LOW_VOL_CANNOT_FALL = "low_vol_cannot_fall"            # "low volatility => no big decline"
    HISTORY_GUARANTEES_FUTURE = "history_guarantees_future"  # stress/backtest = prediction
    DIVERSIFIED_IF_MANY_NAMES = "diversified_if_many_names"  # many tickers => not concentrated
    IGNORES_DATA_QUALITY = "ignores_data_quality"          # trusts a low-confidence score
    SHAP_IS_CAUSAL = "shap_is_causal"                      # attribution = causation


# ── The profile ─────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class UserProfile:
    """A single simulated user's static disposition. All floats are in [0, 1]."""

    user_id: str
    archetype: Archetype
    language: Language

    # Knowledge / ability
    financial_literacy: float
    numeracy: float
    investing_experience: float
    reading_level: float
    probability_comprehension: float
    technical_curiosity: float
    attention_span: float

    # Risk psychology
    risk_tolerance: float
    loss_aversion: float
    uncertainty_tolerance: float
    tendency_to_overtrade: float
    tendency_to_panic: float

    # Trust & influence
    trust_in_automation: float
    trust_in_community: float
    social_proof_sensitivity: float
    confirmation_bias: float
    recency_bias: float
    disclosure_attention: float  # how much attention paid to warnings/caveats

    # Portfolio & context
    portfolio_complexity: float
    portfolio_concentration: float
    investment_horizon: InvestmentHorizon
    current_market_stress: float
    current_financial_stress: float
    churn_threshold: float  # friction tolerance before abandoning a workflow

    # Interaction & accessibility
    accessibility_needs: tuple[AccessibilityNeed, ...]
    color_vision_mode: ColorVisionMode
    preferred_explanation_depth: ExplanationDepth
    preferred_interaction_mode: InteractionMode

    # Goal + initial cognitive state
    current_goal: Goal
    initial_misconceptions: frozenset[Misconception] = field(default_factory=frozenset)

    def has_accessibility_need(self, need: AccessibilityNeed) -> bool:
        return need in self.accessibility_needs


# ── Archetype specification ─────────────────────────────────────────────────
_CONTINUOUS_FIELDS = (
    "financial_literacy", "numeracy", "investing_experience", "reading_level",
    "probability_comprehension", "technical_curiosity", "attention_span",
    "risk_tolerance", "loss_aversion", "uncertainty_tolerance",
    "tendency_to_overtrade", "tendency_to_panic", "trust_in_automation",
    "trust_in_community", "social_proof_sensitivity", "confirmation_bias",
    "recency_bias", "disclosure_attention", "portfolio_complexity",
    "portfolio_concentration", "current_market_stress", "current_financial_stress",
    "churn_threshold",
)

# A sensible neutral default for any continuous trait an archetype doesn't
# override — keeps specs readable (only the *distinctive* traits are listed).
_DEFAULT_TRAIT = Trait(mean=0.5, sd=0.15)


@dataclass(frozen=True)
class ArchetypeSpec:
    """A distribution over ``UserProfile`` fields for one archetype."""

    archetype: Archetype
    traits: dict[str, Trait]
    language: Choice[Language]
    horizon: Choice[InvestmentHorizon]
    goal: Choice[Goal]
    explanation_depth: Choice[ExplanationDepth]
    interaction_mode: Choice[InteractionMode]
    color_vision: Choice[ColorVisionMode]
    accessibility: Subset[AccessibilityNeed]
    # Misconceptions this archetype tends to walk in with, each with a prior
    # probability of being present for a given sampled user.
    misconception_priors: dict[Misconception, float]

    def sample(self, seed: int, index: int) -> UserProfile:
        rng = derive_generator(seed, _archetype_ordinal(self.archetype), index)
        continuous = {
            name: self.traits.get(name, _DEFAULT_TRAIT).sample(rng)
            for name in _CONTINUOUS_FIELDS
        }
        language = self.language.sample(rng)
        interaction = self.interaction_mode.sample(rng)
        accessibility = self.accessibility.sample(rng)
        # Consistency guard: a screen-reader interaction mode implies the need.
        if interaction is InteractionMode.SCREEN_READER and (
            AccessibilityNeed.SCREEN_READER not in accessibility
        ):
            accessibility = (*accessibility, AccessibilityNeed.SCREEN_READER)
        misconceptions = frozenset(
            m for m, p in self.misconception_priors.items() if rng.random() < p
        )
        return UserProfile(
            user_id=f"{self.archetype.value}-{index:04d}",
            archetype=self.archetype,
            language=language,
            investment_horizon=self.horizon.sample(rng),
            current_goal=self.goal.sample(rng),
            preferred_explanation_depth=self.explanation_depth.sample(rng),
            preferred_interaction_mode=interaction,
            color_vision_mode=self.color_vision.sample(rng),
            accessibility_needs=accessibility,
            initial_misconceptions=misconceptions,
            **continuous,
        )


def _archetype_ordinal(archetype: Archetype) -> int:
    return list(Archetype).index(archetype)


# Convenience builders keeping the spec table below terse.
def _en_mostly() -> Choice[Language]:
    return Choice([Language.EN, Language.ZH], [0.85, 0.15])


def _no_accessibility() -> Subset[AccessibilityNeed]:
    return Subset(list(AccessibilityNeed), [0.02, 0.01, 0.03, 0.05])


def _normal_vision() -> Choice[ColorVisionMode]:
    # ~8% of the male population has some red-green deficiency; keep a realistic
    # tail on every archetype so accessibility isn't confined to one group.
    return Choice(
        [ColorVisionMode.NORMAL, ColorVisionMode.DEUTERANOPIA, ColorVisionMode.PROTANOPIA],
        [0.92, 0.05, 0.03],
    )


def _visual_interaction() -> Choice[InteractionMode]:
    return Choice(list(InteractionMode), [0.9, 0.06, 0.04])


ARCHETYPES: dict[Archetype, ArchetypeSpec] = {
    Archetype.FIRST_TIME_RETAIL: ArchetypeSpec(
        archetype=Archetype.FIRST_TIME_RETAIL,
        traits={
            "financial_literacy": Trait(0.20, 0.12),
            "numeracy": Trait(0.28, 0.15),
            "investing_experience": Trait(0.12, 0.10),
            "probability_comprehension": Trait(0.22, 0.13),
            "technical_curiosity": Trait(0.30, 0.18),
            "attention_span": Trait(0.35, 0.18),
            "reading_level": Trait(0.5, 0.18),
            "risk_tolerance": Trait(0.5, 0.2),
            "loss_aversion": Trait(0.6, 0.18),
            "trust_in_automation": Trait(0.68, 0.15),
            "social_proof_sensitivity": Trait(0.7, 0.15),
            "trust_in_community": Trait(0.62, 0.18),
            "disclosure_attention": Trait(0.30, 0.16),
            "tendency_to_panic": Trait(0.55, 0.2),
            "tendency_to_overtrade": Trait(0.45, 0.2),
            "recency_bias": Trait(0.6, 0.17),
            "portfolio_complexity": Trait(0.2, 0.12),
            "portfolio_concentration": Trait(0.7, 0.18),
            "uncertainty_tolerance": Trait(0.35, 0.16),
            "churn_threshold": Trait(0.4, 0.18),
        },
        language=_en_mostly(),
        horizon=Choice(list(InvestmentHorizon), [0.4, 0.45, 0.15]),
        goal=Choice(
            [Goal.UNDERSTAND_RISK, Goal.CHECK_HOLDING, Goal.SPECULATE, Goal.FOLLOW_COMMUNITY],
            [0.4, 0.3, 0.2, 0.1],
        ),
        explanation_depth=Choice(list(ExplanationDepth), [0.5, 0.35, 0.12, 0.03]),
        interaction_mode=_visual_interaction(),
        color_vision=_normal_vision(),
        accessibility=_no_accessibility(),
        misconception_priors={
            Misconception.SCORE_IS_PROBABILITY: 0.55,
            Misconception.SCORE_IS_ADVICE: 0.45,
            Misconception.LOW_RISK_MEANS_SAFE: 0.5,
            Misconception.HISTORY_GUARANTEES_FUTURE: 0.4,
        },
    ),
    Archetype.YOUNG_HIGH_RISK_TRADER: ArchetypeSpec(
        archetype=Archetype.YOUNG_HIGH_RISK_TRADER,
        traits={
            "financial_literacy": Trait(0.45, 0.18),
            "numeracy": Trait(0.5, 0.18),
            "investing_experience": Trait(0.45, 0.2),
            "probability_comprehension": Trait(0.45, 0.2),
            "technical_curiosity": Trait(0.5, 0.2),
            "attention_span": Trait(0.3, 0.16),
            "risk_tolerance": Trait(0.85, 0.12),
            "loss_aversion": Trait(0.3, 0.16),
            "trust_in_automation": Trait(0.55, 0.2),
            "social_proof_sensitivity": Trait(0.75, 0.15),
            "trust_in_community": Trait(0.72, 0.16),
            "disclosure_attention": Trait(0.2, 0.13),
            "tendency_to_panic": Trait(0.35, 0.2),
            "tendency_to_overtrade": Trait(0.8, 0.13),
            "recency_bias": Trait(0.7, 0.15),
            "confirmation_bias": Trait(0.65, 0.16),
            "portfolio_concentration": Trait(0.6, 0.2),
            "uncertainty_tolerance": Trait(0.6, 0.18),
            "churn_threshold": Trait(0.55, 0.18),
        },
        language=_en_mostly(),
        horizon=Choice(list(InvestmentHorizon), [0.7, 0.25, 0.05]),
        goal=Choice(
            [Goal.SPECULATE, Goal.FOLLOW_COMMUNITY, Goal.UNDERSTAND_RISK], [0.6, 0.25, 0.15]
        ),
        explanation_depth=Choice(list(ExplanationDepth), [0.45, 0.3, 0.18, 0.07]),
        interaction_mode=_visual_interaction(),
        color_vision=_normal_vision(),
        accessibility=_no_accessibility(),
        misconception_priors={
            Misconception.SCORE_IS_ADVICE: 0.3,
            Misconception.HISTORY_GUARANTEES_FUTURE: 0.35,
            Misconception.DIVERSIFIED_IF_MANY_NAMES: 0.3,
        },
    ),
    Archetype.CAUTIOUS_RETIREMENT_SAVER: ArchetypeSpec(
        archetype=Archetype.CAUTIOUS_RETIREMENT_SAVER,
        traits={
            "financial_literacy": Trait(0.5, 0.18),
            "numeracy": Trait(0.5, 0.18),
            "investing_experience": Trait(0.55, 0.2),
            "probability_comprehension": Trait(0.45, 0.2),
            "technical_curiosity": Trait(0.35, 0.18),
            "attention_span": Trait(0.6, 0.16),
            "reading_level": Trait(0.55, 0.18),
            "risk_tolerance": Trait(0.2, 0.12),
            "loss_aversion": Trait(0.8, 0.12),
            "trust_in_automation": Trait(0.5, 0.18),
            "social_proof_sensitivity": Trait(0.4, 0.18),
            "trust_in_community": Trait(0.35, 0.18),
            "disclosure_attention": Trait(0.6, 0.16),
            "tendency_to_panic": Trait(0.6, 0.18),
            "tendency_to_overtrade": Trait(0.2, 0.13),
            "recency_bias": Trait(0.45, 0.18),
            "portfolio_complexity": Trait(0.45, 0.2),
            "portfolio_concentration": Trait(0.55, 0.22),
            "uncertainty_tolerance": Trait(0.35, 0.16),
            "churn_threshold": Trait(0.55, 0.18),
        },
        language=_en_mostly(),
        horizon=Choice(list(InvestmentHorizon), [0.05, 0.3, 0.65]),
        goal=Choice(
            [Goal.PRESERVE_CAPITAL, Goal.CHECK_HOLDING, Goal.UNDERSTAND_RISK], [0.5, 0.3, 0.2]
        ),
        explanation_depth=Choice(list(ExplanationDepth), [0.25, 0.45, 0.25, 0.05]),
        interaction_mode=Choice(list(InteractionMode), [0.85, 0.08, 0.07]),
        color_vision=_normal_vision(),
        accessibility=Subset(list(AccessibilityNeed), [0.05, 0.05, 0.12, 0.08]),
        misconception_priors={
            Misconception.LOW_VOL_CANNOT_FALL: 0.3,
            Misconception.HISTORY_GUARANTEES_FUTURE: 0.35,
        },
    ),
    Archetype.LOW_FINANCIAL_LITERACY: ArchetypeSpec(
        archetype=Archetype.LOW_FINANCIAL_LITERACY,
        traits={
            "financial_literacy": Trait(0.12, 0.08),
            "numeracy": Trait(0.18, 0.10),
            "investing_experience": Trait(0.2, 0.15),
            "probability_comprehension": Trait(0.15, 0.10),
            "technical_curiosity": Trait(0.25, 0.16),
            "attention_span": Trait(0.35, 0.18),
            "reading_level": Trait(0.3, 0.15),
            "risk_tolerance": Trait(0.5, 0.2),
            "loss_aversion": Trait(0.6, 0.2),
            "trust_in_automation": Trait(0.7, 0.16),
            "social_proof_sensitivity": Trait(0.65, 0.18),
            "disclosure_attention": Trait(0.25, 0.15),
            "tendency_to_panic": Trait(0.55, 0.2),
            "uncertainty_tolerance": Trait(0.3, 0.16),
            "churn_threshold": Trait(0.3, 0.16),
        },
        language=Choice([Language.EN, Language.ZH], [0.7, 0.3]),
        horizon=Choice(list(InvestmentHorizon), [0.35, 0.4, 0.25]),
        goal=Choice(
            [Goal.UNDERSTAND_RISK, Goal.CHECK_HOLDING, Goal.FOLLOW_COMMUNITY], [0.45, 0.35, 0.2]
        ),
        explanation_depth=Choice(list(ExplanationDepth), [0.6, 0.32, 0.07, 0.01]),
        interaction_mode=_visual_interaction(),
        color_vision=_normal_vision(),
        accessibility=_no_accessibility(),
        misconception_priors={
            Misconception.SCORE_IS_PROBABILITY: 0.6,
            Misconception.SCORE_IS_ADVICE: 0.5,
            Misconception.LOW_RISK_MEANS_SAFE: 0.55,
            Misconception.VAR_IS_MAX_LOSS: 0.5,
            Misconception.IGNORES_DATA_QUALITY: 0.5,
        },
    ),
    Archetype.EXPERIENCED_INVESTOR: ArchetypeSpec(
        archetype=Archetype.EXPERIENCED_INVESTOR,
        traits={
            "financial_literacy": Trait(0.82, 0.10),
            "numeracy": Trait(0.8, 0.12),
            "investing_experience": Trait(0.8, 0.12),
            "probability_comprehension": Trait(0.8, 0.12),
            "technical_curiosity": Trait(0.8, 0.13),
            "attention_span": Trait(0.7, 0.15),
            "reading_level": Trait(0.75, 0.14),
            "risk_tolerance": Trait(0.6, 0.18),
            "loss_aversion": Trait(0.45, 0.18),
            "trust_in_automation": Trait(0.4, 0.18),  # skeptical of composite scores
            "social_proof_sensitivity": Trait(0.25, 0.15),
            "trust_in_community": Trait(0.3, 0.16),
            "disclosure_attention": Trait(0.7, 0.15),
            "tendency_to_panic": Trait(0.25, 0.15),
            "tendency_to_overtrade": Trait(0.4, 0.2),
            "confirmation_bias": Trait(0.45, 0.18),
            "uncertainty_tolerance": Trait(0.7, 0.15),
            "portfolio_complexity": Trait(0.75, 0.16),
            "churn_threshold": Trait(0.6, 0.18),
        },
        language=_en_mostly(),
        horizon=Choice(list(InvestmentHorizon), [0.25, 0.5, 0.25]),
        goal=Choice(
            [Goal.RESEARCH_METHODOLOGY, Goal.CHECK_HOLDING, Goal.UNDERSTAND_RISK], [0.5, 0.3, 0.2]
        ),
        explanation_depth=Choice(list(ExplanationDepth), [0.05, 0.15, 0.35, 0.45]),
        interaction_mode=_visual_interaction(),
        color_vision=_normal_vision(),
        accessibility=_no_accessibility(),
        misconception_priors={
            Misconception.SHAP_IS_CAUSAL: 0.2,
        },
    ),
    Archetype.CHINESE_LANGUAGE: ArchetypeSpec(
        archetype=Archetype.CHINESE_LANGUAGE,
        traits={
            "financial_literacy": Trait(0.45, 0.22),
            "numeracy": Trait(0.5, 0.2),
            "investing_experience": Trait(0.45, 0.22),
            "probability_comprehension": Trait(0.45, 0.2),
            "technical_curiosity": Trait(0.45, 0.2),
            "attention_span": Trait(0.5, 0.18),
            "reading_level": Trait(0.55, 0.18),
            "disclosure_attention": Trait(0.45, 0.18),
            "trust_in_automation": Trait(0.6, 0.18),
            "social_proof_sensitivity": Trait(0.6, 0.18),
            "portfolio_concentration": Trait(0.6, 0.2),
        },
        language=Choice([Language.ZH, Language.EN], [1.0, 0.0]),
        horizon=Choice(list(InvestmentHorizon), [0.3, 0.45, 0.25]),
        goal=Choice([Goal.UNDERSTAND_RISK, Goal.CHECK_HOLDING, Goal.SPECULATE], [0.4, 0.35, 0.25]),
        explanation_depth=Choice(list(ExplanationDepth), [0.3, 0.4, 0.22, 0.08]),
        interaction_mode=_visual_interaction(),
        color_vision=_normal_vision(),
        accessibility=_no_accessibility(),
        misconception_priors={
            Misconception.SCORE_IS_PROBABILITY: 0.45,
            Misconception.LOW_RISK_MEANS_SAFE: 0.4,
        },
    ),
    # ── Phase 3+ archetypes (specs defined now; exercised in later phases) ──
    Archetype.FINANCIAL_ADVISOR: ArchetypeSpec(
        archetype=Archetype.FINANCIAL_ADVISOR,
        traits={
            "financial_literacy": Trait(0.88, 0.08),
            "numeracy": Trait(0.85, 0.10),
            "investing_experience": Trait(0.85, 0.10),
            "probability_comprehension": Trait(0.85, 0.10),
            "technical_curiosity": Trait(0.75, 0.14),
            "attention_span": Trait(0.75, 0.13),
            "reading_level": Trait(0.8, 0.12),
            "risk_tolerance": Trait(0.5, 0.16),
            "loss_aversion": Trait(0.5, 0.16),
            "trust_in_automation": Trait(0.35, 0.16),  # governance-minded skeptic
            "social_proof_sensitivity": Trait(0.2, 0.13),
            "trust_in_community": Trait(0.25, 0.15),
            "disclosure_attention": Trait(0.85, 0.10),
            "tendency_to_panic": Trait(0.2, 0.12),
            "uncertainty_tolerance": Trait(0.7, 0.14),
            "portfolio_complexity": Trait(0.8, 0.14),
            "churn_threshold": Trait(0.65, 0.16),
        },
        language=_en_mostly(),
        horizon=Choice(list(InvestmentHorizon), [0.2, 0.5, 0.3]),
        goal=Choice(
            [Goal.EVALUATE_CLIENT_PORTFOLIO, Goal.RESEARCH_METHODOLOGY, Goal.CHECK_HOLDING],
            [0.6, 0.25, 0.15],
        ),
        explanation_depth=Choice(list(ExplanationDepth), [0.02, 0.1, 0.33, 0.55]),
        interaction_mode=_visual_interaction(),
        color_vision=_normal_vision(),
        accessibility=_no_accessibility(),
        misconception_priors={},
    ),
    Archetype.CONCENTRATED_EMPLOYER_STOCK: ArchetypeSpec(
        archetype=Archetype.CONCENTRATED_EMPLOYER_STOCK,
        traits={
            "financial_literacy": Trait(0.5, 0.2),
            "confirmation_bias": Trait(0.8, 0.12),
            "recency_bias": Trait(0.65, 0.16),
            "loss_aversion": Trait(0.55, 0.18),
            "disclosure_attention": Trait(0.45, 0.18),
            "portfolio_complexity": Trait(0.3, 0.16),
            "portfolio_concentration": Trait(0.9, 0.08),
            "trust_in_automation": Trait(0.45, 0.18),
        },
        language=_en_mostly(),
        horizon=Choice(list(InvestmentHorizon), [0.15, 0.45, 0.4]),
        goal=Choice(
            [Goal.CHECK_HOLDING, Goal.UNDERSTAND_RISK, Goal.PRESERVE_CAPITAL], [0.55, 0.25, 0.2]
        ),
        explanation_depth=Choice(list(ExplanationDepth), [0.2, 0.4, 0.3, 0.1]),
        interaction_mode=_visual_interaction(),
        color_vision=_normal_vision(),
        accessibility=_no_accessibility(),
        misconception_priors={
            Misconception.DIVERSIFIED_IF_MANY_NAMES: 0.2,
            Misconception.LOW_RISK_MEANS_SAFE: 0.35,
        },
    ),
    Archetype.MARKET_CRASH_USER: ArchetypeSpec(
        archetype=Archetype.MARKET_CRASH_USER,
        traits={
            "loss_aversion": Trait(0.8, 0.12),
            "tendency_to_panic": Trait(0.8, 0.12),
            "recency_bias": Trait(0.8, 0.12),
            "social_proof_sensitivity": Trait(0.7, 0.16),
            "trust_in_community": Trait(0.6, 0.18),
            "disclosure_attention": Trait(0.3, 0.16),  # stress narrows attention
            "uncertainty_tolerance": Trait(0.25, 0.14),
            "current_market_stress": Trait(0.9, 0.08),
            "attention_span": Trait(0.3, 0.16),
            "churn_threshold": Trait(0.35, 0.18),
        },
        language=_en_mostly(),
        horizon=Choice(list(InvestmentHorizon), [0.4, 0.4, 0.2]),
        goal=Choice(
            [Goal.URGENT_DECISION, Goal.CHECK_HOLDING, Goal.FOLLOW_COMMUNITY], [0.55, 0.25, 0.2]
        ),
        explanation_depth=Choice(list(ExplanationDepth), [0.55, 0.3, 0.12, 0.03]),
        interaction_mode=_visual_interaction(),
        color_vision=_normal_vision(),
        accessibility=_no_accessibility(),
        misconception_priors={
            Misconception.SCORE_IS_PROBABILITY: 0.5,
            Misconception.SCORE_IS_ADVICE: 0.45,
            Misconception.HISTORY_GUARANTEES_FUTURE: 0.4,
        },
    ),
    Archetype.VISUAL_ACCESSIBILITY: ArchetypeSpec(
        archetype=Archetype.VISUAL_ACCESSIBILITY,
        traits={
            "financial_literacy": Trait(0.5, 0.22),
            "disclosure_attention": Trait(0.55, 0.18),
            "attention_span": Trait(0.55, 0.18),
        },
        language=_en_mostly(),
        horizon=Choice(list(InvestmentHorizon), [0.3, 0.4, 0.3]),
        goal=Choice([Goal.UNDERSTAND_RISK, Goal.CHECK_HOLDING], [0.6, 0.4]),
        explanation_depth=Choice(list(ExplanationDepth), [0.2, 0.4, 0.28, 0.12]),
        interaction_mode=Choice(list(InteractionMode), [0.2, 0.4, 0.4]),
        color_vision=Choice(
            list(ColorVisionMode),
            [0.35, 0.25, 0.15, 0.10, 0.15],
        ),
        accessibility=Subset(list(AccessibilityNeed), [0.5, 0.5, 0.5, 0.4]),
        misconception_priors={},
    ),
    Archetype.ILLIQUID_DATA_SPARSE: ArchetypeSpec(
        archetype=Archetype.ILLIQUID_DATA_SPARSE,
        traits={
            "financial_literacy": Trait(0.5, 0.22),
            "technical_curiosity": Trait(0.55, 0.2),
            "disclosure_attention": Trait(0.45, 0.2),
            "trust_in_automation": Trait(0.55, 0.2),
        },
        language=Choice([Language.EN, Language.ZH], [0.5, 0.5]),
        horizon=Choice(list(InvestmentHorizon), [0.4, 0.4, 0.2]),
        goal=Choice([Goal.UNDERSTAND_RISK, Goal.SPECULATE, Goal.CHECK_HOLDING], [0.4, 0.35, 0.25]),
        explanation_depth=Choice(list(ExplanationDepth), [0.3, 0.35, 0.25, 0.1]),
        interaction_mode=_visual_interaction(),
        color_vision=_normal_vision(),
        accessibility=_no_accessibility(),
        misconception_priors={
            Misconception.IGNORES_DATA_QUALITY: 0.55,
            Misconception.SCORE_IS_PROBABILITY: 0.35,
        },
    ),
    Archetype.COMMUNITY_INFLUENCED: ArchetypeSpec(
        archetype=Archetype.COMMUNITY_INFLUENCED,
        traits={
            "financial_literacy": Trait(0.4, 0.2),
            "social_proof_sensitivity": Trait(0.85, 0.10),
            "trust_in_community": Trait(0.85, 0.10),
            "trust_in_automation": Trait(0.5, 0.2),
            "confirmation_bias": Trait(0.65, 0.16),
            "disclosure_attention": Trait(0.3, 0.16),
            "recency_bias": Trait(0.7, 0.15),
        },
        language=_en_mostly(),
        horizon=Choice(list(InvestmentHorizon), [0.55, 0.35, 0.1]),
        goal=Choice(
            [Goal.FOLLOW_COMMUNITY, Goal.SPECULATE, Goal.UNDERSTAND_RISK], [0.6, 0.25, 0.15]
        ),
        explanation_depth=Choice(list(ExplanationDepth), [0.5, 0.32, 0.14, 0.04]),
        interaction_mode=_visual_interaction(),
        color_vision=_normal_vision(),
        accessibility=_no_accessibility(),
        misconception_priors={
            Misconception.SCORE_IS_ADVICE: 0.4,
            Misconception.HISTORY_GUARANTEES_FUTURE: 0.35,
        },
    ),
    Archetype.FINANCIAL_STRESS: ArchetypeSpec(
        archetype=Archetype.FINANCIAL_STRESS,
        traits={
            "financial_literacy": Trait(0.35, 0.2),
            "loss_aversion": Trait(0.75, 0.14),
            "tendency_to_panic": Trait(0.65, 0.18),
            "uncertainty_tolerance": Trait(0.2, 0.12),
            "disclosure_attention": Trait(0.3, 0.16),
            "current_financial_stress": Trait(0.9, 0.08),
            "risk_tolerance": Trait(0.45, 0.25),  # desperation can spike this
            "churn_threshold": Trait(0.3, 0.16),
        },
        language=_en_mostly(),
        horizon=Choice(list(InvestmentHorizon), [0.75, 0.2, 0.05]),
        goal=Choice(
            [Goal.URGENT_DECISION, Goal.PRESERVE_CAPITAL, Goal.SPECULATE], [0.55, 0.25, 0.2]
        ),
        explanation_depth=Choice(list(ExplanationDepth), [0.55, 0.3, 0.12, 0.03]),
        interaction_mode=_visual_interaction(),
        color_vision=_normal_vision(),
        accessibility=_no_accessibility(),
        misconception_priors={
            Misconception.SCORE_IS_ADVICE: 0.5,
            Misconception.LOW_RISK_MEANS_SAFE: 0.45,
            Misconception.SCORE_IS_PROBABILITY: 0.4,
        },
    ),
    Archetype.ADVERSARIAL_MISUSE: ArchetypeSpec(
        archetype=Archetype.ADVERSARIAL_MISUSE,
        traits={
            "financial_literacy": Trait(0.6, 0.2),
            "technical_curiosity": Trait(0.7, 0.16),
            "trust_in_automation": Trait(0.3, 0.2),
            "disclosure_attention": Trait(0.2, 0.14),
            "tendency_to_overtrade": Trait(0.7, 0.18),
            "social_proof_sensitivity": Trait(0.3, 0.2),
        },
        language=_en_mostly(),
        horizon=Choice(list(InvestmentHorizon), [0.7, 0.25, 0.05]),
        goal=Choice([Goal.MANIPULATE, Goal.SPECULATE], [0.8, 0.2]),
        explanation_depth=Choice(list(ExplanationDepth), [0.3, 0.2, 0.2, 0.3]),
        interaction_mode=_visual_interaction(),
        color_vision=_normal_vision(),
        accessibility=_no_accessibility(),
        misconception_priors={},
    ),
}


# Archetypes explicitly in scope for Phase 1 (the initial six from the plan).
PHASE1_ARCHETYPES: tuple[Archetype, ...] = (
    Archetype.FIRST_TIME_RETAIL,
    Archetype.YOUNG_HIGH_RISK_TRADER,
    Archetype.CAUTIOUS_RETIREMENT_SAVER,
    Archetype.LOW_FINANCIAL_LITERACY,
    Archetype.EXPERIENCED_INVESTOR,
    Archetype.CHINESE_LANGUAGE,
)


def generate_user(archetype: Archetype, seed: int, index: int) -> UserProfile:
    """One deterministic user: fixed by (archetype, seed, index), order-independent."""
    return ARCHETYPES[archetype].sample(seed=seed, index=index)


def generate_cohort(archetype: Archetype, n: int, seed: int) -> list[UserProfile]:
    """``n`` independent users of one archetype, reproducible for a given seed."""
    return [generate_user(archetype, seed, i) for i in range(n)]


def generate_population(
    seed: int, per_archetype: int, archetypes: tuple[Archetype, ...] | None = None
) -> list[UserProfile]:
    """A mixed population across the given archetypes (all 14 by default)."""
    selected = archetypes if archetypes is not None else tuple(Archetype)
    population: list[UserProfile] = []
    for archetype in selected:
        population.extend(generate_cohort(archetype, per_archetype, seed))
    return population
