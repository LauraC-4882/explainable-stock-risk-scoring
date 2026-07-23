"""Phase 6: run a full evaluation and emit the required report artifacts.

``generate_all`` runs a seeded population through the core journeys, the safety
scenarios, the accessibility/language checks and the four experiments, then
writes the fifteen deliverables (ten CSV/JSON data files, a replay directory, and
four Markdown documents). Every artifact carries the "cannot-claim-yet" banner:
these are simulated findings — product-risk hypotheses from developer-encoded
priors, not measurements of real people.

Deterministic given a seed. All output lands under ``out_dir`` (default
``simulation_reports/``, gitignored).
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from . import accessibility as acc
from . import scenarios as scn
from .comprehension import run_comprehension_battery
from .distributions import derive_generator
from .events import EventType, config_hash
from .experiment import ALL_EXPERIMENTS
from .fairness import all_disparities, flag_material_disparities, literacy_band
from .interpret import UserState, interpret_view
from .presentation import PresentationVariant, render_stock_view
from .profiles import Archetype, UserProfile, generate_population
from .replay import write_replay
from .sut import load_scorecard
from .tasks import run_single_stock_analysis

CANNOT_CLAIM_BANNER = (
    "SIMULATED FINDINGS — NOT REAL-USER DATA. Every number here is produced by "
    "developer-encoded behavioural priors, not measured from people. These results "
    "surface product risks and hypotheses to test with real users; they are not "
    "evidence about real behaviour, demographic fairness, returns, or regulatory "
    "compliance. See real-user-study-plan.md and resume-claims-checklist.md."
)


def _write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        fh.write(f"# {CANNOT_CLAIM_BANNER}\n")
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)


@dataclass
class _UserRecord:
    profile: UserProfile
    comprehension: float
    overreliance: bool
    calibration_gap: float
    final_misconceptions: list[str]
    intended_action: str


@dataclass
class ReportManifest:
    out_dir: Path
    files: list[str] = field(default_factory=list)

    def add(self, path: Path) -> Path:
        self.files.append(str(path.relative_to(self.out_dir)))
        return path


def _run_core(
    population: list[UserProfile], seed: int, cfg: str
) -> list[_UserRecord]:
    records: list[_UserRecord] = []
    for i, u in enumerate(population):
        log = run_single_stock_analysis(u, seed=seed + i, config_hash=cfg,
                                        variant=PresentationVariant.AS_IS)
        intent = log.of_type(EventType.USER_ACTION_INTENT_RECORDED)[0]
        comp_state = intent.comprehension_state
        # A separate comprehension battery for the user (fresh state).
        state = UserState.initial(u)
        view = render_stock_view(load_scorecard("TSLA"), variant=PresentationVariant.AS_IS,
                                 language=u.language)
        interpret_view(u, state, view, derive_generator(seed + i, 99))
        battery = run_comprehension_battery(u, state, derive_generator(seed + i, 100))
        records.append(_UserRecord(
            profile=u,
            comprehension=battery.score,
            overreliance=bool(log.of_type(EventType.USER_OVERRELIANCE_DETECTED)),
            calibration_gap=float(comp_state.get("calibration_gap", 0.0)),
            final_misconceptions=intent.misconception_state or [],
            intended_action=intent.intended_financial_action or "none",
        ))
    return records


def _trust_class(gap: float) -> str:
    if gap > 0.15:
        return "over_trust"
    if gap < -0.15:
        return "under_trust"
    return "calibrated"


def generate_all(
    out_dir: Path | str = "simulation_reports",
    *,
    seed: int = 2026,
    per_archetype: int = 12,
    experiment_per_archetype: int | None = None,
) -> ReportManifest:
    """Run the full evaluation and write all fifteen artifacts.

    ``experiment_per_archetype`` overrides the (deliberately larger) experiment
    population — tests shrink it for speed; leave it None in real runs.
    """
    out_dir = Path(out_dir)
    cfg = config_hash({"seed": seed, "per_archetype": per_archetype, "version": 1})
    manifest = ReportManifest(out_dir=out_dir)

    population = generate_population(seed=seed, per_archetype=per_archetype)
    records = _run_core(population, seed, cfg)

    # 3. comprehension-results.csv
    comp_rows = [
        {"user_id": r.profile.user_id, "archetype": r.profile.archetype.value,
         "language": r.profile.language.value, "literacy_band": literacy_band(r.profile),
         "comprehension_score": round(r.comprehension, 3)}
        for r in records
    ]
    _write_csv(manifest.add(out_dir / "comprehension-results.csv"), comp_rows,
               ["user_id", "archetype", "language", "literacy_band", "comprehension_score"])

    # 4. misconception-rates.csv (rate each misconception persists, by archetype)
    misc_counter: dict[str, Counter] = {}
    for r in records:
        c = misc_counter.setdefault(r.profile.archetype.value, Counter())
        c["_n"] += 1
        for m in r.final_misconceptions:
            c[m] += 1
    misc_rows = []
    all_misc = sorted({m for r in records for m in r.final_misconceptions})
    for arche, c in sorted(misc_counter.items()):
        row = {"archetype": arche, "n_users": c["_n"]}
        for m in all_misc:
            row[m] = round(c[m] / c["_n"], 3)
        misc_rows.append(row)
    _write_csv(manifest.add(out_dir / "misconception-rates.csv"), misc_rows,
               ["archetype", "n_users", *all_misc])

    # 5. trust-calibration.csv
    trust_rows = [
        {"user_id": r.profile.user_id, "archetype": r.profile.archetype.value,
         "calibration_gap": round(r.calibration_gap, 3),
         "trust_class": _trust_class(r.calibration_gap),
         "overreliance_detected": r.overreliance}
        for r in records
    ]
    _write_csv(manifest.add(out_dir / "trust-calibration.csv"), trust_rows,
               ["user_id", "archetype", "calibration_gap", "trust_class", "overreliance_detected"])

    # 8. harmful-action-intent.csv
    harm_rows = [
        {"user_id": r.profile.user_id, "archetype": r.profile.archetype.value,
         "intended_action": r.intended_action,
         "is_harmful_exit": r.intended_action in {"sell_all", "reduce_position"},
         "is_overconfident_buy": r.intended_action in {"buy", "buy_more"}}
        for r in records
    ]
    _write_csv(manifest.add(out_dir / "harmful-action-intent.csv"), harm_rows,
               ["user_id", "archetype", "intended_action", "is_harmful_exit",
                "is_overconfident_buy"])

    # 2. user-segment-comparison.csv (comprehension/overreliance by segment)
    comp_pop = [(r.profile, r.comprehension) for r in records]
    over_pop = [(r.profile, 1.0 if r.overreliance else 0.0) for r in records]
    disparities = all_disparities(comp_pop, ["literacy", "language", "color_vision", "archetype"])
    seg_rows = []
    for dim, res in disparities.items():
        over_res = all_disparities(over_pop, [dim])[dim]
        for key, rate in sorted(res.rates.items()):
            seg_rows.append({"dimension": dim, "segment": key, "n": res.counts[key],
                             "mean_comprehension": rate,
                             "overreliance_rate": over_res.rates.get(key, 0.0)})
    _write_csv(manifest.add(out_dir / "user-segment-comparison.csv"), seg_rows,
               ["dimension", "segment", "n", "mean_comprehension", "overreliance_rate"])

    # 6. accessibility-results.csv
    acc_rows = []
    for alt in (False, True):
        acc_pop = generate_population(seed=seed + 1, per_archetype=per_archetype,
                                     archetypes=(Archetype.VISUAL_ACCESSIBILITY,))
        for i, u in enumerate(acc_pop):
            d = acc.run_accessibility_journey(
                u, seed=i, config_hash=cfg, charts_have_alt_text=alt
            ).of_type(EventType.SIMULATION_COMPLETED)[0].detail
            acc_rows.append({"user_id": u.user_id, "charts_have_alt_text": alt,
                             "uses_screen_reader": d["uses_screen_reader"],
                             "completed": d["completed"],
                             "missed_chart": d["missed_chart_content"]})
    _write_csv(manifest.add(out_dir / "accessibility-results.csv"), acc_rows,
               ["user_id", "charts_have_alt_text", "uses_screen_reader", "completed",
                "missed_chart"])

    # 7. language-parity-results.csv
    lang_rows = []
    for i, u in enumerate(population):
        d = acc.run_language_parity(u, seed=i, config_hash=cfg
                ).of_type(EventType.SIMULATION_COMPLETED)[0].detail
        lang_rows.append({"user_id": u.user_id,
                          "en_untranslated_understood": d["en"]["untranslated_understood"],
                          "zh_untranslated_understood": d["zh"]["untranslated_understood"],
                          "parity_gap": d["untranslated_parity_gap"], "parity_ok": d["parity_ok"]})
    _write_csv(manifest.add(out_dir / "language-parity-results.csv"), lang_rows,
               ["user_id", "en_untranslated_understood", "zh_untranslated_understood",
                "parity_gap", "parity_ok"])

    # 9. community-misinformation-results.csv
    comm_rows = []
    for with_sep in (True, False):
        comm_pop = generate_population(
            seed=seed + 2, per_archetype=per_archetype,
            archetypes=(Archetype.COMMUNITY_INFLUENCED, Archetype.FIRST_TIME_RETAIL))
        for i, u in enumerate(comm_pop):
            d = scn.run_community_misinformation(
                u, seed=i, config_hash=cfg, with_disclaimer=with_sep
            ).of_type(EventType.SIMULATION_COMPLETED)[0].detail
            comm_rows.append({"user_id": u.user_id, "with_separation": with_sep,
                              "community_override": d["community_override_of_evidence"],
                              "reported": d["reported"]})
    _write_csv(manifest.add(out_dir / "community-misinformation-results.csv"), comm_rows,
               ["user_id", "with_separation", "community_override", "reported"])

    # 10. data-quality-response.csv
    dq_rows = []
    for warn in (False, True):
        dq_pop = generate_population(
            seed=seed + 3, per_archetype=per_archetype,
            archetypes=(Archetype.ILLIQUID_DATA_SPARSE, Archetype.LOW_FINANCIAL_LITERACY,
                        Archetype.EXPERIENCED_INVESTOR))
        for i, u in enumerate(dq_pop):
            log = scn.run_data_quality_failure(u, seed=i, config_hash=cfg, surface_warning=warn)
            intent = log.of_type(EventType.USER_ACTION_INTENT_RECORDED)[0]
            dq_rows.append({"user_id": u.user_id, "warning_surfaced": warn,
                            "took_at_face_value": intent.detail["took_score_at_face_value"],
                            "correct_no_action": intent.detail["correct_no_action"]})
    _write_csv(manifest.add(out_dir / "data-quality-response.csv"), dq_rows,
               ["user_id", "warning_surfaced", "took_at_face_value", "correct_no_action"])

    # Experiments. Sized independently of the descriptive population: at the
    # default per_archetype the paired tests are underpowered and every verdict
    # collapses to "inconclusive", which says more about n than about the product.
    exp_per_archetype = (
        experiment_per_archetype if experiment_per_archetype is not None
        else max(per_archetype, 20)
    )
    exp_pop = generate_population(seed=seed, per_archetype=exp_per_archetype, archetypes=(
        Archetype.FIRST_TIME_RETAIL, Archetype.LOW_FINANCIAL_LITERACY,
        Archetype.EXPERIENCED_INVESTOR, Archetype.CAUTIOUS_RETIREMENT_SAVER,
        Archetype.CONCENTRATED_EMPLOYER_STOCK, Archetype.MARKET_CRASH_USER))
    experiments = {k: fn(exp_pop, seed=7, config_hash=cfg).to_dict()
                   for k, fn in ALL_EXPERIMENTS.items()}

    # 11. user-replays/ (a spread of illustrative journeys)
    replay_dir = out_dir / "user-replays"
    sample_archetypes = [Archetype.FIRST_TIME_RETAIL, Archetype.LOW_FINANCIAL_LITERACY,
                         Archetype.EXPERIENCED_INVESTOR, Archetype.CHINESE_LANGUAGE,
                         Archetype.MARKET_CRASH_USER, Archetype.COMMUNITY_INFLUENCED]
    for arche in sample_archetypes:
        u = generate_population(seed=seed, per_archetype=1, archetypes=(arche,))[0]
        log = run_single_stock_analysis(u, seed=7, config_hash=cfg,
                                        variant=PresentationVariant.AS_IS)
        jpath, _ = write_replay(log, replay_dir, arche.value)
        manifest.add(jpath)

    # 1. simulated-user-summary.json
    summary = _build_summary(records, disparities, experiments, lang_rows, seed, per_archetype)
    (out_dir).mkdir(parents=True, exist_ok=True)
    manifest.add(out_dir / "simulated-user-summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    # 12-15. Markdown documents
    _write_markdown_docs(out_dir, manifest, summary, experiments, disparities)

    (out_dir / "MANIFEST.json").write_text(
        json.dumps({"files": manifest.files, "banner": CANNOT_CLAIM_BANNER}, indent=2),
        encoding="utf-8")
    return manifest


def _build_summary(records, disparities, experiments, lang_rows, seed, per_archetype) -> dict:
    n = len(records)
    mean_comp = sum(r.comprehension for r in records) / n
    overreliance = sum(1 for r in records if r.overreliance) / n
    harmful = sum(1 for r in records if r.intended_action in {"sell_all", "reduce_position"}) / n
    parity_gap = sum(row["parity_gap"] for row in lang_rows) / max(1, len(lang_rows))
    return {
        "banner": CANNOT_CLAIM_BANNER,
        "seed": seed,
        "n_users": n,
        "per_archetype": per_archetype,
        "headline": {
            "mean_comprehension": round(mean_comp, 3),
            "overreliance_rate": round(overreliance, 3),
            "harmful_exit_intent_rate": round(harmful, 3),
            "mean_language_parity_gap": round(parity_gap, 3),
        },
        "experiments": experiments,
        "disparities": {
            dim: {"gap": res.disparity_gap, "ratio": res.disparity_ratio,
                  "worst_segment": res.worst_segment, "rates": res.rates}
            for dim, res in disparities.items()
        },
        "material_disparities": flag_material_disparities(disparities),
    }


def _verdict_line(exp: dict) -> str:
    e = exp["effect"]
    return (f"`{exp['control_arm']}`={exp['control_mean']} vs `{exp['treatment_arm']}`="
            f"{exp['treatment_mean']} | effect {e['mean_diff']:+} "
            f"CI[{e['ci_low']}, {e['ci_high']}] -> **{e['verdict']}**")


def _write_markdown_docs(out_dir: Path, manifest: ReportManifest, summary: dict,
                         experiments: dict, disparities) -> None:
    from .report_templates import (
        harm_risk_register_md,
        real_user_study_plan_md,
        resume_claims_checklist_md,
        social_impact_report_md,
    )
    manifest.add(out_dir / "social-impact-report.md").write_text(
        social_impact_report_md(summary, experiments), encoding="utf-8")
    manifest.add(out_dir / "harm-risk-register.md").write_text(
        harm_risk_register_md(), encoding="utf-8")
    manifest.add(out_dir / "real-user-study-plan.md").write_text(
        real_user_study_plan_md(), encoding="utf-8")
    manifest.add(out_dir / "resume-claims-checklist.md").write_text(
        resume_claims_checklist_md(summary), encoding="utf-8")
