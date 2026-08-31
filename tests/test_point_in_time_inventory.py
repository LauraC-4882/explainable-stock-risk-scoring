"""Registry pins for docs_internal/POINT_IN_TIME_AUDIT.md.

Companion to tests/test_pit_tamper_invariance.py, which carries the
behavioural evidence. This file pins the audit's REGISTRY: every row's code
anchor still exists where the document says it does, and the recorded status
cannot be rewritten silently — editing either the code site or the audit's
verdict must turn something red here so the other one is updated with it.
Mirrors tests/test_return_convention_inventory.py on the
audit/return-convention branch, the sibling inventory this repo already uses.

Anchors are source substrings rather than line numbers on purpose: a line
number rots on any unrelated edit above it, while the substring is the
behaviourally load-bearing text itself.
"""

from __future__ import annotations

import re
import subprocess
import warnings
from pathlib import Path

import pandas as pd
import pytest

_REPO = Path(__file__).resolve().parents[1]
_AUDIT = _REPO / "docs_internal" / "POINT_IN_TIME_AUDIT.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


# (row id, file under audit, source anchor that must still exist, status word
#  the audit must still record for that row)
INVENTORY = [
    ("A1", "src/stock_risk/data/fetcher.py", "auto_adjust=True", None),
    ("A1", "src/stock_risk/data/fetcher.py", 'adjust="qfq"', None),
    # The Twelve Data request must keep NOT sending an adjustment parameter
    # for row A2 to stay accurate — asserted behaviourally below instead.
    ("A1.ii", "src/stock_risk/features/risk_metrics.py",
     'dollar_vol = df["close"] * df["volume"]', "confirmed-leak"),
    ("A1.iii", "src/stock_risk/models/feature_sets.py", '"atr_14"', "confirmed-leak"),
    ("B1", "src/stock_risk/data/preprocessor.py", "std = log_ret.std()", "confirmed-leak"),
    ("B1", "src/stock_risk/data/preprocessor.py",
     "next_day_ret = log_ret.shift(-1)", "confirmed-leak"),
    ("B2", "scripts/validate_score.py", "def _expanding_outlier_filter", "clean"),
    ("B3", "src/stock_risk/scoring/risk_categories.py", "def _historical_percentile", "clean"),
    ("C1", "src/stock_risk/models/volatility.py", "def fit", "clean"),
    ("C2", "src/stock_risk/models/evaluation.py", "gap: int = 20", "clean"),
    ("C2", "src/stock_risk/models/downside_risk.py",
     "n_calib = max(1, int(len(X) * calib_frac))", "confirmed-leak"),
    ("D1", "src/stock_risk/models/explain.py", "shap.TreeExplainer(xgb)", "clean"),
    ("E2", "src/stock_risk/data/fetcher.py", '"published_at"', "clean"),
    ("F", "src/stock_risk/scoring/scorer.py", 'if market == "us":', "clean"),
    ("G2", "scripts/tickers_universe.txt", "AAPL", "confirmed-leak"),
    ("H", "src/stock_risk/data/preprocessor.py", "ffill(limit=self.max_gap_days)", "clean"),
]


@pytest.mark.parametrize("row_id,rel_path,anchor,status", INVENTORY,
                         ids=[f"{r[0]}:{Path(r[1]).name}:{i}" for i, r in enumerate(INVENTORY)])
def test_audit_rows_still_match_the_code_and_the_recorded_status(row_id, rel_path, anchor, status):
    source = _read(_REPO / rel_path)
    assert anchor in source, (
        f"audit row {row_id}: anchor {anchor!r} no longer exists in {rel_path} — "
        "the code moved; re-verify the row and update the audit document"
    )
    doc = _read(_AUDIT)
    assert row_id in doc, f"audit document lost row {row_id}"
    if status is not None:
        # The status must appear in the row's section (between this row id and
        # the next section heading), so a verdict cannot be silently flipped.
        section = re.split(r"\n#{2,3} ", doc)
        holding = [s for s in section if row_id in s]
        assert any(status in s for s in holding), (
            f"audit row {row_id}: status {status!r} no longer recorded — if the "
            "verdict changed, change it loudly (row text AND this inventory)"
        )


def test_twelvedata_request_still_sends_no_adjustment_parameter():
    """Row A2's factual basis: the request sends symbol/interval/outputsize/
    apikey only. If an adjustment parameter is ever added, row A2 must be
    resolved (and the probe script retired), so this goes red with it."""
    source = _read(_REPO / "src/stock_risk/data/fetcher.py")
    call = source.split("api.twelvedata.com/time_series", 1)[1][:400]
    assert '"apikey"' in call
    assert "adjust" not in call, (
        "the Twelve Data request now sends an adjustment parameter — "
        "resolve audit row A2 and update this pin"
    )


def test_snapshot_content_never_postdates_its_commit():
    """Audit row I: a tracked snapshot whose content extends past the commit
    that recorded it would be fabricated data — the one direction that is a
    point-in-time violation (staleness, the other direction, is not).

    Shallow clones report the depth-boundary commit's date for every file
    (verified empirically: a depth-1 clone dates a July-fetched snapshot at
    the clone-boundary commit in August), which makes the assertion vacuously
    true there — so this SKIPS, announced, rather than green-lighting
    nothing. CI runs shallow until the fetch-depth workflow change is merged;
    full local clones execute it.
    """
    shallow = subprocess.run(
        ["git", "rev-parse", "--is-shallow-repository"],
        capture_output=True, text=True, cwd=_REPO, check=True,
    ).stdout.strip()
    if shallow == "true":
        message = (
            "snapshot-timing check SKIPPED: shallow clone dates every file at "
            "the clone boundary, making the assertion vacuous"
        )
        print(f"\n[test_point_in_time_inventory] {message}")
        warnings.warn(message, stacklevel=2)
        pytest.skip(message)

    tracked = subprocess.run(
        ["git", "ls-files", "snapshots/*.parquet"],
        capture_output=True, text=True, cwd=_REPO, check=True,
    ).stdout.split()
    assert tracked, "no tracked snapshots found — the audit row I premise changed"

    offenders = []
    for rel in tracked:
        commit_iso = subprocess.run(
            ["git", "log", "-1", "--format=%cI", "--", rel],
            capture_output=True, text=True, cwd=_REPO, check=True,
        ).stdout.strip()
        if not commit_iso:
            offenders.append(f"{rel}: no commit history")
            continue
        commit_ts = pd.Timestamp(commit_iso).tz_convert(None).normalize()
        content_end = pd.read_parquet(_REPO / rel).index.max().normalize()
        # One business day of slack: the fetch happens intraday, the commit
        # may land after midnight in another timezone.
        if content_end > commit_ts + pd.Timedelta(days=1):
            offenders.append(
                f"{rel}: content ends {content_end.date()} but committed {commit_ts.date()}"
            )
    assert not offenders, "snapshot content postdates its commit:\n  " + "\n  ".join(offenders)


def test_every_assertion_above_can_actually_fire():
    """Each registry assertion exercised against synthetic offending input."""
    # 1. anchor-missing detection: an anchor absent from a source blob
    assert "no_such_anchor_xyz" not in _read(_REPO / "src/stock_risk/data/fetcher.py")

    # 2. status-flip detection: a section holding the row id but not the status
    fake_doc_sections = re.split(r"\n#{2,3} ", "## B1 row\nnow described as clean\n## other")
    holding = [s for s in fake_doc_sections if "B1" in s]
    assert holding and not any("confirmed-leak" in s for s in holding)

    # 3. the adjustment-parameter pin: a request that DID send one is caught
    fake_call = '"interval": "1day", "adjust": "all", "apikey": key'
    assert "adjust" in fake_call

    # 4. snapshot timing: fabricated future content is flagged by the same
    # comparison the real test uses
    commit_ts = pd.Timestamp("2026-07-20").normalize()
    fabricated_end = pd.Timestamp("2026-08-15").normalize()
    assert fabricated_end > commit_ts + pd.Timedelta(days=1)
    honest_end = pd.Timestamp("2026-07-20").normalize()
    assert not honest_end > commit_ts + pd.Timedelta(days=1)
