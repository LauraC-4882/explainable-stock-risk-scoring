# Portfolio risk — audit and design proposal (Step 1 of 3)

Baseline commit: `2f232b2`. Zero behaviour change: nothing under `src/` or
`ui/web/src/` is modified by the work this document accompanies.

---

## 0. Two corrections to the brief, before anything else

**The paths in the brief do not exist.** This repository is laid out as
`src/stock_risk/`, not `src/riscore/`; the frontend is `ui/web/src/`, not
`frontend/src/`; there is no `src/stock_risk/watchlist/` package and no
`snapshots/validation_manifest.txt`. Every reference below is to a path that was
verified to exist.

| brief | actual |
|---|---|
| `src/riscore/scoring/` | `src/stock_risk/scoring/` |
| `src/riscore/models/schemas.py` | `src/stock_risk/api/schemas.py` |
| `src/riscore/watchlist/` | `WatchlistItem` in `src/stock_risk/auth/models.py:50` |
| `frontend/src/pages/Compare*` | `ui/web/src/components/CompareView.jsx` |
| `snapshots/validation_manifest.txt` | no such file; the reproducible set is the six tracked `snapshots/*.parquet` |

**Portfolio risk is not a greenfield feature. It already ships.**
`src/stock_risk/portfolio/aggregate.py` computes an annualised covariance
matrix, portfolio volatility, VaR/CVaR, Euler-allocated component VaR, marginal
VaR, a diversification ratio, effective-N and HHI. `POST /api/portfolio/risk`
(`src/stock_risk/api/app.py:2013`) serves it and `PortfolioPanel.jsx` renders it.

The question this document can usefully answer is therefore not "can the
existing pipeline be reused" but **"what does the shipped implementation
actually do, and what is missing from it"**. That reframing changes the answer
to audit question 2 completely, so it is stated here rather than buried.

---

## 1. Single-name scoring: what is per-ticker, what is cross-sectional

`RiskScorer.score()` (`src/stock_risk/scoring/scorer.py:171`) returns a 0-100
composite. Its inputs separate cleanly.

**Per-ticker and independent** — nothing about another holding can change these:

| step | where |
|---|---|
| history fetch, preprocessing | `scorer.py:213`, `data/preprocessor.py` |
| technical + risk features | `features/technical.py`, `features/risk_metrics.py` |
| five-category percentile composite | `scoring/risk_categories.py:33` |
| ML drawdown probability + SHAP | `scoring/producers/signals.py:50` |
| stress test multipliers | `scoring/stress_test.py:101` |

The composite is a percentile **against the stock's own two-year history**
(`risk_categories.py:192`). That property is what makes scores non-comparable
across names, and it is the reason section 5 rejects averaging them.

**Cross-sectional or shared state:**

| dependency | where | nature |
|---|---|---|
| market benchmark for beta | `scorer.py:200`, `MARKET_BENCHMARKS` at `scorer.py:47` | SPY for US, 510300.SS for CN — a **second history fetch per score** (`scorer.py:229`) |
| VIX-regime category weights | passed through `ScoringContext` into `risk_categories` | market-wide state, identical for every ticker in a request |
| HMM regime detection | `models/regime_hmm.py`, imported at `scorer.py:21` | fitted per ticker on that ticker's own returns — despite the name, **not** cross-sectional |
| cross-sectional peer percentile | `scoring/cross_sectional.py` + `cross_sectional_reference.json` | a committed peer table; `null` when a market has no entry, and it never falls back to another market's peers |

Practical consequence for a portfolio: **the benchmark fetch is shared**. Ten US
names need one SPY pull, not ten, because the fetch cache serves the repeats
within a request.

---

## 2. Existing covariance / correlation estimation

**It exists.** `portfolio/aggregate.py:102-103`:

```python
cov = matrix.cov().to_numpy() * TRADING_DAYS
portfolio_variance = float(weights @ cov @ weights)
```

A sample covariance matrix on aligned daily log returns, annualised by
`TRADING_DAYS = 252` (`aggregate.py:39`). Built on it:

- marginal VaR as `(cov @ weights) / portfolio_vol` (`aggregate.py:116`),
- component VaR scaled so the parts sum exactly to portfolio VaR — Euler
  allocation (`aggregate.py:119-121`),
- diversification ratio, effective-N, HHI (`aggregate.py:131`).

Everything downstream of that matrix is already implemented.

**Absent from the repository entirely:** shrinkage (Ledoit-Wolf or otherwise),
EWMA or DCC covariance, factor-model covariance, and any correlation estimate
outside this one function. Section 5 argues the shrinkage gap is the most
consequential of those.

---

## 3. Multi-ticker date alignment — measured, not inferred

`_aligned_returns` (`aggregate.py:67`) builds a DataFrame and calls
`dropna(how="any")`: an **inner join**, chosen deliberately, with the reasoning
in its own docstring — zero-filling a missing day would read as "this asset did
not move", understating both its volatility and its correlation, which are the
two inputs the whole calculation rests on.

Measured on the tracked snapshots, through the real preprocessor (which drops
fabricated holiday rows via `drop_non_sessions`):

| portfolio | union of dates | inner-join survivors | discarded |
|---|---|---|---|
| AAPL alone | 554 | 554 (100.0%) | 0 |
| 600519.SS + 000001.SZ + 510300.SS | 493 | 488 (99.0%) | 5 |
| AAPL + the three A-shares | 571 | 471 (**82.5%**) | **100** |

Per-ticker spans: AAPL 554 sessions (2024-05-30 to 2026-08-14); 600519.SS 490;
000001.SZ 491; 510300.SS 490.

**Reading.** Within one calendar the cost is negligible — five days across three
A-shares, which is suspension and nothing more. Across calendars it is **17.5%
of available history**, because the US and Chinese trading calendars diverge on
roughly a hundred days in two years.

**Consequences the current implementation does not surface:**

1. The effective sample for a mixed book is ~471 observations, not ~571. With
   five names that is ~94 observations per estimated parameter — thin but
   usable. The ratio degrades quadratically as names are added, since a
   covariance matrix needs O(N-squared) parameters. This is the strongest
   argument for the 5-position cap at `app.py:2033`, and the cap is currently
   justified in the docstring by fetch cost rather than by estimator stability.
2. `n_observations` is returned (`aggregate.py:64`) but the discarded count is
   not, so a caller cannot distinguish 471-of-571 from 471-of-471.
3. Dropping the union days is not neutral for correlation. The removed days are
   precisely those where one market moved while the other was closed — the days
   carrying genuine asynchronous information. Non-synchronous trading is a known
   source of downward correlation bias, and this design inherits it. The
   estimate is honest about what it saw; what it saw is a biased subsample.

---

## 4. Data-acquisition cost for a ten-position book

**Per single-name score**: history (`scorer.py:213`), benchmark history when the
ticker is not itself the benchmark (`scorer.py:229`), `fetch_info`
(`scorer.py:241`), `fetch_options_signals` (`scorer.py:247`), `fetch_news`
(`scorer.py:308`) — up to five upstream calls.

**The shipped portfolio endpoint is much cheaper.** It fetches history only, one
call per name (`app.py:2047`), and computes no per-ticker score at all. Ten
positions is ten history fetches, plus one benchmark fetch if a portfolio beta
were added — it is deliberately absent, because `app.py:2025` argues a mixed US
+ A-share book has no single honest benchmark.

**What already covers this:**

- **Rate limiting.** `/api/portfolio` carries a token-bucket cost of 5.0 versus
  2.0 for `/api/score/` (`app.py:128`), commented "fans out up to 5 history
  fetches". A ten-name book would need that constant revisited; it encodes
  today's cap.
- **Snapshot fallback.** `fetch_history` serves the last committed snapshot when
  upstream throttles, so a throttled portfolio request degrades to
  stale-but-real data rather than failing — but only for tickers with a snapshot
  on disk.
- **Caching.** Repeated `fetch_history` for the same symbol within a request is
  served from cache, which is why a shared benchmark costs one call and not N.

**Serial + pause: not needed at ten, needed beyond it.** Yahoo rate-limits
aggressively — see `SESSION_LEDGER.md`, where the limiter engaged on ticker 2 of
56 — and Twelve Data's free tier allows 8 requests per minute. Ten sequential
history fetches already exceeds that budget when the key is set. The honest
options are (a) keep a small cap, (b) require every name to have a snapshot, or
(c) add a pause and accept a multi-second response. This document recommends
(a), with the cap justified statistically rather than by fetch cost.

---

## 5. Proposal A — how to aggregate

Three candidates. The recommendation rests on a statistical property, not on
which produces nicer numbers.

### A1. Weighted average of single-name scores

`portfolio_score = sum(w_i * score_i)`

**Correlation assumption: perfect and positive.** A weighted mean of percentiles
is the correct aggregate only if every component moves together; otherwise it is
an upper bound that no diversification can move.

Worse, the scores are not on a common scale. Each is a percentile against *that
stock's own history* (`risk_categories.py:192`), so a utility at its own 90th
percentile and a high-volatility name at its own 90th percentile contribute
equally, while their contributions to portfolio variance may differ by an order
of magnitude. Averaging them is not a weak approximation of portfolio risk; it
is an average of quantities not denominated in the same unit. **Rejected on that
ground alone**, before the correlation argument is even reached.

### A2. Re-run the single-name pipeline on a synthetic portfolio return series

Build `r_p(t) = sum(w_i * r_i(t))`, then feed that series through
`risk_categories.composite_score` as if it were one instrument.

**Correlation assumption: none — it is handled exactly.** Correlation enters
through the realised series itself, so diversification is captured without being
modelled. Conceptually the cleanest of the three, and it reuses the existing
five-factor machinery unchanged.

Its problems are specific and real:

- **The percentile has no reference distribution.** Every category score is a
  percentile against the instrument's own two-year history. A portfolio created
  ten seconds ago has none. The synthetic series can be back-computed, but only
  over the inner-join window and only for the current weights — re-weighting
  rewrites the entire history retroactively, so today's score is not comparable
  to the same portfolio's score yesterday.
- Several categories are undefined or misleading on a synthetic series:
  liquidity (Amihud needs dollar volume, which a portfolio does not have), beta
  (definable, but `app.py:2025` already rejects a single benchmark for a mixed
  book), and the ML drawdown leg (trained on single-name features).
- It inherits the 17.5% sample loss from section 3 twice: once in the synthetic
  series, once in the percentile window.

### A3. Covariance-based risk decomposition (the shipped design)

Estimate the covariance matrix from aligned returns; report portfolio
volatility, VaR/CVaR, and Euler-allocated per-position risk contributions that
sum exactly to the whole.

**Correlation assumption: linear dependence, estimated from a finite sample, and
constant across it.** Two real costs — tail dependence is not captured by a
covariance, and a sample covariance on ~471 observations for five names is noisy
— but this is the *weakest* assumption of the three and the only one that is
explicit.

### Recommendation: keep A3, and close two gaps

The reason is a priori. A3 is the only candidate whose output is **additive by
construction**: Euler allocation guarantees the components sum to the total
(`aggregate.py:119-121`), so "where does this book's risk come from" has an
answer that adds up. A1 produces an aggregate that cannot decompose. A2
decomposes only by ablation — re-run without a holding — which is O(N) extra
computation and is not additive.

Two gaps, in priority order:

1. **Shrink the covariance estimate.** At N=5 and T of roughly 471 the sample
   matrix is usable; at N=10 with the same T it is noticeably unstable, and the
   instability lands hardest on exactly the quantity users read — the smallest
   and largest risk contributions. Ledoit-Wolf shrinkage toward a
   constant-correlation target is the standard answer, has no free parameter to
   tune, and cannot do worse than the sample estimator in expected Frobenius
   loss. This is the single change that would most improve numbers already being
   shown today.
2. **Report the alignment loss.** `n_observations` exists; the union count does
   not. A mixed-calendar book should say so, because 471-of-571 and 471-of-471
   are different claims about the same number.

**Not recommended: a single 0-100 portfolio risk score.** There is no reference
distribution to take a percentile against, and inventing one (peer portfolios? a
fixed volatility scale?) would reintroduce exactly the "precise-looking number
whose inputs are undefined" defect that `SESSION_LEDGER.md` already records
three instances of. Volatility, VaR and CVaR are absolute, interpretable, and
need no reference set.

---

## 6. Proposal B — where diversification shows up

`diversification_ratio` and `effective_n` are already computed
(`aggregate.py:56-57`).

- **Implicit only** — the benefit sits inside the volatility number and is never
  named. Rejected: the reason to show a portfolio view rather than five cards is
  that the interaction is the new information.
- **Explicit as a difference against the weighted-average score** — rejected for
  the A1 reason: the weighted average is not a quantity in the same unit, so a
  difference against it measures nothing.
- **Explicit as the ratio already computed** — recommended. It is unit-free,
  bounded below by 1.0 (meaning no benefit), needs no second aggregate, and is
  directly interpretable. `effective_n` is its intuitive companion: "this
  ten-name book behaves like 4.2 independent ones."

Both are descriptive statistics about realised co-movement, and the copy must
say so — not a claim that the benefit will persist.

---

## 7. Proposal C — SHAP at portfolio level

SHAP explains **one model's prediction for one feature vector**. Here that model
is `DownsideRiskModel`, whose features are single-name
(`models/feature_sets.py:42`) and whose explanation is produced per score
(`models/explain.py`).

- **Per-holding attribution of a portfolio score: mathematically not
  applicable.** There is no portfolio-level model and therefore no prediction
  for SHAP to decompose. Additivity would have to be asserted, not derived. Do
  not build it.
- **Per-factor attribution of a portfolio score: also not applicable**, for the
  same reason — no model, no baseline, no coalition value function.
- **What is additive, and already implemented: Euler risk contributions.**
  `component_var` sums exactly to portfolio VaR by construction. That is the
  portfolio-level analogue of what users read SHAP for; it is exact rather than
  approximate, and it needs no model.
- **Per-holding SHAP remains valid where it already is** — on each single-name
  card. Presenting those alongside a portfolio view is fine; summing them is
  not.

The distinction to hold onto: SHAP decomposes a *prediction*; Euler decomposes a
*risk measure*. A portfolio has the second and not the first.

---

## 8. Proposal D — cold start and degradation

`MIN_TRADING_DAYS = 60` (`data/quality.py:34`) is the floor for a scorable
history; below it the single-name path returns 422 with `INSUFFICIENT_DATA`
(`api/errors.py:63`).

The five codes (`errors.py:44-68`): `TICKER_NOT_FOUND`, `INSUFFICIENT_DATA`,
`UPSTREAM_UNAVAILABLE`, `CALCULATION_FAILED`, `DELISTED`.

**Recommendation: fail the whole portfolio; do not partially degrade.**

A covariance matrix is a joint estimate. Dropping a holding does not produce
"the portfolio minus one name, with a caveat" — it produces a *different
portfolio*, whose weights no longer sum to the user's book and whose
diversification ratio describes something the user did not ask about. Returning
that under the same field names, with a warning attached, is the same class of
error as a precise number with undefined inputs.

Mapping by cause:

| condition | code | status |
|---|---|---|
| a holding has fewer than 60 sessions (new listing) | `INSUFFICIENT_DATA` | 422 |
| a symbol does not resolve | `TICKER_NOT_FOUND` | 404 |
| upstream throttled and no snapshot available | `UPSTREAM_UNAVAILABLE` | 503 |
| inner join leaves too few shared rows | `INSUFFICIENT_DATA` | 422 |
| singular covariance or other numerical failure | `CALCULATION_FAILED` | 500 |
| a holding is delisted | `DELISTED` | 410 |

The response must name **which** holding caused it, in a structured `ticker`
field — never by interpolating an exception into prose.

### A pre-existing violation of the str(exc) constraint

`app.py:2059`, in the shipped portfolio endpoint:

```python
except ValueError as exc:
    raise HTTPException(status_code=422, detail=str(exc)) from exc
```

`str(exc)` reaches the response body. The endpoint also raises a bare
`HTTPException(404, ...)` at `app.py:2050`, outside the `ScoringHTTPError`
taxonomy that `/api/score/` uses via `_scoring_errors` (`app.py:391`,
`app.py:447`). Every message in that taxonomy is a fixed string from
`ERROR_SPECS` (`api/errors.py:117-119`).

This is not introduced by any proposal here — it is in `main` today, and it is
logged rather than fixed because this round is zero-behaviour-change. It should
be the **first** item of Step 2, before any aggregation work, because Step 2
will otherwise build new error paths alongside a non-conforming one.

---

## 9. i18n key plan (planned only; no locale file is touched this round)

Namespace `portfolioRisk.*`, three files in lockstep:
`ui/web/src/i18n/locales/{en,zh-CN,zh-TW}.json`.

| key | en | zh-CN | zh-TW |
|---|---|---|---|
| `portfolioRisk.title` | Portfolio risk | 组合风险 | 組合風險 |
| `portfolioRisk.volatility` | Annualised volatility | 年化波动率 | 年化波動率 |
| `portfolioRisk.var95` | 1-day VaR (95%) | 单日 VaR(95%) | 單日 VaR(95%) |
| `portfolioRisk.cvar95` | 1-day CVaR (95%) | 单日 CVaR(95%) | 單日 CVaR(95%) |
| `portfolioRisk.diversification` | Diversification ratio | 分散化比率 | 分散化比率 |
| `portfolioRisk.effectiveN` | Behaves like {n} independent holdings | 相当于 {n} 个相互独立的持仓 | 相當於 {n} 個相互獨立的持倉 |
| `portfolioRisk.contribution` | Share of portfolio risk | 占组合风险的比重 | 佔組合風險的比重 |
| `portfolioRisk.alignmentNote` | Estimated on {used} of the {available} sessions these holdings share. Different trading calendars account for the rest. | 基于这些持仓共同拥有的 {used}/{available} 个交易日估计。其余交易日因交易日历不同而被剔除。 | 基於這些持倉共同擁有的 {used}/{available} 個交易日估計。其餘交易日因交易日曆不同而被剔除。 |
| `portfolioRisk.disclaimer` | Descriptive statistics about how these holdings moved together in the past. Not a prediction, and not advice. | 这是对这些持仓过去共同变动方式的描述性统计。不是预测，也不构成任何建议。 | 這是對這些持倉過去共同變動方式的描述性統計。不是預測，也不構成任何建議。 |
| `portfolioRisk.error.insufficientData` | {ticker} does not have enough history to include. | {ticker} 的历史数据不足，无法纳入计算。 | {ticker} 的歷史資料不足，無法納入計算。 |

`locales.test.js` enforces key parity but not content parity
(`SESSION_LEDGER.md` entry 3), so a stale translation will not be caught
automatically. Step 3 must diff all three files.

No string above contains a position recommendation, and none should. The
vocabulary throughout is "contributed", "moved together", "share of risk" —
never anything that reads as an instruction.

---

## 10. What Step 2 should do first

1. Bring `/api/portfolio/risk` onto the `ScoringHTTPError` taxonomy and remove
   `str(exc)` from its response body (section 8).
2. Report alignment loss alongside `n_observations` (section 3).
3. Ledoit-Wolf shrinkage on the covariance estimate, with the position cap
   re-justified on estimator stability rather than fetch cost (section 5).

The aggregation methodology itself needs no change. The shipped choice is the
right one; what it lacks is a stable estimator, an honest sample-size
disclosure, and a conforming error path.
