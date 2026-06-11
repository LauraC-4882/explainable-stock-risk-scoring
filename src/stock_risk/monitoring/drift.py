"""Feature drift detection using PSI and KS-test."""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats
from loguru import logger


def _psi(expected: np.ndarray, actual: np.ndarray, bins: int = 10) -> float:
    """Population Stability Index between two distributions."""
    breakpoints = np.percentile(expected, np.linspace(0, 100, bins + 1))
    breakpoints[0] = -np.inf
    breakpoints[-1] = np.inf

    exp_counts = np.histogram(expected, bins=breakpoints)[0] / len(expected)
    act_counts = np.histogram(actual, bins=breakpoints)[0] / len(actual)

    exp_counts = np.where(exp_counts == 0, 1e-4, exp_counts)
    act_counts = np.where(act_counts == 0, 1e-4, act_counts)

    return float(np.sum((act_counts - exp_counts) * np.log(act_counts / exp_counts)))


class DriftDetector:
    """Compares current feature distributions to a stored reference window."""

    PSI_THRESHOLD = 0.2   # >0.2 indicates significant drift
    KS_ALPHA = 0.05

    def __init__(self, reference_df: pd.DataFrame, feature_cols: list[str]):
        self.reference = reference_df[feature_cols].dropna()
        self.feature_cols = feature_cols

    def detect(self, current_df: pd.DataFrame) -> dict[str, dict]:
        current = current_df[self.feature_cols].dropna()
        results = {}
        for col in self.feature_cols:
            ref_vals = self.reference[col].values
            cur_vals = current[col].values
            psi = _psi(ref_vals, cur_vals)
            ks_stat, ks_p = stats.ks_2samp(ref_vals, cur_vals)
            results[col] = {
                "psi": round(psi, 4),
                "psi_drift": psi > self.PSI_THRESHOLD,
                "ks_stat": round(ks_stat, 4),
                "ks_drift": ks_p < self.KS_ALPHA,
            }
            if psi > self.PSI_THRESHOLD:
                logger.warning(f"Drift detected in feature '{col}' | PSI={psi:.3f}")
        return results
