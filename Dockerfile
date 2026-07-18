# Hugging Face Spaces (Docker SDK) build — see README.md's "Deployment" section
# for the [F3] rationale (full ML+SHAP leg, vs. [F2] Render's ENABLE_ML=0 cut-down
# deploy). HF requires this Dockerfile at the repo root, distinct from
# docker/Dockerfile (Render/docker-compose target: port 8000, no model artefact,
# runs as root — none of which fit HF's constraints, see below).

# ── Stage 1: build the React frontend ──────────────────────────────────────
FROM node:20-slim AS frontend
WORKDIR /app/ui/web
COPY ui/web/package.json ui/web/package-lock.json* ./
RUN npm install
COPY ui/web/ ./
RUN npm run build

# ── Stage 2: Python API, serving the built frontend + a real ML model ───────
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY configs/ ./configs/
COPY setup.py .

RUN pip install -e .

COPY --from=frontend /app/ui/web/dist/ ./ui/web/dist/

# Baked into the image rather than trained at build time: training isn't
# reproducible build-to-build (real yfinance data changes daily) and would
# make every image build slow and non-deterministic for no benefit — this is
# a small (553KB), already-validated artefact, not something regenerated per
# deploy. See .gitignore's negated `!models/artefacts/downside_risk_xgb.joblib`
# for why this one file is tracked despite the rest of models/artefacts/ not being.
COPY models/artefacts/ ./models/artefacts/

# HF Spaces runs the container as a non-root user (uid 1000) with /app owned
# by root by default. config.py's Settings.model_post_init() calls mkdir() on
# model_dir/monitoring_log_dir/db_path.parent at import time — under a
# non-writable /app that fails immediately as a permission error before
# uvicorn ever starts, so /app needs to be owned by the user the process
# actually runs as, not just "not root" for its own sake.
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# HF Spaces expects the container to listen on 7860 by default (vs. Render's
# $PORT convention / docker/Dockerfile's 8000) — see this repo's root
# README.md front-matter (app_port: 7860) for the platform-side half of this.
EXPOSE 7860

CMD ["uvicorn", "src.stock_risk.api.app:app", "--host", "0.0.0.0", "--port", "7860"]
