from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

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
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
def health():
    """Returns `{status: ok}` when the API is up."""
    return {"status": "ok"}
