# CLAUDE.md — DIOS App

> Este archivo guía a Claude Code en cada sesión de trabajo sobre este repositorio.
> Léelo completo antes de tocar cualquier archivo.

---

## Visión: DIOS.20

**DIOS** = *Deterministic Ingest and Orchestration System*

El objetivo es un sistema personal de segunda memoria que:

1. **Captura** cualquier texto crudo (nota, tarea, gasto, métrica, hecho) desde cualquier fuente.
2. **Enruta** cada entrada de forma completamente determinista — sin LLM en el camino crítico.
3. **Persiste** en tablas de dominio especializadas con semántica clara.
4. **Expone estado** diario y activo vía API REST mínima.
5. **Cierra días** generando snapshots de memoria que sirven como contexto para sesiones futuras.

La versión 2.0 (DIOS.20) añade:

- **Event sourcing parcial**: toda acción del sistema emite un evento antes de mutar estado.
- **Módulos independientes**: cada dominio (tasks, finance, facts, metrics, projects) es un módulo autocontenido.
- **CLI first**: la API HTTP es una interfaz, no el núcleo.
- **Zero-LLM core**: el núcleo no llama a ningún modelo de lenguaje. Los LLM son consumidores opcionales del bus de eventos.

---

## North Star Metric

> **Tiempo desde captura hasta estado consultable ≤ 200 ms** (p95, sobre Postgres local).

Todo cambio de arquitectura, dependencia nueva o refactor se evalúa contra este número.
Si lo degrada, no entra.

---

## Regla fundamental: Event-First

**Antes de mutar cualquier tabla de dominio, se emite un evento.**

```
raw text
   │
   ▼
[Router determinístico]  ←── rules_router (DB)
   │
   ▼
evento: EntryIngested { id, raw, entry_type, target, day }
   │
   ├──▶ entries (append-only, jamás UPDATE ni DELETE)
   │
   └──▶ fan-out al módulo de dominio
            tasks / transactions / facts / metrics_daily / projects
```

### Invariantes del bus de eventos

| Regla | Detalle |
|-------|---------|
| Los eventos son **inmutables** | Una vez emitidos no se modifican |
| Los eventos van a `entries` | `entries` es el log de auditoría; nunca se purga |
| El estado derivado es **reconstruible** | A partir de `entries` se puede reconstruir cualquier tabla de dominio |
| Sin eventos fantasma | Todo cambio de estado tiene exactamente un evento de origen |

---

## Regla de dependencias: Core sin terceros

```
┌─────────────────────────────────────────┐
│  CORE (app/services/, app/models/)      │
│                                         │
│  ✅ stdlib Python                       │
│  ✅ SQLAlchemy (ORM, no raw SQL libre)  │
│  ✅ Pydantic (validación de esquemas)   │
│                                         │
│  ❌ httpx / requests                    │
│  ❌ openai / anthropic SDK              │
│  ❌ celery / redis / rabbitmq           │
│  ❌ cualquier SDK de terceros           │
└─────────────────────────────────────────┘
        │ solo import / export
        ▼
┌─────────────────────────────────────────┐
│  ADAPTERS (app/routers/, integrations/) │
│  → aquí viven FastAPI, httpx, SDKs      │
└─────────────────────────────────────────┘
```

**Corolario**: si un servicio en `app/services/` necesita llamar HTTP o un SDK externo,
la solución es mover esa llamada a un adapter e inyectarla como dependencia.
El core solo recibe y devuelve tipos de dominio Python puro.

---

## Módulos core

### `app/services/router.py` — Router determinístico
- Lee reglas de `rules_router` ordenadas por `priority DESC`.
- Evalúa regex en orden; el **primer match** gana.
- Retorna `RoutingResult(entry_type, target, rule_name)`.
- Versión pura (`route_entry_from_rules`) para tests sin DB.
- **No lanza excepciones**: regex inválido → skip, sin reglas → fallback `note/facts`.

### `app/services/ingest.py` — Servicio de ingesta
- Punto de entrada único: `ingest_raw(raw, db, source, day)`.
- Llama al router → persiste en `entries` → fan-out al módulo correcto.
- Extracción de datos (monto, tipo TX) mediante regex; nunca NLP externo.
- Hace `db.flush()` antes del fan-out para obtener `entry.id`.

### `app/services/state.py` — Estado del sistema
- `get_state_today(db, day)` → snapshot completo de un día.
- `get_state_active(db)` → tareas abiertas + proyectos activos + días sin cerrar.
- `close_day(db, day, summary)` → cierra `daily_logs` + crea `memory_snapshots`.

### `app/models/` — ORM (9 tablas)

| Módulo | Tabla | Rol |
|--------|-------|-----|
| `entry.py` | `entries` | Log de auditoría append-only |
| `fact.py` | `facts` | Hechos y notas libres |
| `metric.py` | `metrics_daily` | KPIs numéricos por día |
| `transaction.py` | `transactions` | Finanzas (ingreso/gasto/transferencia) |
| `task.py` | `tasks` | Tareas con estado |
| `project.py` | `projects` | Proyectos con ciclo de vida |
| `rule.py` | `rules_router` | Reglas del router (modificables en runtime) |
| `memory.py` | `memory_snapshots` | Snapshots para contexto LLM |
| `daily_log.py` | `daily_logs` | Resumen por día cerrado |

---

## Convenciones de nombres de eventos

Formato: `{Sustantivo}{Participio}` en **PascalCase**, pasado, sin prefijo `on`.

```
# Ingesta
EntryIngested          # entrada cruda recibida y guardada
EntryRouted            # router asignó target

# Dominio — Tareas
TaskCreated
TaskStatusChanged      # pending → in_progress → done | cancelled
TaskAssignedToProject

# Dominio — Finanzas
TransactionRecorded
TransactionCategorized

# Dominio — Hechos y métricas
FactRecorded
MetricRecorded
MetricThresholdBreached  # valor fuera de rango esperado

# Dominio — Proyectos
ProjectCreated
ProjectStatusChanged   # active → paused → done → archived

# Día
DayClosed              # close-day ejecutado
MemorySnapshotCreated  # snapshot generado tras cierre

# Router
RouterRuleMatched
RouterRuleFallbackUsed  # ninguna regla coincidió, se usó default
```

### Reglas de nombrado

1. Sustantivo en singular (`Entry`, no `Entries`).
2. Participio pasado (`Ingested`, no `Ingest` ni `Ingesting`).
3. Sin verbos de infraestructura (`Saved`, `Persisted`, `Written` → **prohibidos**).
4. El nombre debe ser legible por un humano no técnico.
5. Si el evento tiene sub-tipos, usar sufijo descriptivo (`StatusChanged`, no `Updated`).

---

## Estructura del proyecto

```
app/
├── core/        # config, settings — sin lógica de negocio
├── db/          # engine, sesión, Base declarativa
├── models/      # ORM models — solo estructura, sin lógica
├── schemas/     # Pydantic request/response — solo validación
├── services/    # TODA la lógica de negocio — aquí vive el core
└── routers/     # FastAPI HTTP adapters — delegan a services/

migrations/
└── versions/    # Alembic — una migración por feature, nunca squash en main

tests/
├── conftest.py           # fixtures, SQLite in-memory + seed de reglas
├── test_router.py        # tests unitarios del router (sin DB)
├── test_ingest_service.py # tests unitarios de helpers de ingest
└── test_endpoints.py     # tests de integración HTTP end-to-end
```

---

## Convenciones de código

### Nombrado general

| Elemento | Convención | Ejemplo |
|----------|-----------|---------|
| Tablas DB | `snake_case` plural | `daily_logs`, `rules_router` |
| Modelos ORM | `PascalCase` singular | `DailyLog`, `RuleRouter` |
| Servicios | `snake_case` verbo+sustantivo | `ingest_raw`, `close_day` |
| Endpoints | `snake_case` con guiones en URL | `/state/close-day` |
| Eventos | `PascalCase` sustantivo+participio | `EntryIngested` |
| Schemas Pydantic | `PascalCase` + `Request`/`Response` | `IngestRequest` |
| Enums Python | `PascalCase` para la clase, `snake_case` para valores | `TaskStatus.in_progress` |

### Modelos ORM

- Siempre usar **`Mapped[T]`** con `mapped_column` (SQLAlchemy 2.0 style).
- `created_at` con `server_default=func.now()` — nunca `default=datetime.now`.
- Columnas `updated_at` solo donde el registro muta (tasks). En tablas append-only, no aplica.
- **`entries` es append-only**: nunca añadir lógica de UPDATE o DELETE sobre ella.

### Servicios

- Una función = una responsabilidad.
- Los servicios reciben `db: Session` como parámetro; nunca crean su propia sesión.
- `db.flush()` para obtener IDs generados antes de referencias cruzadas.
- `db.commit()` solo al final del servicio raíz (no en helpers internos).

### Migraciones

- Nombre: `{NNNN}_{descripcion_corta}.py` (ej: `0002_add_tags_to_facts.py`).
- Cada migración es atómica: crea o altera una sola cosa lógica.
- **No usar `.create()` explícito para ENUMs** — dejar que `op.create_table` los cree
  (comportamiento correcto en SQLAlchemy 2.0 + Alembic).
- `downgrade()` siempre implementado y probado.

---

## Cómo validar un PR

### Checklist obligatorio (todos deben pasar antes de merge)

```bash
# 1. Tests — deben pasar al 100%, sin warnings nuevos
pytest tests/ -v

# 2. Sin imports del core a terceros
grep -rn "import httpx\|import openai\|import anthropic\|import requests" app/services/ app/models/
# → debe estar vacío

# 3. Migración aplica limpia en DB vacía
# (simular con drop+recreate o usar una DB temporal)
alembic upgrade head

# 4. Migración tiene downgrade funcional
alembic downgrade -1
alembic upgrade head

# 5. El North Star no regresa (manual por ahora)
# POST /ingest con texto simple debe responder en < 200 ms p95
```

### Criterios de rechazo automático

| Señal | Acción |
|-------|--------|
| `pytest` con 1+ fallo | ❌ No merge |
| Import de SDK externo en `app/services/` o `app/models/` | ❌ No merge |
| Migración sin `downgrade()` | ❌ No merge |
| UPDATE o DELETE sobre `entries` | ❌ No merge |
| Nuevo endpoint sin test de integración | ❌ No merge |
| Función de servicio que hace `db.commit()` interna sin ser la raíz | ❌ Revisión requerida |

### Criterios de merge

- Tests: **43/43** (o más si se añaden nuevos) en verde.
- Cada feature nueva viene con al menos 1 test unitario + 1 test de integración.
- El mensaje de commit sigue **Conventional Commits**: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `chore:`.
- PRs pequeños: una sola responsabilidad lógica por PR.

---

## Comandos frecuentes

```bash
# Levantar stack completo
docker compose up --build

# Solo API local (requiere Postgres corriendo)
uvicorn app.main:app --reload --port 8000

# Tests (sin Postgres)
pytest tests/ -v

# Tests de un módulo
pytest tests/test_router.py -v

# Nueva migración
alembic revision --autogenerate -m "descripcion"
alembic upgrade head

# Verificar estado de migraciones
alembic current
alembic history

# Conectar a DB local
psql postgresql://dios:dios@localhost:5432/dios
```

---

## Lo que Claude NO debe hacer en este repo

- ❌ Añadir calls HTTP o SDK externos en `app/services/` o `app/models/`.
- ❌ Hacer `UPDATE` o `DELETE` sobre `entries`.
- ❌ Crear nuevos endpoints sin sus tests correspondientes.
- ❌ Squashear o modificar migraciones ya pusheadas a `main`.
- ❌ Usar `datetime.now()` sin `tz=timezone.utc` (siempre UTC).
- ❌ Añadir lógica de negocio en `app/routers/` — los routers solo validan y delegan.
- ❌ Commitear con tests fallando.
- ❌ Añadir dependencias a `requirements.txt` sin justificación explícita en el PR.
