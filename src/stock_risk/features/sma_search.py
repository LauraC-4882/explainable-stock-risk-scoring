"""[G6] SMA window optimisation — the in-sample grid search, and the
walk-forward version that is safe to use as a model feature.

Two functions that look similar and must not be confused:

  - `best_sma_window(close)` sweeps windows 5..25, scores each by the
    cumulative return of a long/short crossover rule, and returns the winner.
    This is the classic notebook version and it is **in-sample by
    construction**: the window is chosen with full knowledge of the whole
    price path, including the future relative to every row it then labels. It
    is a legitimate research/reporting tool ("which lookback described this
    history best") and an invalid feature — a column built this way leaks the
    future into every training row and the backtest that uses it will look far
    better than anything reachable live.

  - `walk_forward_sma_window(close)` re-runs that same search on a trailing
    `lookback` window only, re-selecting every `refit_every` days and applying
    each selection strictly forward. Same search, no lookahead, so this is the
    one `OptimizedSMAFeatures` uses to build columns.

The gap between the two is the point, and it is measurable: run both on the
same series and compare the resulting strategy's cumulative return. The
in-sample number is the upper bound you cannot trade; the walk-forward number
is the honest one.

Signal convention throughout (matching the rest of the repo's backtest layer):
`+1` when close is above the moving average, `-1` when below, and the P&L at
row *t* is `signal_t * (close_{t+1} / close_t - 1)` — the position is taken on
information available at *t* and earns the *next* day's return, so the
alignment itself introduces no lookahead.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

DEFAULT_WINDOWS = tuple(range(5, 26))

# Walk-forward defaults: choose the window from one year of trailing daily bars
# and keep it for a month before re-selecting. Re-selecting every day would
# make the chosen window itself a noisy, fast-flipping series (and cost ~21x
# the compute) without adding information — a moving-average lookback that is
# genuinely better is better for longer than one session.
DEFAULT_LOOKBACK = 252
DEFAULT_REFIT_EVERY = 21

FEATURE_COLS = ["sma_opt_window", "dist_sma_opt", "signal_sma_opt"]


def sma_signal(close: pd.Series, window: int) -> pd.Series:
    """+1 above the `window`-day SMA, -1 below. NaN during the SMA warm-up
    (`min_periods=window`), so warm-up rows never silently score as -1."""
    sma = close.rolling(window=window, min_periods=window).mean()
    return pd.Series(np.where(close > sma, 1.0, -1.0), index=close.index).where(sma.notna())


def forward_returns(close: pd.Series) -> pd.Series:
    """Next-day simple return, aligned to the row whose signal earns it."""
    return close.pct_change().shift(-1)


def sma_strategy_return(close: pd.Series, window: int) -> float:
    """Cumulative return of the long/short SMA crossover rule, or NaN when the
    series is too short for the window to produce any signal at all."""
    pnl = (sma_signal(close, window) * forward_returns(close)).dropna()
    if pnl.empty:
        return float("nan")
    return float((1 + pnl).prod() - 1)


@dataclass
class SMASearchResult:
    """Winner of a window sweep, plus every window's score for inspection."""

    window: int
    cumulative_return: float
    scores: dict[int, float] = field(default_factory=dict)


def best_sma_window(
    close: pd.Series, windows: tuple[int, ...] = DEFAULT_WINDOWS
) -> SMASearchResult:
    """Sweep `windows` and return the one with the highest cumulative return.

    IN-SAMPLE — see the module docstring before using the result as a feature.
    Raises ValueError when no window scores at all (a series shorter than the
    smallest window), rather than returning a silently meaningless winner.
    """
    scores = {w: sma_strategy_return(close, w) for w in windows}
    valid = {w: s for w, s in scores.items() if pd.notna(s)}
    if not valid:
        raise ValueError(
            f"No SMA window in {min(windows)}..{max(windows)} scored on a series of "
            f"length {len(close)} — need at least {min(windows) + 2} usable rows"
        )
    best = max(valid, key=valid.__getitem__)
    return SMASearchResult(window=best, cumulative_return=valid[best], scores=scores)


def sma_crossovers(close: pd.Series, window: int) -> tuple[pd.Series, pd.Series]:
    """(cross_up, cross_down) boolean masks — the bars where price crossed the
    SMA, i.e. the entry/exit points rather than the held state.

    Both the current and the previous bar must have a defined SMA: on the first
    row of the warm-up there is no prior side to have crossed *from*, and
    treating "no previous state" as "was below" would report a spurious entry
    on every series that happens to open above its own moving average.
    """
    sma = close.rolling(window=window, min_periods=window).mean()
    above = close > sma
    prev_above = above.shift(1, fill_value=False)
    warm = sma.notna() & sma.shift(1).notna()
    cross_up = above & ~prev_above & warm
    cross_down = ~above & prev_above & warm
    return cross_up, cross_down


def walk_forward_sma_window(
    close: pd.Series,
    windows: tuple[int, ...] = DEFAULT_WINDOWS,
    lookback: int = DEFAULT_LOOKBACK,
    refit_every: int = DEFAULT_REFIT_EVERY,
) -> pd.Series:
    """Per-row chosen SMA window, selected using only prior data.

    At each refit point *i* the search runs on `close[i - lookback : i + 1]`
    and the winning window is applied to rows *i* through *i + refit_every*.
    Rows before the first refit point get NaN — there is no honest selection
    available for them.
    """
    chosen = pd.Series(np.nan, index=close.index)
    if len(close) <= lookback:
        return chosen

    for i in range(lookback, len(close), refit_every):
        history = close.iloc[i - lookback : i + 1]
        try:
            window = best_sma_window(history, windows).window
        except ValueError:
            continue
        chosen.iloc[i : i + refit_every] = window
    return chosen


class OptimizedSMAFeatures:
    """Walk-forward optimised-SMA columns.

    Same call contract as the other feature classes. Emits:

      - `sma_opt_window` — the window in force on that row (the selection
        itself is informative: it drifts short in choppy regimes and long in
        trending ones).
      - `dist_sma_opt` — normalised distance from that SMA, matching the
        `dist_ema_20`/`dist_ema_50` convention in `technical.py`. This is the
        column a model should use; the raw SMA level is non-stationary.
      - `signal_sma_opt` — the +1/-1 crossover state.
    """

    def __init__(
        self,
        windows: tuple[int, ...] = DEFAULT_WINDOWS,
        lookback: int = DEFAULT_LOOKBACK,
        refit_every: int = DEFAULT_REFIT_EVERY,
    ):
        self.windows = windows
        self.lookback = lookback
        self.refit_every = refit_every

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        close = df["close"]
        chosen = walk_forward_sma_window(
            close, self.windows, self.lookback, self.refit_every
        )
        df["sma_opt_window"] = chosen

        # One rolling mean per distinct window actually selected (at most
        # len(windows)), then gathered per row — cheaper and clearer than a
        # per-row variable-window rolling apply.
        sma_opt = pd.Series(np.nan, index=close.index)
        for window in chosen.dropna().unique():
            w = int(window)
            rolled = close.rolling(window=w, min_periods=w).mean()
            mask = chosen == window
            sma_opt[mask] = rolled[mask]

        df["dist_sma_opt"] = (close - sma_opt) / sma_opt
        df["signal_sma_opt"] = np.sign(df["dist_sma_opt"]).replace(0.0, 1.0)
        return df
