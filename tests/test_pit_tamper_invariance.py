"""Point-in-time tamper invariance — the strong-evidence half of the PIT audit.

Companion to docs_internal/POINT_IN_TIME_AUDIT.md (rows A1.i / A1.ii). The
question: does any number attributed to time t change when the *future* of the
series changes? Backward price adjustment is the one mechanism in this
repository where the answer is structurally "the data itself changes": a
dividend/split with ex-date T rewrites every price at dates <= T by a factor k
the moment the series is re-fetched. The direction matters and was corrected
in review: the rewrite reaches BACKWARD over the whole history including t,
not forward — a tamper that scales prices after t is trivially invisible to
time-t features and proves nothing.

So the tamper here is the real shape: pick a fake ex-date T AFTER the
evaluation date t, multiply every price at dates <= T by k (the whole visible
history at t included), and compare

    as-of-t fetch      : pipeline(raw[: t])          — what a fetch on day t saw
    post-event fetch   : pipeline(tampered)[: t]     — what a fetch after T says day t was

Two claims, both mathematical and both asserted per element:

* **Ratio-class features are invariant** (audit row A1.i): every return,
  volatility, drawdown ratio, tail quantile and beta consumes prices only
  through ratios of two visible-window prices, and the same k multiplies
  numerator and denominator. With k = 2.0 the float scaling is exact
  (mantissas untouched), so equality is asserted BITWISE; with realistic k
  (0.97, 1/1.03) float rounding breaks bit-identity and equality is asserted
  at rtol=1e-9 — the composite, which rounds to 0.1, must still match
  exactly.

* **Level-class features are NOT invariant, and move by exactly k**
  (audit row A1.ii) — characterization, not xfail:
      dollar_volume_21d(k·P) == k · dollar_volume_21d(P)
      amihud_illiq_21d(k·P)  ==     amihud_illiq_21d(P) / k
  This records the current (defective-in-levels) behaviour precisely. IF
  THESE EQUALITIES GO RED, A1.ii HAS BEEN FIXED (e.g. dollar volume moved to
  unadjusted prices): update docs_internal/POINT_IN_TIME_AUDIT.md row A1.ii
  and this test together — the fix must be explicit, never silent. xfail was
  rejected deliberately: it can degrade to a silent skip, the exact failure
  mode the font gate had.

A corollary this file PROVES rather than assumes (recorded in the audit): the
own-history percentile composite is invariant even in its liquidity category,
because at any t <= T the entire visible window is scaled by the same k and
percentile ranks are scale-free. Scope, deliberately narrow: the composite is
the 85% leg of the published headline, NOT the headline itself — the 15% ML
leg consumes atr_14, a price level, and carries the leak (audit row A1.iii).
The level-class damage is therefore confined to cross-stock aggregation,
absolute displays, and the ML leg — never read this docstring as "the
published score is unaffected".

Inputs are tracked snapshots only — offline and deterministic.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from stock_risk.data.preprocessor import DataPreprocessor
from stock_risk.features.risk_metrics import RiskMetrics
from stock_risk.scoring.risk_categories import composite_score

SNAPSHOT_DIR = Path(__file__).resolve().parents[1] / "snapshots"

TICKERS = ["AAPL", "600519_SS", "000001_SZ"]
BENCHMARK = "510300_SS"

PRICE_COLS = ["open", "high", "low", "close"]

# Every feature that consumes prices only through same-window ratios (plus the
# volume-only column, trivially price-free). beta_63d joins via the benchmark
# pass-through below.
RATIO_COLS = [
    "log_return", "pct_return",
    "vol_7d", "vol_21d", "vol_63d", "parkinson_vol_21d", "gk_vol_21d",
    "var_95_21d", "var_99_21d", "cvar_95_21d", "var_95_100d", "cvar_95_100d",
    "drawdown", "max_drawdown_63d", "drawdown_duration", "drawdown_acceleration",
    "ewma_vol", "ewma_vol_20", "ewma_vol_60", "vol_regime_change", "vol_of_vol_20",
    "downside_dev_63d", "sharpe_63d", "sortino_63d",
    "skew_63d", "kurt_63d", "skew_20d", "skew_momentum",
    "volume_vol_21d", "beta_63d",
]

# k appears once and cannot cancel: the value scales deterministically.
LEVEL_COLS = {"dollar_volume_21d": +1, "amihud_illiq_21d": -1}  # exponent of k

# (k, T placement, exact float equality expected)
# k=2.0 scales mantissa-exactly, so bitwise equality is provable; it is only
# used with T at the series end, where no artificial boundary return exists
# (real adjusted series are smooth at T — the adjustment exists to make them
# so; a giant synthetic jump at T+1 would exercise the outlier filter, which
# is audit row B1's topic, not this one). The mid-series T case uses a
# realistic k whose 3% boundary step stays far below the 6-sigma filter.
CASES = [
    pytest.param(2.0, "end", True, id="k2.0-end-bitwise"),
    pytest.param(0.97, "end", False, id="k0.97-end"),
    pytest.param(1 / 1.03, "end", False, id="k1.03inv-end"),
    pytest.param(0.97, "mid", False, id="k0.97-midT"),
]

T_AFTER_T_ROWS = 20   # mid case: fake ex-date sits 20 rows after t
EVAL_ROWS_FROM_END = 60


def _bench_log_return() -> pd.Series:
    raw = pd.read_parquet(SNAPSHOT_DIR / f"{BENCHMARK}_2y_1d.parquet")
    return DataPreprocessor().process(raw)["log_return"]


def _pipeline(raw: pd.DataFrame, bench: pd.Series) -> pd.DataFrame:
    return RiskMetrics().compute(
        DataPreprocessor().process(raw.copy()), benchmark_returns=bench
    )


def _tamper(raw: pd.DataFrame, t_last_pos: int, k: float, where: str) -> pd.DataFrame:
    """Scale every price at dates <= T by k; T is after the evaluation date."""
    scaled = raw.copy()
    t_event = len(raw) - 1 if where == "end" else t_last_pos + T_AFTER_T_ROWS
    assert t_event > t_last_pos  # the event must postdate the evaluation date
    scaled.iloc[: t_event + 1, [scaled.columns.get_loc(c) for c in PRICE_COLS]] *= k
    return scaled


def _row_pair(ticker: str, k: float, where: str, bench: pd.Series):
    raw = pd.read_parquet(SNAPSHOT_DIR / f"{ticker}_2y_1d.parquet")
    t_pos = len(raw) - EVAL_ROWS_FROM_END

    asof_frame = _pipeline(raw.iloc[: t_pos + 1], bench)
    t_date = asof_frame.index[-1]

    tampered_frame = _pipeline(_tamper(raw, t_pos, k, where), bench).loc[:t_date]
    # Same rows must survive preprocessing in both arms — a divergence here
    # would mean the tamper changed which historical rows EXIST (that is the
    # full-sample outlier filter's failure mode, audit row B1, and it must
    # surface as a loud index mismatch rather than a shifted comparison).
    assert list(tampered_frame.index) == list(asof_frame.index)
    return asof_frame, tampered_frame, t_date


def _series_at(frame: pd.DataFrame, date, cols) -> pd.Series:
    return frame.loc[date, cols].astype(float)


def _compare(a: pd.Series, b: pd.Series, exact: bool) -> list[str]:
    """NaN-aware elementwise comparison; returns the offending column names."""
    bad = []
    for col in a.index:
        x, y = a[col], b[col]
        if pd.isna(x) and pd.isna(y):
            continue
        if pd.isna(x) != pd.isna(y):
            bad.append(f"{col}: NaN mismatch ({x!r} vs {y!r})")
            continue
        if exact:
            if x != y:
                bad.append(f"{col}: {x!r} != {y!r} (bitwise)")
        elif not np.isclose(x, y, rtol=1e-9, atol=0.0):
            bad.append(f"{col}: {x!r} vs {y!r} (rtol 1e-9)")
    return bad


@pytest.mark.parametrize("ticker", TICKERS)
@pytest.mark.parametrize("k,where,exact", CASES)
def test_ratio_features_at_t_ignore_a_future_adjustment_event(ticker, k, where, exact):
    """Audit row A1.i: uniform backward rescaling cancels in every ratio."""
    bench = _bench_log_return()
    asof, tampered, t_date = _row_pair(ticker, k, where, bench)

    cols = [c for c in RATIO_COLS if c in asof.columns]
    assert len(cols) >= 25  # the inventory must actually be exercised
    bad = _compare(_series_at(asof, t_date, cols), _series_at(tampered, t_date, cols), exact)
    assert not bad, f"{ticker} k={k} T={where}: future event leaked into t:\n  " + "\n  ".join(bad)


@pytest.mark.parametrize("ticker", TICKERS)
@pytest.mark.parametrize("k,where,exact", CASES)
def test_the_published_composite_at_t_is_invariant(ticker, k, where, exact):
    """The end-to-end claim, liquidity category included: at t <= T the whole
    visible window carries the same k, so even the level-based percentiles
    are rank-invariant and the published score cannot move."""
    bench = _bench_log_return()
    asof, tampered, t_date = _row_pair(ticker, k, where, bench)

    a = composite_score(asof)
    b = composite_score(tampered)
    assert a == b, (
        f"{ticker} k={k} T={where}: composite moved: "
        f"{a['composite_score']} vs {b['composite_score']}"
    )


@pytest.mark.parametrize("ticker", TICKERS)
@pytest.mark.parametrize("k,where,exact", CASES)
def test_level_features_scale_by_exactly_k(ticker, k, where, exact):
    """Audit row A1.ii — CHARACTERIZATION of the current defect, not a wish.

    dollar_volume_21d and amihud_illiq_21d consume the adjusted price LEVEL,
    so the fake future event rescales history they report for day t:
    dollar_volume by k, amihud by 1/k — asserted as exact relationships, not
    "changed". IF THIS TEST GOES RED, THE DEFECT HAS BEEN FIXED: update
    docs_internal/POINT_IN_TIME_AUDIT.md row A1.ii and this test in the same
    change. (Not xfail, on purpose: xfail can rot into a silent skip.)
    """
    bench = _bench_log_return()
    asof, tampered, t_date = _row_pair(ticker, k, where, bench)

    for col, power in LEVEL_COLS.items():
        x = float(asof.loc[t_date, col])
        y = float(tampered.loc[t_date, col])
        expected = x * (k ** power)
        if exact:
            assert y == expected, f"{col}: {y!r} != {x!r} * k^{power} (bitwise, k={k})"
        else:
            assert np.isclose(y, expected, rtol=1e-9, atol=0.0), (
                f"{col}: {y} vs expected {expected} (k={k})"
            )


def test_atr_the_one_level_feature_in_the_ml_set_scales_by_k():
    """Audit rows A1.ii / D3 — the enumerated premise violation on the
    published headline path, characterized.

    Of the 18 ML feature columns, exactly one consumes a price LEVEL:
    atr_14 (feature_sets.py VOLATILITY_COLS). It meets constants fixed at
    training time (the scaler's mu/sigma, the trees' split thresholds), so
    the scale-invariance premise fails there by construction: a future
    adjustment event rescales the atr_14 the model sees for day t by
    exactly k. Empirically (recorded in the audit, not asserted here
    because it depends on the committed artefact): at k=0.5 the raw
    XGBoost probability moved by -2.7e-2; the isotonic calibration
    plateau happened to absorb it for the probed rows, which is luck,
    not a guarantee. IF THIS GOES RED, THE atr_14 LEAK HAS BEEN FIXED —
    update the audit row and this test together.
    """
    tech = pytest.importorskip("stock_risk.features.technical")
    bench = _bench_log_return()
    raw = pd.read_parquet(SNAPSHOT_DIR / "AAPL_2y_1d.parquet")
    t_pos = len(raw) - EVAL_ROWS_FROM_END
    k = 2.0  # exact float scaling -> bitwise equality provable

    def with_tech(frame_raw):
        df = DataPreprocessor().process(frame_raw.copy())
        df = tech.TechnicalFeatures().compute(df)
        return RiskMetrics().compute(df, benchmark_returns=bench)

    asof = with_tech(raw.iloc[: t_pos + 1])
    t_date = asof.index[-1]
    tampered = with_tech(_tamper(raw, t_pos, k, "end")).loc[:t_date]

    a = float(asof.loc[t_date, "atr_14"])
    b = float(tampered.loc[t_date, "atr_14"])
    assert b == a * k, f"atr_14: {b!r} != {a!r} * {k} — has the level leak been fixed?"


def test_a_level_quantity_meeting_a_constant_is_where_invariance_dies():
    """The reverse fixture pinning the PREMISE ITSELF (audit section A1.ii,
    premise clause): scale-invariance of the composite holds only while a
    level quantity is compared exclusively against other same-window levels.
    The moment it meets a CONSTANT — a hardcoded liquidity floor, a scaler
    mean frozen at training time, another stock's value — k stops cancelling
    and the comparison's outcome depends on when the data was fetched.

    Demonstrated on the real pipeline: a fixed dollar-volume threshold placed
    between the as-of value and the post-event value flips its verdict under
    the tamper, while every percentile (level vs same-window levels) held in
    the tests above. Anyone adding an absolute threshold to a level feature
    re-creates exactly this; the audit's enumeration of such sites must be
    updated when that happens.
    """
    bench = _bench_log_return()
    k = 0.97
    asof, tampered, t_date = _row_pair("AAPL", k, "end", bench)

    x = float(asof.loc[t_date, "dollar_volume_21d"])
    y = float(tampered.loc[t_date, "dollar_volume_21d"])
    assert np.isclose(y, x * k, rtol=1e-9)  # the characterized scaling, again

    threshold = float(np.sqrt(x * y))  # a constant strictly between the two
    assert (x > threshold) and not (y > threshold), (
        "a fixed threshold between the two fetches' values must flip its "
        "verdict — if it did not, the premise demonstration is broken"
    )


def test_every_assertion_above_can_actually_fire():
    """Fire-check: each comparison helper must be able to report a violation.

    Synthetic vectors only — no snapshot, no pipeline. A checker that cannot
    go red proves nothing (established rule; see the docs-consistency and
    locale gates for precedent).
    """
    a = pd.Series({"vol_21d": 0.20, "beta_63d": 1.1, "skew_63d": np.nan})

    # clean case — bitwise and tolerant both silent
    assert _compare(a, a.copy(), exact=True) == []
    assert _compare(a, a.copy(), exact=False) == []

    # a leaked value must be reported in both modes
    leaked = a.copy()
    leaked["vol_21d"] = 0.21
    assert any("vol_21d" in o for o in _compare(a, leaked, exact=True))
    assert any("vol_21d" in o for o in _compare(a, leaked, exact=False))

    # sub-tolerance float dust: caught bitwise, forgiven at rtol — the reason
    # k=2.0 exists as a case at all
    dust = a.copy()
    dust["beta_63d"] = a["beta_63d"] * (1 + 1e-14)
    assert any("beta_63d" in o for o in _compare(a, dust, exact=True))
    assert _compare(a, dust, exact=False) == []

    # NaN asymmetry is a violation, never silently equal
    denan = a.copy()
    denan["skew_63d"] = 0.0
    assert any("skew_63d" in o for o in _compare(a, denan, exact=True))

    # the characterization arithmetic itself: a fixed (invariant) level
    # feature would break the k-scaling equality
    k = 0.97
    assert not np.isclose(1.0, 1.0 * k, rtol=1e-9)  # invariant value vs k-scaled claim
