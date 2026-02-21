#!/usr/bin/env bash
# start.sh — entrypoint for Railway / Render
#
# 1. Run Alembic migrations  (idempotent — safe on every deploy)
# 2. Start Gunicorn + Uvicorn workers
#
# Exit immediately on any error so the platform marks the deploy as failed
# instead of silently running with a broken schema.
set -euo pipefail

echo "==> [DIOS] Running database migrations..."
alembic upgrade head
echo "==> [DIOS] Migrations complete."

echo "==> [DIOS] Starting server on port ${PORT:-8000}..."
exec gunicorn app.main:app --config gunicorn.conf.py
