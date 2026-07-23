"""Phase 6: report artifact generation, honesty banners, and run reproducibility."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from stock_risk.simulation.report import CANNOT_CLAIM_BANNER, generate_all

REQUIRED_FILES = [
    "simulated-user-summary.json",
    "user-segment-comparison.csv",
    "comprehension-results.csv",
    "misconception-rates.csv",
    "trust-calibration.csv",
    "accessibility-results.csv",
    "language-parity-results.csv",
    "harmful-action-intent.csv",
    "community-misinformation-results.csv",
    "data-quality-response.csv",
    "social-impact-report.md",
    "harm-risk-register.md",
    "real-user-study-plan.md",
    "resume-claims-checklist.md",
]


@pytest.fixture(scope="module")
def report_dir(tmp_path_factory):
    out = tmp_path_factory.mktemp("sim_report")
    generate_all(out, seed=99, per_archetype=3, experiment_per_archetype=6)
    return out


def test_all_required_artifacts_are_written(report_dir):
    for name in REQUIRED_FILES:
        assert (report_dir / name).exists(), f"missing artifact {name}"
    replays = list((report_dir / "user-replays").glob("*.json"))
    assert len(replays) >= 5              # the 11th deliverable: user-replays/
    assert (report_dir / "MANIFEST.json").exists()


def test_every_csv_carries_the_cannot_claim_banner(report_dir):
    for name in REQUIRED_FILES:
        if not name.endswith(".csv"):
            continue
        first = (report_dir / name).read_text(encoding="utf-8").splitlines()[0]
        assert first.startswith("#")
        assert "NOT REAL-USER DATA" in first


def test_markdown_docs_carry_the_banner_and_key_sections(report_dir):
    social = (report_dir / "social-impact-report.md").read_text(encoding="utf-8")
    assert "NOT REAL-USER DATA" in social
    # The report must cover all 19 required sections.
    for n in range(1, 20):
        assert f"## {n}." in social, f"social-impact-report missing section {n}"

    claims = (report_dir / "resume-claims-checklist.md").read_text(encoding="utf-8")
    assert "Cannot claim" in claims or "cannot claim" in claims.lower()
    for forbidden_claim in ("reduced real investor losses", "Demographic fairness",
                            "Regulatory compliance"):
        assert forbidden_claim.lower() in claims.lower()

    register = (report_dir / "harm-risk-register.md").read_text(encoding="utf-8")
    assert "| Harm |" in register and "Mitigation" in register

    study = (report_dir / "real-user-study-plan.md").read_text(encoding="utf-8")
    for section in ("Participant screening", "Consent language", "stop-criteria",
                    "Privacy-minimising data plan"):
        assert section.lower() in study.lower()


def test_summary_json_shape(report_dir):
    d = json.loads((report_dir / "simulated-user-summary.json").read_text(encoding="utf-8"))
    assert d["banner"] == CANNOT_CLAIM_BANNER
    assert d["n_users"] > 0
    for key in ("mean_comprehension", "overreliance_rate", "harmful_exit_intent_rate",
                "mean_language_parity_gap"):
        assert key in d["headline"]
    for exp_key in ("A", "B", "C", "I"):
        assert exp_key in d["experiments"]
        assert d["experiments"][exp_key]["effect"]["verdict"] in {
            "positive_effect", "negative_effect", "no_effect", "inconclusive"
        }


def test_replays_include_the_honesty_banner(report_dir):
    md_files = list((report_dir / "user-replays").glob("*.md"))
    assert md_files
    for p in md_files:
        assert "not evidence about a real person" in p.read_text(encoding="utf-8")


def _digest(directory: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(directory.rglob("*")):
        if p.is_file():
            h.update(p.read_bytes())
    return h.hexdigest()


def test_same_seed_reproduces_identical_artifacts(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    generate_all(a, seed=5, per_archetype=2, experiment_per_archetype=5)
    generate_all(b, seed=5, per_archetype=2, experiment_per_archetype=5)
    assert _digest(a) == _digest(b)


def test_reports_never_contain_personalised_trade_advice(report_dir):
    # Acceptance invariant: no artifact may tell a user to buy or sell.
    banned = ("you should buy", "you should sell", "we recommend buying",
              "we recommend selling", "guaranteed profit", "guaranteed safe")
    for path in report_dir.rglob("*"):
        if path.is_file() and path.suffix in {".md", ".csv", ".json"}:
            text = path.read_text(encoding="utf-8").lower()
            for phrase in banned:
                assert phrase not in text, f"{path.name} contains advice phrase: {phrase}"
