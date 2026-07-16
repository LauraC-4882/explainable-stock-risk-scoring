# ── Stage 1: build the React frontend ──────────────────────────────────────
FROM node:20-slim AS frontend
WORKDIR /app/ui/web
COPY ui/web/package.json ui/web/package-lock.json* ./
RUN npm install
COPY ui/web/ ./
RUN npm run build

# ── Stage 2: Python API, serving the built frontend ─────────────────────────
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY configs/ ./configs/
COPY setup.py .

RUN pip install -e .

COPY --from=frontend /app/ui/web/dist/ ./ui/web/dist/

EXPOSE 8000

CMD ["uvicorn", "src.stock_risk.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
