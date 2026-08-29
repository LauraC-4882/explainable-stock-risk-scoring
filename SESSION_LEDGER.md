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

## 6. One of the three M1 edits exists only in the working tree

**Where** `README.md`, the "Effect of the holiday-fill fix" section — which is
**not in `HEAD`**. That whole section is the parallel session's unpushed work,
and the edit sits on top of it.

**What** The correction — that `var_95_21d` is a scoring feature and not the
reported 95% VaR, monotone in local tail risk so its noise costs statistical
power rather than biasing the ranking — has three landing sites, deliberately
worded identically: the README's Kupiec section (A2/A4,
committed), `scripts/validate_score.py`'s docstring (B1, committed), and the
tail-category locale copy (B3, committed) — plus this one (A3), which could not
be staged without carrying the parallel session's entire section along with it.

**Risk if it is lost** The README ends up in a state where every *other* place
carries the "monotone in local tail risk, noise costs power not direction"
qualification and this one does not — i.e. the single passage that still reads
as if the project considers the estimator simply broken, sitting inside a
section about a different fix. That is worse than never having written the
qualification, because the inconsistency implies the argument was abandoned.

**Backstop, and its limit** `tests/test_docs_consistency.py::
test_the_21_day_series_is_always_qualified` would catch it — but only once that
section is committed. Until then the check has nothing to look at. A backstop
that fires after the risk window has closed is not cover for the window.

**Suggested (not done here)** Copy the edit to `notes/A3_pending_edit.md` so it
has an anchor independent of one working tree. This is the same move as
materialising a stash into a branch: the content survives whatever happens to
the uncommitted state around it.

**Why it is only logged** Creating that file is a write to the main checkout,
which this round is not doing. The recommendation is recorded so the decision is
explicit rather than implied by silence.

---

## 7. `git update-ref` on the checked-out branch produced a false health reading

**What happened** After rebasing this session's commit onto `origin/main` inside
a temporary worktree, the push failed, but the local branch ref had already been
moved to the rebased commit with `git update-ref`. Moving the ref of the branch
you are standing on does **not** touch the working tree, so `git status` then
reported every difference between the old and new tips as a working-tree change.
The uncommitted-entry count jumped 132 → 137.

**Resolved** The ref was pointed back at the original commit, the count returned
to 132, and nothing was lost. The branch was then pushed directly instead.

**Why it is worth a ledger entry** Not for blame — for what it did to a signal.
Throughout this session the count of uncommitted entries has been used as the
cheap check that the parallel session's work survived a stash round-trip. This
is the first time that number moved for a reason having nothing to do with file
contents, which means the check is weaker than it was being relied on to be.

**The rule that follows** A change in the uncommitted-entry count no longer
licenses the inference "content changed". Confirm `HEAD` and the working tree
refer to the same base first — e.g. that the branch ref has not been moved
underneath the tree — and only then read the count. The count answers "how many
paths differ from HEAD", which is only the intended question while HEAD is where
you left it.

## Methodology conclusions (candidates for the model card)

The two sections below are not retrospectives on this session. They are claims
about **where verification effort should go**, which belongs in a model card's
methodology chapter rather than in a changelog. Marked here, to be lifted when
`docs/model_card.md` is written; not implemented now.

### Where the correctness pressure actually sits

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

### A newly written check is inert until proven otherwise

Seven assertions were added to `tests/test_docs_consistency.py` in the change
that produced this ledger. All seven passed against the real documents on the
first run. Two of them could not have failed for **any** input:

- `QUALIFIER` accepted a bare `feature`. That word appears in roughly half
  the paragraphs of a project README, so the rule "a mention of the short-window
  series must be qualified" was satisfied by essentially every paragraph in the
  file.
- `SHORT_SERIES` was written through a string-rewriting step that turned the
  intended `` word boundaries into two literal **backspace bytes** (`0x08`).
  The pattern therefore matched no text at all, and the assertion it fed was
  vacuously true.

Both looked green, and green was indistinguishable from working. **Inert rate:
2 of 7, 29%.** They were found by mutating the document to break each rule in
turn and confirming the corresponding test failed.

**The general rule.** A green result from a new check proves only that it did
not fire. It says nothing about whether it *can*. Treat every newly written
assertion as inert until a deliberately broken input has made it fail — and
note that the two defects here were of different kinds (one semantic, one an
encoding accident), so neither careful reading of the pattern nor careful
reading of the code would reliably have caught both.

**Why this is durable rather than advice.** The mutation exercise is itself a
test (`test_every_assertion_above_can_actually_fire`), asserting that the
patterns match text that must trip them and do not match text that must not. It
runs on every CI cycle. The rule therefore does not depend on anyone
remembering to apply it, which is the property that separates a control from a
good intention — the same distinction the model registry draws between a
validation gate and a README section.

