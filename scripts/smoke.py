"""End-to-end smoke test: train a tiny real model, serve it, hit the live API.

Unit tests check that pieces are individually correct in isolation; this
checks that the whole assembled chain — a trained model on disk -> the
service boots -> a real HTTP request -> a JSON response -> json.dumps() at
the monitoring layer -- actually works together. That boundary is exactly
where a real bug slipped past 88+ passing unit tests: explain.py's
predicted_probability carried a numpy.float32 into the API response, which
only crashes json.dumps() once a *real* trained model (not the `None`
fallback every unit test exercises) is loaded and hit through the live API.
See CLAUDE.md hard rule #4 for the full story and the regression test.

Deliberately does NOT shell out to scripts/train.py, which also runs
compare_classifiers()/walk_forward_evaluate() for diagnostic logging --
useful for a real training run, unneeded (and too slow to comfortably fit
a smoke test meant to run in well under two minutes) when the only thing
this script needs is a valid, loadable model artifact on disk.

Fully self-contained: trains into a temp directory (never touches
models/artefacts/), serves on an OS-assigned free port (never touches
whatever's on 8000), and points the server at a temp SQLite DB too — so it
doesn't collide with a developer's already-running dev server or pollute
any tracked/real state. Exit code reflects pass/fail for CI.
"""

from __future__ import annotations

import atexit
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

TICKERS = ["AAPL", "MSFT"]
LOOKBACK_DAYS = 365
READY_TIMEOUT_S = 45
HTTP_TIMEOUT_S = 30

# EX_TEMPFAIL: the smoke gate DID NOT run because Yahoo throttled the data
# fetch — distinct from exit 1 (a real app/harness failure) so CI can warn
# loudly and stay neutral instead of failing every push during an external
# outage. Verified live 2026-07-18/19: three consecutive CI runs died at
# this step with YFRateLimitError while the same commits' test suites
# passed, and the same workflow had passed smoke five times on 2026-07-17 —
# i.e. GitHub-runner IPs are *intermittently* rate-limited, so keeping the
# gate active (rather than deleting it from CI) still buys real coverage
# on the runs where Yahoo lets the fetch through.
EXIT_RATE_LIMITED = 75


def is_rate_limit_failure(exc: BaseException) -> bool:
    """True when *exc* is (or was caused by) yfinance's rate-limit error.

    Matched by class name and message rather than importing yfinance's
    exception type — smoke must be able to classify the failure even if the
    import context differs, and the message check catches re-wrapped errors.
    """
    seen: list[BaseException] = []
    e: BaseException | None = exc
    while e is not None and e not in seen:
        seen.append(e)
        if type(e).__name__ == "YFRateLimitError" or "Rate limited" in str(e):
            return True
        e = e.__cause__ or e.__context__
    return False


def _step(msg: str) -> None:
    print(f"[smoke] {msg}", flush=True)


def _rmtree_retry(path: Path, attempts: int = 5, delay_s: float = 0.3) -> None:
    """shutil.rmtree with retries — on Windows, SQLite's db file can still be
    handle-locked for a brief moment after the owning process is terminated,
    so a single rmtree attempt right after proc.wait() can race it and
    silently leave the directory behind (ignore_errors=True would hide it
    rather than actually clean up)."""
    for attempt in range(attempts):
        try:
            shutil.rmtree(path)
            return
        except FileNotFoundError:
            return
        except OSError:
            if attempt == attempts - 1:
                raise
            time.sleep(delay_s)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def train_tiny_model(model_dir: Path) -> None:
    """Fetch real data for TICKERS and fit+save a real DownsideRiskModel —
    the minimum needed to exercise the exact code path that broke in
    production (a *real* trained model loaded by RiskScorer), without
    train.py's extra diagnostic-only evaluation steps."""
    from stock_risk.data.fetcher import MarketDataFetcher
    from stock_risk.data.preprocessor import DataPreprocessor
    from stock_risk.features.risk_metrics import RiskMetrics
    from stock_risk.features.technical import TechnicalFeatures
    from stock_risk.models.downside_risk import DownsideRiskModel
    from stock_risk.models.feature_sets import build_dataset

    fetcher = MarketDataFetcher()
    preprocessor = DataPreprocessor()
    tech = TechnicalFeatures()
    risk = RiskMetrics()

    period = f"{LOOKBACK_DAYS // 365}y" if LOOKBACK_DAYS >= 365 else f"{LOOKBACK_DAYS}d"
    per_ticker_dfs = {}
    for ticker in TICKERS:
        raw = fetcher.fetch_history(ticker, period=period)
        df = preprocessor.process(raw)
        df = tech.compute(df)
        df = risk.compute(df)
        per_ticker_dfs[ticker] = df

    dataset = build_dataset(per_ticker_dfs)
    model = DownsideRiskModel()
    model.fit_calibrated(dataset)
    model.save(model_dir)


def _tail(log_path: Path, n_chars: int = 4000) -> str:
    try:
        text = log_path.read_text(errors="replace")
    except OSError:
        return "(could not read server log)"
    return text[-n_chars:]


def wait_for_health(
    base_url: str, proc: subprocess.Popen, log_path: Path, timeout_s: float
) -> None:
    deadline = time.time() + timeout_s
    last_error: Exception | None = None
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(
                f"server process exited early (code {proc.returncode})\n{_tail(log_path)}"
            )
        try:
            with urllib.request.urlopen(f"{base_url}/health", timeout=3) as resp:
                if resp.status == 200:
                    return
        except (urllib.error.URLError, ConnectionError, TimeoutError) as exc:
            last_error = exc
        time.sleep(0.5)
    raise TimeoutError(
        f"server did not become healthy within {timeout_s}s (last error: {last_error})"
    )


def check_json_endpoint(base_url: str, path: str) -> object:
    """GET *path*, assert HTTP 200 and a valid JSON body, return the parsed body."""
    url = f"{base_url}{path}"
    try:
        with urllib.request.urlopen(url, timeout=HTTP_TIMEOUT_S) as resp:
            status, body = resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        status, body = exc.code, exc.read()

    if status != 200:
        raise AssertionError(f"GET {path} -> HTTP {status}: {body[:500]!r}")
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise AssertionError(
            f"GET {path} -> response body is not valid JSON: {exc}\nbody={body[:500]!r}"
        )


def main() -> int:
    start = time.time()
    model_dir = Path(tempfile.mkdtemp(prefix="stock_risk_smoke_model_"))
    db_dir = Path(tempfile.mkdtemp(prefix="stock_risk_smoke_db_"))
    log_path = db_dir / "server.log"
    proc: subprocess.Popen | None = None

    def cleanup() -> None:
        nonlocal proc
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
        for path in (model_dir, db_dir):
            try:
                _rmtree_retry(path)
            except OSError as exc:
                print(f"[smoke] warning: could not remove temp dir {path}: {exc}", file=sys.stderr)

    atexit.register(cleanup)

    try:
        _step(f"training a tiny model on {TICKERS} ({LOOKBACK_DAYS}d lookback) -> {model_dir}")
        train_tiny_model(model_dir)

        port = _free_port()
        base_url = f"http://127.0.0.1:{port}"
        env = {
            **os.environ,
            "MODEL_DIR": str(model_dir),
            "DB_PATH": str(db_dir / "smoke.db"),
        }

        # Redirect to a real file, not subprocess.PIPE: loguru's exception
        # formatting (diagnose=True by default) dumps full tracebacks with
        # per-frame local-variable values, which is easily large enough to
        # fill the OS pipe buffer if nothing drains it. Nothing here reads
        # the pipe while polling for health / making requests, so a PIPE
        # would make uvicorn block on its own stdout write the moment it hit
        # exactly the kind of crash this script exists to catch — silently
        # turning "server returned 500 fast" into "client request hangs
        # until the timeout," which is a much more confusing failure mode.
        _step(f"starting uvicorn on {base_url} (MODEL_DIR={model_dir}, log={log_path})")
        with open(log_path, "w") as log_file:
            proc = subprocess.Popen(
                [
                    sys.executable, "-m", "uvicorn", "stock_risk.api.app:app",
                    "--host", "127.0.0.1", "--port", str(port),
                ],
                cwd=str(ROOT),
                env=env,
                stdout=log_file,
                stderr=subprocess.STDOUT,
            )

            wait_for_health(base_url, proc, log_path, READY_TIMEOUT_S)
            _step("service is healthy")

        health = check_json_endpoint(base_url, "/health")
        assert health.get("status") == "ok", f"/health body missing status=ok: {health}"
        _step("GET /health -> 200, status=ok")

        score = check_json_endpoint(base_url, "/api/score/AAPL")
        for key in ("risk_score", "risk_label", "risk_breakdown"):
            assert key in score, f"/api/score/AAPL missing key {key!r}: {list(score.keys())}"
        _step(
            f"GET /api/score/AAPL -> 200, "
            f"risk_score={score['risk_score']} risk_label={score['risk_label']}"
        )

        timeseries = check_json_endpoint(base_url, "/api/score/AAPL/timeseries")
        assert isinstance(timeseries, list) and len(timeseries) > 0, (
            f"/api/score/AAPL/timeseries expected a non-empty list, "
            f"got: {type(timeseries).__name__}"
        )
        for key in ("date", "risk_score", "close"):
            assert key in timeseries[0], (
                f"timeseries[0] missing key {key!r}: {list(timeseries[0].keys())}"
            )
        _step(f"GET /api/score/AAPL/timeseries -> 200, {len(timeseries)} points")

        elapsed = time.time() - start
        _step(f"ALL CHECKS PASSED in {elapsed:.1f}s")
        return 0

    except Exception as exc:
        elapsed = time.time() - start
        # Server-log check covers the case where the rate limit hits inside
        # the *served* process (scoring request 500s -> our assertion raises
        # a plain AssertionError, but the server log carries the real cause).
        # Sound in this harness specifically: no smoke request before the
        # scoring calls triggers a yfinance fetch, so a YFRateLimitError in
        # the log can only belong to the request whose failure we're
        # classifying — not some unrelated earlier one.
        rate_limited = is_rate_limit_failure(exc) or (
            log_path.exists() and "YFRateLimitError" in _tail(log_path)
        )
        if rate_limited:
            _step(
                f"SKIPPED after {elapsed:.1f}s — Yahoo rate-limited the data fetch "
                f"(exit {EXIT_RATE_LIMITED}). The smoke gate DID NOT run: this is "
                "a skip, not a pass. Rerun once the limit clears."
            )
            return EXIT_RATE_LIMITED
        _step(f"FAILED after {elapsed:.1f}s: {exc}")
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
        if log_path.exists():
            print("\n[smoke] server log (tail):\n" + _tail(log_path), file=sys.stderr)
        return 1
    finally:
        cleanup()


if __name__ == "__main__":
    sys.exit(main())
