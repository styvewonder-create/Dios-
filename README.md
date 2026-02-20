# DIOS App — Backend

**Deterministic Ingest and Orchestration System**

FastAPI + PostgreSQL backend that accepts raw text entries, routes them to the correct domain table via a deterministic rule engine, and exposes daily-state endpoints.

---

## Stack

| Layer | Technology |
|-------|-----------|
| API | FastAPI 0.111 |
| ORM | SQLAlchemy 2.0 (mapped columns) |
| Migrations | Alembic |
| Database | PostgreSQL 16 |
| Tests | pytest + SQLite in-memory |
| Runtime | Docker / docker-compose |

---

## Quick Start

```bash
# 1. Copy and configure environment
cp .env.example .env

# 2. Start everything
docker-compose up --build

# 3. API available at http://localhost:8000
# 4. Interactive docs at http://localhost:8000/docs
```

Alembic runs `upgrade head` automatically on container start, seeding the default routing rules.

---

## API Endpoints

### `POST /ingest`
Accept a raw text entry, route it deterministically, and persist to the matching domain table.

```json
// Request
{ "raw": "TODO: finish the report", "source": "cli", "day": "2026-02-20" }

// Response 201
{
  "id": 1,
  "raw": "TODO: finish the report",
  "entry_type": "task",
  "routed_to": "tasks",
  "rule_matched": "task_prefix",
  "day": "2026-02-20",
  "created_at": "2026-02-20T10:00:00+00:00"
}
```

### `GET /state/today?day=YYYY-MM-DD`
Full snapshot of a day (defaults to today): all entries, tasks, transactions, facts, metrics.

### `GET /state/active`
Open tasks, active projects, and days that have entries but are not yet closed.

### `POST /state/close-day`
Close a day: compute totals, mark it in `daily_logs`, create a `memory_snapshots` record.

```json
// Request
{ "day": "2026-02-20", "summary": "Productive day." }
```

---

## Deterministic Router

Routing rules are stored in `rules_router` (priority DESC). The first matching regex wins.

| Rule | Pattern | Target table | Entry type |
|------|---------|-------------|-----------|
| `task_prefix` | `^(TODO\|TASK\|tarea\|hacer)` | `tasks` | task |
| `income_keyword` | `(ingreso\|income\|cobr)` | `transactions` | transaction |
| `expense_keyword` | `(gast\|pagué\|expense\|paid)` | `transactions` | transaction |
| `fact_keyword` | `^(FACT\|DATO\|nota\|note):` | `facts` | fact |
| `metric_keyword` | `^(METRIC\|METRICA\|KPI):` | `metrics_daily` | metric |
| `project_keyword` | `^(PROJECT\|PROYECTO):` | `projects` | project |
| `default_note` | `.*` | `facts` | note |

Rules can be modified in the DB at runtime — the router re-reads them per request.

---

## Database Tables

| Table | Description |
|-------|-------------|
| `entries` | Every ingested raw entry — the source of truth |
| `facts` | Extracted facts / notes |
| `metrics_daily` | Named numeric metrics per day |
| `transactions` | Income / expense / transfer records |
| `tasks` | To-do items with status tracking |
| `projects` | Projects with lifecycle status |
| `rules_router` | Routing rules evaluated in priority order |
| `memory_snapshots` | Periodic state snapshots (created on close-day) |
| `daily_logs` | One record per closed day with aggregate counts |

---

## Development

### Run tests (no Postgres required)

```bash
pip install -r requirements.txt
pytest tests/ -v
```

### Generate a new migration

```bash
alembic revision --autogenerate -m "describe change"
alembic upgrade head
```

### Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql://dios:dios@db:5432/dios` | Full Postgres DSN |
| `POSTGRES_USER` | `dios` | Used by docker-compose |
| `POSTGRES_PASSWORD` | `dios` | Used by docker-compose |
| `POSTGRES_DB` | `dios` | Used by docker-compose |
| `APP_ENV` | `development` | Environment tag |
| `SECRET_KEY` | `changeme-secret-key` | For future auth |

---

## Project Structure

```
.
├── app/
│   ├── core/          # Settings
│   ├── db/            # Engine, session, Base
│   ├── models/        # SQLAlchemy ORM models (9 tables)
│   ├── routers/       # FastAPI routers (ingest, state)
│   ├── schemas/       # Pydantic request/response models
│   ├── services/      # Business logic (router, ingest, state)
│   └── main.py        # FastAPI app
├── migrations/
│   └── versions/      # Alembic migration files
├── tests/             # pytest suite (SQLite, no Postgres needed)
├── docker-compose.yml
├── Dockerfile
├── alembic.ini
├── requirements.txt
└── .env.example
```
