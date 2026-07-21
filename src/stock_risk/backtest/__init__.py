"""[G6] Strategy backtesting: rule-based signals and performance evaluation."""

from .performance import (
    annualized_return,
    annualized_volatility,
    compare_performance,
    cumulative_return,
    equity_curve,
    expected_shortfall,
    max_drawdown,
    performance_summary,
    sharpe_ratio,
    sortino_ratio,
    value_at_risk,
)
from .signals import (
    backtest_signal,
    build_signals,
    compare_signal_strategies,
    macd_signal,
    momentum_signal,
    rsi,
    rsi_signal,
    sma_signal,
    turnover,
)

__all__ = [
    "annualized_return",
    "annualized_volatility",
    "backtest_signal",
    "build_signals",
    "compare_performance",
    "compare_signal_strategies",
    "cumulative_return",
    "equity_curve",
    "expected_shortfall",
    "macd_signal",
    "max_drawdown",
    "momentum_signal",
    "performance_summary",
    "rsi",
    "rsi_signal",
    "sharpe_ratio",
    "sma_signal",
    "sortino_ratio",
    "turnover",
    "value_at_risk",
]
