"""Markdown templates for the four narrative report artifacts.

Kept separate from report.py so the (long) prose lives in one place. Each
document opens with the cannot-claim banner and weaves in the run's computed
headline numbers where they are load-bearing, so the narrative stays tied to the
actual output rather than drifting into claims the data doesn't support.
"""

from __future__ import annotations

from .report import CANNOT_CLAIM_BANNER


def _banner_block() -> str:
    return f"> ⚠️ **{CANNOT_CLAIM_BANNER}**\n"


def social_impact_report_md(summary: dict, experiments: dict) -> str:
    h = summary["headline"]
    exp = experiments

    def verdict(key: str) -> str:
        e = exp[key]["effect"]
        return (f"{exp[key]['control_arm']} {exp[key]['control_mean']} → "
                f"{exp[key]['treatment_arm']} {exp[key]['treatment_mean']} "
                f"(effect {e['mean_diff']:+}, "
                f"CI[{e['ci_low']}, {e['ci_high']}], **{e['verdict']}**)")

    return f"""# Social-Impact Evaluation — Simulated-User Study

{_banner_block()}

## 1. Executive summary

A seeded, offline simulated-user harness evaluated the Explainable Equity Risk
platform for **comprehension, harm reduction, trust calibration, accessibility,
and fairness** — deliberately NOT for engagement. Across {summary['n_users']}
simulated users spanning 14 archetypes, headline signals were: mean comprehension
**{h['mean_comprehension']}**, over-reliance rate **{h['overreliance_rate']}**,
harmful-exit-intent rate **{h['harmful_exit_intent_rate']}**, and a mean
English↔Chinese parity gap of **{h['mean_language_parity_gap']}** on untranslated
content. The strongest, most defensible product levers were **portfolio risk
attribution** and a **crisis-safe presentation**; the clearest risk was that
**safeguards which rely on reading (data-quality warnings, model-degradation
notices) reach the literate and largely miss the users who most need them.**

## 2. Methodology

Every simulated user is a typed disposition vector drawn from a seeded,
per-archetype distribution. The platform's *real* pure functions (percentile
composite, component-VaR portfolio aggregation, historical outcomes) generate the
system output; a "perception bridge" turns that output into typed content units,
and an interpretation model decides — per unit — what the user notices,
understands, or misreads, updating a live misconception set. Actions are chosen by
a seeded utility model. Inference is paired, user-level bootstrap with a declared
MDE and Benjamini-Hochberg correction on segment analyses. Nothing touches the
network; the same seed reproduces the run byte-for-byte.

## 3. Simulated user groups

Fourteen archetypes: first-time retail, young high-risk trader, cautious
retirement saver, low-financial-literacy, experienced investor, financial advisor,
concentrated-employer-stock holder, market-crash user, visual-accessibility user,
Chinese-language user, illiquid/data-sparse user, community-influenced user,
financially-stressed user, and adversarial/misuse user. Each is a distribution,
not a template — within-group variance is enforced and tested.

## 4. Behavioural assumptions

All coefficients (trait means/spreads, concept difficulties, notice/understand
functions, utility weights) are **developer-encoded priors**, documented in code
so they can be inspected and sensitivity-tested. They are plausible and
directionally defensible, not measured from people.

## 5. Comprehension findings

Mean comprehension **{h['mean_comprehension']}**, with a steep literacy gradient
(see `comprehension-results.csv` and `user-segment-comparison.csv`). Low-literacy
users answer core probability/VaR items correctly far less often than
professionals.

## 6. Misconceptions

The most persistent misconceptions were *score-as-probability*,
*score-as-advice*, and *ignores-data-quality* (see `misconception-rates.csv`).
The score-as-probability misconception forms readily when the 0–100 score is seen
without its plain-language, self-relative meaning.

## 7. Trust calibration

Over-reliance rate **{h['overreliance_rate']}** (see `trust-calibration.csv`).
Over-trust concentrates in high-automation-trust users who did not take in the
disclaimer; model-degradation disclosure calibrated trust for professionals but
barely reached novices.

## 8. Decision-quality findings

Portfolio attribution: {verdict('B')}. Crisis-safe presentation on harmful-exit
intent (a harm — a negative effect is the good outcome): {verdict('C')}.

## 9. Accessibility findings

Chart alt-text materially raised screen-reader task completion; a hypothetical
colour-only design stripped the protection that the current product's redundant
text labels provide to colour-deficient users (see `accessibility-results.csv`).

## 10. Language-parity findings

Mean untranslated-content parity gap **{h['mean_language_parity_gap']}**: Chinese
users lose ground specifically on the audited English-only strings (stress-test
narratives, SHAP feature names), not on the translated core (see
`language-parity-results.csv`).

## 11. Community and misinformation risks

The permanent opinion-vs-model separation disclaimer reduced community override of
model evidence; highly-upvoted misleading posts still swayed the most
socially-sensitive users (see `community-misinformation-results.csv`).

## 12. Market-crash scenario

A non-alarmist, delayed-action crisis-safe presentation reduced harmful-exit
intent relative to the standard card — the effect is strongest for mid/high
literacy and weakest for the panic-narrowed, low-disclosure users.

## 13. Data-quality and model-degradation findings

The current product surfaces **no confidence, freshness, or model-version flag on
a score**. In the simulation, low-quality data is taken at face value ~100% of the
time without a warning; a surfaced warning helps — but far more for professionals
than for low-literacy users (`data-quality-response.csv`).

## 14. Harm-risk register

See `harm-risk-register.md` for the ranked register (severity × likelihood ×
affected-users × detectability × reversibility, each with a mitigation).

## 15. Product recommendations

1. Surface a **data-confidence / freshness flag** on the score, and **suppress**
   the score when evidence is insufficient (do not fall back to a silent neutral).
2. Show **concentration/attribution before the composite** for portfolios, in
   plain language, not raw component-VaR alone.
3. Ship a **crisis-safe presentation mode** (freshness, uncertainty, delayed-action
   framing, muted colour).
4. Add a **plain-language layer** and a **probability-misconception clarifier** to
   the score hero.
5. Translate the remaining **English-only strings**; add **chart text
   alternatives** and modal focus management.
Each recommendation cites its scenario, affected segment, observed metric,
trade-off, and limitation in the harm register.

## 16. Social-impact opportunities

Financial-literacy education, risk communication, concentration awareness, model
transparency, misinformation resistance, accessibility, and responsible design
that rewards understanding over trading — with the measurable outcome, potential
harm, mitigation, and required evidence for each.

## 17. Limitations

Simulated users are not people; the harness discovers product risks, not
population behaviour. Coefficients could encode the hoped-for conclusion (mitigated
by inspectable priors + sensitivity analysis). An accessibility "pass" here is not
a real axe/screen-reader pass.

## 18. Claims that cannot yet be made

See `resume-claims-checklist.md`. In short: no claim of reduced real losses,
improved returns, real-user comprehension gains, demographic fairness, regulatory
compliance, or suitability for individualised advice.

## 19. Proposed real-user validation plan

See `real-user-study-plan.md` — a low-risk moderated usability study with
screening, consent, non-advisory framing, task script, comprehension items, a
distress stop-rule, and a privacy-minimising data plan.
"""


def harm_risk_register_md() -> str:
    rows = [
        ("Score read as probability of loss", "High", "High", "Novice, low-numeracy",
         "Medium", "Reversible",
         "Add a probability-misconception clarifier + plain-language meaning next to the score."),
        ("Score read as buy/sell advice", "High", "Medium", "Novice, financially-stressed",
         "Medium", "Reversible",
         "Keep the non-advisory disclaimer prominent; add a comprehension "
         "checkpoint before sharing."),
        ("Low-confidence data shown as a normal score", "High", "High", "Illiquid/data-sparse, all",
         "Low (no flag today)", "Reversible",
         "Surface a confidence/freshness flag; suppress the score when evidence is insufficient."),
        ("Panic selling amplified by red/high score", "High", "Medium", "Crash-mode, loss-averse",
         "Medium", "Hard to reverse (a real sale)",
         "Crisis-safe mode: muted colour, freshness, delayed-action framing, "
         "professional-help off-ramp."),
        ("Concentration blindness", "Medium", "High", "Employer-stock, novice",
         "Medium", "Reversible",
         "Show plain-language concentration/attribution before the composite."),
        ("Model degradation invisible to users", "Medium", "High", "All (governance unwired live)",
         "Low", "Reversible",
         "Thread model_version + degraded status into the score response and UI."),
        ("Community hype overrides model evidence", "Medium", "Medium", "Socially-sensitive",
         "Medium", "Reversible",
         "Keep opinion/model separation; add friction before acting on unsupported claims."),
        ("English-only strings in Chinese UI", "Medium", "High", "Chinese-language",
         "High", "Reversible",
         "Translate stress narratives, risk_note, SHAP feature names; add parity tests."),
        ("Colour-only risk cues", "Medium", "Low (today)", "Colour-vision-deficient",
         "High", "Reversible",
         "Preserve redundant text labels; never ship colour-only meaning."),
        ("Chart content invisible to screen readers", "Medium", "High", "Screen-reader users",
         "Low", "Reversible", "Add chart text alternatives / data-table summaries."),
        ("SHAP attribution read as causation", "Low", "Medium", "Experienced (mis)readers",
         "Medium", "Reversible", "Label SHAP as associational, not causal."),
        ("Historical stress test read as prediction", "Medium", "Medium", "All",
         "Medium", "Reversible", "Keep the descriptive framing; reinforce 'not a forecast'."),
    ]
    header = (
        "| Harm | Severity | Likelihood | Most-affected | Detectability | "
        "Reversibility | Mitigation |\n"
        "|---|---|---|---|---|---|---|\n"
    )
    body = "\n".join("| " + " | ".join(r) + " |" for r in rows)
    return f"""# Harm-Risk Register — Simulated-User Study

{_banner_block()}

Ranked most-severe first. Severity/likelihood/affected/detectability/reversibility
are simulation-informed judgements, each paired with a concrete mitigation. These
are hypotheses to confirm with real users, not measured incident rates.

{header}{body}

## Cross-cutting finding

The three highest-impact risks (probability misread, low-confidence data shown as
normal, panic selling) share a root cause: **the product presents a single
confident number without the confidence, freshness, and plain-language context a
non-expert needs to read it safely** — and the safeguards that do exist rely on
reading fine print, which the most vulnerable users skip.
"""


def real_user_study_plan_md() -> str:
    return f"""# Real-User Validation Plan (Low-Risk Usability Study)

{_banner_block()}

This plan prepares a **future** moderated usability study. It does not recruit or
contact anyone, and stores no real brokerage credentials, account numbers, or
personal portfolios. Synthetic/fictional portfolios are the default.

## Participant screening
- Adults (18+) who make or influence their own investment decisions.
- Mixed financial literacy and numeracy (self-reported screener).
- Include English- and Chinese-preferring participants.
- Include participants who use a screen reader, keyboard-only navigation, or have
  colour-vision deficiency.
- Exclude anyone seeking personalised investment advice from the session.

## Consent language (draft)
"This is a research session about how people understand a risk-analysis tool. It is
**not** investment advice and gives no buy/sell recommendations. Participation is
voluntary; you may stop at any time. We record only what is needed to study
comprehension, and we do not collect account numbers, credentials, or real
holdings."

## Non-advisory study disclaimer
Displayed before and during the session: the tool is educational, describes
historical risk, is not a forecast, and is not personalised advice.

## Task script (maps to the simulated tasks)
1. Analyse one stock and say, in your own words, what the score means.
2. Compare two stocks of different risk.
3. Review a (synthetic) concentrated portfolio; identify the biggest risk source.
4. Interpret a 95% VaR figure and a high composite score.
5. Review a stress scenario and a data-quality warning.
6. Read a community post that conflicts with the model; decide what you'd do.
7. Switch to Chinese (if applicable); complete a task keyboard-only / with a
   screen reader (if applicable).

## Comprehension questions
The ten items in the harness's question bank (score-as-probability, low-vol-safe,
VaR-as-max-loss, low-risk-returns, history-guarantees-future, breach-rate,
illiquid-unreliable, component-VaR, many-names-diversified, low-confidence-action).

## Interview questions
- What does the score tell you? What does it NOT tell you?
- When would you distrust it? Did you notice any caveats?
- What would you do next, and why?

## Moderator guide
Neutral prompts only; never suggest a trade; do not lead toward "correct" answers;
capture verbatim interpretations.

## Severity rubric
Critical (would act harmfully on a misread) > Major (persistent misconception) >
Minor (confusion, self-corrected) > Cosmetic.

## Observation template
Per task: content noticed / understood / misread; confidence; intended action;
any caveat noticed; accessibility friction; verbatim quote.

## Distress stop-criteria
If a participant shows acute financial distress or treats the session as personal
advice, the moderator stops the task, restates the non-advisory boundary, offers a
break, and provides signposting to qualified, independent guidance. No diagnosis,
no inference of protected characteristics.

## Privacy-minimising data plan
Pseudonymous IDs; synthetic portfolios; no credentials/account numbers; recordings
stored encrypted with a short retention window and a clear deletion date; analysis
on de-identified transcripts.
"""


def resume_claims_checklist_md(summary: dict) -> str:
    h = summary["headline"]
    return f"""# Resume / Claims Checklist — What Is (and Isn't) Defensible

{_banner_block()}

## ✅ Defensible now (about the *work*, not real users)
- "Designed and built a **seeded, fully offline, deterministic simulated-user
  evaluation harness** for an equity-risk platform, spanning 14 typed archetypes,
  20 tasks, and 10 scenarios."
- "Modelled **comprehension, misconception formation/correction, trust
  calibration, and action intent**, driving the platform's own risk functions."
- "Ran **pre-declared paired experiments** with user-level bootstrap CIs, an MDE,
  and Benjamini-Hochberg correction; distinguished **no-effect from
  inconclusive**."
- "Surfaced concrete product risks (e.g. a **low-confidence score shown with no
  confidence flag**; **English-only strings in the Chinese UI**; **chart content
  invisible to screen readers**) and proposed prioritised mitigations."
- "Found, in simulation, that **portfolio attribution** and a **crisis-safe
  presentation** were the strongest levers, while **read-dependent safeguards
  under-serve low-literacy users**."

## ❌ Cannot claim (needs real users / data the harness does not have)
- ❌ Reduced real investor losses or improved real-world returns.
- ❌ That real users understand risk better (only simulated comprehension of
  {h['mean_comprehension']} was observed).
- ❌ Demographic fairness (no demographic data exists; only product-experience
  disparities across simulated dimensions).
- ❌ Regulatory compliance or suitability for individualised advice.
- ❌ Any causal or clinical claim about real people.
- ❌ That the simulated effect sizes (e.g. attribution, crisis-safe) will hold in a
  real population.

## Phrase effects as hypotheses
Every effect above is a **hypothesis to test with real users**, produced by
developer-encoded behavioural priors — see `real-user-study-plan.md`.
"""
