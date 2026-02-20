from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import ingest as ingest_router
from app.routers import state as state_router

app = FastAPI(
    title="DIOS App API",
    description=(
        "Deterministic Ingest and Orchestration System — "
        "routes raw text entries to domain tables and tracks daily state."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ingest_router.router)
app.include_router(state_router.router)


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok"}
