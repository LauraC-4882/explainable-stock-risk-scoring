"""[G6] Realised-vol vs. implied-vol (VIX) risk-on/risk-off regime features.

The rule these columns generalise: *if realised volatility is below where the
VIX was a month ago (plus a buffer), the market is calm — risk-on; otherwise
risk-off.* The comparison is the interesting part, not either leg alone. The
VIX is a forward-looking, one-month implied volatility quote, so the honest
comparison for today's realised 21-day volatility is against the VIX level
from ~21 trading days ago — the quote that was actually predicting *this*
window. Comparing today's realised vol against today's VIX compares a
backward-looking measurement to a forward-looking forecast of a period that
hasn't happened yet, which is a different (and much noisier) quantity.

The gap itself is the variance risk premium: implied vol normally sits above
subsequent realised vol, which is why the rule needs a buffer rather than a
bare inequality — without one, "realised < implied" is the base case and the
flag almost never fires.

Units: the VIX is quoted in annualised percentage points (18.5 means 18.5%),
so realised vol is scaled by 100 to match before differencing. The buffer is
in the same units (`buffer_pct=2.0` is the two-percentage-point cushion).

This module complements, and does not replace, the existing VIX machinery:
`scoring/risk_categories.regime_for_vix` buckets the *current* VIX level for
composite-score weighting, and `[G4]`'s term-structure signal compares VIX to
VIX3M. Those are point-in-time, market-level, and cross-sectional; these are a
per-row time series usable as model features and as a backtestable allocation
signal.

Degradation: when no VIX history is available (a throttled or China-market
fetch), every column is emitted as all-NaN rather than omitted, so downstream
code that selects these columns keeps working and the imputer treats them as
missing — the same policy the rest of the feature layer uses.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_DAYS = 252

DEFAULT_WINDOW = 21
DEFAULT_LAG = 21
DEFAULT_BUFFER_PCT = 2.0

REGIME_COLS = [
    "realized_vol_pct",
    "vix_lagged_pct",
    "vol_risk_premium",
    "risk_on",
    "risk_on_persistence_21d",
]


class RegimeFeatures:
    """Realised-vs-implied volatility regime columns.

    Unlike the other feature classes this one needs a second input — the VIX
    close series — so `compute` takes it explicitly rather than pulling it from
    the frame.
    """

    def __init__(
        self,
        window: int = DEFAULT_WINDOW,
        lag: int = DEFAULT_LAG,
        buffer_pct: float = DEFAULT_BUFFER_PCT,
    ):
        self.window = window
        self.lag = lag
        self.buffer_pct = buffer_pct

    def compute(
        self, df: pd.DataFrame, vix_close: pd.Series | None = None
    ) -> pd.DataFrame:
        df = df.copy()

        if "log_return" in df.columns:
            r = df["log_return"]
        else:
            r = np.log(df["close"] / df["close"].shift(1))

        df["realized_vol_pct"] = (
            r.rolling(self.window).std() * np.sqrt(TRADING_DAYS) * 100
        )

        if vix_close is None or len(vix_close.dropna()) == 0:
            for col in ("vix_lagged_pct", "vol_risk_premium", "risk_on",
                        "risk_on_persistence_21d"):
                df[col] = np.nan
            return df

        # Reindex onto the stock's calendar before lagging: the VIX trades on
        # the US calendar and the stock may not, so lagging first and then
        # reindexing would shift by a different number of *stock* sessions than
        # intended. ffill covers holidays the stock trades through.
        vix = vix_close.reindex(df.index).ffill()
        df["vix_lagged_pct"] = vix.shift(self.lag)

        # Positive = implied (as quoted a month ago, plus buffer) exceeded what
        # actually materialised — the calm/risk-on case.
        df["vol_risk_premium"] = (
            df["vix_lagged_pct"] + self.buffer_pct - df["realized_vol_pct"]
        )
        df["risk_on"] = (df["vol_risk_premium"] > 0).astype(float).where(
            df["vol_risk_premium"].notna()
        )
        # How much of the last month was risk-on: a single day's flag flips on
        # noise around the threshold, the fraction does not.
        df["risk_on_persistence_21d"] = df["risk_on"].rolling(21).mean()
        return df


def risk_on_allocation(
    df: pd.DataFrame,
    risk_on_returns: pd.Series,
    risk_off_returns: pd.Series,
) -> pd.Series:
    """Strategy returns for the switch the regime flag implies: hold the
    risk-on sleeve on risk-on days, the risk-off sleeve otherwise.

    Expects `df` to already carry a `risk_on` column (i.e. to have been through
    `RegimeFeatures.compute`). The flag at *t* selects the sleeve that earns
    *t+1*'s return, so the allocation only ever uses information available when
    the decision is made. Days with no flag (VIX warm-up or missing) are NaN,
    not silently defaulted to either sleeve — an unknown regime is not a
    risk-off signal.
    """
    if "risk_on" not in df.columns:
        raise ValueError("df has no 'risk_on' column — run RegimeFeatures.compute first")

    flag = df["risk_on"]
    on = risk_on_returns.reindex(df.index).shift(-1)
    off = risk_off_returns.reindex(df.index).shift(-1)
    allocated = pd.Series(np.where(flag == 1.0, on, off), index=df.index)
    return allocated.where(flag.notna())
