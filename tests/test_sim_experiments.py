"""Phase 5: statistics primitives and the four pre-declared experiments."""

from __future__ import annotations

from stock_risk.simulation import experiment as exp
from stock_risk.simulation.events import config_hash
from stock_risk.simulation.profiles import Archetype, generate_population
from stock_risk.simulation.stats import (
    benjamini_hochberg,
    classify_effect,
    holm,
    paired_bootstrap,
)

CFG = config_hash({"phase": 5})

_POP_ARCHETYPES = (
    Archetype.FIRST_TIME_RETAIL,
    Archetype.LOW_FINANCIAL_LITERACY,
    Archetype.EXPERIENCED_INVESTOR,
    Archetype.CAUTIOUS_RETIREMENT_SAVER,
    Archetype.CONCENTRATED_EMPLOYER_STOCK,
    Archetype.MARKET_CRASH_USER,
)


def _population(per=20):
    return generate_population(seed=2026, per_archetype=per, archetypes=_POP_ARCHETYPES)


# ── stats primitives ─────────────────────────────────────────────────────────
def test_classify_effect_distinguishes_no_effect_from_inconclusive():
    assert classify_effect(-0.02, 0.03, 0.05) == "no_effect"       # tight around zero
    assert classify_effect(-0.20, 0.10, 0.05) == "inconclusive"    # wide, crosses zero
    assert classify_effect(0.02, 0.10, 0.05) == "positive_effect"
    assert classify_effect(-0.10, -0.02, 0.05) == "negative_effect"


def test_paired_bootstrap_detects_a_real_positive_effect():
    control = [0.0] * 40 + [1.0] * 10
    treatment = [1.0] * 40 + [1.0] * 10   # treatment strictly >= control, mostly +1
    est = paired_bootstrap(control, treatment, seed=1, mde=0.05)
    assert est.mean_diff > 0
    assert est.ci_low > 0
    assert est.verdict == "positive_effect"


def test_paired_bootstrap_is_deterministic():
    c = [0.0, 1.0, 0.0, 1.0, 1.0, 0.0]
    t = [1.0, 1.0, 0.0, 1.0, 1.0, 1.0]
    a = paired_bootstrap(c, t, seed=5)
    b = paired_bootstrap(c, t, seed=5)
    assert a.to_dict() == b.to_dict()


def test_multiple_comparison_corrections_are_monotone_and_bounded():
    raw = [0.01, 0.04, 0.03, 0.20]
    for adj in (holm(raw), benjamini_hochberg(raw)):
        assert all(0.0 <= a <= 1.0 for a in adj)
        assert all(a >= r - 1e-9 for a, r in zip(adj, raw))  # never smaller than raw
    # Holm is at least as conservative as BH.
    assert all(h >= b - 1e-9 for h, b in zip(holm(raw), benjamini_hochberg(raw)))


# ── experiments ──────────────────────────────────────────────────────────────
def test_attribution_experiment_shows_a_positive_effect():
    r = exp.experiment_b_generic_vs_attribution(_population(), seed=7, config_hash=CFG)
    assert r.treatment_mean > r.control_mean
    assert r.effect.verdict == "positive_effect"
    assert r.effect.ci_low > 0


def test_crisis_safe_experiment_reduces_the_harm():
    # Primary metric is harmful-exit intent; a NEGATIVE effect is the good outcome.
    r = exp.experiment_c_normal_vs_crisis_safe(_population(), seed=7, config_hash=CFG)
    assert r.treatment_mean < r.control_mean
    assert r.effect.verdict == "negative_effect"
    assert r.effect.ci_high < 0


def test_experiment_reports_segments_with_bh_correction():
    r = exp.experiment_b_generic_vs_attribution(_population(), seed=7, config_hash=CFG)
    assert "literacy" in r.segments
    for _seg, rec in r.segments["literacy"].items():
        assert "p_value_bh" in rec
        assert rec["analysis"] == "exploratory"


def test_experiments_are_deterministic():
    a = exp.experiment_c_normal_vs_crisis_safe(_population(per=10), seed=3, config_hash=CFG)
    b = exp.experiment_c_normal_vs_crisis_safe(_population(per=10), seed=3, config_hash=CFG)
    assert a.to_dict() == b.to_dict()


def test_experiments_are_deterministic_across_processes():
    """Reproducibility must survive a fresh interpreter, not just a second call.

    Regression test for a real bug: `_comprehension_after_variant` derived its
    RNG stream from the builtin `hash(user_id)`, which CPython salts with
    PYTHONHASHSEED. Experiments A and I were therefore stable within one process
    (so the same-process check above passed) and different on every new run —
    exactly the guarantee this package advertises, silently broken. Running the
    experiment in two subprocesses is the only way to catch that class of bug.
    """
    import json
    import subprocess
    import sys

    script = (
        "from stock_risk.simulation import experiment as exp;"
        "from stock_risk.simulation.events import config_hash;"
        "from stock_risk.simulation.profiles import Archetype, generate_population;"
        "import json;"
        "pop = generate_population(seed=2026, per_archetype=6, archetypes=("
        "Archetype.FIRST_TIME_RETAIL, Archetype.EXPERIENCED_INVESTOR));"
        "r = exp.experiment_a_score_only_vs_explained("
        "pop, seed=7, config_hash=config_hash({'x': 1}));"
        "print(json.dumps(r.to_dict()))"
    )
    runs = []
    for _ in range(2):
        out = subprocess.run(
            [sys.executable, "-c", script], capture_output=True, text=True, check=True
        )
        runs.append(json.loads(out.stdout.strip().splitlines()[-1]))
    assert runs[0] == runs[1]


def test_null_experiments_do_not_manufacture_an_effect():
    # A (score-only vs explained) and I (technical vs plain) should NOT come back
    # as confident positive effects on a general comprehension battery — the
    # framework must not invent an effect where the mechanism is weak.
    a = exp.experiment_a_score_only_vs_explained(_population(), seed=7, config_hash=CFG)
    i = exp.experiment_i_technical_vs_plain_language(_population(), seed=7, config_hash=CFG)
    assert a.effect.verdict in {"no_effect", "inconclusive"}
    assert i.effect.verdict in {"no_effect", "inconclusive"}
