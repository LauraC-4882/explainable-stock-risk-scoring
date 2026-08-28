# Session ledger — found, not yet fixed

Defects and gaps that have been **identified and characterised** but
deliberately **not** fixed in the change that found them, with the reason for
deferring. Nothing here is a vague "we should look at this some time": each
entry names the file and line, states the impact with a measurement, and
proposes a fix.

The point of writing them down is that a finding deferred without a record is a
finding lost. The point of deferring them at all is that a documentation change
and an interface change do not belong in one pull request.

---

## 1. `validate_tail.py` selects its sample by globbing a directory

**Where** `scripts/validate_tail.py:37` —
`sorted(snapshot_dir.glob("*.parquet"))`

**What** The tail-test suite runs on whatever `snapshots/` happens to contain,
so the sample is a filesystem state rather than a declared set. The README once
reported "9 tickers, 4,613 ticker-days" from such a run; at the time of writing
this the working tree holds **101** parquet files (6 tracked, 95 untracked from
in-progress work), so the same command produces a 101-ticker result locally and
a 6-ticker result in CI. Both are correct; neither is what the document said.

**Why it matters beyond reproducibility** Pooled Kupiec's likelihood-ratio
statistic scales with `n`. Moving the ticker set from 9 to 101 changes the LR
and its p-value by an order of magnitude, so the historical statistic was
computed on a sample nobody recorded. A reviewer asking "how were those nine
tickers chosen?" currently has the answer "they weren't — that is what the glob
returned."

<!-- historical-record: legacy-21d-estimator -->
> The figure in question, quoted so this entry is checkable: `LR 1160.9`.
> Anchored because `tests/test_docs_consistency.py` forbids that number in live
> prose — correctly, since it is a retracted measurement. An entry describing
> the retraction is the one place it still belongs.
<!-- /historical-record -->

**Fix** Take an explicit ticker list (a file, or `--tickers`), and refuse a bare
glob by default. The sample is part of the analysis and should not be decided by
the filesystem.

**Deferred because** it changes the script's interface, and mixing that with the
documentation rewrite would make both harder to review.

---

## 2. `validate_tail.py` grades a log-return VaR line against percentage returns

**Where** `scripts/validate_tail.py:69` reads `df["pct_return"]`, while
`src/stock_risk/features/risk_metrics.py:23` builds every VaR/ES series from
`df["log_return"]`.

**What** On loss days `pct_return > log_return` (less negative) — measured at
+0.00029 on average for AAPL. Comparing the less-negative series against a
line fitted to the more-negative one counts **fewer** breaches than the
estimator actually incurs.

**Direction, stated plainly** Unlike entries 1 and 3, this bias is *not*
neutral. It points one way: it makes the reported VaR look better than it is.
Measured on the six tracked snapshots:

| convention | pooled n | mean breach | Kupiec rejections |
|---|---|---|---|
| `pct_return` (current) | 2618 | 5.41% | 0 of 6 |
| `log_return` (consistent) | 2618 | 5.57% | 1 of 6 |

The effect is uneven — three of the six tickers are unchanged, `301189_SZ`
differs by 0.70pp and `601318_SS` by 0.24pp — which is enough to flip a Kupiec
verdict.

**Fix** Read `log_return`, matching the series the VaR was estimated from. One
line, plus a test that the two conventions are not silently mixed.

**Deferred because** it is a behaviour change to a script whose output gates CI,
and it needs its own test and review rather than riding along with prose edits.

---

## 3. `locales.test.js` checks key presence, not content parity

**Where** `ui/web/src/i18n/locales/locales.test.js`

**What** It verifies that `en`, `zh-CN` and `zh-TW` carry the same key set. It
cannot notice that one locale's copy still says something the other two have
corrected — updating two of three files passes.

**Why it matters here** The VaR narrative correction touched three keys in each
locale. Nothing but review caught whether all three files moved together.

**Fix** Unclear, and that is why it is only logged. Byte-comparing translations
is meaningless; a heuristic (e.g. flag when one locale changes and its siblings
do not, in the same commit) belongs in a hook or a lint rule rather than a unit
test.

---

## 4. Nested working clone was present in the tree

**Where** `./explainable-stock-risk-scoring/` (gitignored by `a904799`)

**What** A full second checkout of this repository sat inside the working tree,
carrying a pre-fix `signals.py`, an outdated README, and a local `.env`
containing `ADMIN_EMAIL` / `ADMIN_PASSWORD`. `.gitignore` hides it from git and
from ripgrep, but not from `pytest` collection or from build contexts that copy
the directory wholesale.

**Status** Credentials flagged for rotation; directory removal and rotation are
being handled outside this repository's history. The `admin` seeding path
(`src/stock_risk/auth/admin.py:58-77`) **never overwrites an existing password
hash**, so rotating `ADMIN_PASSWORD` in the environment does not invalidate the
old one where the account row persists — see entry 5.

---

## 5. Rotating `ADMIN_PASSWORD` does not invalidate the old password

**Where** `src/stock_risk/auth/admin.py:58-77`

**What** `ensure_admin_user` creates the admin row when absent and otherwise
only flips `is_admin` / `is_banned`. The docstring says so explicitly ("Never
touches `hashed_password`"), and that behaviour is right for its original
purpose — a user who registered with that address keeps the password they
chose. The consequence is that changing the environment variable is not a
password rotation wherever the database persists.

**Fix** An explicit `ADMIN_FORCE_RESEED=1` switch that re-hashes on boot.
Deliberately *not* "re-seed whenever the env value differs from the stored
hash": that variant would silently revert a password the admin changed through
the UI, on every redeploy, in a way nobody would trace back to deployment.

**Blocked on** confirming whether production sets `DATABASE_URL` (persistent
Postgres) or falls back to dyno-local SQLite (`src/stock_risk/db.py:29-31`),
since the latter resets on redeploy and reseeds with the new value by itself.

---

## Pattern worth naming

Entries 1, 2 and the estimator defect already fixed in `93b5871` are three
instances of one failure: **a number that reads as precise while the inputs
that produced it are undefined** — the estimator's plotting position, the
sample set, the return convention.

All three sit in `validate_tail.py` and its upstream, which is not a
coincidence. That is the one path where a computed value becomes an outward
claim, so it carries the most correctness pressure — and it had the least test
coverage in the repository, with no golden fixture and nothing asserting that
its arithmetic was right. Code that produces external numbers should be
verified at least as hard as code that produces internal features. This project
had it the other way around.

Entry 2 deserves one further note for anyone presenting this work: its bias
points in the direction that flatters the product, and it was found and
disclosed anyway.
