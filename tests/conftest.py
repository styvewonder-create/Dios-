"""
Shared pytest fixtures.

Uses an in-memory SQLite database so no Postgres is required for tests.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base, get_db
from app.main import app
from app.models.rule import RuleRouter

SQLITE_URL = "sqlite:///./test_dios.db"

engine = create_engine(SQLITE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

_DEFAULT_RULES = [
    ("task_prefix",      r"^(TODO|TASK|tarea|hacer)",                     "tasks",          "task",        100),
    ("income_keyword",   r"(ingreso|income|cobré|cobr)",                   "transactions",   "transaction",  90),
    ("expense_keyword",  r"(gast|pagué|pague|compré|compre|expense|paid)", "transactions",   "transaction",  80),
    ("fact_keyword",     r"^(FACT|DATO|nota|note):",                       "facts",          "fact",         70),
    ("metric_keyword",   r"^(METRIC|METRICA|KPI):",                        "metrics_daily",  "metric",       60),
    ("project_keyword",  r"^(PROJECT|PROYECTO):",                          "projects",       "project",      50),
    ("default_note",     r".*",                                            "facts",          "note",          0),
]


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="session", autouse=True)
def create_tables():
    Base.metadata.create_all(bind=engine)
    # Seed default routing rules (normally done by Alembic migration)
    db = TestingSessionLocal()
    try:
        if db.query(RuleRouter).count() == 0:
            for name, pattern, target, entry_type, priority in _DEFAULT_RULES:
                db.add(RuleRouter(
                    name=name,
                    pattern=pattern,
                    target=target,
                    entry_type=entry_type,
                    priority=priority,
                    is_active=True,
                ))
            db.commit()
    finally:
        db.close()
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture()
def client(db):
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
