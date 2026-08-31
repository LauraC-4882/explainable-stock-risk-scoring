"""Pins the audit findings in docs_internal/PORTFOLIO_RISK_DESIGN.md.

The design document makes factual claims about the codebase as of `2f232b2` —
which aggregation exists, where covariance is estimated, what is per-ticker and
what is cross-sectional. Those claims are the basis for the Step 2 proposal, so
they need to fail loudly when they stop being true rather than quietly become a
document describing a codebase nobody has any more.

This is an inventory, not a behaviour test: it asserts what is present and what
is absent. Every assertion names the document section it protects, so a failure
tells you which paragraph to go and rewrite.

It deliberately does NOT assert numbers that were measured (the 82.5%
inner-join survival, the observation counts). Those move with the snapshot
refresh, and pinning them here would recreate the defect the ledger already
records three instances of: a precise figure detached from the inputs that
produced it.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from stock_risk.portfolio import aggregate

REPO = Path(__file__).resolve().parents[1]
DESIGN_DOC = REPO / "docs_internal" / "PORTFOLIO_RISK_DESIGN.md"


# ── Finding 2: covariance estimation exists, and has no shrinkage ────────────


def test_covariance_estimation_exists():
    """Section 2. The brief assumed portfolio aggregation was greenfield; it is
    not, and the document opens by correcting that. If this ever stops being
    true the correction is wrong and section 2 has to be rewritten."""
    source = inspect.getsource(aggregate.compute_portfolio_risk)
    assert ".cov()" in source, "no covariance estimate in compute_portfolio_risk"
    assert "TRADING_DAYS" in source, "covariance is no longer annualised"


def test_euler_allocation_is_exact():
    """Sections 5 and 7. The whole recommendation rests on component risk being
    additive BY CONSTRUCTION rather than approximately — it is what makes Euler
    the portfolio analogue of SHAP, and what makes A1 and A2 inferior. A change
    that broke exactness would invalidate both sections."""
    rng = np.random.default_rng(0)
    index = pd.bdate_range("2024-01-01", periods=400)
    returns = {
        name: pd.Series(rng.standard_normal(400) * scale, index=index)
        for name, scale in (("AAA", 0.01), ("BBB", 0.02), ("CCC", 0.015))
    }
    book = [aggregate.Position(t, w) for t, w in (("AAA", 0.5), ("BBB", 0.3), ("CCC", 0.2))]

    risk = aggregate.compute_portfolio_risk(returns, book)

    # Tolerance follows the storage rounding, not float precision. var_95 is
    # persisted to 6 decimals and the components to 8 (aggregate.py:160-165),
    # so the reconstruction can differ by at most half of the coarser unit.
    # Asserting tighter than the data is stored would test rounding, not
    # additivity.
    assert sum(risk.component_var.values()) == pytest.approx(risk.var_95, abs=5e-7)
    assert sum(risk.risk_contribution_pct.values()) == pytest.approx(100.0, abs=1e-3)


def test_no_shrinkage_estimator_anywhere():
    """Section 5, recommendation 1. The proposal is to ADD Ledoit-Wolf
    shrinkage, which presupposes none is present. Step 2 introducing one must
    make this fail so the recommendation is marked as done rather than left
    reading as outstanding."""
    hits = []
    for path in (REPO / "src").rglob("*.py"):
        body = path.read_text(encoding="utf-8", errors="replace").lower()
        for token in ("ledoit", "shrinkage", "shrunk_covariance", "oas("):
            if token in body:
                hits.append(f"{path.relative_to(REPO)}: {token}")
    assert not hits, (
        "A covariance shrinkage estimator now exists; section 5's recommendation "
        "1 is stale:\n  " + "\n  ".join(hits)
    )


def test_alignment_is_an_inner_join_with_no_filling():
    """Section 3. The measured sample loss, and the whole
    non-synchronous-trading caveat, follow from this being an inner join. A
    switch to forward-filling or reindexing would silently invalidate the
    section."""
    source = inspect.getsource(aggregate._aligned_returns)
    assert "dropna" in source, "alignment no longer drops incomplete rows"
    for forbidden in ("ffill", "fillna", "reindex", "resample"):
        assert forbidden not in source, f"alignment now uses {forbidden}"


def test_alignment_loss_is_not_yet_reported():
    """Section 3, consequence 2 and section 10, item 2. `n_observations` is
    returned but the union count is not, so a caller cannot distinguish a
    complete sample from a heavily-trimmed one."""
    fields = set(aggregate.PortfolioRisk.__dataclass_fields__)
    assert "n_observations" in fields
    assert not fields & {"n_available", "n_discarded", "union_observations"}, (
        "The alignment loss is now reported; section 3 and section 10 item 2 "
        "need updating."
    )


# ── Finding 1: what is per-ticker vs cross-sectional ────────────────────────


def test_single_name_scoring_still_fetches_its_own_benchmark():
    """Section 1 and section 4. The per-score fetch count — and the claim that a
    portfolio shares one benchmark pull rather than paying N — depends on the
    benchmark being fetched inside score() rather than passed in."""
    from stock_risk.scoring.scorer import RiskScorer

    source = inspect.getsource(RiskScorer.score)
    assert "MARKET_BENCHMARKS" in source or "benchmark_ticker" in source
    assert "fetch_history" in source


def test_the_composite_is_a_self_relative_percentile():
    """Section 5, the argument that rejects A1. If scores ever became
    cross-sectionally comparable, averaging them would stop being a category
    error and A1 would have to be re-evaluated on its merits."""
    from stock_risk.scoring import risk_categories

    source = inspect.getsource(risk_categories)
    assert "_MIN_HISTORY" in source
    assert "percentile" in source.lower(), (
        "The composite no longer describes itself as a percentile; section 5's "
        "rejection of score averaging rests on it being one."
    )


# ── The document itself ─────────────────────────────────────────────────────


def test_design_document_exists_and_names_its_baseline():
    """A design document without the commit it audited is a document about an
    unknown codebase."""
    assert DESIGN_DOC.exists(), f"{DESIGN_DOC} is missing"
    text = DESIGN_DOC.read_text(encoding="utf-8")
    assert "2f232b2" in text, "the audited baseline commit is not recorded"


def test_design_document_contains_no_position_advice():
    """Repository-wide rule, and this document describes a portfolio feature —
    the surface where advice language is most tempting."""
    text = DESIGN_DOC.read_text(encoding="utf-8").lower()
    # Word-boundary matched, and "hold" only in its imperative sense: the
    # document legitimately says "holding(s)" throughout and "distinction to
    # hold onto" once, none of which is a position instruction. A bare
    # substring check flagged that sentence, which is a checker problem rather
    # than a copy problem.
    import re

    forbidden = (
        r"\bbuy\b", r"\bsell\b", r"\bshould buy\b", r"\bshould sell\b",
        r"\bhold (?:this|that|it|the position)\b",
        r"\byou should\b", r"\brecommend (?:buying|selling|holding)\b",
        r"\bprice target\b", r"\boverweight\b", r"\bunderweight\b",
    )
    hits = [pattern for pattern in forbidden if re.search(pattern, text)]
    assert not hits, f"advice language in the design document: {hits}"
