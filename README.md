# DIOS App — Backend

**Deterministic Ingest and Orchestration System**

FastAPI + PostgreSQL backend that accepts raw text entries, routes them to the
correct domain table via a deterministic rule engine, and exposes daily-state
endpoints, a memory compiler, North Star clarity metrics, and a behavioral
engine that reacts automatically to your patterns.

---

## Stack

| Layer | Technology |
|-------|-----------|
| API | FastAPI 0.111 |
| ORM | SQLAlchemy 2.0 (mapped columns) |
| Migrations | Alembic |
| Database | PostgreSQL 16 |
| Tests | pytest + SQLite in-memory |
| Server | Gunicorn + Uvicorn workers |
| Deploy | Railway (recommended) |

---

## Deploy to Railway in 5 minutes

> No laptop required after this setup. Every `git push` redeploys automatically.

### Step 1 — Fork / push the repo to GitHub

If you haven't already:

```bash
git remote add origin https://github.com/YOUR_USER/dios.git
git push -u origin main
```

### Step 2 — Create a Railway project

1. Go to [railway.app](https://railway.app) → **New Project**
2. Choose **Deploy from GitHub repo** → select this repo
3. Railway detects `railway.toml` and configures everything automatically

### Step 3 — Add a PostgreSQL database

1. Inside your Railway project click **+ New** → **Database** → **PostgreSQL**
2. Railway automatically injects `DATABASE_URL` into your service — nothing to copy

### Step 4 — Set environment variables

In your Railway service → **Variables** tab, add these three:

| Variable | Value |
|----------|-------|
| `APP_ENV` | `production` |
| `SECRET_KEY` | *(run `python -c "import secrets; print(secrets.token_hex(32))"` locally)* |
| `CORS_ORIGINS` | `*` *(or your specific frontend URL)* |

`DATABASE_URL` and `PORT` are injected by Railway automatically — do **not** add them.

### Step 5 — Deploy

Click **Deploy** (or just push a commit). Railway will:

1. Install dependencies from `requirements.txt`
2. Run `bash start.sh` which:
   - Executes `alembic upgrade head` (runs all migrations)
   - Starts `gunicorn` with Uvicorn workers bound to `$PORT`
3. Poll `GET /health` until it returns `200`

Your API is live at the URL shown in the Railway dashboard (e.g. `https://dios-production.up.railway.app`).

### Step 6 — Smoke test

```bash
BASE=https://dios-production.up.railway.app

# Health check
curl "$BASE/health"
# → {"status":"ok","db":"ok","env":"production"}

# Ingest a task
curl -s -X POST "$BASE/ingest" \
  -H "Content-Type: application/json" \
  -d '{"raw": "TODO: probar el deploy", "source": "cli"}' | python3 -m json.tool
```

---

## iPhone Shortcuts — cURL Quick Reference

Use these inside the **Shortcuts** app with the **Run Script over SSH** action
(to a home server), or paste them into the **Get Contents of URL** action
pointing at your Railway URL.

> Replace `BASE` with your Railway URL in every snippet.

### Log a task

```bash
curl -s -X POST "https://YOUR-APP.up.railway.app/ingest" \
  -H "Content-Type: application/json" \
  -d '{"raw": "TODO: comprar leche", "source": "voice"}'
```

### Log income

```bash
curl -s -X POST "https://YOUR-APP.up.railway.app/ingest" \
  -H "Content-Type: application/json" \
  -d '{"raw": "ingreso 1500 freelance", "source": "voice"}'
```

### Log an expense

```bash
curl -s -X POST "https://YOUR-APP.up.railway.app/ingest" \
  -H "Content-Type: application/json" \
  -d '{"raw": "gasté 35 en comida", "source": "voice"}'
```

### Log a fact / note

```bash
curl -s -X POST "https://YOUR-APP.up.railway.app/ingest" \
  -H "Content-Type: application/json" \
  -d '{"raw": "FACT: el proyecto X usa React 18", "source": "text"}'
```

### Log a metric

```bash
curl -s -X POST "https://YOUR-APP.up.railway.app/ingest" \
  -H "Content-Type: application/json" \
  -d '{"raw": "METRIC: pasos 8234", "source": "text"}'
```

### Check today'\''s state

```bash
curl -s "https://YOUR-APP.up.railway.app/state/today" | python3 -m json.tool
```

### Check North Star (Clarity Score)

```bash
curl -s "https://YOUR-APP.up.railway.app/metrics/north-star" | python3 -m json.tool
```

### Compile today'\''s memory

```bash
curl -s -X POST "https://YOUR-APP.up.railway.app/memory/compile-day" \
  -H "Content-Type: application/json" \
  -d '{}'
```

### Close today

```bash
curl -s -X POST "https://YOUR-APP.up.railway.app/state/close-day" \
  -H "Content-Type: application/json" \
  -d '{"day": "2026-02-21", "summary": "Buen día."}'
```

### Batch ingest (multiple entries at once)

```bash
curl -s -X POST "https://YOUR-APP.up.railway.app/ingest/batch" \
  -H "Content-Type: application/json" \
  -d '{
    "source": "voice",
    "items": [
      {"raw": "TODO: llamar al banco"},
      {"raw": "gasté 12 en café"},
      {"raw": "FACT: aprendí sobre event sourcing"}
    ]
  }' | python3 -m json.tool
```

---

## Shortcut template for iPhone

The minimal Shortcut to log a voice note:

1. **Dictate Text** — store in `VoiceInput`
2. **Get Contents of URL**
   - URL: `https://YOUR-APP.up.railway.app/ingest`
   - Method: `POST`
   - Headers: `Content-Type: application/json`
   - Body (JSON):
     ```json
     {"raw": "[VoiceInput]", "source": "voice"}
     ```
3. **Show Result** — display the response

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Liveness probe (checks DB connectivity) |
| `POST` | `/ingest` | Ingest one raw entry |
| `POST` | `/ingest/batch` | Ingest up to 100 entries (207 Multi-Status) |
| `GET` | `/state/today` | Full snapshot of a day |
| `GET` | `/state/active` | Open tasks + active projects + unclosed days |
| `POST` | `/state/close-day` | Close a day (creates memory snapshot) |
| `POST` | `/memory/compile-day` | Compile daily narrative memory |
| `POST` | `/memory/compile-week` | Compile weekly narrative memory |
| `GET` | `/memory/snapshots` | List memory snapshots |
| `GET` | `/memory/snapshots/{id}` | Get one snapshot |
| `GET` | `/metrics/north-star` | Weekly Clarity Score (0.0 – 1.0) |
| `GET` | `/metrics/north-star/day` | Single-day clarity breakdown |
| `GET` | `/behavior/events` | Behavioral engine events log |
| `GET` | `/docs` | Swagger UI |
| `GET` | `/redoc` | ReDoc UI |

---

## Deterministic Router

Rules stored in `rules_router` (evaluated in priority DESC order).
First match wins — no LLM in the critical path.

| Rule | Pattern | Target | Entry type |
|------|---------|--------|-----------|
| `task_prefix` | `^(TODO\|TASK\|tarea\|hacer)` | `tasks` | task |
| `income_keyword` | `(ingreso\|income\|cobr)` | `transactions` | transaction |
| `expense_keyword` | `(gast\|pagué\|expense\|paid)` | `transactions` | transaction |
| `fact_keyword` | `^(FACT\|DATO\|nota\|note):` | `facts` | fact |
| `metric_keyword` | `^(METRIC\|METRICA\|KPI):` | `metrics_daily` | metric |
| `project_keyword` | `^(PROJECT\|PROYECTO):` | `projects` | project |
| `default_note` | `.*` | `facts` | note |

---

## North Star — Clarity Score

A day is **Complete** when all three criteria are met:

| Criterion | Condition |
|-----------|-----------|
| Activity | ≥ 3 logged entries |
| Outcome | ≥ 1 task done **or** ≥ 1 transaction recorded |
| Reflection | Daily memory snapshot compiled |

**Clarity Score** = `complete_days / 7` over the last 7 days.

The Behavioral Engine reacts automatically:

| Score | Rule triggered |
|-------|---------------|
| `< 0.4` | `clarity_warning` event emitted |
| 3 consecutive incomplete days | `reset_day_protocol` event + Task auto-created |
| `= 1.0` | `perfect_week` event emitted |

---

## Database Tables

| Table | Description |
|-------|-------------|
| `entries` | Every ingested raw entry — append-only source of truth |
| `facts` | Extracted facts / notes |
| `metrics_daily` | Named numeric metrics per day |
| `transactions` | Income / expense / transfer records |
| `tasks` | To-do items with status tracking |
| `projects` | Projects with lifecycle status |
| `rules_router` | Routing rules evaluated in priority order |
| `memory_snapshots` | Periodic state snapshots (created on close-day) |
| `daily_logs` | One record per closed day with aggregate counts |
| `narrative_memory` | Deterministic narrative compiled from the event store |
| `north_star_snapshots` | Cached Clarity Score calculations |
| `behavior_events` | Automatic system reactions log |

---

## Local Development

### Run tests (no Postgres required)

```bash
pip install -r requirements.txt
pytest tests/ -v
```

### Run with Docker Compose

```bash
cp .env.example .env
docker compose up --build
# API at http://localhost:8000  |  Docs at http://localhost:8000/docs
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
| `APP_ENV` | `development` | Environment tag |
| `SECRET_KEY` | `changeme-secret-key` | Future auth signing key |
| `CORS_ORIGINS` | `*` | Comma-separated allowed origins |
| `PORT` | `8000` | TCP port (set automatically by Railway) |
| `WORKERS` | `2` | Gunicorn worker count |

---

## Project Structure

```
.
├── app/
│   ├── core/          # Settings, error classes
│   ├── db/            # Engine, session, Base
│   ├── models/        # SQLAlchemy ORM models (12 tables)
│   ├── routers/       # FastAPI routers (ingest, state, memory, metrics, behavior)
│   ├── schemas/       # Pydantic request/response models
│   ├── services/      # Business logic — zero LLM, zero HTTP
│   └── main.py        # FastAPI app + CORS + exception handlers
├── migrations/
│   └── versions/      # Alembic migration files (0001–0004)
├── tests/             # pytest suite (194 tests, SQLite in-memory)
├── gunicorn.conf.py   # Gunicorn production config
├── start.sh           # Entrypoint: migrations → gunicorn
├── railway.toml       # Railway deployment config
├── docker-compose.yml # Local dev stack
├── alembic.ini
├── requirements.txt
└── .env.example
```
