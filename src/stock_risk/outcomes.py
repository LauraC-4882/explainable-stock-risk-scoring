"""Historical conditional outcome distributions.

Answers "when this stock previously sat in its current risk band, what
happened over the following N trading days?" — up/down frequency, the
interquartile range of forward returns, and how often a 10%+ drawdown or
10%+ rally occurred. This is *descriptive statistics about the past*, the
same epistemic category as the stress test and the metric "readings": it
is deliberately NOT a forecast, and the numbers exist to teach the core
lesson that a higher risk score widens the distribution of outcomes in
BOTH directions rather than predicting a fall. The frontend pairs every
rendering of this data with the standard not-a-recommendation disclaimer.

Input is the exact row shape scorer.score_timeseries() already produces
({date, close, risk_score, risk_label, ...}), so the computation needs no
extra data fetch beyond the timeseries the app can already build — and
because those scores are computed with no lookahead, conditioning on them
here introduces none either.
"""

from __future__ import annotations

HORIZON_DAYS = 20
# Below this many observations a band's percentages are noise, not signal —
# the band is still returned (with its stats) but flagged so the UI can
# visually de-emphasise it instead of silently presenting 3 samples as "33%".
MIN_SAMPLE = 10

BAND_ORDER = ["LOW", "MODERATE", "HIGH", "EXTREME"]


def _percentile(sorted_values: list[float], p: float) -> float:
    """Linear-interpolated percentile of an already-sorted list."""
    n = len(sorted_values)
    if n == 1:
        return sorted_values[0]
    k = (n - 1) * p
    f = int(k)
    c = min(f + 1, n - 1)
    return sorted_values[f] + (sorted_values[c] - sorted_values[f]) * (k - f)


def compute_outcome_distribution(rows: list[dict], horizon_days: int = HORIZON_DAYS) -> dict:
    """Per-risk-band forward-outcome statistics from a daily score timeseries.

    For every day t that has a full *horizon_days* of history after it, the
    forward window close[t+1..t+horizon] yields: the end-of-horizon return,
    whether the window ever traded 10%+ below the entry close (drawdown),
    and whether it ever traded 10%+ above it (rally). Samples are grouped
    by that day's risk_label. All returned numerics are native Python
    types (percentages rounded to 1dp), per the project's no-numpy-scalars
    API rule.
    """
    samples: dict[str, list[tuple[float, bool, bool]]] = {label: [] for label in BAND_ORDER}
    closes = [float(r["close"]) for r in rows]

    for i in range(len(rows) - horizon_days):
        label = rows[i].get("risk_label")
        c0 = closes[i]
        if label not in samples or c0 <= 0:
            continue
        window = closes[i + 1 : i + 1 + horizon_days]
        fwd = window[-1] / c0 - 1
        drawdown10 = min(window) / c0 - 1 <= -0.10
        rally10 = max(window) / c0 - 1 >= 0.10
        samples[label].append((fwd, drawdown10, rally10))

    bands = []
    for label in BAND_ORDER:
        s = samples[label]
        n = len(s)
        if n == 0:
            bands.append({"label": label, "days": 0, "sufficient": False})
            continue
        rets = sorted(x[0] for x in s)
        ups = sum(1 for x in s if x[0] > 0)
        bands.append(
            {
                "label": label,
                "days": n,
                "sufficient": n >= MIN_SAMPLE,
                "up_pct": round(100 * ups / n, 1),
                "down_pct": round(100 * (n - ups) / n, 1),
                "p25": round(100 * _percentile(rets, 0.25), 1),
                "median": round(100 * _percentile(rets, 0.5), 1),
                "p75": round(100 * _percentile(rets, 0.75), 1),
                "drawdown10_pct": round(100 * sum(1 for x in s if x[1]) / n, 1),
                "rally10_pct": round(100 * sum(1 for x in s if x[2]) / n, 1),
            }
        )

    return {
        "horizon_days": horizon_days,
        "start_date": rows[0]["date"] if rows else None,
        "end_date": rows[-1]["date"] if rows else None,
        "sample_days": sum(len(s) for s in samples.values()),
        "current_label": rows[-1].get("risk_label") if rows else None,
        "bands": bands,
    }
