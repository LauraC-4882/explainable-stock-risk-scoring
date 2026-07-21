"""Tests for the historical conditional outcome distribution (outcomes.py).

The math is exercised on small synthetic series where every forward return
is known by construction, plus the project's standing "no numpy scalars in
API responses" walk (CLAUDE.md rule 4) over the full payload.
"""

import json

from stock_risk.outcomes import MIN_SAMPLE, compute_outcome_distribution


def _rows(closes, labels):
    return [
        {"date": f"2026-01-{i + 1:02d}", "close": c, "risk_score": 50.0, "risk_label": label}
        for i, (c, label) in enumerate(zip(closes, labels))
    ]


def test_forward_returns_and_band_grouping():
    # 8 rows, horizon 2: day i's sample = close[i+2]/close[i] - 1.
    closes = [100, 100, 110, 121, 121, 121, 100, 100]
    labels = ["LOW", "LOW", "HIGH", "HIGH", "HIGH", "HIGH", "LOW", "LOW"]
    result = compute_outcome_distribution(_rows(closes, labels), horizon_days=2)

    assert result["horizon_days"] == 2
    assert result["sample_days"] == 6  # 8 rows - 2 horizon
    assert result["current_label"] == "LOW"
    by_label = {b["label"]: b for b in result["bands"]}

    # LOW samples: day0 -> 110/100-1 = +10%, day1 -> 121/100-1 = +21%
    low = by_label["LOW"]
    assert low["days"] == 2
    assert low["up_pct"] == 100.0
    assert low["down_pct"] == 0.0
    assert low["median"] == 15.5  # midpoint of +10% and +21%
    # +10% forward window max qualifies as a rally (>= +10%)
    assert low["rally10_pct"] == 100.0
    assert low["drawdown10_pct"] == 0.0

    # HIGH samples: days 2..5 -> 121/110-1=+10%, 121/121-1=0%, 100/121-1=-17.4%, 100/121-1=-17.4%
    high = by_label["HIGH"]
    assert high["days"] == 4
    assert high["up_pct"] == 25.0  # only +10% counts; 0% is not "up"
    assert high["down_pct"] == 75.0
    assert high["drawdown10_pct"] == 50.0  # the two -17.4% windows

    # Bands never observed still appear, flagged empty.
    assert by_label["MODERATE"]["days"] == 0
    assert by_label["MODERATE"]["sufficient"] is False
    assert by_label["EXTREME"]["days"] == 0


def test_small_samples_flagged_insufficient_but_still_reported():
    closes = [100, 101, 102, 103, 104]
    labels = ["EXTREME"] * 5
    result = compute_outcome_distribution(_rows(closes, labels), horizon_days=2)
    extreme = {b["label"]: b for b in result["bands"]}["EXTREME"]
    assert 0 < extreme["days"] < MIN_SAMPLE
    assert extreme["sufficient"] is False
    assert extreme["up_pct"] == 100.0  # stats still computed


def test_sufficient_flag_at_threshold():
    n = MIN_SAMPLE + 2  # exactly MIN_SAMPLE samples after the horizon is cut
    closes = [100 + i for i in range(n)]
    labels = ["MODERATE"] * n
    result = compute_outcome_distribution(_rows(closes, labels), horizon_days=2)
    moderate = {b["label"]: b for b in result["bands"]}["MODERATE"]
    assert moderate["days"] == MIN_SAMPLE
    assert moderate["sufficient"] is True


def test_empty_and_too_short_inputs():
    assert compute_outcome_distribution([], horizon_days=20)["sample_days"] == 0
    short = _rows([100, 101, 102], ["LOW", "LOW", "LOW"])
    result = compute_outcome_distribution(short, horizon_days=20)
    assert result["sample_days"] == 0
    assert all(b["days"] == 0 for b in result["bands"])
    assert result["current_label"] == "LOW"


def test_payload_is_json_serializable_with_native_types():
    closes = [100 * (1.01 ** i) for i in range(60)]
    labels = (["LOW"] * 15 + ["MODERATE"] * 15 + ["HIGH"] * 15 + ["EXTREME"] * 15)
    result = compute_outcome_distribution(_rows(closes, labels), horizon_days=10)
    json.dumps(result)  # would raise on any non-native numeric

    def walk(o):
        if isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
        elif o is not None and not isinstance(o, (str, bool)):
            assert type(o) in (int, float), f"non-native numeric leaf: {type(o)}"

    walk(result)


def test_mock_fixture_matches_endpoint_contract():
    """The ui_shot fixture must stay shape-compatible with the real
    computation so the mock-mode frontend renders the same structure."""
    from pathlib import Path

    fixture = json.loads(
        (Path(__file__).parent / "fixtures" / "mock_api" / "outcomes_tsla.json").read_text(
            encoding="utf-8"
        )
    )
    real = compute_outcome_distribution(
        _rows([100 + i for i in range(40)], ["LOW"] * 40), horizon_days=20
    )
    assert set(fixture.keys()) == set(real.keys())
    real_band_keys = set(next(b for b in real["bands"] if b["days"] > 0).keys())
    for band in fixture["bands"]:
        assert set(band.keys()) == real_band_keys
