from .volatility import VolatilityModel

# DownsideRiskModel is deliberately NOT re-exported here (unlike VolatilityModel)
# — see [F1]: this __init__.py runs whenever *any* stock_risk.models submodule
# is imported (e.g. scorer.py's `from ..models.volatility import VolatilityModel`),
# so eagerly importing DownsideRiskModel here would drag xgboost into every
# such caller regardless of whether it needs the ML leg — exactly the module
# that was supposed to be deferred. Nothing in this codebase imports
# DownsideRiskModel via this package's __init__ (verified: grep finds every
# caller already using `from ..models.downside_risk import DownsideRiskModel`
# directly) — if that changes, import it lazily at the call site instead of
# re-adding it here.
__all__ = ["VolatilityModel"]
