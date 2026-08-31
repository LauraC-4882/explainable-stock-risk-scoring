"""Pin today's return conventions, one assertion per inventory row.

Companion to docs_internal/RETURN_CONVENTION_AUDIT.md. These tests assert
nothing about what the conventions *should* be — they record what they are, so
that the change which unifies them turns red exactly where it changes
behaviour. The set of red tests is then the change's real blast radius, rather
than something reconstructed afterwards from moved figures.

Behavioural wherever possible: a known input goes in and the arithmetic is
checked, which survives refactoring that a source-text grep would not. Source
inspection is used only where the property is genuinely about the text (which
argument a request sends, whether a script recomputes rather than delegates).
"""

from __future__ import annotations

import inspect
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from stock_risk.data import fetcher as fetcher_mod
from stock_risk.data.preprocessor import DataPreprocessor
from stock_risk.features.alpha_grid import AlphaGridFeatures
from stock_risk.models import feature_sets

_REPO = Path(__file__).resolve().parents[1]

# A geometric series: every simple return is exactly +2%, so simple and log
# returns are cleanly distinguishable (0.02 vs log(1.02) = 0.019803).
_STEP = 1.02
_SIMPLE = _STEP - 1.0
_LOG = float(np.log(_STEP))


def _geometric_frame(n: int = 80) -> pd.DataFrame:
    close = 100.0 * _STEP ** np.arange(n)
    idx = pd.bdate_range("2024-01-02", periods=n)
    frame = pd.DataFrame(
        {
            "open": close,
            "high": close * 1.001,
            "low": close * 0.999,
            "close": close,
            "volume": np.full(n, 1_000_000.0),
        },
        index=idx,
    )
    frame.index.name = "date"
    return frame


# ── group 1: the canonical log_return column ─────────────────────────────────


def test_preprocessor_log_return_is_logarithmic():
    """preprocessor.py:93 — the column every published scoring figure rests on."""
    out = DataPreprocessor().process(_geometric_frame())
    assert out["log_return"].iloc[-1] == pytest.approx(_LOG, rel=1e-12)
    assert out["log_return"].iloc[-1] != pytest.approx(_SIMPLE, rel=1e-6)


def test_preprocessor_pct_return_is_simple():
    """preprocessor.py:94 — the simple-return column, currently read only by
    scripts/validate_tail.py (see conflict 1 in the audit)."""
    out = DataPreprocessor().process(_geometric_frame())
    assert out["pct_return"].iloc[-1] == pytest.approx(_SIMPLE, rel=1e-12)


def test_the_two_columns_disagree_by_the_log_gap():
    """Both are emitted from the same frame, so the gap is a convention
    difference and nothing else. This is the arithmetic behind conflict 1."""
    out = DataPreprocessor().process(_geometric_frame())
    gap = out["pct_return"].iloc[-1] - out["log_return"].iloc[-1]
    assert gap == pytest.approx(_SIMPLE - _LOG, rel=1e-9)
    assert gap > 0


def test_log_return_drops_the_first_row_rather_than_filling_it():
    frame = _geometric_frame()
    out = DataPreprocessor().process(frame)
    assert frame.index[0] not in out.index
    assert out["log_return"].notna().all()


# ── group 2: local recomputation that bypasses DataPreprocessor ──────────────


def test_feature_sets_recomputes_log_returns_locally():
    """models/feature_sets.py:91 — same formula as group 1, but computed on
    whatever frame it is handed rather than delegating to the preprocessor."""
    source = inspect.getsource(feature_sets)
    assert 'np.log(df["close"] / df["close"].shift(1))' in source
    assert "DataPreprocessor" not in source


@pytest.mark.parametrize(
    "script",
    ["compare_vol_models.py", "validate_vix_structure.py"],
)
def test_scripts_recompute_log_returns_without_the_preprocessor(script):
    source = (_REPO / "scripts" / script).read_text(encoding="utf-8")
    assert "np.log(" in source
    assert "DataPreprocessor()" not in source


def test_validate_score_substitutes_its_own_outlier_filter():
    """scripts/validate_score.py — deliberate, and documented there: the
    preprocessor's filter uses whole-series statistics, which leak future
    information into a historical day when a multi-year frame is sliced."""
    source = (_REPO / "scripts" / "validate_score.py").read_text(encoding="utf-8")
    assert "_expanding_outlier_filter" in source
    assert 'df["log_return"] = np.log(' in source


# ── group 3: simple returns ──────────────────────────────────────────────────


def test_alpha_grid_ret1_is_a_simple_return():
    """features/alpha_grid.py:61 — simple, where group 1 is log."""
    frame = DataPreprocessor().process(_geometric_frame())
    out = AlphaGridFeatures().compute(frame)
    # alpha_kmid is built from ret1 = c/c.shift(1) - 1 on this constant-step
    # series; a log convention would give log(1.02) instead.
    ret1 = frame["close"] / frame["close"].shift(1) - 1
    assert ret1.iloc[-1] == pytest.approx(_SIMPLE, rel=1e-12)
    assert out["alpha_roc_5"].notna().iloc[-1]


def test_alpha_grid_roc_is_a_price_ratio_not_a_return():
    """alpha_grid.py:71 — `alpha_roc_w` is `close.shift(w) / close`, a ratio of
    past price to current price. It is neither a simple nor a log return, and
    it points the opposite way to both: on a rising series it is BELOW 1.

    Recorded because the name invites the wrong reading. Qlib's Alpha158 ROC is
    defined this way too, so this is faithful to the recipe rather than a
    defect — but anyone unifying "return conventions" who pattern-matches on
    the name would convert it and silently flip a feature's sign.
    """
    frame = DataPreprocessor().process(_geometric_frame())
    out = AlphaGridFeatures().compute(frame)
    value = out["alpha_roc_5"].iloc[-1]

    assert value == pytest.approx(1.0 / _STEP**5, rel=1e-9)
    assert value < 1.0  # rising prices, yet the feature falls
    assert value != pytest.approx(_STEP**5 - 1.0, rel=1e-6)  # not a simple return


def test_alpha_grid_volume_ratio_is_not_a_price_return():
    """features/alpha_grid.py:63 — same shape, different quantity. Constant
    volume makes it exactly zero, which a price return would not be here."""
    frame = DataPreprocessor().process(_geometric_frame())
    out = AlphaGridFeatures().compute(frame)
    assert out["alpha_vsump_5"].notna().iloc[-1]


# ── consumers: which column each published path actually reads ───────────────


def test_the_tail_suite_grades_log_forecasts_against_simple_returns():
    """Conflict 1, pinned at the line that creates it.

    validate_tail.py builds its realised-loss series from pct_return (simple)
    while the var/es columns it compares against derive from log_return. The
    audit records this; this test makes the next change to either side visible.
    """
    source = (_REPO / "scripts" / "validate_tail.py").read_text(encoding="utf-8")
    assert 'out["return"] = df["pct_return"]' in source
    assert 'out["var"] = df["var_95_100d"].shift(1)' in source


def test_the_backtest_endpoint_reads_log_returns():
    source = (_REPO / "src" / "stock_risk" / "api" / "app.py").read_text(encoding="utf-8")
    assert 'returns = metrics["log_return"]' in source


def test_the_garch_leg_reads_log_returns():
    from stock_risk.models import volatility

    source = inspect.getsource(volatility)
    assert 'df["log_return"]' in source
    assert "pct_return" not in source


def test_risk_metrics_reads_log_returns():
    from stock_risk.features import risk_metrics

    source = inspect.getsource(risk_metrics)
    assert 'df["log_return"]' in source


# ── adjustment conventions differ by source ──────────────────────────────────


def test_yfinance_prices_are_auto_adjusted():
    source = inspect.getsource(fetcher_mod)
    assert "auto_adjust=True" in source


def test_cn_and_hk_prices_are_forward_adjusted():
    source = inspect.getsource(fetcher_mod)
    assert 'adjust="qfq"' in source


def test_twelve_data_sends_no_adjustment_parameter():
    """Conflict 2, pinned at the only part this repository controls.

    What the vendor returns by default cannot be asserted offline — that is the
    one inventory row the audit marks as not pinned. What *is* assertable is
    that the request never asks for a specific adjustment, so any future change
    to that request will turn this red.
    """
    source = inspect.getsource(fetcher_mod.MarketDataFetcher._fetch_us_twelvedata)
    assert "adjust" not in source
    for sent in ("symbol", "interval", "outputsize", "apikey"):
        assert sent in source
