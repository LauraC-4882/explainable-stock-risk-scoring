# CLAUDE.md

Project-level instructions for Claude Code sessions in this repo. Every rule
below is paired with a command that verifies it — if a rule can't be checked
by running something, it doesn't belong here.

All facts in this file were verified against the actual repo state on
2026-07-16/17 (Windows dev machine, Python 3.10.6, ubuntu-latest CI on
Python 3.11) — not assumed. If something here stops matching reality, fix
the file in the same PR that breaks it.

## 1. Environment

- **Interpreter**: a project-local virtualenv, not the system Python.
  - Windows: `.venv\Scripts\python.exe`
  - macOS/Linux (and what CI would use if it created a venv — it currently
    doesn't, see below): `.venv/bin/python`
- **Setup** (matches `make install` and `.github/workflows/ci.yml`):
  ```bash
  python -m venv .venv
  .venv/bin/python -m pip install -e ".[dev]"
  ```
  CI itself (`ubuntu-latest`, Python 3.11) skips the venv step and installs
  straight into the runner with plain `pip install -e ".[dev]"` — that's the
  one command every environment variant (your local venv, CI, a fresh
  contributor clone) has in common, so it's the one to trust if something
  else in this section drifts.
- **`shap==0.49.1`, pinned exactly, not left as `shap>=0.45`.** XGBoost 3.x
  changed how `base_score` is serialized, and shap 0.49.1 cannot parse the
  new format (`ValueError: could not convert string to float: '[5E-1]'`) —
  that's why `xgboost>=2.0,<3.0` is also pinned in `requirements.txt` and
  `setup.py`, with a comment on that exact line explaining why. Checked
  2026-07-17: `0.49.1` is currently the *latest* shap release on PyPI (`pip
  index versions shap`), so an unbounded `>=0.45` isn't actively broken
  today — but it has no upper bound stopping a future shap release from
  reintroducing the same incompatibility silently on a fresh install. The
  exact pin removes that risk instead of hoping it doesn't recur.
  ```bash
  .venv/bin/python -m pip show shap xgboost | grep -E "Name|Version"
  # Version: 0.49.1   (shap)
  # Version: 2.1.4    (xgboost, or anything <3.0)
  ```

## 2. Verification commands

| Command | Status | What it checks |
|---|---|---|
| `.venv/bin/python -m pytest tests/ -q` | **live** — 104 passed, 0 failed as of 2026-07-17 | Full test suite |
| `.venv/bin/python -m ruff check src/ tests/` | **live** — clean as of 2026-07-17 | Lint |
| `make smoke` (→ `python scripts/smoke.py`) | **live** — [D1] landed 2026-07-17; ~11s locally, exit 0 | End-to-end: train a real tiny model, serve it, hit `/health` + `/api/score/AAPL` + `/api/score/AAPL/timeseries` over real HTTP, assert 200 + valid JSON + expected keys |
| `bash scripts/ui_shot.sh` | **live** — [D2] landed 2026-07-17; ~15-20s locally, exit 0 | Frontend screenshot round-trip: build, serve (mock data, no network — see below), Playwright-screenshot a real card at 1280px + 375px to `$UI_SHOT_OUT_DIR` (default `/tmp`) |

`make smoke` red/green-tested against the exact bug in rule 4 below: run
against the pre-fix `explain.py` and it fails in ~10s with the real
`TypeError: Object of type float32 is not JSON serializable` traceback in
its output; run against the fix and it passes. Self-contained (temp model
dir, temp DB, OS-assigned free port — never touches `models/artefacts/`,
a developer's real DB, or port 8000) and self-cleaning (temp dirs and the
server subprocess are gone whether it passes or fails).

`scripts/ui_shot.sh` runs against `STOCK_RISK_MOCK=1` (fixture data captured
from a real `/api/score/TSLA` + `/api/score/TSLA/timeseries` response,
`tests/fixtures/mock_api/`), not a live yfinance call — a real request takes
~2.7s and would make repeated screenshot runs slow and network-flaky, and
this harness verifies the UI renders correctly, not that the data is fresh.
Verified mock mode never touches the network by routing `HTTP_PROXY`/
`HTTPS_PROXY` to a dead host (with `NO_PROXY=127.0.0.1` so the harness's own
localhost health check still works) and confirming the script still exits 0.
Self-cleaning like `make smoke`: `trap cleanup EXIT INT TERM` kills the
server on any exit path, checked by confirming nothing is left listening on
its port afterward.

## 3. Hard rules

Every rule here is a **must**, each with the command that proves you did it.

1. **Any backend change → run the test suite *and* the smoke test before
   calling it done.** Unit tests alone already missed the bug in rule 4 —
   every unit test uses `RiskScorer` with no model loaded (the `None`
   fallback path), so none of them ever exercised a real trained model
   through a real HTTP response the way `make smoke` does.
   ```bash
   .venv/bin/python -m pytest tests/ -q
   make smoke   # or: .venv/bin/python scripts/smoke.py
   ```
   Both must exit 0.

2. **Any `ui/web` change → run `scripts/ui_shot.sh` and look at both PNGs,
   self-review against `scripts/ui_checklist.md`, iterate up to 3 rounds,
   attach the final screenshots to the PR.** A clean `npm run build` proves
   the bundler is happy, not that the feature works — `ui_shot.sh` builds,
   serves mock data, and Playwright-screenshots a real populated card at
   desktop (1280px) and mobile (375px) widths.
   ```bash
   bash scripts/ui_shot.sh
   # then actually open $UI_SHOT_OUT_DIR/ui-desktop.png and .../ui-mobile.png
   # (default /tmp) and check every item in scripts/ui_checklist.md against
   # the pixels — a blank/broken/503 render, or a checklist item you can't
   # point at specific pixels to justify, is a fail, not a pass.
   ```
   One checklist item (the gauge vs. daily-risk-score-chart consistency
   check) is *expected* to currently fail — that's [E1]'s bug, not a
   regression in whatever you just changed; don't "fix" the checklist by
   deleting the item.

3. **Every new `except Exception` must either log or explain the silence.**
   No bare `except Exception: pass`-style swallowing.
   ```bash
   grep -A1 "except Exception" <changed-file>
   # the line right after must be either a logger.* call, or a comment
   # explaining why swallowing it silently is correct here
   ```
   Current state (audited 2026-07-17, `grep -rn "except Exception" src/ |
   wc -l` → 15): 14/15 already log or comment; the one violation
   (`api/app.py`'s legacy `/score/{ticker}` — silently swallowed, no log)
   was found and fixed in this same session by adding `logger.exception`.

4. **Any numeric value must be a native Python type (`float()`/`int()`)
   before it reaches an API response — never a bare `numpy` scalar.**
   `numpy.float64` happens to subclass `float` so it slips past `json.dumps`
   undetected, but `numpy.float32` (XGBoost's and SHAP's native dtype) does
   **not** subclass `float` and raises `TypeError: Object of type float32 is
   not JSON serializable` the moment it reaches `ModelMonitor.record()`.
   ```bash
   .venv/bin/python -c "
   from stock_risk.scoring.scorer import RiskScorer
   result = RiskScorer().score('AAPL')

   def walk(o, path=''):
       if isinstance(o, dict):
           for k, v in o.items(): walk(v, f'{path}.{k}')
       elif isinstance(o, list):
           for i, v in enumerate(o): walk(v, f'{path}[{i}]')
       elif type(o).__module__ == 'numpy' and not isinstance(o, (float, int)):
           print(f'LEAK: {path} = {type(o).__name__}')
   walk(result)
   "
   # must print nothing
   ```
   This is not hypothetical: reproduced live in this session by training a
   real model and hitting `/api/score/AAPL` — `explain.py`'s
   `predicted_probability` carried a `numpy.float32` from
   `values.sum()` (SHAP's raw output dtype) straight into the response dict,
   and `monitor.record()`'s `json.dumps()` 500'd on it. Fixed by casting to
   `float()` before it enters the result dict; regression test at
   `tests/test_explain.py::test_explain_prediction_is_json_serializable`
   (json-dumps the real explanation dict, asserts every numeric leaf is a
   native Python `float`). Verified the test actually catches the
   regression by reverting the fix and re-running it — it fails with the
   exact same `TypeError` before the fix, passes after.

## 4. Definition of Done

A change is done when all three are true, and the PR description says so
with the actual evidence attached (not "should work" — the real output):

1. **Tests pass.** Paste the tail of `.venv/bin/python -m pytest tests/ -q`
   (pass count, not just "green").
2. **Harness passes.** `make smoke` output once [D1] lands; a real
   screenshot PNG (not a description of one) for any UI change.
3. **PR description has before/after evidence** for the actual bug/feature —
   e.g. "before: `curl .../api/score/AAPL` → `500 {"detail": "Internal
   scoring error"}`; after: `200` with the real JSON body," not just "fixed
   the bug."

---

*Note on provenance: the issue that prompted this file claimed Python
3.12.13 via `uv`, a `.venv/bin/python` layout, "67 tests with 1 known
failure," and shap resolving to a nonexistent `0.52` release. None of that
matched this repo when checked — actual local venv is plain `venv` on
Python 3.10.6, CI is Python 3.11, the suite was 89/89 passing, and 0.49.1 is
PyPI's actual latest shap release. Everything above reflects what was
verified, not what was claimed. If you're reading this from a later
snapshot of this project and the numbers no longer match, re-run the
commands in §2 and trust what they print over what this file says.*
