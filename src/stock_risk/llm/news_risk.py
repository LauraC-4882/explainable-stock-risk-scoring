"""LLM-based news event extraction — schema and prompt are wired end-to-end;
the actual Claude API call is NOT invoked by default anywhere in this codebase.

Design constraints (see project decision log): the LLM never computes VaR,
drawdown, or the composite risk score, and it never freely narrates a risk
verdict — every call is forced into a fixed JSON schema via Claude's
structured-outputs contract (`output_config.format`), so the same headline
always maps to the same field set regardless of phrasing. Determinism is
enforced by that schema, not a `temperature` parameter — `temperature` is
not accepted on current Claude models and was never a reliable determinism
lever to begin with.

Model choice: Claude Haiku 4.5, not the usual Opus default. This is a
high-volume, low-stakes classification task (one call per headline, output
already constrained by the schema) — Opus's extra reasoning capability isn't
load-bearing here, and Haiku is ~5x cheaper per token. Note Haiku 4.5 does
NOT support the `effort` parameter (it 400s), unlike Opus/Sonnet 5 — omit it.

To wire up a live call: pass `call_claude_news_extractor` as the `call_llm`
argument to `extract_news_risk()` (requires `pip install anthropic` and
`ANTHROPIC_API_KEY` set). Until then, `extract_news_risk()` returns a
clearly-labeled stub so the rest of the pipeline (fetch → extract →
aggregate) can be exercised end-to-end without spending API credits.
"""

from __future__ import annotations

import json
from typing import Callable, Optional

MODEL = "claude-haiku-4-5"

# Fixed taxonomy — do not let the model invent new categories; "none" is the
# explicit no-signal case so severity=0 is distinguishable from "not classified".
EVENT_TYPES = [
    "earnings_miss", "guidance_cut", "regulatory_investigation", "lawsuit",
    "management_departure", "product_failure", "cybersecurity_incident",
    "credit_liquidity_concern", "supply_chain_disruption", "macro_exposure", "none",
]
RISK_CATEGORIES = ["operational", "legal_regulatory", "financial", "reputational", "market", "none"]
SENTIMENTS = ["negative", "neutral", "positive"]
TIME_HORIZONS = ["immediate", "short_term", "medium_term", "long_term", "unknown"]

NEWS_RISK_SCHEMA = {
    "type": "object",
    "properties": {
        "event_type": {"type": "string", "enum": EVENT_TYPES},
        "risk_category": {"type": "string", "enum": RISK_CATEGORIES},
        "sentiment": {"type": "string", "enum": SENTIMENTS},
        "severity": {
            "type": "integer",
            "enum": [0, 1, 2, 3, 4, 5],
            "description": "0 = no material risk signal, 5 = severe / company-threatening",
        },
        "time_horizon": {"type": "string", "enum": TIME_HORIZONS},
        "confidence": {
            "type": "number",
            "description": "Model's confidence in this classification, roughly 0.0-1.0",
        },
        "evidence": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Short verbatim quotes from the headline/summary supporting the classification",
        },
    },
    "required": [
        "event_type", "risk_category", "sentiment", "severity",
        "time_horizon", "confidence", "evidence",
    ],
    "additionalProperties": False,
}

SYSTEM_PROMPT = (
    "You are a financial risk event classifier. Given a single news headline "
    "and summary about a publicly traded company, classify it into a fixed "
    "taxonomy. Base your answer only on the provided text — do not use prior "
    "knowledge about the company or speculate beyond what the text states. "
    "If the article contains no identifiable risk signal (e.g. routine "
    'market commentary, a product announcement with no downside), use '
    'event_type="none", risk_category="none", sentiment="neutral", severity=0.'
)


def build_extraction_prompt(ticker: str, headline: str, summary: str = "") -> str:
    """Build the user-turn prompt for a single news article."""
    return (
        f"Ticker: {ticker}\n"
        f"Headline: {headline}\n"
        f"Summary: {summary or '(no summary available)'}"
    )


def call_claude_news_extractor(prompt: str) -> dict:
    """Reference implementation of the real Claude API call.

    Not invoked by default anywhere in this codebase — pass this function as
    `call_llm` to `extract_news_risk()` once `anthropic` is installed and
    `ANTHROPIC_API_KEY` is configured.
    """
    import anthropic  # local import: keep anthropic an opt-in dependency

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=MODEL,
        max_tokens=512,
        system=SYSTEM_PROMPT,
        # No `effort` here — unlike Opus/Sonnet 5, Haiku 4.5 doesn't accept it (400s).
        output_config={"format": {"type": "json_schema", "schema": NEWS_RISK_SCHEMA}},
        messages=[{"role": "user", "content": prompt}],
    )
    text = next(b.text for b in response.content if b.type == "text")
    return json.loads(text)


_MOCK_RESULT = {
    "event_type": "none",
    "risk_category": "none",
    "sentiment": "neutral",
    "severity": 0,
    "time_horizon": "unknown",
    "confidence": 0.0,
    "evidence": [],
}


def extract_news_risk(
    article: dict, call_llm: Optional[Callable[[str], dict]] = None
) -> dict:
    """Classify a single news article's risk signal.

    *article* is a dict with at least "title" (from `MarketDataFetcher.fetch_news`).
    Without `call_llm`, returns a clearly-labeled stub (`source: "mock"`) so the
    fetch -> extract -> aggregate pipeline is exercisable without a live API call.
    """
    if call_llm is None:
        return {
            **_MOCK_RESULT,
            "title": article.get("title"),
            "source": "mock",
        }
    prompt = build_extraction_prompt(
        ticker=article.get("ticker", ""),
        headline=article.get("title", ""),
        summary=article.get("summary", ""),
    )
    result = call_llm(prompt)
    return {**result, "title": article.get("title"), "source": "llm"}


def summarize_news_risk(extractions: list[dict]) -> dict:
    """Aggregate per-article extractions into a single news-risk summary."""
    if not extractions:
        return {"max_severity": 0, "negative_count": 0, "articles": []}
    return {
        "max_severity": max(e.get("severity", 0) for e in extractions),
        "negative_count": sum(1 for e in extractions if e.get("sentiment") == "negative"),
        "articles": extractions,
    }
