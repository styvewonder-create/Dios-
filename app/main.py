from fastapi import FastAPI, Depends
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.db.base import get_db
from app.core.config import settings
from app.routers import ingest as ingest_router
from app.routers import state as state_router
from app.routers import memory as memory_router
from app.routers import metrics as metrics_router
from app.routers import behavior as behavior_router
from app.core.errors import (
    DIOSException,
    dios_exception_handler,
    validation_exception_handler,
    unhandled_exception_handler,
)

app = FastAPI(
    title="DIOS App API",
    description=(
        "**Deterministic Ingest and Orchestration System**\n\n"
        "Routes raw text entries to domain tables via a priority-ordered rule engine "
        "and exposes daily-state endpoints.\n\n"
        "All error responses follow the `{code, message, details}` envelope."
    ),
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Exception handlers (most specific first) ---
app.add_exception_handler(DIOSException, dios_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

# --- Routers ---
app.include_router(ingest_router.router)
app.include_router(state_router.router)
app.include_router(memory_router.router)
app.include_router(metrics_router.router)
app.include_router(behavior_router.router)


@app.get("/health", tags=["health"], summary="Health check")
def health(db: Session = Depends(get_db)):
    """
    Returns `{"status": "ok", "db": "ok"}` when both the API and the database
    are reachable. Returns HTTP 503 if the DB is down.
    Used by Railway / Render for liveness probes.
    """
    try:
        db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception:
        db_status = "unreachable"

    if db_status != "ok":
        return JSONResponse(
            status_code=503,
            content={"status": "error", "db": db_status},
        )
    return {"status": "ok", "db": "ok", "env": settings.APP_ENV}
