# Session ledger — found, not yet fixed

Defects and gaps that have been **identified and characterised** but
deliberately **not** fixed in the change that found them, with the reason for
deferring. Nothing here is a vague "we should look at this some time": each
entry names the file and line, states the impact with a measurement, and
proposes a fix.

The point of writing them down is that a finding deferred without a record is a
finding lost. The point of deferring them at all is that a documentation change
and an interface change do not belong in one pull request.

An entry whose fix has since landed keeps its text as written and gains a
**Status** line naming the commit and the test that pins the fix. Nothing is
marked fixed on the strength of a commit alone.

---

## 0. A write in the `pit2` worktree was reverted, and no record names by whom

**Class** Shared mutable state — the same family as entry 7 (a branch ref
moved under a working tree) and the 2026-08-28 concurrent clobber of the notes
ledger. Recorded as an *observed instance*, dated from reflogs, file
timestamps and commit times. The cause was not determined and is not guessed
at here.

**The two worktrees** `riscore-worktrees/pit2` (branch
`fix/conflict1-pin-reconciliation`) and `riscore-worktrees/fix-migration`
(branch `verify/alpha-roc-mutation`, later `main`). Both hang off the one
shared `.git`, so every reflog below is visible from either.

**Timeline** (local time, UTC-7; the right-hand column is where each row was
read from)

| when | what | source |
|---|---|---|
| 2026-09-02 18:01:02 | `origin/main` fast-forwards to `b44678a`, the rebase-merged batch of PRs that left main red: 829 passed, 1 failed, the failure being the conflict-1 inventory pin | `refs/remotes/origin/main` reflog |
| 2026-09-02 18:01:58 | fix-migration checks out `verify/alpha-roc-mutation` at `b44678a` | `worktrees/fix-migration/HEAD` reflog |
| 2026-09-02 18:02:18 | pit2 checks out `origin/main` (`b44678a`). Every tracked file in pit2 carries this mtime, and none carries a later one | pit2 `HEAD` reflog; `ls --time-style=full-iso` over `git ls-files` |
| 2026-09-02 18:05:41 | pit2 records its baseline, `baseline_b44678a.log`: 1 failed / 829 passed | ignored log, mtime and content |
| 2026-09-02 18:06:08 | pit2 creates `fix/conflict1-pin-reconciliation` from `b44678a` and rewrites its index. The branch never receives a commit | branch reflog; `worktrees/pit2/index` mtime |
| 2026-09-11 20:55:48 | fix-migration commits the pin inversion on `verify/alpha-roc-mutation`; pushed four seconds later | `worktrees/fix-migration/HEAD` reflog; `refs/remotes/origin/verify/alpha-roc-mutation` reflog |
| 2026-09-11 20:59:02 | pit2 runs the full suite, `recon_pytest.log`: **still 1 failed / 829 passed, the same test**. The tree pit2 measured did not contain the inversion | ignored log, mtime and content |
| 2026-09-11 20:59:20 to 21:00:37 | pit2 runs vitest, `recon_vitest.log`: 176 passed | ignored log |
| 2026-09-11 22:09:00 | the inversion reaches main as `61fdee8` (#45, squash) | commit time |

**What the worktree shows now** pit2 is clean, its branch has zero commits
beyond `b44678a`, no tracked file has an mtime later than the 18:02:18
checkout, no stash was taken from it, and no dangling commit in the shared
object store is dated inside the window (the newest is 2026-08-31 21:46:07).
A filesystem search for anything in pit2 modified after 18:07 on the 2nd
returns only ignored run artefacts: the two `recon_*.log` files, a ruff cache
entry and `logs/monitoring/AAPL.jsonl`, all written by the 20:59 run itself.
The reported write left nothing that git or the filesystem retains. That
absence is the observation worth keeping: **a write to a worktree on a shared
checkout can be undone with no record for at least nine days** (18:06:08 on
the 2nd to 20:59:02 on the 11th), and it was noticed only because the same
work was committed from a different worktree and pit2's own run disagreed
with it.

**Not concluded here** who or what reverted it, or whether it was a checkout,
a stash, a tool, or an edit that never reached disk. The evidence is
consistent with more than one of those, and this record does not choose.

**What it adds to entry 7's rule** "Confirm `HEAD` and the tree agree before
reading the count" has a blind spot for a complete revert: the tree agrees
with `HEAD` *because* the work is gone. The mitigation that does not depend
on anyone noticing is the one the notes ledger already states — coordinate
through git refs (commit and push early), never through the state of a
worktree.

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

**Status (2026-09-28)** Fixed at `1736ddd`: the sample is declared in
`snapshots/validation_manifest.txt`, a listed file missing from disk raises,
and a missing manifest raises rather than falling back to the glob.
Verification:
`tests/test_validation_manifest.py::test_the_sample_comes_from_the_manifest_not_the_directory`,
with `test_a_missing_manifest_is_fatal_rather_than_falling_back` and
`test_the_loader_does_not_select_by_globbing` as the counter-examples.

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

**Status (2026-09-28)** Fixed at `fc58109`: the realised-loss series reads
`log_return`, the convention the forecast was estimated from, and a mismatched
pairing is refused. Verification:
`tests/test_tail_return_convention.py::test_realised_losses_use_the_forecast_convention`
and `::test_a_mismatched_pairing_is_refused`. The inventory pin that recorded
the defect was inverted at `61fdee8` so it now guards the fix.

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

**It happened a second time, and the second time was dangerous.** Preparing the
very pull request that added this entry, the same sequence ran again: rebase
onto `origin/main` in a worktree, `update-ref`, count 132 → 137. This time the
five paths reported as modified were `.github/workflows/ci.yml`,
`src/stock_risk/db.py`, `tests/conftest.py`, `tests/test_data.py` and
`tests/test_migrations.py` — files the working tree still held at their
*pre-`origin/main`* content. **Committing from that state would have reverted
the contents of two already-merged pull requests.**

**Why that is hard to catch in review, which is the actual severity.** The
failure does not present as an error. It presents as an ordinary commit whose
diff says "5 files changed", on a branch whose stated subject is something else
entirely — so those files read as incidental drive-by edits rather than as a
revert. Nothing in the diff announces that the "new" content is older than what
is on the mainline; a reviewer would have to already suspect the problem and go
looking for it. The first occurrence cost nothing and produced only a confusing
number. The second could have silently undone merged work, and the only reason
it did not is that the count anomaly was recognised from having just written
this entry.

**Root fix, adopted** Push first; move the local ref only after the push
succeeds. The original ordering was the reverse — `update-ref` then push — so
when the push failed the ref had already been moved and the tree was left
inconsistent with no operation having completed. With the corrected ordering a
failed push leaves everything exactly as it was, and the ref only ever moves to
a commit that is known to exist on the remote.

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

---

## 8. The docs gate caught its own author three times, and the rule held each time

Three separate occasions in this session, `tests/test_docs_consistency.py`
failed on text written **in the same change that was adding or relying on the
gate**:

| # | What tripped it | Assertion | Resolution |
|---|---|---|---|
| 1 | `SESSION_LEDGER.md` quoted the retracted Kupiec statistic while explaining why it was retracted | 1 — retracted numbers | Wrapped in a `historical-record` anchor |
| 2 | A newly written README bullet said "under the old `var_95_21d` estimator" with no qualifier | 3 — the short-window series must be qualified | Added "now retained only as a scoring feature" |
| 3 | Ledger entry 6 named `var_95_21d` while describing the very correction that qualifies it | 3 — same assertion | Rewrote the sentence to carry the qualification |

**Every one was resolved by changing the text, never by relaxing the
assertion.** That is the part worth recording, and it is why these belong in one
entry rather than three footnotes: separately they are three small edits;
together they are evidence.

**Why the repetition is evidence rather than noise.** A rule bent the first time
it becomes inconvenient is not a rule; it is a preference with a test attached.
Three consecutive opportunities to widen a pattern — each with a
reasonable-sounding justification available ("it is only a ledger", "the bullet
is obviously about the old estimator", "this sentence is literally explaining
the distinction") — and the pattern was not widened once. The assertion is as
strong now as when it was written, which is not true of most checks that
survive contact with their own authors.

**Why it also validates the coverage.** All three catches landed on text written
*after* the gate existed, by the person who wrote the gate. A checker built by
grepping for known-bad historical strings would have gone quiet as soon as the
old text was cleaned up; this one kept finding new violations in new prose,
including prose whose subject was the rule itself. Assertion 3 is doing real
work rather than pattern-matching a fixed corpus.

**A fourth instance, of a different kind — and the gate did not catch this
one.** The paragraph in this file describing how `SHORT_SERIES` was broken by
two literal backspace bytes **itself contained two literal backspace bytes**,
introduced by the same class of string-rewriting step, and was committed and
merged that way. The docs gate has no control-character assertion, so nothing
flagged it; it was noticed by reading the rendered file. Recorded because it is
the strongest available argument for the rule in the methodology section below:
the author of a defect, writing the account of that defect, immediately after
fixing it, reproduced it. Careful reading is not a control.

**Suggested (not done in this round, which is documentation-only)** Add an
eighth assertion to `tests/test_docs_consistency.py`: no tracked text file may
contain a C0 control character other than tab, LF or CR. It is three lines, it
has no false-positive surface, and it would have caught this instance and the
`SHORT_SERIES` one before either reached a commit. Both defects were introduced
by the same mechanism — a string-rewriting step where an escape sequence was
interpreted one layer earlier than intended — so the class is worth a check
even though each instance looks like a one-off.

## 9. Test-count baselines: vitest 171 to 176, and the 764-era pytest list

**Vitest, observed** 171 was measured in the pit2 worktree at `2f232b2`
(notes ledger, 2026-08-31: "unchanged, no frontend diff"). 176 was measured at
`61fdee8` (the #45 squash) and again in this round at `a67eb22`, this change's
base: 20 files, 176 passed. Between the two measurements exactly one vitest
file changed on main:

| file | commit | when | change |
|---|---|---|---|
| `ui/web/src/i18n/locales/locales.test.js` | `677cb52` (additive-gates batch), reformatted by `e155f30` | 2026-09-02 17:59:44 | +90 lines: the five zh residual-English gate tests |

`git diff --stat 2f232b2 61fdee8` over `ui/web/**/*.test.*` lists that file
and nothing else, and `git diff 61fdee8 a67eb22 -- ui/web/` is empty. The
delta is +5, the locale-gate tests, exactly as the notes ledger predicted
before the batch landed ("176 passed (= 171 + 5, prediction hit)").

**A correction to how this round was briefed** The brief attributed the delta
to "the file list that arrived via the #45 squash (AlertSettings.test.jsx,
GovernancePanel.test.jsx, ...)". Git does not support that: `61fdee8` touches
`docs_internal/KUPIEC_POWER_ANALYSIS.md`, `tests/test_kupiec_power.py` and
`tests/test_return_convention_inventory.py`, and no file under `ui/`. The two
named test files were added by `b7786ce` on 2026-08-13, eighteen days before
the 171 measurement, so they were already inside it. Recorded as briefed, then
contradicted, rather than adjusted to fit.

**The 764-era pytest collected list: closed as unrecoverable** "764 passed,
0 failed as of 2026-08-11" exists only in the uncommitted `CLAUDE.md` of the
main checkout; the tracked copy on main still says 610 as of 2026-08-07. No
`--collect-only` output was archived beside either number, the venv and
working tree that produced them have moved on, and the commits since have
added and reshaped test modules, so the list of ids behind 764 cannot be
rebuilt from anything this repository holds. Closed, not deferred. The rule
that stops a repeat is the one `.baselines/` now enforces: a count is a
baseline only when the collected list it summarises is archived next to it
under the sha that produced it.

---

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

- `QUALIFIER` accepted a bare `feature\b`. That word appears in roughly half
  the paragraphs of a project README, so the rule "a mention of the short-window
  series must be qualified" was satisfied by essentially every paragraph in the
  file.
- `SHORT_SERIES` was written through a string-rewriting step that turned the
  intended `\b` word boundaries into two literal **backspace bytes** (`0x08`).
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

