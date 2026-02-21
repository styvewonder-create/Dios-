"""
Gunicorn configuration for DIOS production server.

Tuned for Railway / Render single-instance containers.
Env vars that override defaults:
  PORT     — TCP port to bind (Railway sets this automatically)
  WORKERS  — number of worker processes (default: 2)
"""
import os

# Bind to the port Railway/Render injects via $PORT
bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"

# 2 workers is safe for a 512 MB container.
# Increase to 4 on the $10 Railway plan (1 GB RAM).
workers = int(os.environ.get("WORKERS", "2"))

# Each worker runs Uvicorn's ASGI event loop inside Gunicorn's process manager.
worker_class = "uvicorn.workers.UvicornWorker"

# Keep connections alive for 5 s between requests (good for mobile clients).
keepalive = 5

# Kill a worker that hasn't responded in 120 s (prevents zombie workers).
timeout = 120

# Structured logging — stdout only (Railway / Render capture it automatically).
loglevel = "info"
accesslog = "-"
errorlog = "-"
access_log_format = '%(h)s "%(r)s" %(s)s %(b)sB %(D)sµs'

# Graceful restart: wait up to 30 s for in-flight requests to finish.
graceful_timeout = 30
