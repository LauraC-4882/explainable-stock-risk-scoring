# Stock Risk Scoring System

**Live demo (FastAPI + React, full pipeline incl. ML+SHAP):** https://explainable-stock-risk-scoring.onrender.com — Render free tier: spins down after 15 min idle (~50s+ wake), and the `/api/score/*` endpoints depend on Yahoo not throttling Render's shared egress IP, which it does for extended windows (`/health` and the UI always respond; see [Deployment](#deployment) for the honest details — that IP-reputation constraint, not memory, turned out to be the real free-tier limit).

A production-style system that predicts **downside risk** and **volatility** for individual stocks using live market data fetched via `yfinance`, technical indicators, and machine learning models (XGBoost + sklearn Pipeline).

**Project status (as of 2026-07-19):**

- **Validated & live**: percentile composite score (quintile backtest + Kupiec POF, see *Score Validation*); ML drawdown leg (walk-forward AUC 0.671 on 56 tickers × 5y) — **fusion gate opened 2026-07-19**: risk_score now blends percentile (85%) + ML crash probability (15%), with per-response composition reporting; producer-layer architecture with typed validation-gated fusion weights ([G1]); TTL-cached fetcher with real timeouts + snapshot fallback against Yahoo's datacenter-IP throttling ([C3]+); end-to-end smoke + visual-regression harnesses ([D1]/[D2]); Render deploy (full pipeline).
- **Landed, experiments pending a data window**: [G2] label engineering (vol-scaled dynamic thresholds + triple-barrier first-touch labels, unit-tested; the three-way walk-forward comparison needs a fresh 56×5y fetch, currently blocked by the Yahoo datacenter-IP throttling documented under *Deployment*) and [G3] Alpha158-style factor grid + IC/FDR screen (89 factors implemented and golden-tested; screening + feature-surface comparison queued behind the same data fetch).
- **Known limits, documented not hidden**: `var_95_21d` under-states risk ~2× (Kupiec-rejected — measured, unpatched); ML recall is low (0.11); scores are not comparable across stocks (by construction); yfinance has no SLA and throttles datacenter IPs for extended windows.

## Architecture

```
yfinance (live data)
       │
       ▼
DataPreprocessor          ← gap-fill, outlier removal, log/pct returns
       │
       ▼
TechnicalFeatures         ← RSI, MACD, Bollinger Bands, ATR, OBV, EMA
       │
       ▼
RiskMetrics               ← VaR, CVaR, Sharpe, Sortino, drawdown, EWMA vol, liquidity, beta,
       │                     vol_regime_change, vol_of_vol, drawdown_acceleration, skew_momentum
       ▼
ScoringContext            ← shared inputs fetched once (benchmark returns, ^VIX regime,
       │                     info/IV, news headlines, analyst+insider counts)
       ▼
┌─ Producer layer (scoring/producers/, [G1]) ── each: score 0-100|None · raw · detail ─┐
│  PercentileComposite   weight 0.85 validated (quintile+Kupiec)  → risk_score          │
│  MLDrawdown            weight 0.15 validated (WF AUC 0.671)     → + ml_drawdown_*     │
│  GarchVol (GJR-skewt)  weight 0.0  unvalidated (absolute σ)     → garch_volatility_*  │
│  HarVol (HAR-RV on GK) weight 0.0  unvalidated (absolute σ)     → har_volatility_*    │
│  OptionsImplied        weight 0.0  unvalidated (fwd-looking)    → options_implied     │
│  NewsRisk              weight 0.0  unvalidated (mock extractor) → news_risk           │
│  AltData               weight 0.0  unvalidated (raw counts)     → alt_data            │
└──────────────────────────┬───────────────────────────────────────────────────────────┘
                           ▼
        fuse(): Σwᵢsᵢ/Σwᵢ over available scores — unvalidated producers are
        FORCED to weight 0 at startup (typed guard, not convention). Fusion
        gate OPENED 2026-07-19 after [A1]/[A2] validations: {percentile: 0.85,
        ml_drawdown: 0.15} (ML_FUSION_WEIGHT-configurable; 0 reproduces the
        pure-percentile score). The ML share blends an absolute calibrated
        crash probability into the relative percentile — a small absolute
        anchor, kept small because ML recall is low (0.11). When the ML leg
        is unavailable (no artefact / ENABLE_ML=0) weights renormalise to
        percentile-only, and risk_score_composition in every response reports
        exactly what fed the number.

2008/2020/2022 scenarios ──► stress_test.py (percentile score only, beta-scaled shocks) ─ stress_test
                │
                ▼
          Risk Scorecard (0–100 + label + category breakdown)
                │
       ┌────────┐
       ▼        ▼
  FastAPI   React SPA
  REST API  ui/web/
  /api/*    (built, served at /)
```

## Components

| Module | Description |
|--------|-------------|
| `data/fetcher.py` | Fetches OHLCV, fundamentals, and options IV via **yfinance** |
| `data/preprocessor.py` | Business-day alignment, 6σ outlier removal, log/pct returns |
| `features/technical.py` | RSI, MACD, Bollinger Bands, ATR, OBV, EMA 20/50/200 via **pandas-ta** |
| `features/risk_metrics.py` | Rolling VaR, CVaR, Sharpe, Sortino, drawdown, skew, kurtosis, EWMA vol, liquidity, beta, + vol-regime/vol-of-vol/drawdown-acceleration/skew-momentum cross features |
| `scoring/risk_categories.py` | Percentile-based composite score across 5 risk categories, VIX-threshold regime-weighted (explainable baseline) |
| `scoring/stress_test.py` | Historical-scenario (2008/2020/2022) stress test on the percentile composite, beta-scaled shocks |
| `models/volatility.py` | GARCH(1,1) volatility forecasting via **arch** |
| `models/downside_risk.py` | **XGBoost** classifier (P[max drawdown ≤ -10% in 20d]) inside **sklearn ColumnTransformer** pipeline, isotonic-calibrated for production via `fit_calibrated` |
| `models/evaluation.py` | Chronological Logistic Regression / Random Forest / XGBoost comparison, plus a per-ticker `TimeSeriesSplit` walk-forward backtest with calibration (Precision/Recall/F1/ROC-AUC/PR-AUC/Brier score per fold) |
| `models/explain.py` | **SHAP** attribution for the XGBoost classifier — which features drove `ml_drawdown_probability` |
| `llm/news_risk.py` | News event extraction schema + prompt (Claude structured outputs) — extraction call is mocked until wired |
| `scoring/scorer.py` | End-to-end orchestration: fetch → preprocess → engineer → score |
| `monitoring/drift.py` | PSI + KS-test feature drift detection |
| `monitoring/metrics.py` | Prometheus gauges and JSONL score logging |
| `api/app.py` | **FastAPI** REST endpoints with Prometheus `/metrics` |

## Quick Start

```bash
# 1. Install dependencies
pip install -e ".[dev]"
# `requirements.lock` (uv-generated, full transitive pin of every package —
# regenerate with `uv pip compile requirements.txt -o requirements.lock`
# after changing requirements.txt) is optional, for a byte-for-byte
# reproducible install: pip install -r requirements.lock

# 2. Copy and configure environment
cp .env.example .env

# 3. Train baseline models
python scripts/train.py --tickers AAPL MSFT GOOGL --lookback 730

# 4. Score a single ticker (CLI)
python scripts/score.py --ticker TSLA

# 5. Build the React web frontend (one-time / after any ui/web change)
cd ui/web && npm install && npm run build && cd ../..

# 6. Start the REST API — serves the built React app at http://localhost:8000/
uvicorn src.stock_risk.api.app:app --reload
# or:  make api

# For frontend development with hot reload instead of rebuilding on every change:
cd ui/web && npm run dev   # proxies /api, /health, /metrics to :8000 — run the API too
```

## Data Pipeline

```python
from stock_risk.data.fetcher import MarketDataFetcher
from stock_risk.data.preprocessor import DataPreprocessor
from stock_risk.features.technical import TechnicalFeatures
from stock_risk.features.risk_metrics import RiskMetrics

fetcher = MarketDataFetcher()
raw = fetcher.fetch_history("AAPL", period="2y")          # Twelve Data (US) / akshare (CN, HK)
df  = DataPreprocessor().process(raw)                      # clean
df  = TechnicalFeatures().compute(df)                      # indicators
df  = RiskMetrics().compute(df)                            # risk metrics
```

## Data Quality & Limitations

**Price history is now split by market, not single-sourced from yfinance**
(2026-07 migration, prompted by the chronic datacenter-IP throttling
documented in Deployment below):

| Market | Source | Why |
|---|---|---|
| US equities | **Twelve Data** (real commercial API) if `TWELVE_DATA_KEY` is set, else yfinance | A real API vendor built for programmatic/cloud traffic isn't subject to the same IP-reputation throttle as scraping Yahoo's unofficial endpoint — the actual fix for the Render/CI throttling problem. Free plan: US-only, no options, 800 req/day. |
| CN A-shares + the CSI 300 benchmark ETF | **akshare**, Sina-backed (`stock_zh_a_daily` / `fund_etf_hist_sina`) | Free, no key. akshare's own most-documented functions (eastmoney-backed, e.g. `stock_zh_a_hist`) got connection-reset on every attempt from this project's dev machine — verified live, not assumed; the Sina/Tencent-backed ones didn't. |
| ~~HK equities~~ *(out of scope, 2026-07-22)* | **akshare**, Tencent-backed (`stock_hk_daily`) | Same reasoning; verified live with real OHLCV including volume. **Retained as a working code path but no longer part of the supported universe** — see the scope note below. |
| ~~The HK benchmark `^HSI`~~ *(out of scope, 2026-07-22)* | **akshare**, Sina-backed (`stock_hk_index_daily_sina`) | Routed to akshare too, so the China bucket is fully akshare-backed with zero yfinance in its price/beta path. Verified live. |
| `^VIX`, `^VIX3M` | yfinance, unconditionally | US CBOE volatility indices feeding only the soft, already-degrading market-regime signal — not any China-bucket price/beta computation — so leaving them on yfinance costs nothing when they fail. |

**Supported universe: US equities and mainland China A-shares only.** Hong
Kong listings (`.HK`) were dropped from scope on 2026-07-22. The removal is
scoped to everything user-facing — the market switcher's quick-pick chips
(`EmptyState.jsx` POPULAR), the search placeholders and `known_symbols.py`
search fallback, `refresh_snapshots.py`'s snapshot UNIVERSE, the stored
`.HK`/`^HSI` snapshots, and the English/Chinese site copy. `SearchBar.jsx`
no longer rewrites a bare non-6-digit numeric code into a `.HK` ticker; only
exactly-6-digit A-share codes are normalized (`.SS`/`.SZ`). The akshare HK
fetch paths in `fetcher.py` and `MARKET_BENCHMARKS["hk"]` in `scorer.py` are
deliberately **left in place** — they still work if given a `.HK` ticker
directly, they are simply no longer reachable from the product surface.

All paths still funnel through the same `validate_ohlcv()` contract,
TTL cache, and snapshot fallback (below) — a provider outage degrades
exactly like a yfinance outage always has. yfinance itself remains the
source for options chains and news (`fetch_options_signals`, `fetch_news`)
— both already optional, gracefully-degrading producers (see
`RiskProducer`), so keeping them on the less-reliable free source costs
nothing when it fails and doesn't block the higher-stakes fix above.
`fetch_info` (fundamentals metadata) is also still yfinance-only; its
call site in `scorer.py` now degrades to `{}` on failure rather than
failing the whole request, matching the pattern the benchmark fetch
already used. The `beta` shown in the metric tile prefers yfinance's
fundamental beta but falls back to the 63-day rolling beta computed against
the (now akshare/Twelve-Data-sourced) market benchmark, so a throttled
yfinance no longer leaves every stock's beta reading "—".

None of these are licensed, SLA-backed data feeds — akshare and yfinance
are both unofficial scrapes, and even Twelve Data's free tier is meant for
development/light use, not a production data contract. This remains a
student/portfolio project's data layer, just a more resilient one; a real
production deployment would still want a paid, accountable vendor for
every market, not just US equities.

**Bad data is validated at the fetch boundary, not trusted.**
`data/validation.py`'s `validate_ohlcv()` runs on every `fetch_history()`
call before any other code sees the result, and rejects (raises
`DataValidationError`, never silently drops or repairs):
- non-positive open/high/low/close, or `high < low`
- negative volume
- a non-monotonic or duplicated date index
- a gap between consecutive trading days bigger than what the preprocessor
  can safely forward-fill (`MAX_GAP_TRADING_DAYS` in `validation.py`, kept
  aligned with `DataPreprocessor.max_gap_days` — both are 8, not 5, because
  CN A-share holidays (Spring Festival, National Day) create gaps up to 6
  missing trading days, longer than any single US market holiday)

A still-open "today" session (NaN OHLC on the most recent row, before the
market closes) is explicitly *not* treated as bad data — it's normal,
expected, and already handled by `DataPreprocessor`'s own `dropna()`.

**The 6-sigma outlier filter deletes fat-finger ticks, not large moves.**
An earlier version filtered purely on `|log return| > 6 sigma`, which
verifiably deleted real market history (SPY's 2025-04-09 tariff-pause
rally, +9.99%, one of the largest single-day gains since 2008) — self-
defeating for a system whose whole job is measuring tail risk. It now also
requires the next day to reverse more than half the move before treating a
spike as bad data; see `DataPreprocessor._remove_price_outliers`'s
docstring for the full reasoning.

**Fundamentals (`fetch_info`) are a live snapshot, not point-in-time.**
`sector`, `market_cap`, `trailing_pe`, analyst rating changes, and insider
transaction counts all reflect *today's* values, not what they were on the
date being scored — there's no free point-in-time fundamentals source.
This is a real limitation, sidestepped by a deliberate design choice rather
than papered over: analyst/insider activity is surfaced as informational
`alt_data` only (see `scorer.py`) and never enters `risk_score`, which is
built entirely from the price/volume history that *is* point-in-time.

**Upgrade path**, roughly in order of effort: (1) a paid single source with
an actual SLA, (2) cross-checking a sample of closes against a second free
source (e.g. Tiingo's free tier) and warning — not blocking — on >0.5%
divergence, (3) a real point-in-time fundamentals feed if fundamentals ever
need to enter the score itself rather than staying informational.

## Model Training

The primary risk score (`risk_score` in the API response) is a **percentile-based composite** over five categories — volatility, tail, drawdown, market sensitivity, liquidity — computed relative to each stock's own historical distribution (see `scoring/risk_categories.py`). It requires no training and is fully explainable via `risk_breakdown`.

A secondary, ML-derived signal (`ml_drawdown_probability`) is produced by an **XGBoost classifier** wrapped in a **scikit-learn pipeline** with a `ColumnTransformer` that applies median imputation + `StandardScaler` independently to three feature groups (momentum, volatility, quality). Its target is binary: did the stock's max drawdown breach -10% within the next 20 trading days?

```python
from stock_risk.models.downside_risk import DownsideRiskModel

model = DownsideRiskModel(n_estimators=300, max_depth=5)
model.fit(df)             # label = forward 20-day max drawdown <= -10%
score = model.predict(df)["downside_risk_score"]   # P(event) x 100
```

Falls back to a constant base-rate score (instead of raising) when the training window has no drawdown events at all, since XGBoost can't fit a single-class target.

`ml_drawdown_probability` is otherwise a black box, so `models/explain.py` attaches a **SHAP** (`TreeExplainer`) attribution alongside it as `ml_drawdown_explanation` — the top features pushing that probability up or down, in log-odds units (additive: `base_probability`'s log-odds + every feature's `shap_contribution` = `predicted_probability`'s log-odds). `None` when the model is in fallback mode. Requires `xgboost<3.0` — `shap` 0.49.1 can't parse XGBoost 3.x's `base_score` serialization format.

Feature importances are accessible via `model.feature_importance()`. `scripts/train.py` also runs `models/evaluation.py::compare_classifiers`, which benchmarks Logistic Regression / Random Forest / XGBoost on a chronological (never random) train/test split and reports Precision/Recall/F1/ROC-AUC/PR-AUC/confusion-matrix — accuracy alone is misleading here since drawdown events are a rare minority class.

### Walk-forward backtest + probability calibration

A single train/test split can look fine by luck of where the cut falls. `models/evaluation.py::walk_forward_evaluate` instead runs a per-ticker `TimeSeriesSplit` (with a `gap` between train/test so the forward-looking label window can never leak across the boundary), pooling each fold across tickers, and reports one row per fold plus a mean/std summary — so a caller can see whether e.g. recall holds up or degrades in a specific period instead of only the average:

```python
from stock_risk.models.evaluation import walk_forward_evaluate

result = walk_forward_evaluate(per_ticker_dfs, n_splits=5, gap=20)
#       precision  recall    f1  roc_auc  pr_auc  brier_raw  brier_calibrated
# fold
# 1        ...
```

An uncalibrated XGBoost probability isn't trustworthy at face value — "P=0.7" should mean the event actually happens in ~70% of such cases, which the training objective doesn't guarantee. Each fold's classifier is isotonic-calibrated (`sklearn.calibration.CalibratedClassifierCV`) on a **chronological** held-out slice — the last 20% of the training rows, strictly after what the model fit on and strictly before the test fold — never a random split, which would leak future rows into "calibration" the same way a random train/test split leaks them into training. `brier_raw` vs `brier_calibrated` makes "does calibration actually help" a number instead of an assumption.

The production model uses the same calibration path: `scripts/train.py` calls `DownsideRiskModel.fit_calibrated(...)` (not the plain `fit`/`fit_dataset`), so `ml_drawdown_probability` in the API response is the calibrated estimate. Because isotonic calibration is a post-hoc, non-smooth remap with no SHAP decomposition of its own, `models/explain.py`'s SHAP breakdown still explains the *raw* pre-calibration model — `ml_drawdown_explanation.predicted_probability` (raw) and `.calibrated_probability` (what's actually served) are both reported when a model is calibrated, so the two never get silently conflated.

### Does the XGBoost signal actually work? Two real experiments, not one

The walk-forward framework above is honest and correctly leak-free — that's
exactly what let it expose a real problem instead of hiding one. First
run, small universe (`scripts/train.py --tickers AAPL MSFT GOOGL TSLA NVDA
--lookback 730`, 5 tickers × 2 years):

| fold | precision | recall | ROC-AUC | brier_raw | brier_cal |
|---|---|---|---|---|---|
| 1 | 0.00 | 0.00 | 0.36 | 0.44 | 0.37 |
| 2 | 0.09 | 1.00 | 0.66 | 0.15 | 0.46 |
| 3 | 0.15 | 0.92 | 0.77 | 0.27 | 0.15 |
| 4 | 0.00 | 0.00 | 0.54 | 0.32 | 0.16 |
| 5 | 0.00 | 0.00 | 0.48 | 0.26 | 0.18 |
| **mean** | **0.05** | **0.38** | **0.56** | — | — |

Mean AUC 0.56 — essentially a coin flip — with 3 of 5 folds at recall=0.
Not enough data to reliably learn a drawdown-prediction signal from 5
tickers over 2 years (~2,470 rows before the 15-20% positive rate even
applies).

Second run, per this issue's decision procedure ("expand the data and
retry before concluding the signal is dead"): `scripts/train.py
--tickers-file scripts/tickers_universe.txt --lookback 1825` — 56
cross-sector tickers × 5 years, 73,022 total feature rows, 68,430 after
label construction:

| fold | test period | precision | recall | ROC-AUC | pr_auc | brier_raw | brier_cal |
|---|---|---|---|---|---|---|---|
| 1 | 2022-07 → 2023-05 | 0.40 | 0.26 | 0.684 | 0.327 | 0.354 | 0.162 |
| 2 | 2023-05 → 2024-02 | 0.49 | 0.05 | 0.682 | 0.203 | 0.163 | 0.076 |
| 3 | 2024-02 → 2024-11 | 0.36 | 0.16 | 0.682 | 0.216 | 0.160 | 0.098 |
| 4 | 2024-11 → 2025-09 | 0.34 | 0.02 | 0.617 | 0.237 | 0.218 | 0.135 |
| 5 | 2025-09 → 2026-06 | 0.47 | 0.08 | 0.692 | 0.274 | 0.183 | 0.119 |
| **mean** | | **0.41** | **0.11** | **0.671** | **0.251** | | |

**Decision: keep the signal, data volume was the actual constraint.**
Mean AUC 0.56 → 0.671, every fold now individually above 0.6 (vs. swinging
0.36–0.77 before), and the recall=0 folds are gone. That's not "AUC went
up" noise — it's the difference between "sometimes finds nothing" and "a
real, if imperfect, discriminative signal." Precision improved too (0.05 →
0.41 mean).

**What's still weak, stated plainly**: recall stays low (0.11 mean, and
fold 4 is 0.02) — the model is conservative and misses most actual
drawdown events even though what it does flag is reasonably precise. This
is a real limitation, not a rounding error, and it's why
`ml_drawdown_probability` is presented as a secondary signal alongside the
percentile composite score (validated separately, see "Score Validation"
above) rather than a standalone prediction. If recall specifically needs
to improve, the next lever is almost certainly the fixed threshold
(`-10%`/20-day drawdown) and class-imbalance handling, not more data —
this run already used a fairly large, diverse universe.

## Score Validation

The composite score (`risk_categories.composite_score`, `risk_score` in the
API response) is explainable by construction — every category and metric
is a named, inspectable percentile — but "explainable" and "predictive"
are different claims, and until this section the second one had never been
tested. `scripts/validate_score.py` (`make validate`) runs two standard
checks against real market data: **36 tickers, 5 years, 37,869 (ticker,
date) observations**, cross-sector (tech, financials, healthcare, energy,
industrials, consumer, utilities, materials, real estate, plus a few
high-volatility names for score-range coverage).

**No-lookahead by construction**: every historical day is scored via
`composite_score(df.iloc[:i+1])` — the exact same function production
uses, called on data truncated at that day, never anything after it.
Verified directly in `tests/test_risk_categories.py::
test_composite_score_has_no_lookahead`, which recomputes features from a
price series that never had the later rows to begin with and checks the
score matches slicing a fully-computed history afterward. That test caught
a real, if narrow, leak during development: `DataPreprocessor`'s outlier
filter uses whole-series mean/std, which is correct for how it's actually
called in production (a fresh fetch always ends "today") but leaks future
statistics into a historical day's outlier classification when a
precomputed multi-year frame gets sliced for backtesting instead —
`validate_score.py` uses its own expanding-window variant of the same
filter to avoid this.

**1. Quintile backtest** — bucket every observation by that day's score,
check whether subsequent 20-trading-day outcomes are monotonically worse
for higher-scored quintiles:

| Quintile | n | mean score | mean fwd 20d max drawdown | mean fwd realized vol |
|---|---|---|---|---|
| Q1 | 7,440 | 24.1 | -5.02% | 27.3% |
| Q2 | 7,454 | 36.0 | -5.10% | 29.0% |
| Q3 | 7,474 | 45.7 | -5.22% | 30.1% |
| Q4 | 7,401 | 56.1 | -5.64% | 33.0% |
| Q5 | 7,380 | 71.6 | -5.80% | 36.4% |

Both monotonic: drawdown gets worse and realized volatility rises cleanly
from Q1 to Q5. At this scale, the composite score does what a risk score
is supposed to do — higher score, worse subsequent outcomes, in order.

**2. Kupiec POF test on `var_95_21d`** — it claims "5% of days breach this
line"; count actual breaches and run the likelihood-ratio test on whether
the observed rate is statistically consistent with 5%:

| n | breaches | breach rate | LR statistic | p-value | reject H₀ (5%) |
|---|---|---|---|---|---|
| 37,833 | 3,498 | 9.25% | 1160.9 | ~0 | **Yes** |

This is the honest negative result: **`var_95_21d` under-states risk by
roughly 2x** — actual breaches happen at ~9.25%, not the claimed 5%, and
the p-value leaves no ambiguity about whether that's noise. The rolling
21-day empirical quantile is doing what it's defined to do (a historical
quantile, not a distributional forecast); it just isn't a calibrated VaR
estimate at the 95% level, and this README previously had no way of
knowing that. Not fixed as part of this validation pass — this is a
measurement, not a patch — but it's real ammunition for [A3]'s weight/
threshold-calibration review, and any UI copy that implies "5% chance of
breaching this line" should be corrected or caveated until it's addressed.

### Are the five categories actually independent? (`make analyze-categories` / `scripts/analyze_categories.py`)

`CATEGORY_WEIGHTS` (25/25/20/15/15) implies five distinct risk dimensions
being blended. Volatility, VaR, CVaR, and drawdown are all different
lenses on the same underlying price-move-size, so it's a fair question
whether the composite is really counting one factor five times with
different labels. Tested directly: category scores for 14 cross-sector
tickers × 2 years (6,173 observations with all five categories present),
correlation matrix + PCA:

| | volatility | tail | drawdown | sensitivity | liquidity |
|---|---|---|---|---|---|
| **volatility** | 1.000 | 0.672 | 0.503 | 0.238 | 0.535 |
| **tail** | 0.672 | 1.000 | 0.460 | 0.177 | 0.406 |
| **drawdown** | 0.503 | 0.460 | 1.000 | 0.046 | 0.383 |
| **sensitivity** | 0.238 | 0.177 | 0.046 | 1.000 | 0.152 |
| **liquidity** | 0.535 | 0.406 | 0.383 | 0.152 | 1.000 |

No pair exceeds 0.8 — the highest is volatility↔tail at 0.672, a moderate
relationship (unsurprising: both are downstream of how large daily price
moves are), not the near-duplication that would make the weighting
cosmetic. PCA needs **4 of 5 components to reach 90% of variance**
(51.1% / 70.5% / 83.0% / 94.0% / 100.0% cumulative) — the opposite of "two
factors doing all the work." `sensitivity` (beta) in particular is the
most distinct category (correlations of 0.046–0.238 with everything else),
which tracks: market-beta co-movement is a genuinely different question
from a stock's own return-distribution shape.

**Honest conclusion**: this didn't turn up the collinearity problem this
section set out to check for. The five categories carry meaningfully
separate information at this sample size, so the weighting isn't
double-counting one signal under five names — though `volatility`/`tail`
sharing 0.672 correlation, and both drawing partly on `drawdown` (0.50 and
0.46), means the 25/25/20 split across those three isn't fully
independent either. Worth re-running at larger scale (this used 2 years;
`validate_score.py`'s 36-ticker/5-year universe would sharpen the
estimate) before treating the exact weight percentages as load-bearing.

## Historical-Scenario Stress Testing

`scoring/stress_test.py` answers "if 2008/2020/2022 conditions recurred, where would this stock's risk score land?" — scoped deliberately to `risk_categories.py`'s percentile composite only, **not** the XGBoost leg. XGBoost's momentum features (RSI, Bollinger %B, distance-from-moving-average) have no defensible "shock" mapping — there's no established rule for "VIX→80 means RSI→X" — and inventing one would undermine the credibility a stress test is supposed to add.

Three built-in scenarios carry real, approximate historical magnitudes (S&P 500 peak-to-trough drawdown, a realized/implied-vol multiplier) sourced from public market history:

| Scenario | Market drawdown | Vol multiplier |
|---|---|---|
| `2008_financial_crisis` | −50% | 3.5× |
| `2020_covid_crash` | −34% | 4.0× |
| `2022_rate_hike_selloff` | −25% | 1.8× |

Each metric is shocked with an actual rationale, not a guess: volatility/VaR/CVaR/kurtosis scale multiplicatively with the vol multiplier (they move roughly linearly with the vol regime); drawdown gets a **CAPM-style beta-scaled shock** (`beta × market_drawdown` — a low-beta utility and a high-beta growth stock don't fall the same amount under the same market move); liquidity metrics scale by a liquidity multiplier; **beta itself is left unchanged** (it measures sensitivity — a scenario doesn't shock the thing that determines its own propagation). Shocked values are ranked against the stock's own real historical distribution using the *same* percentile machinery the live score uses (`risk_categories.composite_score(df, latest=shocked_row)`), not a separately fit model.

```python
from stock_risk.scoring.stress_test import run_stress_test

result = run_stress_test(df, beta=1.8)
result["scenarios"]["2020_covid_crash"]["narrative"]
# "If 2020 COVID-19 Crash conditions recurred, this stock's risk score would move from 67.1 to 92.9 (+25.8)."
```

Baseline and stressed scores within one scenario always use the *same* category weights (that scenario's regime-implied weights), so the reported `delta` reflects only the shock — comparing against a differently-weighted live score would silently mix in a regime-reweighting effect. This also makes `stressed_score >= baseline_score` a mathematical guarantee per scenario, not an empirical tendency. Known limitation: once a shocked value already exceeds the stock's *entire* historical range, its percentile saturates near 100 regardless of how much further it's pushed — so a more severe scenario (2008) is not guaranteed to score strictly higher than a milder one (2022) for the same stock; both can saturate at the same ceiling. This is an inherent property of percentile-based scoring, not a bug — the underlying shocked values themselves remain correctly ordered by severity.

## News / Event Risk Layer (schema ready, LLM call mocked)

`data/fetcher.py::fetch_news` pulls real recent headlines per ticker via yfinance's built-in news (no extra API key). Each headline is run through `llm/news_risk.py::extract_news_risk`, which classifies it into a fixed taxonomy (`event_type`, `risk_category`, `sentiment`, `severity` 0–5, `time_horizon`, `confidence`, `evidence`) using Claude's structured-outputs contract (`output_config.format` + a JSON schema) — the LLM never computes a risk score itself, only extracts structured fields from a single headline.

**The actual Claude API call is not wired in yet** — `extract_news_risk()` returns a clearly-labeled stub (`"source": "mock"`, `severity: 0`) so the fetch → extract → aggregate pipeline runs end-to-end without spending API credits. The `news_risk.llm_configured` field in the API response is `false` until this is activated. To activate: `pip install anthropic`, set `ANTHROPIC_API_KEY`, and pass `llm.news_risk.call_claude_news_extractor` as the `call_llm` argument wherever `extract_news_risk()` is called in `scoring/scorer.py`.

Model: **Claude Haiku 4.5**, not the usual Opus default — this is a high-volume, low-stakes classification task with output already constrained by the schema, so Opus's extra reasoning isn't load-bearing and Haiku is ~5x cheaper per token. Determinism comes from the fixed JSON schema, not a `temperature` parameter (current Claude models don't accept one).

### Options-implied signals ([G4]) — the only forward-looking family

Everything else in this system is derived from historical prices; option
prices are the one input that encodes what the market is paying *today* for
protection against *tomorrow*. The `options_implied` response block carries:

- **put_skew** — OTM-put IV (strike ≈ 95% of spot; yfinance has no deltas, so
  moneyness is the standard stand-in) minus ATM IV. Steepens when crash
  insurance gets bid up; stock-level predictive evidence: Xing–Zhang–Zhao
  (2010, JFQA). The SKEW-index-level story is mixed and deliberately not used.
- **iv_hv_ratio** — ATM IV over realized `vol_21d` (both annualized): the fear
  premium; >1 means the market expects more turbulence than recently realized.
- **vix_term_structure** — VIX/VIX3M ratio + backwardation flag: near-term
  fear above 3-month fear is the practitioner-standard market-level risk-off
  switch, and the ONE options signal that is backtestable today
  (`scripts/validate_vix_structure.py`; both legs have full daily history).

All three ship at fusion weight 0 (unvalidated — the [G1] guard enforces
this): yfinance provides no historical IV series, so put_skew/iv_hv cannot be
walk-forward validated yet. `scripts/collect_iv_snapshots.py` appends a daily
{date, ticker, atm_iv, put_skew} JSONL snapshot to start building that
history — **stock-level IV rank (the same percentile machinery the composite
already uses, fed a forward-looking series) unlocks after ~252 trading days
of collection.** Tickers without options degrade gracefully: every field
null, scoring unaffected.

### Free alt-data (analyst ratings, insider transactions, VIX regime)

No paid data vendor required — all via yfinance:

- `fetch_analyst_activity` / `fetch_insider_activity` — recent analyst downgrade/upgrade counts and insider sale/purchase counts, surfaced as `alt_data` in the API response. Informational only for now (not folded into `risk_score`'s calibrated weights).
- `fetch_vix` + `risk_categories.regime_adjusted_weights` — a rule-based (not HMM) regime switch: VIX ≥ 30 ("panic") shifts weight from day-to-day volatility toward tail risk (25/25/20/15/15 → 20/40/15/10/15); VIX ≥ 20 ("elevated") shifts partway there; below 20 ("calm") uses the base weights. Surfaced as `market_regime` in the API response.

## FastAPI Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/score/{ticker}` | Real-time risk score for a ticker |
| GET | `/score/{ticker}/history` | Historical risk scores (JSONL log) |
| GET | `/health` | Health check |
| GET | `/metrics` | Prometheus-compatible metrics |
| POST | `/api/auth/register` | Create an account, returns a JWT |
| POST | `/api/auth/login` | Returns a JWT for an existing account |
| GET | `/api/auth/me` | Current user (requires `Authorization: Bearer <token>`) |
| GET | `/api/watchlist` | Current user's saved tickers |
| POST | `/api/watchlist` | Save a ticker (`{ticker, market, notes?}`) |
| DELETE | `/api/watchlist/{item_id}` | Remove a saved ticker |

### Example Response

```json
{
  "ticker": "TSLA",
  "timestamp": "2026-06-11T10:30:00Z",
  "risk_score": 72.4,
  "risk_label": "HIGH",
  "risk_note": "Score reflects this stock's risk relative to its own historical distribution ...",
  "risk_breakdown": {
    "volatility": {"score": 81.2, "weight": 0.25, "metrics": {"vol_21d": 88.4, "vol_63d": 79.1, "downside_dev_63d": 76.0}},
    "tail": {"score": 74.5, "weight": 0.25, "metrics": {"cvar_95_21d": 80.2, "var_95_21d": 71.0, "skew_63d": 65.8, "kurt_63d": 79.3}},
    "drawdown": {"score": 69.8, "weight": 0.20, "metrics": {"max_drawdown_63d": 75.1, "drawdown": 63.4, "drawdown_duration": 60.2}},
    "sensitivity": {"score": 88.0, "weight": 0.15, "metrics": {"beta_63d": 88.0}},
    "liquidity": {"score": 45.3, "weight": 0.15, "metrics": {"amihud_illiq_21d": 40.1, "volume_vol_21d": 51.2, "dollar_volume_21d": 55.0}}
  },
  "market_regime": {"vix": 22.4, "regime": "elevated"},
  "ml_drawdown_probability": 66.1,
  "ml_drawdown_explanation": {
    "base_probability": 0.08,
    "predicted_probability": 0.601,
    "calibrated_probability": 0.661,
    "top_features": [
      {"feature": "volatility__vol_21d", "raw_value": 0.62, "shap_contribution": 1.42},
      {"feature": "volatility__max_drawdown_63d", "raw_value": -0.24, "shap_contribution": 0.87},
      {"feature": "momentum__rsi_14", "raw_value": 71.2, "shap_contribution": 0.31}
    ],
    "note": "shap_contribution is in log-odds units ... predicted_probability is the raw (pre-calibration) model's output that this SHAP breakdown explains — calibrated_probability is what model.predict() actually serves ..."
  },
  "garch_volatility_forecast": {"vol_1d": 0.031, "vol_30d": 0.51},
  "news_risk": {
    "llm_configured": false,
    "max_severity": 0,
    "negative_count": 0,
    "articles": [
      {"event_type": "none", "risk_category": "none", "sentiment": "neutral", "severity": 0,
       "time_horizon": "unknown", "confidence": 0.0, "evidence": [], "title": "...", "source": "mock"}
    ]
  },
  "alt_data": {
    "analyst_activity": {"downgrade_count": 2, "upgrade_count": 0},
    "insider_activity": {"sale_count": 3, "purchase_count": 0, "net_transaction_count": -3}
  },
  "stress_test": {
    "live_score": 72.4,
    "scenarios": {
      "2008_financial_crisis": {
        "label": "2008 Global Financial Crisis", "baseline_score": 67.1, "stressed_score": 92.9,
        "delta": 25.8, "narrative": "If 2008 Global Financial Crisis conditions recurred, this stock's risk score would move from 67.1 to 92.9 (+25.8).",
        "stressed_categories": { "...": "..." }
      },
      "2020_covid_crash": { "...": "..." },
      "2022_rate_hike_selloff": { "...": "..." }
    }
  },
  "volatility_30d": 0.48,
  "var_95": -0.034,
  "cvar_95": -0.052,
  "beta": 1.87,
  "max_drawdown_90d": -0.21,
  "implied_volatility": 0.62,
  "indicators": {
    "rsi_14": 68.2,
    "bb_pct": 0.82,
    "atr_14": 9.41
  },
  "fundamentals": {
    "sector": "Consumer Cyclical",
    "market_cap": 712000000000,
    "trailing_pe": 52.1
  }
}
```

## Web Frontend (React + Tailwind)

`ui/web/` is a Vite + React 18 + Tailwind CSS single-page app (multi-ticker search, side-by-side risk cards, SVG gauge, Chart.js price/risk charts) served by FastAPI at `/` once built — see step 6 in Quick Start. Source lives in `ui/web/src/`; `npm run build` outputs to `ui/web/dist/`, which `api/app.py` mounts at `/assets` and serves `index.html` from at `/`. If `dist/` hasn't been built yet, `/` returns a 503 with instructions rather than a confusing 404.

- `src/App.jsx` — top-level state (ticker list, selected timeframe, market)
- `src/components/StockCard.jsx` — per-ticker fetch + render (score, gauge, direction signal, metric tiles, charts, favorite star)
- `src/api.js` — thin fetch wrappers over `/api/search`, `/api/score/{ticker}`, `/api/score/{ticker}/timeseries`, `/api/auth/*`, `/api/watchlist`
- `src/i18n/` — English/Simplified Chinese locale files + a lightweight Context-based translator (no external i18n library, given the app's size)
- `src/auth/` — `AuthContext` (JWT stored in `localStorage`, session restored on load via `/api/auth/me`), `AuthModal` (separate Sign in / Sign up entry points, same form), `WatchlistPanel`, `ProfilePanel` (avatar, email, member-since, watchlist count, replay-tutorial, sign out)
- `src/onboarding/` — `OnboardingContext` (auto-opens once per browser via a `localStorage` flag) + `OnboardingTour`, a skippable multi-step walkthrough explaining what each part of a risk card is actually useful for when deciding what to do about a position, not just what the number is
- `tailwind.config.js` — theme colors matched to the original dark palette (risk label colors, accent gradient)

### Accounts & watchlist

Auth is self-hosted (FastAPI + SQLite + JWT), not a third-party service — no external account is needed to run the app. Passwords are hashed with bcrypt; tokens are bearer JWTs valid for 7 days. Set `JWT_SECRET_KEY` in `.env` before deploying with real users — the app runs fine without it for local dev but logs a startup warning, since the fallback is a published placeholder value. The avatar shown when signed in is a deterministic initials circle (first letter of the email, hashed to one of the brand hues) — there's no image upload, deliberately, since the app has no durable file storage (same constraint as the DB, next paragraph).

**Known limitation: accounts don't survive a redeploy on most free-tier hosts.** SQLite (`db_path`, default `data/app.db`) lives on the app's own local filesystem, which most free PaaS tiers (including Render's) don't persist across restarts/redeploys — every registered account is silently gone the next time the service restarts. `settings.database_url` (env var `DATABASE_URL`) overrides the SQLite path with any SQLAlchemy URL, so pointing it at a durable external database (a hosted Postgres, etc. — install the matching driver, e.g. `psycopg2-binary`) fixes this with no code change; unset, behavior is unchanged. Which provider to use is a real cost/account decision, not something this app picks for you.

**Admin account & moderation.** A single site-owner admin account gates the usage-analytics dashboard (page views, unique users, hour-of-day histogram, top pages), the user list with ban/unban, and moderation of any community post. Because the SQLite DB is wiped on every redeploy (above), the admin account isn't seeded once — it's re-created/promoted on **every** app boot from two environment variables, `ADMIN_EMAIL` and `ADMIN_PASSWORD` (see `.env.example`). Set both in your local `.env` to test admin features locally, **and** in your host's dashboard (e.g. Render's Environment tab) for production — the app only reads them, it can't set them for you, so an admin account only exists once you've configured them there yourself. If the email already belongs to a normal account, that account is promoted to admin without changing its password; if unset, no admin exists and the admin UI stays hidden. A ban blocks login and every write action (posting, voting) on the next request but leaves public read access intact; it does not delete the banned user's existing posts (that's a separate, explicit admin action). There is deliberately no defense against a banned user simply registering a new email — this is a lightweight moderation tool for a small community, not an adversarial-hardened system.

Verified end-to-end with a headless-Chromium (Playwright) smoke test: multi-card grid, live search with debounce, Enter-to-add, timeframe switching, zero console errors, real yfinance data rendering in both the SVG gauge and Chart.js line charts.

## Model Governance ([R4]) & Lineage ([R5])

The project already had the *ingredients* of model governance — walk-forward
validation, isotonic calibration, drift monitoring, a rule that unvalidated
signals ship at zero weight. What it lacked was anywhere those were recorded.
"Is this model approved?" was answered by reading a README section; "which
version is deployed?" by a file's mtime; "why was the old one retired?" by
nothing at all.

### Lifecycle

```
development ──> validated ──> approved ──> shadow ──> active
                                              │         │
                                              │         ▼
                                              └──── degraded ──> (re-validate)
                     everything ─────────────────────────────> retired
```

Transitions are declared as data, so an illegal one raises instead of being a
silently-accepted string assignment. Two absences are deliberate:
`development -> active` (skipping validation is what this prevents) and
`degraded -> active` (a model that breached its bar re-validates; it doesn't
get waved through because the metric recovered on its own).

```bash
make registry                 # list models and status
make registry-compare v=2.0.0 # champion vs challenger
python scripts/registry.py promote downside_risk 2.0.0 --reason "..."
python scripts/registry.py rollback downside_risk
```

| Control | Behaviour |
|---|---|
| Validation gate | `validate()` **raises** below the recorded thresholds — a gate that can be ignored is documentation, not a control |
| Missing metrics | Fail, not pass. Absent evidence is how ungated models reach production |
| One champion | `promote_to_active` demotes the incumbent; two ACTIVE versions means "which model produced this score?" has no answer |
| Immutable records | Re-registering a version raises rather than overwriting the evidence |
| Automatic demotion | `check_for_breach` demotes a champion whose live drift/AUC crosses its own bar |
| Rollback | `previous_champion()` derives the target from history, not a stored pointer |
| Retirement | Requires a reason. "We turned it off at some point" is not an audit trail |

Promotion is deliberately **not** automated even when a challenger wins.
Automating it removes the only step where a human asks whether the improvement
is real.

### Reproducibility manifests ([R5])

Every training run writes a manifest recording the git commit (and whether the
tree was dirty — a model trained from uncommitted code is *not* reproducible
from its hash, and the manifest says so rather than implying otherwise), the
feature schema version, the universe, which tickers were excluded and why, the
label definition, hyperparameters, a data-quality report, and a **dataset
hash**.

The dataset hash is the load-bearing piece. `yfinance` returns *today's* view of
history — prices get restated for splits and dividends, delisted tickers stop
resolving, vendors backfill gaps — so retraining "the same" window a month later
can legitimately produce a different model. Hashing the actual feature values
(not a filename, not a row count, both of which stay identical while the numbers
move) makes `manifest.differences_from(other)` a triage tool: dataset hash
differs → the data moved; commit differs → the code moved; neither differs but
metrics did → the run is nondeterministic, which is itself the finding.

Floats are rounded to 10dp before hashing, so cross-platform BLAS noise doesn't
flag drift that isn't there.

## Tail-Risk Validation Beyond Coverage ([R6])

`make validate` already ran a Kupiec POF test and found `var_95_21d` breaching
9.25% against its 5% claim. That is the *unconditional* half of VaR validation,
and a VaR model can pass it while still being unusable.

`make validate-tail` (`scripts/validate_tail.py`, offline from the committed
snapshots so the numbers reproduce) adds three tests Kupiec structurally cannot
perform. Results across 9 tickers, 4,613 ticker-days:

| Test | Result | Reading |
|---|---|---|
| Kupiec POF | LR 144.85, p≈0, **reject** | 9.30% breach rate vs 5% claimed — independently reproduces the earlier 36-ticker finding on different data |
| Christoffersen independence | LR 4.90, p=0.027, **reject** | Breaches **cluster**: 12.4% chance of a breach the day after a breach vs 9.0% otherwise (ratio 1.38) |
| Conditional coverage | LR 149.76, p≈0, **reject** | Fails jointly, as expected once both components fail |
| Acerbi–Szekely Z2 (ES) | −1.78, p≈0, **reject** | Breaches averaged −2.79% against a predicted ES of −2.26% — ES **understates** tail severity by ~23% |

The independence result is the one Kupiec was blind to. Counting breaches
cannot see *when* they arrive, and clustered breaches are exactly when losses
compound. Longest observed run: 4 consecutive days; 22.6% of all breaches
occurred inside multi-day runs; worst month February 2025 with 32.

Two honest caveats. Breaches cluster partly because volatility clusters and a
21-day rolling window adapts slowly — this measures the deployed estimator, not
a claim that no VaR model could do better. And Z2's p-value is bootstrapped
over the breach set (seeded, so it's reproducible); the first implementation
resampled the full return series against the same ES path, which is circular —
the null inherited the very error under test and reported p≈0.5 for an ES
understating the tail by 2x.

## Champion–Challenger ([R8])

```bash
make challenger    # or: python scripts/challenger.py --register
```

Runs logistic regression, random forest, and a **monotonically-constrained**
XGBoost through the *identical* walk-forward path as the champion — same folds,
same embargo gap, same calibration slice. Comparing a single-split baseline
against a walk-forward champion would flatter whichever got the easier
evaluation.

Reported alongside mean AUC: fold-to-fold **stability** (`auc_std`, `auc_min`,
`folds_below_coin_flip`). Two models with identical mean AUC are not equally
good if one swings 0.36–0.77 across folds and the other holds 0.66–0.69 — this
project has seen exactly that pattern, and the mean alone hid it.

The monotonic challenger is the interesting one: constraining the model so
higher volatility can only *raise* estimated risk is what makes it defensible to
a reviewer, and the question worth answering is how much discriminative power
that guarantee costs. If the answer is "almost none", the constrained model is
the better production choice on every axis that isn't AUC.

## Portfolio-Level Risk ([R7])

Single-name scores don't add up: two stocks each scoring 70 make a portfolio
riskier than either alone if they're the same sector, and materially safer if
they're uncorrelated. A weighted average of scores says the same thing in both
cases, so `portfolio/aggregate.py` computes from the underlying return series
instead.

| Output | What it answers |
|---|---|
| Component VaR | Where risk actually comes from. Euler allocation, so components sum **exactly** to portfolio VaR — a decomposition whose parts don't sum to the whole isn't an attribution |
| Marginal VaR | What one more unit of a position adds |
| Diversification ratio | How much of the weighted-average standalone risk is actually avoided |
| Effective N / HHI | "Effectively 2.3 positions" lands where "HHI 0.43" doesn't |
| Sector exposure | Concentration the position count hides |
| Stress attribution | Beta-scaled shock propagation, per position — a flat shock reports a loss no plausible scenario produces |

The decomposition exists to surface that **the largest position is frequently
not the largest risk contributor** — a 20% weight in a high-volatility name can
carry >80% of portfolio risk, which is pinned by a test.

Concentration alerts are phrased as observations ("X accounts for N% of total
portfolio risk"), never instructions — the same advice boundary the rest of the
product holds, enforced by a test that fails on words like "reduce" or "sell".
The position threshold is relative to fair share (1/N), not a flat percentage:
a flat 25% bar fired on every equally-weighted four-position book, where each
holding contributes ~25% *by construction*, and an alert that goes off on a
textbook-diversified portfolio trains people to ignore alerts.

## API Hardening ([R2])

The scoring API is public, unauthenticated, and on a cache miss makes a live
upstream call that takes ~2.7s. Before [R2] a single client in a loop could
saturate the worker pool *and* burn the upstream quota — and since Yahoo
throttles by egress IP, one abusive caller gets the whole deployment throttled
for everyone.

| Control | Where | What it stops |
|---|---|---|
| Token-bucket rate limiting, per-endpoint cost | `security/ratelimit.py` | Request flooding; a cold score costs 5 tokens, `/health` costs 0 |
| Per-account login lockout | `FailedLoginTracker` | Credential stuffing that rotates IPs against one account |
| Single-flight cache | `security/cache.py` | Cache stampede — 20 concurrent misses become 1 upstream call |
| Stale-while-revalidate | same | The 2.7s latency cliff at every cache expiry |
| Stale-on-error | same | Upstream outage becoming total outage |
| Strict CORS allowlist | `api/app.py` | Any site reading this API on a signed-in user's behalf |
| CSP + security headers | `security/headers.py` | XSS, clickjacking, MIME sniffing, referrer leakage |
| Audit log | `security/audit.py` | "Who banned this account, and when?" being unanswerable |
| 12h JWT + silent refresh | `auth/security.py` | A leaked token staying valid for a week |

Three choices worth explaining, since each looks like it could have been done
more simply:

**Token bucket, not a fixed window.** A fixed window lets a client spend its
whole allowance in the last instant of one window and again in the first
instant of the next — a 2x burst at the boundary. A bucket refills
continuously, so burst is an explicit bounded parameter rather than an artifact
of where the window edges fall.

**Rate limiting *and* per-account lockout.** They cover different attacks. The
limiter keys on IP (or user), so an attacker rotating IPs against one account
stays under it indefinitely; the lockout keys on email, so a spray across many
accounts from one IP stays under *it*. Either alone leaves an obvious hole. The
lockout is time-limited, not permanent — a permanent lock triggered by failed
passwords is a denial-of-service anyone can aim at any known email address.

**CORS was `allow_origins=["*"]` next to JWT auth.** That let any website a
signed-in user visited read every response from this API, including the full
scoring output. Now an explicit allowlist via `CORS_ALLOWED_ORIGINS`, with
`allow_credentials=False` (tokens travel in a header, not cookies).

`X-Forwarded-For` is trusted only when `TRUST_PROXY_HEADERS=1` (true behind
Render, false for a directly-exposed server). Trusting it unconditionally would
make IP rate limiting useless — the header is attacker-controlled, so anyone
could send a fresh value per request and get a fresh bucket every time.

Rate limiting is **per-process**, not shared across replicas: with N workers the
effective limit is N x the configured rate. A shared Redis counter would be
exact, but putting a network dependency in the request hot path — one that
fails either open or closed, both bad — is a worse trade at this scale.

## Frontend Testing & CI ([R3])

6,600 lines of JSX previously had no automated coverage at all; the only gate
was `ui_shot.sh`'s screenshots, graded by eye. CI didn't run `npm` anything, so
a syntax error could reach `main`.

```bash
make web-ci      # lint + test + build, exactly what CI runs
make web-test    # vitest run
```

44 tests across 6 files (Vitest + React Testing Library + jsdom), plus ESLint
(flat config) and Prettier, all gated in CI. The tests target behaviour a user
can observe rather than implementation details:

| Test area | Why it's the one that matters |
|---|---|
| `windowStats` null handling | Regression: null risk fields rendered as a confident `0–0` |
| en/zh key-tree parity | Catches a translator adding a key to one locale only |
| `t()` interpolation + fallback | A missing key must fall back to English, not render `window.stat.high` |
| Floored two-sided tiles | A below-neutral liquidity tile must never render green (see [R4]) |
| StockCard states | Loading, error, populated, and *period change refetches timeseries but not score* |
| Charts with missing data | See below — this found a real bug |

**Two real bugs found by writing these tests.** `PriceChart`, `RiskChart` and
`AdminAnalyticsChart` all called `.map()` on their series prop unguarded. They
render inside the card with no error boundary, so an absent series would blank
the entire dashboard — including the still-valid score hero above it. Fixed
with `= []` defaults. Second: a stale
`eslint-disable-next-line react-hooks/exhaustive-deps` in `CommunityPanel.jsx`
whose dep array was actually complete, removed so it can't mask a future real
warning.

## Schema Migrations & Backup/Restore ([R1])

The database holds the only data in this system that cannot be recomputed:
accounts, watchlists, community posts, votes, moderation reports and the
score-snapshot history. Everything else — prices, features, model artefacts —
can be refetched or retrained.

Until [R1] that data was managed by `SQLModel.metadata.create_all()` plus a
hand-rolled `db.ensure_columns()` helper that bolted on missing columns with
raw `ALTER TABLE ADD COLUMN` at boot. That could add a table and append a
column, and nothing else: no version record, no downgrade path, and no way to
express a type change, a rename, a backfill or a dropped column. Any of those
meant hand-written SQL against a live database with real accounts in it.

### Versioned migrations (Alembic)

```bash
make migration m="add user timezone"   # autogenerate a revision from the models
make migrate-dry-run                   # rehearse on a copy — touches nothing
make migrate                           # the guarded path (see below)
make migrate-sql                       # print the SQL, execute nothing
```

`make migrate` (`scripts/migrate.py`) is not a wrapper around
`alembic upgrade head` — it is that command plus the three things that make it
recoverable:

1. **Staging rehearsal.** The migration runs first against a throwaway copy of
   the real database. Data-dependent failures — a `NOT NULL` added to a column
   containing NULLs, a unique constraint added to data that already violates
   it — fail *there*, on the copy, while production is untouched. Testing a
   migration only against an empty schema cannot catch any of them.
2. **Verified pre-migration backup**, taken before the real upgrade and checked
   with `PRAGMA integrity_check` before being trusted.
3. **Automatic restore on failure.** If the real upgrade fails anyway, the
   backup is restored before the process exits non-zero, so the database is
   left at its pre-migration state rather than half-migrated.

Exit codes: `0` migrated (or already at head), `1` failed and rolled back,
`2` failed *and* the restore failed — manual recovery, backup path printed.

**Adopting the already-deployed database.** The live deployment predates
Alembic: it has all seven tables and no version record. Replaying the baseline
against it would fail on "table already exists", so `db.run_migrations()`
*stamps* it at the baseline instead. That is only safe if a `create_all()`
database and a migrated one really are identical, which
`tests/test_migrations.py::test_stamped_legacy_schema_matches_freshly_migrated_schema`
asserts by building one of each and diffing them, rather than assuming it.

### Backup and restore

```bash
make backup           # verified backup + prune to backup_retention (default 10)
make backup-list
make restore-drill    # prove the newest backup actually restores
python scripts/backup_db.py restore <path>
```

SQLite backups use `sqlite3`'s **online backup API**, not a file copy — a copy
taken mid-write, or with un-checkpointed WAL content, can land a torn database
that only fails later at read time. Postgres uses `pg_dump -Fc`. Restores move
the existing database aside to `<name>.pre-restore-<timestamp>` first, so
restoring the *wrong* backup is itself recoverable.

`make restore-drill` is the one worth running on a schedule, and
`.github/workflows/backup.yml` does exactly that daily. A backup that has never
been restored is an assumption, not a recovery plan: the drill restores the
newest backup into a scratch database, checks its tables, row counts and
Alembic revision, and throws it away. It found a real bug the first time it ran
— `latest_backup()` sorted backups by filename, and since names are
`{label}_{timestamp}`, the *label* dominated the ordering: `manual_…T193206Z`
sorted before `pre-migration_…T193157Z` despite being 49 seconds newer. The
drill restored a stale backup and correctly reported it unusable. Pinned by
`test_latest_backup_orders_by_time_not_label_across_mixed_labels`.

### What's covered by tests

`tests/test_migrations.py` (19 tests) covers what `ensure_columns` had no way
to express:

| Guarantee | Test |
|---|---|
| Models and migration head cannot drift | `test_models_match_migration_head_with_no_pending_changes` |
| Every migration is reversible | `test_downgrade_upgrade_roundtrip_is_reversible` |
| Rows survive an upgrade | `test_migration_preserves_rows_when_upgrading_in_place` |
| Pre-Alembic databases adopt correctly | `test_preexisting_unversioned_database_is_stamped_not_recreated` |
| Stamping is schema-equivalent | `test_stamped_legacy_schema_matches_freshly_migrated_schema` |
| An interrupted downgrade still adopts | `test_populated_database_with_empty_alembic_version_is_stamped` |
| Backups restore lost data | `test_restore_recovers_data_deleted_after_the_backup` |
| A corrupt backup is detected | `test_corrupt_backup_fails_verification` |

The drift guard is the highest-value one: edit a SQLModel table without
generating a migration and it fails immediately, naming the drift — instead of
the mismatch surfacing in production as an `OperationalError` on a column that
exists in Python but not in the database. CI additionally runs the real
`alembic` CLI through upgrade → downgrade → upgrade, plus a backup and restore
drill, on every push.

## Deployment

### Render ([F2]) — live at https://explainable-stock-risk-scoring.onrender.com

The API and the built React SPA are one process — `app.py` mounts `ui/web/dist/assets`
as static files and serves `dist/index.html` at `/`, so the whole app is a single
Render Web Service, no separate frontend host needed.

- **Build command:** `pip install -e . && cd ui/web && npm ci && npm run build`
- **Start command:** `uvicorn src.stock_risk.api.app:app --host 0.0.0.0 --port $PORT`
- **Health check path:** `/health`
- **Environment variable:** `ENABLE_ML=1` (shipped as `0`, then flipped after a live
  memory experiment — full story below)

**The `ENABLE_ML` toggle, and why it ended up ON.** Render's free tier is 512MB RAM /
0.15 CPU. Importing `RiskScorer` used to eagerly pull in `xgboost` and, transitively
through `explain_prediction`, `shap` — multi-hundred-MB libraries loaded whether or
not anyone asks for the ML leg. `ENABLE_ML=0` makes
`RiskScorer._try_load_downside_model()` skip the import entirely (not just discard
the result — see `scoring/scorer.py`), so `shap`/`xgboost` never enter `sys.modules`:
```bash
ENABLE_ML=0 python -c "
import sys
from stock_risk.api.app import app
assert 'shap' not in sys.modules and 'xgboost' not in sys.modules
print('lazy OK')
"
```
The deploy shipped with `ENABLE_ML=0` as a precaution based on the issue's *estimated*
memory numbers — then the estimate was tested instead of trusted: flipping to
`ENABLE_ML=1` on the live 512MB instance (xgboost + the model artefact load at
startup) produced a healthy process, `/health` solid, and **zero restarts in Render's
Events log** across the monitored window. The memory cut wasn't needed; the toggle
stays in the codebase as a real knob for smaller tiers, and the deploy keeps the full
pipeline on. Two honest caveats: the shap leg only loads on the first *successful*
scoring request, which the rate limit below kept blocking, so "full request under
load" memory remains unverified; and Render's free tier hides the Metrics usage graph
behind a paywall (the panel shows only the limit — 512MB / 0.15 CPU, not the 0.1 the
original issue assumed), so zero-restarts is the best available proxy, not an RSS
number.

**The real free-tier constraint turned out to be IP reputation, not memory.**
`/api/score/{ticker}` returned `500 {"detail": "Internal scoring error"}` for every
ticker — Render's own logs show the cause:
`yfinance.exceptions.YFRateLimitError: Too Many Requests` at Yahoo's edge. Monitored
with an automated probe every 5 minutes for 4+ hours: **every single probe failed**,
each after the server burned its full ~80s of yfinance-internal retries. Meanwhile,
within the same window, a residential IP recovered from the same rate limit and CI
(GitHub Actions) alternated between green and throttled runs day-to-day. The pattern:
Yahoo throttles *shared datacenter egress IPs* (Render's free tier, cloud CI runners)
aggressively and for extended periods — a residential-IP dev machine barely notices.
Consequences, stated plainly:
- Every free PaaS + yfinance "live data" demo has this failure mode built in; [C3]'s
  cache only helps *after* a first successful fetch per ticker/TTL window.
- The app degrades exactly as designed under it ([C1]/[C3]'s error handling: logged
  `YFRateLimitError`, generic 500, no internals leaked, `/health` and the UI stay up).
- **Mitigation shipped (2026-07-19): snapshot fallback + daily refresh.** Every
  successful `fetch_history` persists the frame under `snapshots/` (tracked in
  git); when the live fetch fails, the fetcher serves the last snapshot with a
  loud staleness warning instead of 500ing, and a weekday GitHub Actions cron
  (`refresh-snapshot.yml`) re-fetches the demo universe after US close and
  commits whatever Yahoo allowed — runners are only intermittently throttled,
  so snapshots converge to fresh over days, and free-tier deploys (which clone
  the repo) ship with recent data baked in. Serving real-time data reliably
  still requires an upstream-source change (paid API with an SLA / clean
  egress) — the snapshot layer makes the demo resilient, not the data live.
- CI handles the same root cause explicitly: `make smoke` exits 75 when Yahoo
  throttles the runner, and CI surfaces that as a loud warning instead of a false
  "commit broken" red (see CLAUDE.md §2).
- **Actual upstream fix shipped (2026-07-20): Twelve Data for US, akshare for
  CN/HK.** The prediction two bullets up ("still requires an upstream-source
  change") is exactly what happened — see "Data Quality & Limitations" above
  for the full per-market breakdown. Set `TWELVE_DATA_KEY` on Render to route
  US equities off yfinance entirely; CN/HK already do by default, no key
  needed. The snapshot layer above stays as the safety net for whatever's
  left on yfinance (options, news, index symbols) and for the free tiers'
  own rate limits.

**Still unmeasured, deliberately not guessed at:** a true cold-start number (the
service was continuously warm during testing; Render's own claim is "50s or more"
after 15 min idle) — measure it by leaving the service idle 15+ minutes and timing
the next request.

### Hugging Face Spaces ([F3]) — attempted, closed by two successive platform paywalls; assets kept

The plan: while Render ran the cut-down config, HF Spaces' roomier free CPU tier
(2 vCPU / 16GB, 48h-inactivity sleep) would host the **full** pipeline with
`ml_drawdown_probability` and the SHAP `top_features` both live. It ended with no
free HF path existing at all — the full-ML goal was ultimately met on Render instead
(see `ENABLE_ML=1` above). The chronicle stays here because "platform constraints
discovered mid-flight, decisions re-made with evidence" *is* the deployment lesson:

1. **Paywall #1 — Docker SDK.** The original design (push the verified root
   `Dockerfile`, reuse the FastAPI+React app as-is) died in the Space-creation UI:
   Docker SDK newly gated behind a "Paid" badge requiring PRO, even on free
   hardware. Cross-checked against community reports ([Docker SDK now marked as
   "Paid"](https://discuss.huggingface.co/t/docker-sdk-now-marked-as-paid-when-creating-a-new-space/177580))
   — a days-old, platform-wide, unannounced change, with the [official Docker Spaces
   docs](https://huggingface.co/docs/hub/en/spaces-sdks-docker) not yet updated at
   check time. Pivoted to a Gradio Space (`ui/gradio_app.py`), which was still free.
2. **The Gradio Space actually shipped, briefly.** Repo pushed (with a real detour:
   HF's pre-receive hook rejects plain-git binaries, and the model artefact
   ultimately went up via the `huggingface_hub` API after git-LFS/Xet transfer
   failures), build succeeded, model loaded, Gradio server started — then the
   platform killed it (`RUNTIME_ERROR`): the Space had been auto-created on
   **ZeroGPU** hardware (the pre-highlighted "free" option), whose supervisor is
   built for `@spaces.GPU`-pattern apps, and HF refused to downgrade the Space to
   plain CPU without — again — PRO.
3. **Paywall #2 — Gradio SDK.** Deleting and recreating the Space on CPU Basic
   revealed the creation form now says it outright: *"Gradio and Docker Spaces
   require a paid plan. Static Spaces stay free for everyone."* At that point HF's
   free tier can no longer run this app in any form, and the Space was deleted.

**Resolution:** the "full ML+SHAP live" goal moved back to Render — the live
`ENABLE_ML=1` experiment (above) showed 512MB holds it fine, which retroactively
makes the two-platform split unnecessary. The HF-specific assets stay in the repo,
verified and ready if the paywall reverts or PRO appears: `ui/gradio_app.py` and the
root `Dockerfile` (both below), plus a note — the HF YAML front-matter (`sdk: gradio`,
`app_file: ui/gradio_app.py`) was removed from this README's head when the Space
died; re-add it before pushing to a future Space.

**The root `Dockerfile` stays in the repo, unused for now.** It's fully built and
verified (see below) for whenever Docker SDK is free again, or if this account gets
PRO — deleting working, verified infrastructure code over a reversible external policy
change would be premature. `docker/Dockerfile` (Render/docker-compose target: port
8000, no model artefact, runs as root) is a different file for a different target;
the root one fixes four real, verified pitfalls specific to HF's Docker constraints:
port `7860` not `8000`, bundling the otherwise-gitignored 509KB model artefact
(`!models/artefacts/downside_risk_xgb.joblib` in `.gitignore`, no LFS needed — and
deliberately not trained at build time, since real yfinance data changes daily and
that would make every image non-reproducible), the `shap`/`llvmlite` build failure
[N1] already pinned `shap==0.49.1` against, and HF's non-root (uid 1000) container
execution needing `/app` chowned before `USER appuser`. **Verified locally**
(Docker Desktop, this repo's actual `Dockerfile`):
```bash
docker build -t stock-risk-hf -f Dockerfile .
docker run --rm stock-risk-hf pip show shap   # Version: 0.49.1
docker run --rm stock-risk-hf whoami          # appuser (not root)
docker run -d --rm -p 7860:7860 stock-risk-hf
curl -s http://localhost:7860/health          # {"status":"ok"}
```
Build succeeds in one pass, model loads at startup with no permission errors,
`/health` returns `200`. `/api/score/TSLA` against the local container hit the *same*
external `YFRateLimitError` documented in the Render section above — the fourth
independent confirmation of that outage in one session (local machine, GitHub Actions
CI, Render, and this local container all hit it), strong evidence it's a broad
Yahoo-side rate limit and not anything specific to this deployment.

**`ui/gradio_app.py`** is a from-scratch Gradio Blocks UI, not a wrapper around the
React frontend (Gradio Spaces run a Python entry point, not an arbitrary Dockerfile,
so the built React SPA can't be reused there). It calls `RiskScorer.score()` directly
— same scoring pipeline as the API, full ML leg on — and renders the risk gauge,
five-category breakdown, historical stress-test table, and the SHAP `top_features`
table. **Verified locally end-to-end with mocked market data** (real yfinance was
rate-limited at the time, same outage as above): a full run produces a real gauge
figure, populated breakdown/stress-test tables, and genuine SHAP contributions, e.g.
`volatility__cvar_95_21d: -1.479`, `volatility__vol_63d: -1.249` — confirming the
rendering pipeline itself is correct independent of the live-data outage. Runnable
locally anytime: `python ui/gradio_app.py` → http://127.0.0.1:7860.

**A flagged risk that later broke for real — now closed.** When this container first
ran, loading the model logged `InconsistentVersionWarning` (artefact pickled with
scikit-learn 1.7.2, fresh installs resolving the then-unbounded `scikit-learn>=1.4`
to 1.9.0). It was deliberately left unfixed at the time — "nothing observed actually
broke" — and documented here as the same *shape* of risk `shap`/`xgboost` got exact
pins for. Within a day it graduated from warning to failure: in CI's fresh
environment, 1.9.0's `SimpleImputer` raised `'SimpleImputer' object has no attribute
'_fill_dtype'` on the 1.7.2 pickle at predict time, the ML producer degraded to
null, and [G1]'s golden test caught the behavioral difference (pre-[G1], this would
have been a silent warning and silently-null ML fields). Fixed with
`scikit-learn>=1.7,<1.8` in `requirements.txt`/`setup.py`, matching the committed
artefact and the existing `requirements.lock` pin (already 1.7.2).

**Final state of the two-platform plan ([F2]+[F3]), summarized honestly:**

| | Plan | Reality |
|---|---|---|
| Render ([F2]) | Cut-down (`ENABLE_ML=0`) forced by 512MB | Full pipeline (`ENABLE_ML=1`) — the memory estimate didn't survive a live test; zero OOM restarts |
| HF Spaces ([F3]) | Full ML+SHAP on the roomier free tier | No free path left (Docker SDK, then Gradio SDK, paywalled mid-project); Space deleted, app + Dockerfile kept |
| Binding constraint | 512MB of RAM | Yahoo throttling shared datacenter egress IPs — blocks live data on *any* free PaaS, regardless of RAM |

The deployment story worth telling is the middle column colliding with the right one:
both platform assumptions (memory pressure, HF's free tier) failed against reality
within a day, and every re-decision above is backed by a live experiment or a
primary-source check rather than the original estimates.

```bash
# Docker (API only)
docker-compose up --build

# Run continuous monitoring loop
python scripts/monitor.py --tickers AAPL MSFT TSLA --interval 3600
# or: make monitor
```

## Risk Score Interpretation

| Score | Label | What it means |
|-------|-------|-------------|
| 0–25 | LOW | Calmer than usual for this stock, relative to its own recent history |
| 26–50 | MODERATE | Within a fairly normal range for this stock |
| 51–75 | HIGH | More turbulent than usual for this stock |
| 76–100 | EXTREME | Near the most turbulent levels seen in this stock's recent history |

### Scores are not comparable across stocks

Every category and metric behind `risk_score` is a percentile **within
that one stock's own historical distribution** (see `risk_categories.py`,
and the `risk_note` field every `/api/score/{ticker}` response carries —
now also rendered on every card in the web UI, not just returned in the
API). A stock that's calm by *its own* standards can outscore a stock
that's turbulent by *its own* standards, if the second one happens to be
sitting near its personal historical median at the moment — the score says
nothing about which one is riskier in absolute terms. Putting two stocks'
cards side by side (the web UI's normal layout) invites exactly the
comparison the score can't support; the fix isn't hiding the layout, it's
making sure the caveat travels with every card instead of living only in a
field nobody was reading.

If cross-stock comparability is ever needed, it requires a materially
different design — e.g. ranking by an *absolute* metric (realized
volatility, VaR in dollar terms) rather than a within-stock percentile — not
a UI tweak on top of the current score.

### Direction Signal — removed

`score_timeseries` used to also return `up_prob`/`down_prob`, a sigmoid
blend of four technical signals (RSI, Bollinger %B, distance from the
20-day EMA, 63-day Sharpe), rendered front-and-center on every card as
"↑ Upside 53% / ↓ Downside 47%" with an "Likely to INCREASE/DECREASE"
verdict. It was never backtested before shipping — a percentage in a
finance UI reads as calibrated confidence whether or not it's earned that,
so this got checked directly: 14 tickers × 2 years, 6,453 (ticker, date)
observations, comparing the signal's prediction against the *next* day's
actual return.

| | n | actual next-day up-rate |
|---|---|---|
| Predicted "up" (up_prob > 0.55) | 2,359 | **48.6%** |
| Predicted "down" (up_prob < 0.45) | 1,854 | **50.9%** |
| Unconditional baseline | 6,453 | 49.9% |

Both numbers are on the wrong side of useless: "predicted up" days closed
up *less* often than the unconditional baseline, and "predicted down" days
closed up *more* often — the signal isn't just noisy, it's mildly
anti-predictive on both branches. That rules out downgrading it to a bare
qualitative arrow (↑/→/↓) as a middle ground — an arrow with no percentage
attached still asserts a direction, and the direction it would assert is
measurably wrong more often than a coin flip. Deleted rather than kept in
any form: `RiskScorer._direction_probabilities` (backend),
`up_prob`/`down_prob` from the `timeseries` response, and
`DirectionSignal.jsx` (frontend) are gone, not hidden behind a flag —
see `scorer.py`'s comment at the deletion site for the numbers in context.

## Project Structure

```
stock_risk/
├── src/stock_risk/
│   ├── data/          fetcher.py · preprocessor.py
│   ├── features/      technical.py · risk_metrics.py
│   ├── models/        base.py · volatility.py · downside_risk.py
│   ├── scoring/       scorer.py
│   ├── monitoring/    drift.py · metrics.py
│   ├── api/           app.py  (FastAPI)
│   └── config.py
├── ui/
│   └── web/           React + Vite + Tailwind SPA (src/, package.json, dist/ after build)
├── scripts/           train.py · score.py · monitor.py
├── tests/             test_data · test_features · test_llm · test_models ·
│                       test_explain · test_risk_categories · test_scorer · test_api
├── configs/           model_config.yaml · monitoring_config.yaml
├── docker/            Dockerfile · docker-compose.yml
└── .github/workflows/ ci.yml · cd.yml
```

## Dependencies & Citations

Libraries (backend):

- **yfinance** — Aroussi, R. (2019). *yfinance: Download market data from Yahoo Finance's API*. https://github.com/ranaroussi/yfinance
- **Twelve Data** — Twelve Data Inc. *Twelve Data API*. https://twelvedata.com (US equity history when `TWELVE_DATA_KEY` is set)
- **akshare** — Albert King & contributors. *AKShare: an elegant and simple financial data interface library*. https://github.com/akfamily/akshare (CN A-share + HK equity history)
- **XGBoost** — Chen, T., & Guestrin, C. (2016). XGBoost: A scalable tree boosting system. *Proceedings of KDD 2016*, 785–794. https://doi.org/10.1145/2939672.2939785
- **scikit-learn** — Pedregosa et al. (2011). Scikit-learn: Machine Learning in Python. *JMLR*, 12, 2825–2830. https://jmlr.org/papers/v12/pedregosa11a.html
- **SHAP** — Lundberg, S. M., & Lee, S.-I. (2017). A unified approach to interpreting model predictions. *NeurIPS 30*. https://github.com/shap/shap
- **pandas / NumPy / SciPy** — the scientific-Python stack every computation here rests on. https://pandas.pydata.org · https://numpy.org · https://scipy.org
- **pandas-ta** — Twang (2021). *pandas_ta: A Technical Analysis Library in Python*. https://github.com/twopirllc/pandas-ta
- **arch** — Sheppard, K. (2023). *ARCH: Autoregressive Conditional Heteroskedasticity models in Python*. https://github.com/bashtage/arch
- **pandera** — Niels Bantilan (2020). pandera: Statistical data validation of pandas dataframes. *Proceedings of SciPy 2020*. https://pandera.readthedocs.io
- **cachetools** — Kemmler, T. *cachetools: Extensible memoizing collections and decorators*. https://github.com/tkem/cachetools
- **FastAPI** — Ramírez, S. (2021). *FastAPI*. https://fastapi.tiangolo.com — plus **Pydantic**, **SQLModel**, **uvicorn**, **PyJWT**, **bcrypt** for the API/auth layer
- **Gradio** — Abid et al. (2019). Gradio: Hassle-free sharing and testing of ML models in the wild. https://gradio.app (`ui/gradio_app.py`)
- **Prometheus / prometheus-client** — Prometheus Authors (2012–2026). https://prometheus.io
- **loguru**, **pytest**, **ruff**, **Playwright** (screenshot harness `scripts/ui_shot.sh`) — logging/test/lint/visual-regression tooling

Libraries (web frontend): **React** (https://react.dev), **Chart.js** + react-chartjs-2 (https://www.chartjs.org), **Tailwind CSS** (https://tailwindcss.com), **Vite** (https://vitejs.dev).

Methodology sources (implemented from the papers/books — none of these are code dependencies):

- **Value at Risk** — Jorion, P. (2006). *Value at Risk: The New Benchmark for Managing Financial Risk* (3rd ed.). McGraw-Hill.
- **GARCH** — Bollerslev, T. (1986). Generalized autoregressive conditional heteroskedasticity. *Journal of Econometrics*, 31(3), 307–327. https://doi.org/10.1016/0304-4076(86)90063-1
- **VaR backtesting (POF test)** — Kupiec, P. (1995). Techniques for verifying the accuracy of risk measurement models. *Journal of Derivatives*, 3(2), 73–84. (`scripts/validate_score.py`)
- **EWMA volatility** — J.P. Morgan/Reuters (1996). *RiskMetrics — Technical Document* (4th ed.). (`features/risk_metrics.py`, λ=0.94)
- **Amihud illiquidity** — Amihud, Y. (2002). Illiquidity and stock returns. *Journal of Financial Markets*, 5(1), 31–56.
- **Triple-barrier labeling & the fixed-horizon critique** — López de Prado, M. (2018). *Advances in Financial Machine Learning*, ch. 3. Wiley. (`models/feature_sets.py`'s `vol_scaled`/`triple_barrier` label modes, [G2]; the concept's reference implementations — mlfinlab, now frozen/commercial, and its active successors vectorbt/skfolio/mlfinpy — were consulted as prior art, but the ~30-line pandas implementation here is original and dependency-free)
- **Alpha158 factor recipe** — Yang, X., et al. (2020). Qlib: An AI-oriented quantitative investment platform. arXiv:2009.11189. https://github.com/microsoft/qlib (`features/alpha_grid.py` transplants the operator-by-window recipe — K-bar shape features + rolling price/volume operator grid — **without** taking qlib as a dependency)
- **Factor screening discipline (IC + FDR)** — Jansen, S. (2020). *Machine Learning for Algorithmic Trading* (2nd ed.), ch. 7. Packt. Combined with Benjamini, Y., & Hochberg, Y. (1995). Controlling the false discovery rate. *JRSS B*, 57(1), 289–300. (`scripts/factor_screen.py`)
- **Isotonic probability calibration** — Zadrozny, B., & Elkan, C. (2002). Transforming classifier scores into accurate multiclass probability estimates. *KDD 2002*.
- **GJR-GARCH** — Glosten, L., Jagannathan, R., & Runkle, D. (1993). On the relation between the expected value and the volatility of the nominal excess return on stocks. *Journal of Finance*, 48(5). (`models/volatility.py`, [G5])
- **HAR-RV** — Corsi, F. (2009). A simple approximate long-memory model of realized volatility. *Journal of Financial Econometrics*, 7(2), 174–196. (`models/har_volatility.py`)
- **Range volatility estimators** — Parkinson, M. (1980). *Journal of Business*, 53(1); Garman, M., & Klass, M. (1980). *Journal of Business*, 53(1). (`features/risk_metrics.py`'s `parkinson_vol_21d`/`gk_vol_21d`)
- **QLIKE loss for vol-forecast evaluation** — Patton, A. (2011). Volatility forecast comparison using imperfect volatility proxies. *Journal of Econometrics*, 160(1). (`scripts/compare_vol_models.py`)
- **Option-implied crash risk (stock-level put skew)** — Xing, Y., Zhang, X., & Zhao, R. (2010). What does the individual option volatility smirk tell us about future equity returns? *JFQA*, 45(3). (`fetch_options_signals`, [G4])

Data sources: **Yahoo Finance** via yfinance (unofficial API — no SLA, personal/research use; see Data Quality & Limitations). Deployment platforms evaluated: **Render** (live), **Hugging Face Spaces** ([F3], closed by platform paywalls, see Deployment), **Streamlit Community Cloud** (deployed under [F1], later retired in favor of a single canonical product on Render — the standalone `ui/dashboard.py` frontend was removed from the repo).
