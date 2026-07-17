"""Tests for the percentile composite scorer and VIX-regime weighting."""

import numpy as np
import pandas as pd
import pytest

from stock_risk.data.preprocessor import DataPreprocessor
from stock_risk.features.risk_metrics import RiskMetrics
from stock_risk.scoring import risk_categories


@pytest.mark.parametrize("vix,expected_regime", [
    (None, "calm"),
    (12.0, "calm"),
    (19.9, "calm"),
    (20.0, "elevated"),
    (25.0, "elevated"),
    (29.9, "elevated"),
    (30.0, "panic"),
    (45.0, "panic"),
])
def test_regime_for_vix_thresholds(vix, expected_regime):
    assert risk_categories.regime_for_vix(vix) == expected_regime


@pytest.mark.parametrize("regime_name", ["calm", "elevated", "panic"])
def test_regime_weights_sum_to_one(regime_name):
    weights = risk_categories.REGIME_WEIGHTS[regime_name]
    assert set(weights) == set(risk_categories.CATEGORY_WEIGHTS)
    assert sum(weights.values()) == pytest.approx(1.0)


def test_panic_regime_weighs_tail_more_than_calm():
    calm = risk_categories.regime_adjusted_weights(10.0)
    panic = risk_categories.regime_adjusted_weights(35.0)
    assert panic["tail"] > calm["tail"]
    assert panic["volatility"] < calm["volatility"]


def test_regime_adjusted_weights_falls_back_to_base_when_vix_none():
    assert risk_categories.regime_adjusted_weights(None) == risk_categories.CATEGORY_WEIGHTS


def _raw_ohlcv(seed: int, n: int = 500) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rets = rng.standard_normal(n) * 0.01 + 0.0002
    rets[-40:] = rng.standard_normal(40) * 0.03 - 0.01
    close = 100 * np.exp(np.cumsum(rets))
    dates = pd.bdate_range("2023-01-01", periods=n)
    raw = pd.DataFrame({
        "open": close * 0.995, "high": close * 1.01,
        "low": close * 0.985, "close": close,
        "volume": rng.integers(1_000_000, 5_000_000, n).astype(float),
    }, index=dates)
    raw.index.name = "date"
    return raw


def _stressed_df(seed: int, n: int = 500) -> pd.DataFrame:
    return RiskMetrics().compute(DataPreprocessor().process(_raw_ohlcv(seed, n)))


def test_composite_score_accepts_custom_weights():
    df = _stressed_df(seed=1)
    base = risk_categories.composite_score(df)
    panic = risk_categories.composite_score(df, weights=risk_categories.REGIME_WEIGHTS["panic"])

    assert base["categories"]["tail"]["weight"] == risk_categories.CATEGORY_WEIGHTS["tail"]
    assert panic["categories"]["tail"]["weight"] == risk_categories.REGIME_WEIGHTS["panic"]["tail"]
    assert 0 <= base["composite_score"] <= 100
    assert 0 <= panic["composite_score"] <= 100


def test_composite_score_accepts_latest_override():
    """A modified `latest` row (e.g. a stress-test shock) must be ranked
    against the *same* historical distribution as the real row, via the same
    percentile machinery — this is what stress_test.py relies on."""
    df = _stressed_df(seed=2)
    real_latest = df.iloc[-1]
    baseline = risk_categories.composite_score(df)

    shocked = real_latest.copy()
    shocked["vol_21d"] = real_latest["vol_21d"] * 10  # push far outside the stock's own history
    shocked_result = risk_categories.composite_score(df, latest=shocked)

    shocked_vol_score = shocked_result["categories"]["volatility"]["score"]
    baseline_vol_score = baseline["categories"]["volatility"]["score"]
    assert shocked_vol_score >= baseline_vol_score
    # explicitly passing the real row must reproduce the default-latest result
    identical = risk_categories.composite_score(df, latest=real_latest)
    assert identical["composite_score"] == baseline["composite_score"]


def test_composite_score_has_no_lookahead():
    """scripts/validate_score.py's whole backtest methodology depends on
    composite_score(df.iloc[:i+1]) at day i reflecting only data up to and
    including day i — never anything from i+1 onward. Slicing an
    already-computed dataframe can't by itself prove that (composite_score
    only ever sees what's in the object it's given, so that comparison is
    trivially true regardless of any bug); the real risk is upstream, in
    RiskMetrics' rolling-window feature engineering — a `rolling(21,
    center=True)` instead of the intended trailing `rolling(21)` would leak
    future values into vol_21d/cvar_95_21d/etc. without composite_score
    itself doing anything wrong.

    So this recomputes RiskMetrics from scratch on a price series that's
    genuinely truncated at the raw-price level (never had the later rows to
    begin with) and checks the resulting score matches computing features
    once on the full history and slicing afterward — the only way a
    centered or otherwise forward-looking window would show up is as a
    mismatch here.

    Deliberately skips DataPreprocessor's outlier filter in this test (uses
    plain returns instead) — that step's whole-series mean/std is a
    separate, already-identified leak risk of its own when a precomputed
    multi-year frame gets sliced at historical dates (found by an earlier
    version of this exact test), unrelated to whether RiskMetrics' rolling
    windows are correctly trailing. validate_score.py works around it with
    its own expanding-window outlier filter; see that module's
    _expanding_outlier_filter docstring for the full story.
    """
    raw = _raw_ohlcv(seed=7, n=600)

    def _returns_only(df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["log_return"] = np.log(df["close"] / df["close"].shift(1))
        df["pct_return"] = df["close"].pct_change()
        return df.dropna(subset=["close", "log_return"])

    full_history = RiskMetrics().compute(_returns_only(raw))

    # Cut by *date*, not row position: _returns_only's dropna(subset=[...])
    # drops the very first row (its log_return is NaN — no prior close to
    # diff against), so a raw frame truncated to N rows produces N-1 feature
    # rows. Slicing both sides positionally at the same integer would then
    # compare two different calendar dates and look like a mismatch that
    # has nothing to do with lookahead — caught by this test itself before
    # the fix below, worth keeping in mind for any similar comparison.
    for as_of_date in (raw.index[300], raw.index[450], raw.index[560], raw.index[599]):
        raw_truncated = raw.loc[:as_of_date]  # never had rows past this date
        from_scratch = RiskMetrics().compute(_returns_only(raw_truncated))
        from_full_history_sliced = full_history.loc[:as_of_date]
        assert from_scratch.index[-1] == from_full_history_sliced.index[-1] == as_of_date

        score_from_scratch = risk_categories.composite_score(from_scratch)
        score_from_sliced = risk_categories.composite_score(from_full_history_sliced)
        assert score_from_scratch == score_from_sliced, f"mismatch as of {as_of_date}"
