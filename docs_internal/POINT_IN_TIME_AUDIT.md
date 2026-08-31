# Point-in-time audit

Audit only. **No calculation was changed, no published figure was recomputed,
and no production code path was touched by this change.** Baseline for every
count in this document: `2f232b2` (691 passed + 2 skipped, local, own venv,
no `.env` / no built frontend / no CI variable).

Question audited: **is every number attributed to time t computed only from
information genuinely available at or before t?** Statuses: `confirmed-leak`,
`clean`, `needs-empirical-check`, `deferred-with-reason`. Clean rows are in
the body on purpose — an audit that lists only problems is marketing.

Companion evidence: `tests/test_pit_tamper_invariance.py` (behavioural — a
tampered future must not change the past) and
`tests/test_point_in_time_inventory.py` (registry — the rows below cannot be
silently rewritten). Sibling audit: the return-convention inventory on branch
`audit/return-convention` (`docs_internal/RETURN_CONVENTION_AUDIT.md` there)
covers the same data sources from the convention-consistency angle; its
adjustment matrix is cross-referenced here, not restated.

## A. Backward price adjustment (the headline section)

Every price source rewrites history retroactively:
[fetcher.py:259,264](../src/stock_risk/data/fetcher.py) (yfinance,
`auto_adjust=True`, splits+dividends), :313/:322 (akshare `adjust="qfq"`),
:281-290 (Twelve Data — **no adjustment parameter sent; vendor default
applies, undetermined**). A corporate event with ex-date T multiplies every
stored price at dates ≤ T by a factor k the moment the series is re-fetched.

### A1.i — ratio-class features: clean, proven

Every return, volatility, drawdown ratio, tail quantile and beta consumes
prices only through ratios of two same-window prices; the same k multiplies
numerator and denominator and cancels. **Status: clean** — proven, not
assumed: `test_ratio_features_at_t_ignore_a_future_adjustment_event` scales
the entire history ≤ T (T after t) and asserts the t-row bitwise-equal at
k = 2.0 (exact float scaling) and at rtol 1e-9 for realistic k, across 30
feature columns × 3 tickers × 4 tamper cases. The tamper provably reaches the
t-row: the level columns in the same run move by exactly k (A1.ii), so the
invariance is not a tamper that missed.

### A1.ii — level-class quantities: confirmed-leak, with a precise boundary

`dollar_volume_21d` and `amihud_illiq_21d`
([risk_metrics.py:190-196](../src/stock_risk/features/risk_metrics.py))
consume the adjusted price LEVEL; a future event rescales what they report
for day t by exactly k (dollar volume ×k, Amihud ×1/k — characterized as
exact equalities in `test_level_features_scale_by_exactly_k`; if that test
goes red the leak has been fixed and this row must be updated with it).
**Status: confirmed-leak.**

**The narrowing, stated with its premise.** The published own-history
composite is invariant to this leak — including its liquidity category —
because at any t ≤ T the entire visible window carries the same k and
percentile ranks are scale-free. Twelve composite-invariance cases prove it.
The premise this rests on: **a level quantity's scale-invariance holds only
while it is compared exclusively against other levels from the same window;
the moment it meets any constant (a hardcoded floor, a training-time scaler
moment, a tree split threshold) or a cross-ticker value, k stops cancelling.**
`test_a_level_quantity_meeting_a_constant_is_where_invariance_dies` pins the
premise itself: a fixed threshold between the two fetches' dollar-volume
values flips its verdict under the tamper.

**Enumeration of premise violations** (method: classification of all 18 ML
feature columns level-vs-ratio; `grep -rnE "clip\(|winsor|min_volume|
min_dollar|MIN_PRICE|penny|> *1e[0-9]"` over `src/` and the two production
scripts; line-read of `data/quality.py`, `data/validation.py`,
`scoring/stress_test.py`, `scripts/train.py`):

| site | verdict |
|---|---|
| hardcoded liquidity / dollar-volume floors | **none exist** — the only consumers of the two level columns are their own-history percentiles |
| data-quality gates ([quality.py](../src/stock_risk/data/quality.py), [validation.py](../src/stock_risk/data/validation.py)) | clean — row counts, gap days, staleness age, NaN masks, price>0; all invariant under k>0 |
| winsorize / clip bounds | clean — every clip is a zero lower bound on a ratio-class quantity (invariant for k>0) or on a probability |
| training-universe filters ([train.py](../scripts/train.py)) | clean — static ticker list + fetch-coverage count; no level filter (survivorship is row G2, a separate issue) |
| stress test ([stress_test.py](../src/stock_risk/scoring/stress_test.py)) | clean — multiplicative shocks ranked against own-window history; k cancels in the percentile |
| cross-sectional pooled panel | violation by construction, **not on this baseline** — the module lives on the WIP branch (wip/parallel-session); registered as G1, deferred-with-reason |
| **ML feature set** ([feature_sets.py:43](../src/stock_risk/models/feature_sets.py)) | **one violation: `atr_14`** — see A1.iii |

### A1.iii — atr_14 through the ML leg: confirmed-leak on the published headline

Of the 18 ML feature columns, exactly one is a price level: `atr_14`. It
meets constants frozen at training time — the StandardScaler's μ/σ and the
XGBoost split thresholds — so the premise fails there by construction, and
the leak sits on the **published headline** (the ML leg carries 15% of
`risk_score`). Empirical probe on the committed artefact (2026-08-31,
recorded not asserted — it depends on the artefact): atr_14 importance
0.073 (4th–5th of 18); under the tamper atr_14 is the only changed feature;
at k = 0.97 the raw XGBoost probability did not move (no split crossed for
the probed rows), at **k = 0.5 it moved by −2.7e-2**; the isotonic
calibration plateau absorbed both for the probed rows — plateaus have edges,
so that is luck, not a guarantee. **Status: confirmed-leak** (structural;
magnitude row-dependent). Pinned structurally by
`test_atr_the_one_level_feature_in_the_ml_set_scales_by_k`.
Not fixed here: removing/normalising atr_14 changes the trained artefact and
every published ML metric — a retrain decision, not an audit's.

### A2 — vendor adjustment semantics: needs-empirical-check ×2

* Twelve Data default adjustment (splits only? dividends?) —
  `scripts/pit_probes/probe_twelvedata_adjustment.py` (needs a real key).
* Whether yfinance volume is split-adjusted in step with `auto_adjust`
  prices — `scripts/pit_probes/probe_yfinance_volume_split.py` (needs
  network). Until answered, `volume_ratio`/`volume_vol_21d` around split
  dates are unverified.

## B. Full-sample statistics

* **B1** [preprocessor.py:65-72](../src/stock_risk/data/preprocessor.py):
  the outlier filter derives its 6σ threshold from the whole fetched series
  and confirms with the NEXT day's return. **confirmed-leak** (row existence
  decided with future data); the live card is safe (the last row cannot be
  deleted), `score_timeseries` and any backtest reusing `process()` inherit
  it. Deferred-with-reason: changing the filter shifts feature distributions
  and the golden score — needs its own retrain-aware change.
* **B2** [validate_score.py:69-115](../scripts/validate_score.py) claims
  point-in-time and the claim is **clean — verified**: expanding-window
  filter, `composite_score(df.iloc[:i+1])`, outcomes strictly after t.
* **B3** percentile engine
  ([risk_categories.py:181-194](../src/stock_risk/scoring/risk_categories.py))
  is expanding-from-fetch-start and backward-only — **clean** (window origin
  is a baseline definition, not lookahead); `cummax` drawdown likewise.

## C. Model fitting windows

* **C1** GJR-GARCH / HAR-RV: live path refits per request on history ending
  today and forecasts forward
  ([volatility.py:56-87](../src/stock_risk/models/volatility.py)); the
  comparison backtest uses expanding-window refits every 21 trading days
  ([compare_vol_models.py:79-83](../scripts/compare_vol_models.py)) — both
  **clean**; nothing fits once on the full sample and backfills.
* **C2** XGBoost walk-forward: time-ordered `TimeSeriesSplit(gap=20)` — the
  embargo equals the 20-day label horizon
  ([evaluation.py:220-237](../src/stock_risk/models/evaluation.py));
  **clean**. The inner calibration split
  ([downside_risk.py:132-140](../src/stock_risk/models/downside_risk.py),
  [evaluation.py:153-160](../src/stock_risk/models/evaluation.py)) is
  chronological but embargo-free: boundary labels overlap. **confirmed-leak
  (mild) — and the calibration map is part of the USER-FACING output**: the
  served ML probability (and through fusion, the headline score) passes
  through the isotonic calibrator this split trains. Not a diagnostics-only
  artifact. Deferred-with-reason: fixing requires dropping horizon rows
  between the slices and a recalibration.

## D. Transformers

* **D1** SHAP: `TreeExplainer(xgb)` with no background dataset
  ([explain.py:57](../src/stock_risk/models/explain.py)) — **clean**.
* **D2** StandardScaler/Imputer: fit only inside the Pipeline on the
  training fold — **clean** as a fitting protocol.
* **D3** The same scaler's frozen moments are the constants `atr_14` meets —
  that interaction is A1.iii, not a separate fitting defect.

## E. Exogenous inputs

* **E1** VIX regime weights use the level fetched at request time (available
  at decision time by construction); historical chart days deliberately get
  base weights; the term-structure backtest conditions on the t close for
  t+1-onward outcomes — **clean**.
* **E2** News: `published_at` is carried
  ([fetcher.py:510](../src/stock_risk/data/fetcher.py)), consumed live only,
  zero weight, no backtest consumer — **clean by inertness**; if it ever
  gains weight, publication-timestamp filtering becomes mandatory.

## F. Cross-market calendars

CN tickers see CN prices, the CN benchmark and CN sessions end to end; VIX
is fetched for `market == "us"` only
([scorer.py:253-262](../src/stock_risk/scoring/scorer.py)). No same-date US
close reaches a CN feature. **clean.**

## G. Cross-section and universe

* **G1** sector-at-current-date classification and the pooled cross-ticker
  panel: the module exists only on the WIP branch — **deferred-with-reason**
  (re-audit at WIP close-out; the pooled panel is also where A1.ii's k
  becomes visible across tickers).
* **G2** survivorship: [tickers_universe.txt](../scripts/tickers_universe.txt)
  holds currently-listed names only; training and the validation panel both
  draw from it. **confirmed-leak (structural, direction: overstates
  stability, understates tails); magnitude needs-empirical-check** —
  `scripts/pit_probes/probe_survivorship_universe.py` documents what data a
  quantification needs (a delisting-inclusive constituent source; none in
  this repository).

## H. Holiday forward-fill

[preprocessor.py:36-37](../src/stock_risk/data/preprocessor.py)
`asfreq("B").ffill(limit=8)` fabricates a row per holiday from the previous
session. **clean as point-in-time** (it reuses past information) but it
double-weights that information: realised volatility dilutes, percentile
histories pad. The WIP branch replaces it with provenance-based session
dropping; when that lands, volatility/tail features rise and published
scores move — described here so the move is attributable, not implemented
here.

## I. Snapshots as a data source

Tracked snapshots' content may never postdate the commit that recorded them
(that would be fabricated data) — pinned by
`test_snapshot_content_never_postdates_its_commit`, which self-skips with an
announced reason on shallow clones. Verified empirically before writing the
skip: a depth-1 clone dates every file at the clone-boundary commit (a
July-fetched snapshot reported an August commit date), so the assertion
would pass vacuously there — the lesson of the font and hash gates, applied
in advance this time. As a backtest source: usable for
ratio-class series, **not** a point-in-time store for price levels — each
snapshot carries the adjustment state of its fetch date (see A1), and a
single latest snapshot cannot reconstruct as-of-date views. **clean with
scope limits, registered.**

## Pinned / not pinned

Behavioural: A1.i, A1.ii, A1.iii (structural half), the premise fixture, I.
Registry (`test_point_in_time_inventory.py`): every row above's file:line
and status. Not pinned: A2 (needs a live vendor call), G2's magnitude
(needs external data), A1.iii's empirical magnitude (depends on the
committed artefact; recorded above with its probe date).
