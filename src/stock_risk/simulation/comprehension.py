"""Comprehension question bank, answer model, and misconception detection.

The framework needs to measure *understanding*, not clicks. Each question is a
statement about a core risk concept with a known correct answer and, when the
wrong answer is diagnostic, the specific misconception it reveals (e.g. answering
"yes" to "does 80/100 mean an 80% chance of loss?" reveals
``SCORE_IS_PROBABILITY``). The answer model is deliberately simple and legible:

* a user who *holds* the associated misconception answers per that misconception
  (usually wrong), and the wrong answer is recorded as a detection;
* otherwise, the probability of a correct answer is a logistic function of the
  user's concept ability versus the question's difficulty, lifted if they took in
  and understood the relevant explanation earlier in the session.

Confidence is tracked separately from correctness so the framework can see
over-confidence (sure and wrong) distinctly from calibrated uncertainty. All
questions carry both English and Chinese prompts so the language-parity scenario
can run the identical battery in either language.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import numpy as np

from .interpret import UserState, _ability_for, _clamp
from .presentation import Concept
from .profiles import Misconception, UserProfile


@dataclass(frozen=True)
class Question:
    """A single comprehension item with a known answer and diagnostic misconception."""

    qid: str
    concept: Concept
    # The statement is FALSE for probability/advice traps; correct_answer is what a
    # user who understands SHOULD say (True/False to the framed statement).
    correct_answer: bool
    difficulty: float
    prompt_en: str
    prompt_zh: str
    misconception_if_wrong: Optional[Misconception] = None


# The ten concepts the framework calls out, as answerable items.
QUESTION_BANK: tuple[Question, ...] = (
    Question(
        "q_score_probability", Concept.COMPOSITE_SCORE, correct_answer=False, difficulty=0.4,
        prompt_en="Does a risk score of 80/100 mean an 80% chance of loss?",
        prompt_zh="风险评分 80/100 是否意味着有 80% 的亏损概率？",
        misconception_if_wrong=Misconception.SCORE_IS_PROBABILITY,
    ),
    Question(
        "q_low_vol_safe", Concept.VOLATILITY, correct_answer=False, difficulty=0.45,
        prompt_en="Does low volatility mean a stock cannot decline substantially?",
        prompt_zh="低波动率是否意味着该股票不会大幅下跌？",
        misconception_if_wrong=Misconception.LOW_VOL_CANNOT_FALL,
    ),
    Question(
        "q_var_max_loss", Concept.VAR, correct_answer=False, difficulty=0.6,
        prompt_en="Does a 5% VaR mean losses can never exceed the VaR amount?",
        prompt_zh="5% 的 VaR 是否意味着亏损永远不会超过该 VaR 数值？",
        misconception_if_wrong=Misconception.VAR_IS_MAX_LOSS,
    ),
    Question(
        "q_low_risk_returns", Concept.RISK_LABEL, correct_answer=False, difficulty=0.4,
        prompt_en="Does a low risk score imply high expected returns?",
        prompt_zh="较低的风险评分是否意味着较高的预期回报？",
        misconception_if_wrong=Misconception.LOW_RISK_MEANS_SAFE,
    ),
    Question(
        "q_history_guarantee", Concept.HISTORICAL_OUTCOMES, correct_answer=False, difficulty=0.35,
        prompt_en="Does historical performance guarantee future behaviour?",
        prompt_zh="历史表现是否保证未来的走势？",
        misconception_if_wrong=Misconception.HISTORY_GUARANTEES_FUTURE,
    ),
    Question(
        "q_breach_rate", Concept.VAR, correct_answer=True, difficulty=0.8,
        prompt_en="A 9.25% realised breach rate versus a 5% target indicates the model "
                  "underestimates tail risk. True?",
        prompt_zh="实际突破率 9.25% 对比 5% 的目标，说明模型低估了尾部风险。对吗？",
    ),
    Question(
        "q_illiquid_unreliable", Concept.LIQUIDITY, correct_answer=True, difficulty=0.55,
        prompt_en="Can an illiquid stock have an unreliable risk score?",
        prompt_zh="流动性差的股票，其风险评分是否可能不可靠？",
    ),
    Question(
        "q_component_var", Concept.RISK_CONTRIBUTION, correct_answer=True, difficulty=0.68,
        prompt_en="Does component VaR show how much each position contributes to total "
                  "portfolio risk?",
        prompt_zh="成分 VaR 是否显示每个持仓对投资组合总风险的贡献？",
    ),
    Question(
        "q_many_names_diversified", Concept.CONCENTRATION, correct_answer=False, difficulty=0.55,
        prompt_en="Is a portfolio automatically well-diversified just because it holds "
                  "many stocks?",
        prompt_zh="仅仅因为持有很多股票，投资组合就一定是充分分散的吗？",
        misconception_if_wrong=Misconception.DIVERSIFIED_IF_MANY_NAMES,
    ),
    Question(
        "q_low_confidence_action", Concept.UNCERTAINTY, correct_answer=True, difficulty=0.5,
        prompt_en="When model confidence is low, is the appropriate response to treat the score "
                  "with extra caution (or not act on it alone)?",
        prompt_zh="当模型置信度较低时，恰当的做法是否是对评分更加谨慎（或不单凭它行动）？",
    ),
)


@dataclass
class QuestionResult:
    qid: str
    concept: str
    correct: bool
    confidence: float
    misconception_revealed: Optional[str]
    prompt: str


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def answer_question(
    profile: UserProfile,
    state: UserState,
    question: Question,
    rng: np.random.Generator,
) -> QuestionResult:
    """Model one answer. Holding the trap misconception drives a wrong answer."""
    holds_misconception = (
        question.misconception_if_wrong is not None
        and question.misconception_if_wrong in state.misconceptions
    )
    ability = _ability_for(profile, question.concept)
    understood_boost = 0.15 if question.concept in state.understood_concepts else 0.0

    if holds_misconception:
        # Small chance they answer correctly despite the misconception (partial
        # knowledge / guessing), but mostly they answer per the misconception.
        p_correct = _clamp(0.12 + 0.2 * ability)
    else:
        p_correct = _clamp(
            _sigmoid(5.0 * (ability + understood_boost - question.difficulty))
        )

    correct = bool(rng.random() < p_correct)

    # Confidence: driven by numeracy/prob-comprehension and automation trust; a
    # held misconception makes a user *more* sure of their (wrong) answer.
    confidence = _clamp(
        0.35
        + 0.3 * profile.probability_comprehension
        + 0.2 * profile.numeracy
        + (0.2 if holds_misconception else 0.0)
    )

    revealed: Optional[Misconception] = None
    if not correct and question.misconception_if_wrong is not None:
        revealed = question.misconception_if_wrong
        state.misconceptions.add(revealed)  # a wrong diagnostic answer reveals/holds it

    prompt = question.prompt_zh if profile.language.value == "zh" else question.prompt_en
    return QuestionResult(
        qid=question.qid,
        concept=question.concept.value,
        correct=correct,
        confidence=round(confidence, 3),
        misconception_revealed=revealed.value if revealed else None,
        prompt=prompt,
    )


@dataclass
class ComprehensionOutcome:
    results: list[QuestionResult]
    n_correct: int
    n_total: int
    misconceptions_revealed: list[str]

    @property
    def score(self) -> float:
        return self.n_correct / self.n_total if self.n_total else 0.0

    @property
    def overconfident_wrong(self) -> int:
        """Count of answers that were wrong yet held with high confidence."""
        return sum(1 for r in self.results if (not r.correct and r.confidence >= 0.6))


def run_comprehension_battery(
    profile: UserProfile,
    state: UserState,
    rng: np.random.Generator,
    questions: tuple[Question, ...] = QUESTION_BANK,
) -> ComprehensionOutcome:
    """Ask the whole bank (or a subset) and score it."""
    results = [answer_question(profile, state, q, rng) for q in questions]
    revealed = sorted({r.misconception_revealed for r in results if r.misconception_revealed})
    return ComprehensionOutcome(
        results=results,
        n_correct=sum(1 for r in results if r.correct),
        n_total=len(results),
        misconceptions_revealed=revealed,
    )
