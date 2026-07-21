"""[G6] Rule-based trading signals and the harness that scores them.

Each builder maps a price series to a position series in {-1, 0, +1}, and
`backtest_signal` turns a position series into strategy returns. The alignment
is the part that has to be right:

    pnl_t = signal_t * (close_{t+1} / close_t - 1)

The position is decided from information available at the close of *t* and
earns *t+1*'s return. Multiplying `signal_t` by `close_t / close_{t-1}` instead
would score every rule against the return that *created* its own signal — a
lookahead bug that makes any momentum rule look extraordinary.

Warm-up rows carry NaN signals (not 0, and not -1) so an indicator that has not
yet accumulated enough history is *absent* rather than silently short.

Why these rules exist alongside the model: they are the interpretable baseline.
A gradient-boosted model over 100+ engineered features has to beat a 25-day
moving-average crossover before its complexity is worth anything, and
`compare_signal_strategies` is how that comparison gets made rather than
assumed.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .performance import compare_performance


def _positions(condition: pd.Series, valid: pd.Series) -> pd.Series:
    """+1/-1 from a boolean condition, NaN wherever the indicator is not warm."""
    out = pd.Series(np.where(condition, 1.0, -1.0), index=condition.index)
    return out.where(valid)


def sma_signal(close: pd.Series, window: int = 25) -> pd.Series:
    """Long above the SMA, short below."""
    sma = close.rolling(window=window, min_periods=window).mean()
    return _positions(close > sma, sma.notna())


def macd_signal(
    close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
) -> pd.Series:
    """Long while MACD is above its signal line.

    `adjust=False` and `min_periods` on the spans: the EWM warm-up is not a
    period during which the indicator is merely imprecise, it is a period
    during which the fast and slow lines are computed from different amounts of
    data and their difference is not a MACD at all.
    """
    ema_fast = close.ewm(span=fast, adjust=False, min_periods=fast).mean()
    ema_slow = close.ewm(span=slow, adjust=False, min_periods=slow).mean()
    macd = ema_fast - ema_slow
    macd_signal_line = macd.ewm(span=signal, adjust=False, min_periods=signal).mean()
    return _positions(macd > macd_signal_line, macd_signal_line.notna())


def rsi(close: pd.Series, window: int = 14) -> pd.Series:
    """Wilder-style RSI on a simple moving average of gains/losses."""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window=window, min_periods=window).mean()
    avg_loss = loss.rolling(window=window, min_periods=window).mean()
    # All-gain windows make avg_loss zero — RSI is 100 there, not NaN, which is
    # what the bare division would produce.
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100 - 100 / (1 + rs)
    return out.mask(avg_loss.eq(0) & avg_gain.gt(0), 100.0)


def rsi_signal(
    close: pd.Series, window: int = 14, oversold: float = 30, overbought: float = 70
) -> pd.Series:
    """Mean-reversion: long when oversold, short when overbought, **flat in
    between**.

    The only three-state rule here, and deliberately so — RSI at 50 carries no
    information, and forcing it into ±1 like the trend rules would turn "no
    opinion" into a full-size position held most of the time.
    """
    r = rsi(close, window)
    out = pd.Series(0.0, index=close.index)
    out[r < oversold] = 1.0
    out[r > overbought] = -1.0
    return out.where(r.notna())


def momentum_signal(close: pd.Series, window: int = 10) -> pd.Series:
    """Long when the trailing `window`-day rate of change is positive."""
    roc = close.pct_change(periods=window)
    return _positions(roc > 0, roc.notna())


def backtest_signal(signal: pd.Series, close: pd.Series) -> pd.Series:
    """Strategy returns from a position series (see the alignment note above).

    Frictionless — no transaction costs or slippage. That is a real limitation
    for the high-turnover rules here (the RSI rule changes position hundreds of
    times over a multi-year sample), so treat cross-rule Sharpe comparisons as
    indicative rather than tradeable; use `turnover` to see which rules the
    omission flatters most.
    """
    forward = close.pct_change().shift(-1)
    return (signal * forward).dropna()


def turnover(signal: pd.Series) -> float:
    """Average absolute position change per period — the cost proxy the
    frictionless backtest above leaves out."""
    s = signal.dropna()
    return float(s.diff().abs().mean()) if len(s) > 1 else float("nan")


def build_signals(close: pd.Series, sma_window: int = 25) -> dict[str, pd.Series]:
    """The four classic rules, keyed by name."""
    return {
        "SMA": sma_signal(close, window=sma_window),
        "MACD": macd_signal(close),
        "RSI": rsi_signal(close),
        "Momentum": momentum_signal(close),
    }


def compare_signal_strategies(
    close: pd.Series,
    signals: dict[str, pd.Series] | None = None,
    include_buy_and_hold: bool = True,
) -> pd.DataFrame:
    """Performance table across rules, with a `turnover` column appended.

    Buy-and-hold is included by default because it is the benchmark that
    actually matters: a rule that trades constantly to underperform holding the
    asset has negative value, and a table without that row makes it easy not to
    notice.
    """
    signals = build_signals(close) if signals is None else signals
    strategies = {name: backtest_signal(sig, close) for name, sig in signals.items()}

    if include_buy_and_hold:
        hold = pd.Series(1.0, index=close.index)
        strategies["BuyAndHold"] = backtest_signal(hold, close)
        signals = {**signals, "BuyAndHold": hold}

    table = compare_performance(strategies)
    table["turnover"] = pd.Series({name: turnover(sig) for name, sig in signals.items()})
    return table
