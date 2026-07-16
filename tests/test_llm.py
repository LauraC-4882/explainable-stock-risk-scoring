"""Tests for the news-risk extraction schema/prompt scaffolding (no live LLM calls)."""

from stock_risk.llm.news_risk import (
    NEWS_RISK_SCHEMA,
    build_extraction_prompt,
    extract_news_risk,
    summarize_news_risk,
)


def test_schema_has_no_unsupported_numeric_constraints():
    """Claude's structured-outputs schema support excludes minimum/maximum —
    severity must be an enum of integers, not a bounded integer range."""
    severity = NEWS_RISK_SCHEMA["properties"]["severity"]
    assert "minimum" not in severity and "maximum" not in severity
    assert severity["enum"] == [0, 1, 2, 3, 4, 5]
    assert NEWS_RISK_SCHEMA["additionalProperties"] is False
    assert set(NEWS_RISK_SCHEMA["required"]) == set(NEWS_RISK_SCHEMA["properties"])


def test_build_extraction_prompt_includes_inputs():
    prompt = build_extraction_prompt(
        "AAPL", "Apple faces antitrust probe", "Regulators announced..."
    )
    assert "AAPL" in prompt
    assert "antitrust probe" in prompt
    assert "Regulators announced" in prompt


def test_extract_news_risk_without_llm_returns_labeled_mock():
    article = {"title": "Some headline", "summary": "Some summary"}
    result = extract_news_risk(article)
    assert result["source"] == "mock"
    assert result["event_type"] == "none"
    assert result["severity"] == 0
    assert result["title"] == "Some headline"


def test_extract_news_risk_with_llm_uses_call_llm():
    article = {"title": "Regulator sues company", "ticker": "XYZ", "summary": "..."}

    def fake_llm(prompt: str) -> dict:
        assert "XYZ" in prompt
        return {
            "event_type": "lawsuit", "risk_category": "legal_regulatory",
            "sentiment": "negative", "severity": 4, "time_horizon": "short_term",
            "confidence": 0.8, "evidence": ["Regulator sues company"],
        }

    result = extract_news_risk(article, call_llm=fake_llm)
    assert result["source"] == "llm"
    assert result["severity"] == 4
    assert result["title"] == "Regulator sues company"


def test_summarize_news_risk_aggregates_max_severity_and_negative_count():
    extractions = [
        {"severity": 2, "sentiment": "negative"},
        {"severity": 5, "sentiment": "negative"},
        {"severity": 0, "sentiment": "neutral"},
    ]
    summary = summarize_news_risk(extractions)
    assert summary["max_severity"] == 5
    assert summary["negative_count"] == 2
    assert len(summary["articles"]) == 3


def test_summarize_news_risk_empty():
    summary = summarize_news_risk([])
    assert summary == {"max_severity": 0, "negative_count": 0, "articles": []}
