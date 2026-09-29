# Collected-test baselines

One file per mainline commit, named by the full 40-character sha, holding the
output of `pytest --collect-only -q` with the timing summary stripped: one
collected test id per line, so the line count *is* the count, and the file
describes the commit in its name, not whatever `HEAD` happens to be.
**Reconciliation rule:** a pytest count reported anywhere (a PR body, a ledger
entry, CLAUDE.md §2) is a baseline only if the archive for the sha it was
measured at exists here; when a run at a newer sha collects a different
number, the delta is explained by diffing that run's id list against the
archived one and naming the ids that appeared or disappeared, never by
adopting the new number. A count that moves with no id-level explanation is an
open discrepancy and is reported as one. `tests/test_baselines.py` fails if an
archived sha does not resolve to a commit reachable from `origin/main`, so a
rebase that rewrites the sha, or an archive taken on an unpushed branch, is
loud rather than silently stale. Refresh from a clean checkout of the commit
being archived, and commit the file in the same change that cites the count:

```bash
.venv/bin/python -m pytest --collect-only -q | grep '::' > ".baselines/$(git rev-parse HEAD).txt"
```
