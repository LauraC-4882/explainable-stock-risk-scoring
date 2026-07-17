#!/usr/bin/env bash
# Visual regression harness: build -> serve (mock data, no network) -> screenshot
# desktop + mobile -> exit non-zero on any failure. See scripts/ui_checklist.md
# for what to look for in the two screenshots afterward (this script only
# captures them, it doesn't grade them — that's the "AI looks at the PNG" step).
#
# Mock mode (STOCK_RISK_MOCK=1) means this never touches yfinance: a real
# /api/score/{ticker} call takes ~2.7s and would make repeated screenshot runs
# slow and network-flaky, and the point of this harness is "does the UI render
# correctly," not "is the data fresh." Fixtures are a real captured response
# (tests/fixtures/mock_api/), including the actual gauge-vs-chart score
# mismatch this repo currently has — the harness isn't supposed to hide that,
# it's supposed to make it visible (see scripts/ui_checklist.md's last item).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PORT="${UI_SHOT_PORT:-8971}"
BASE_URL="http://127.0.0.1:${PORT}"
OUT_DIR="${UI_SHOT_OUT_DIR:-/tmp}"
SERVER_LOG="$(mktemp)"

# Windows venvs use Scripts/python.exe; everything else uses bin/python — see
# CLAUDE.md's Environment section for why both are documented, not just one.
if [ -x "$ROOT/.venv/Scripts/python.exe" ]; then
  PYTHON="$ROOT/.venv/Scripts/python.exe"
elif [ -x "$ROOT/.venv/bin/python" ]; then
  PYTHON="$ROOT/.venv/bin/python"
else
  echo "[ui_shot] no .venv interpreter found (checked Scripts/python.exe and bin/python)" >&2
  exit 1
fi

SERVER_PID=""
cleanup() {
  local exit_code=$?
  if [ -n "$SERVER_PID" ]; then
    kill "$SERVER_PID" >/dev/null 2>&1 || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
  rm -f "$SERVER_LOG"
  exit $exit_code
}
trap cleanup EXIT INT TERM

echo "[ui_shot] building frontend..."
(cd ui/web && npm run build) || { echo "[ui_shot] npm run build failed" >&2; exit 1; }

echo "[ui_shot] starting uvicorn (mock mode) on port ${PORT}..."
STOCK_RISK_MOCK=1 "$PYTHON" -m uvicorn stock_risk.api.app:app --host 127.0.0.1 --port "$PORT" \
  > "$SERVER_LOG" 2>&1 &
SERVER_PID=$!

echo "[ui_shot] waiting for /health..."
ready=0
for _ in $(seq 1 30); do
  # --noproxy '*': an ambient HTTP_PROXY/HTTPS_PROXY (common in corporate
  # networks, and used deliberately here to test that mock mode survives a
  # broken external network) would otherwise route this *localhost* health
  # check through the proxy too and make it fail/hang for reasons that have
  # nothing to do with whether the server is actually up.
  if curl -sf --noproxy '*' "${BASE_URL}/health" >/dev/null 2>&1; then
    ready=1
    break
  fi
  if ! kill -0 "$SERVER_PID" >/dev/null 2>&1; then
    echo "[ui_shot] server process exited early:" >&2
    cat "$SERVER_LOG" >&2
    exit 1
  fi
  sleep 1
done
if [ "$ready" -ne 1 ]; then
  echo "[ui_shot] server never became healthy within 30s:" >&2
  cat "$SERVER_LOG" >&2
  exit 1
fi
echo "[ui_shot] service is healthy"

echo "[ui_shot] capturing screenshots..."
if ! "$PYTHON" "$ROOT/scripts/ui_shot.py" --base-url "$BASE_URL" --out-dir "$OUT_DIR"; then
  echo "[ui_shot] screenshot capture failed — server log:" >&2
  cat "$SERVER_LOG" >&2
  exit 1
fi

echo "[ui_shot] done: ${OUT_DIR}/ui-desktop.png, ${OUT_DIR}/ui-mobile.png"
