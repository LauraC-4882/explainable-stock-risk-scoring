# Return-convention audit

Inventory only. **No calculation was changed, no published figure was
recomputed, and no `.py` calculation logic was touched by this document.**

Purpose: the next change unifies return conventions and will therefore move
published figures. Recording the current state first is what makes it possible
to tell "the convention changed" apart from "a bug was fixed along the way"
once those figures move.

Scope of the search: `src/`, `scripts/`, `tests/`. Patterns searched:
`pct_change`, `np.log(`, `np.diff`, `.shift(1)`, `diff()`, `log_return`,
`simple_return`, `ret`, `returns`. There is no `notebooks/` directory in this
repository.

Matches for `np.log(` inside likelihood, variance or divergence formulas
(`validation/tail_tests.py`, `monitoring/drift.py`, the Garman-Klass and
Parkinson estimators) are **not** price-to-return conversions and are excluded.

## Inventory

| file:line | expression | simple / log | price column | missing days | consumed by |
|---|---|---|---|---|---|
| `data/preprocessor.py:93` | log of close over previous close | **log** | `close` (adjusted — see below) | non-sessions dropped upstream by `drop_non_sessions`; first row NaN then dropped | the canonical `log_return` column: `RiskMetrics` (all vol/tail/drawdown metrics), `VolatilityModel` (GJR-GARCH), `har_volatility`, the scorer beta leg, the backtest endpoint |
| `data/preprocessor.py:94` | `close.pct_change()` | **simple** | `close` | same rows as above | `scripts/validate_tail.py:76` only, plus two test references. No production consumer |
| `data/preprocessor.py:64` | log of close over previous close | **log** | `close` | computed before the dropna, inside `_remove_price_outliers` | outlier detection only; local to the function and discarded |
| `models/feature_sets.py:91` | log of close over previous close | **log** | `close` | recomputed locally; relies on the frame already being preprocessed | drawdown-event labels for the XGBoost model |
| `features/alpha_grid.py:61` | close over previous close minus one | **simple** | `close` | inherits the preprocessed frame | the K-bar `alpha_*` columns, screened by `factor_screen.py` |
| `features/alpha_grid.py:71` | `close.shift(w) / close` | **neither** — a price ratio | `close` | inherits the preprocessed frame | the `alpha_roc_*` columns |
| `features/alpha_grid.py:63` | log of volume ratio plus one | **log** | `volume` (not a price) | inherits the preprocessed frame | volume-family alpha columns |
| `scripts/validate_score.py:137` | log of close over previous close | **log** | `close` | own expanding-window outlier filter, then dropna | quintile backtest, Kupiec check |
| `scripts/validate_score.py:138` | `close.pct_change()` | **simple** | `close` | as above | written into the frame; not read by the backtest |
| `scripts/validate_score.py:162` | log of forward close over window start | **log** | `close` | forward window, no fill | forward max-drawdown outcome |
| `scripts/validate_score.py:107` | log of close over previous close | **log** | `close` | pre-filter, inside the point-in-time outlier filter | outlier detection only |
| `scripts/compare_vol_models.py:41` | log of close over previous close | **log** | `close` | own dropna; does **not** call `DataPreprocessor` | QLIKE volatility-model comparison |
| `scripts/validate_vix_structure.py:48` | log of close over previous close | **log** | `close` of an index | own handling | VIX term-structure study |
| `api/app.py:1942` | reads `log_return` | **log** | — | inherits preprocessor | backtest endpoint realised-loss series |
| `api/app.py:2048` | reads `log_return` | **log** | — | inherits preprocessor | portfolio aggregation |
| `models/volatility.py:57,91` | reads `log_return` | **log** | — | `.dropna()` | GJR-GARCH fit; rolling realised vol |
| `scripts/validate_tail.py:76` | reads `pct_return` | **simple** | — | dropna after aligning with the shifted forecast | the tail-test suite realised-loss series |

### Adjustment: a column, not a line

The meaning of `close` is **not uniform across data sources**, so "same
expression" does not imply "same input":

| source | routing | adjustment |
|---|---|---|
| yfinance | US without a Twelve Data key; indices | `auto_adjust=True` — split- and dividend-adjusted |
| akshare | CN A-shares, HK | `adjust="qfq"` — forward-adjusted |
| Twelve Data | US when the key is set (`fetcher.py:281`) | no adjustment parameter is sent; the vendor default applies |

Marked **suspected inconsistency**. The Twelve Data request passes symbol,
interval, outputsize and the key only. Whether its default matches yfinance's
`auto_adjust=True` was not determined here — that needs a live call, which is
out of scope for an inventory. Recorded, not resolved.

## a. Convention groups

Four groups, by what is actually computed. The fourth is the one that a name-based reading gets wrong.

1. **Log returns on the preprocessed close** — `preprocessor.py:93` and every
   consumer of the `log_return` column. The dominant group; everything the
   scoring path publishes flows through it.
2. **Log returns recomputed locally, bypassing `DataPreprocessor`** —
   `feature_sets.py:91`, `compare_vol_models.py:41`,
   `validate_vix_structure.py:48`, and `validate_score.py:137`, which
   deliberately substitutes an expanding-window outlier filter to avoid
   lookahead. Same formula, different missing-day and outlier handling.
3. **Simple returns** — `preprocessor.py:94` and `alpha_grid.py:61`.
4. **Not returns at all, but named or shaped like them** —
   `alpha_grid.py:71` (`alpha_roc_*` is `close.shift(w) / close`, a ratio of a
   past price to the current one) and `alpha_grid.py:63` (a volume ratio).

Group 4 emerged from writing the pinning tests rather than from reading the
code: `alpha_roc_*` reads as a rate of change, and it is not one. On a rising
series it sits **below 1** — the opposite direction to both a simple and a log
return. Qlib's Alpha158 defines ROC this way, so the implementation is faithful
to the recipe it was transplanted from and is **not** flagged as a defect. It is
recorded because a unification pass that matched on names would convert it and
silently invert a feature.

Group 2 is a *provenance* split rather than a formula split: the arithmetic
matches group 1 exactly, but the rows reaching it differ.

## b. Conflicts — different conventions feeding one published figure

Two.

1. **The tail-test suite grades a log-return forecast against simple returns.**
   `validate_tail.py:76` takes the realised loss from `pct_return` (simple),
   while the forecast columns it is compared against are derived from
   `log_return` (log). Both come from the same `DataPreprocessor` frame, so
   this is a convention mismatch inside one comparison, not a data mismatch.
   Already noted as open in the `tests/test_docs_consistency.py` header. The
   published tail figures rest on this pairing.

2. **The same nominal close carries different adjustment conventions across
   markets.** A CN ticker's returns come from `qfq` prices, a US ticker's from
   `auto_adjust=True` prices, and a US ticker fetched with a Twelve Data key
   from whatever that vendor returns by default. Any figure aggregating across
   markets — the cross-sectional peer table, the multi-ticker tail validation
   panel — mixes these. Marked **suspected inconsistency**; the Twelve Data leg
   is unverified.

## c. Harmless — inconsistencies with no published-figure impact

- `preprocessor.py:64` and `validate_score.py:107`: log returns computed inside
  outlier filters. Local variables, discarded after use.
- `preprocessor.py:94` reached through the scoring path: written into every
  scored frame but read by no production code. Its only reader is
  `validate_tail.py`, which is conflict 1; through every other path it is inert.
- `validate_score.py:138`: written and never read by that script's backtest.
- `alpha_grid.py:61` (simple) against group 1 (log): the `alpha_*` columns are a
  candidate grid screened by `factor_screen.py`; none currently carries weight
  in a published score.
- `alpha_grid.py:63`: a volume ratio, not a return.

## Pinned / not pinned

Every row above is pinned by `tests/test_return_convention_inventory.py`
except:

| row | why not pinned |
|---|---|
| Twelve Data adjustment default | Needs a live vendor call. The test pins what the code *sends* — no adjustment parameter — which is the part under this repository's control; what the vendor does with that is not assertable offline. |
