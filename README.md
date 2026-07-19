# Stock Risk Scoring System

**Live demo (FastAPI + React, full pipeline incl. ML+SHAP):** https://explainable-stock-risk-scoring.onrender.com — Render free tier: spins down after 15 min idle (~50s+ wake), and the `/api/score/*` endpoints depend on Yahoo not throttling Render's shared egress IP, which it does for extended windows (`/health` and the UI always respond; see [Deployment](#deployment) for the honest details — that IP-reputation constraint, not memory, turned out to be the real free-tier limit).

A production-style system that predicts **downside risk** and **volatility** for individual stocks using live market data fetched via `yfinance`, technical indicators, and machine learning models (XGBoost + sklearn Pipeline).

**Project status (as of 2026-07-19):**

- **Validated & live**: percentile composite score (quintile backtest + Kupiec POF, see *Score Validation*); ML drawdown leg (walk-forward AUC 0.671 on 56 tickers × 5y); producer-layer architecture with typed validation-gated fusion weights ([G1]); TTL-cached fetcher with real timeouts ([C3]); end-to-end smoke + visual-regression harnesses ([D1]/[D2]); Render deploy (full pipeline).
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
│  PercentileComposite   weight 1.0  validated (quintile+Kupiec)  → risk_score          │
│  MLDrawdown            weight 0.0  validated (WF AUC 0.671)     → ml_drawdown_*       │
│  GarchVol              weight 0.0  unvalidated (absolute σ)     → garch_volatility_*  │
│  NewsRisk              weight 0.0  unvalidated (mock extractor) → news_risk           │
│  AltData               weight 0.0  unvalidated (raw counts)     → alt_data            │
└──────────────────────────┬───────────────────────────────────────────────────────────┘
                           ▼
        fuse(): Σwᵢsᵢ/Σwᵢ over available scores — unvalidated producers are
        FORCED to weight 0 at startup (typed guard, not convention). Current
        config {percentile: 1.0, rest: 0} ⇒ fused score ≡ percentile composite;
        raising any other weight is a deliberate, validation-gated future step.

2008/2020/2022 scenarios ──► stress_test.py (percentile score only, beta-scaled shocks) ─ stress_test
                │
                ▼
          Risk Scorecard (0–100 + label + category breakdown)
                │
       ┌────────┬────────┐
       ▼        ▼        ▼
  FastAPI   React SPA   Streamlit
  REST API  ui/web/     Dashboard
  /api/*    (built,     ui/dashboard.py
            served at /)
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
| `ui/dashboard.py` | **Streamlit** interactive dashboard with Plotly charts |

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

# 5. Launch the Streamlit dashboard
streamlit run ui/dashboard.py
# or:  make dashboard

# 6. Build the React web frontend (one-time / after any ui/web change)
cd ui/web && npm install && npm run build && cd ../..

# 7. Start the REST API — serves the built React app at http://localhost:8000/
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
raw = fetcher.fetch_history("AAPL", period="2y")          # yfinance live
df  = DataPreprocessor().process(raw)                      # clean
df  = TechnicalFeatures().compute(df)                      # indicators
df  = RiskMetrics().compute(df)                            # risk metrics
```

## Data Quality & Limitations

**yfinance is an unofficial scrape of Yahoo Finance, not a licensed data
feed.** No SLA, no uptime guarantee, endpoints can change or disappear
without notice, and its own terms of service don't permit commercial use —
appropriate for a student/portfolio project, not for anything that would
need a real data contract with an accountable vendor. If this were headed
to production, the first change would be a paid source (e.g. Polygon.io,
IEX Cloud, Tiingo's paid tier) behind the same `MarketDataFetcher`
interface, so nothing downstream would need to change.

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
- `src/auth/` — `AuthContext` (JWT stored in `localStorage`, session restored on load via `/api/auth/me`), `AuthModal`, `WatchlistPanel`

### Accounts & watchlist

Auth is self-hosted (FastAPI + SQLite + JWT), not a third-party service — no external account is needed to run the app. Passwords are hashed with bcrypt; tokens are bearer JWTs valid for 7 days. Set `JWT_SECRET_KEY` in `.env` before deploying with real users — the app runs fine without it for local dev but logs a startup warning, since the fallback is a published placeholder value.
- `tailwind.config.js` — theme colors matched to the original dark palette (risk label colors, accent gradient)

Verified end-to-end with a headless-Chromium (Playwright) smoke test: multi-card grid, live search with debounce, Enter-to-add, timeframe switching, zero console errors, real yfinance data rendering in both the SVG gauge and Chart.js line charts.

## Streamlit Dashboard

Run `streamlit run ui/dashboard.py` (or `make dashboard`) and open `http://localhost:8501`.

Features:
- Risk gauge (0–100) with colour-coded label
- Key metric tiles: volatility, VaR, CVaR, max drawdown, beta, implied vol
- Interactive candlestick chart with Bollinger Bands and EMAs
- RSI panel with overbought/oversold lines
- Rolling volatility comparison (21d vs 63d)
- Rolling drawdown from peak
- Raw feature table and JSON scorecard expanders

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
- The fix is an upstream-source change (paid data API with an SLA, or a proxy with
  clean egress), not an app change — same "upgrade path" already documented in
  Data Quality & Limitations.
- CI handles the same root cause explicitly: `make smoke` exits 75 when Yahoo
  throttles the runner, and CI surfaces that as a loud warning instead of a false
  "commit broken" red (see CLAUDE.md §2).

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
│   ├── dashboard.py   (Streamlit)
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
- **XGBoost** — Chen, T., & Guestrin, C. (2016). XGBoost: A scalable tree boosting system. *Proceedings of KDD 2016*, 785–794. https://doi.org/10.1145/2939672.2939785
- **scikit-learn** — Pedregosa et al. (2011). Scikit-learn: Machine Learning in Python. *JMLR*, 12, 2825–2830. https://jmlr.org/papers/v12/pedregosa11a.html
- **SHAP** — Lundberg, S. M., & Lee, S.-I. (2017). A unified approach to interpreting model predictions. *NeurIPS 30*. https://github.com/shap/shap
- **pandas / NumPy / SciPy** — the scientific-Python stack every computation here rests on. https://pandas.pydata.org · https://numpy.org · https://scipy.org
- **pandas-ta** — Twang (2021). *pandas_ta: A Technical Analysis Library in Python*. https://github.com/twopirllc/pandas-ta
- **arch** — Sheppard, K. (2023). *ARCH: Autoregressive Conditional Heteroskedasticity models in Python*. https://github.com/bashtage/arch
- **pandera** — Niels Bantilan (2020). pandera: Statistical data validation of pandas dataframes. *Proceedings of SciPy 2020*. https://pandera.readthedocs.io
- **cachetools** — Kemmler, T. *cachetools: Extensible memoizing collections and decorators*. https://github.com/tkem/cachetools
- **FastAPI** — Ramírez, S. (2021). *FastAPI*. https://fastapi.tiangolo.com — plus **Pydantic**, **SQLModel**, **uvicorn**, **PyJWT**, **bcrypt** for the API/auth layer
- **Streamlit** — Streamlit Inc. (2019–2026). *Streamlit: The fastest way to build data apps*. https://streamlit.io
- **Gradio** — Abid et al. (2019). Gradio: Hassle-free sharing and testing of ML models in the wild. https://gradio.app (`ui/gradio_app.py`)
- **Plotly** — Plotly Technologies Inc. (2015–2026). *Plotly Python graphing library*. https://plotly.com/python
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

Data sources: **Yahoo Finance** via yfinance (unofficial API — no SLA, personal/research use; see Data Quality & Limitations). Deployment platforms evaluated: **Render**, **Hugging Face Spaces**, **Streamlit Community Cloud**.
