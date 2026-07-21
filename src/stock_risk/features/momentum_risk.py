"""[G6] Momentum, momentum-crash risk, and 52-week relative position.

All pure-price arithmetic on the OHLCV frame already in hand — no extra fetch,
which is why this family is worth adding to the live scoring path when several
of its neighbours (earnings dates, short interest, macro betas) are not.

**Momentum crash risk** is the reason this module exists rather than three
`pct_change` calls. Momentum's well-documented failure mode is not gradual
mean reversion, it is an abrupt crash: Daniel & Moskowitz (2016) show momentum
strategies suffer rare, severe drawdowns concentrated in high-volatility
states following large run-ups. A stock that has run up hard is not risky
because it went up, and high volatility alone is already measured by
`vol_21d` — the danger is the *conjunction*, and neither component column
expresses it. `momentum_crash_risk` is that interaction made explicit:

    momentum_crash_risk = momentum_percentile x volatility_percentile

Both legs are ranked within the stock's own trailing history (expanding rank,
no lookahead), so the product is on 0-1 and reads as "how far into this
stock's own high-momentum AND high-volatility corner is it right now". A stock
at the 95th percentile of both scores ~0.90; one that is merely volatile, or
merely trending, scores near zero.

**52-week position** (`price_vs_52w_high`, `pct_of_52w_range`) is the relative
strength leg. It is deliberately expressed as distance from the high and
position within the range rather than as a raw price: both are scale-free and
comparable across tickers, which a price level is not.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# ~1, 3, and 12 months of trading days. The 12-month leg intentionally does not
# skip the most recent month the way the academic UMD factor does: that skip
# exists to avoid short-term reversal contaminating a *return-predicting*
# factor, and this column is an input to a risk model, where the recent month
# is the part a reader most wants included.
_HORIZONS = {"momentum_1m": 21, "momentum_3m": 63, "momentum_12m": 252}

_52W = 252
_MIN_RANK_HISTORY = 63  # below this an expanding rank is too unstable to mean anything

MOMENTUM_COLS = [
    "momentum_1m", "momentum_3m", "momentum_12m",
    "momentum_crash_risk", "price_vs_52w_high", "pct_of_52w_range",
]


def _expanding_rank(series: pd.Series) -> pd.Series:
    """Each row's percentile rank (0-1) within the values seen up to and
    including it.

    Expanding, not full-sample: a full-sample rank would tell every historical
    row where it sits relative to data from its own future, which is the same
    lookahead the walk-forward SMA search in `sma_search.py` exists to avoid.
    """
    ranked = series.expanding(min_periods=_MIN_RANK_HISTORY).apply(
        lambda window: (window <= window[-1]).mean(), raw=True
    )
    return ranked


class MomentumRiskFeatures:
    """Momentum horizons, the crash-risk interaction, and 52-week position."""

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        close = df["close"]

        for col, window in _HORIZONS.items():
            df[col] = close.pct_change(periods=window)

        # Crash risk needs a volatility leg. Prefer the RiskMetrics column when
        # the frame has been through it; otherwise compute the same 21-day
        # realised vol locally, so this class keeps the standalone call contract
        # every other feature class has.
        if "vol_21d" in df.columns:
            vol = df["vol_21d"]
        else:
            r = df["log_return"] if "log_return" in df.columns else np.log(close / close.shift(1))
            vol = r.rolling(21).std() * np.sqrt(252)

        momentum_rank = _expanding_rank(df["momentum_3m"])
        vol_rank = _expanding_rank(vol)
        df["momentum_crash_risk"] = momentum_rank * vol_rank

        high_52w = close.rolling(_52W, min_periods=_52W // 2).max()
        low_52w = close.rolling(_52W, min_periods=_52W // 2).min()
        df["price_vs_52w_high"] = (close - high_52w) / high_52w
        span = (high_52w - low_52w).replace(0, np.nan)
        df["pct_of_52w_range"] = (close - low_52w) / span

        return df
