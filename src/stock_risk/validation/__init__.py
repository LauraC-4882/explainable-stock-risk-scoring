"""[R6] Tail-risk model validation: coverage, independence, Expected Shortfall."""

from .tail_tests import (
    TestResult,
    acerbi_szekely_z2,
    breach_clustering_profile,
    christoffersen_conditional_coverage,
    christoffersen_independence,
    kupiec_pof,
    run_full_suite,
)

__all__ = [
    "TestResult",
    "acerbi_szekely_z2",
    "breach_clustering_profile",
    "christoffersen_conditional_coverage",
    "christoffersen_independence",
    "kupiec_pof",
    "run_full_suite",
]
