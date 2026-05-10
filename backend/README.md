# Backend

This directory contains the backend for `trader-refactor`.

Current state:

- FastAPI application bootstrap
- async SQLAlchemy persistence
- Alembic-managed PostgreSQL schema migrations
- Redis/Celery integration points
- logging scaffold with request context

Source layout:

- `migrations`
- `src/api`
- `src/application`
- `src/domain`
- `src/infrastructure`
- `src/bootstrap`
- `src/worker`
- `src/main.py`
- `src/settings.py`

Database migrations:

```bash
poetry run alembic upgrade head
poetry run alembic downgrade -1
poetry run alembic revision --autogenerate -m "describe change"
```

Alembic reads `DATABASE_URL` through `src/settings.py`, so local commands should be run from `backend/` with the same `.env` used by the application.

Local dev stack:

```bash
./scripts/start_dev_stack.sh
```

The script starts the FastAPI server, a Celery worker, Celery beat, and enqueues one `run_historical_bars_gap_reconciliation` task after startup. It expects PostgreSQL and Redis to already be reachable through the configured `.env`.

Default log files:

```text
var/log/application.log
var/log/celery-worker.log
var/log/celery-beat.log
```

Useful overrides:

```bash
APP_PORT=8010 ./scripts/start_dev_stack.sh
RUN_GAP_RECONCILIATION_ON_START=0 ./scripts/start_dev_stack.sh
CELERY_WORKER_CONCURRENCY=1 ./scripts/start_dev_stack.sh
```

Notes:

- `src/` is intentionally flat
- there is no extra `src/trader_refactor_backend/` wrapper package
- `domain/value_objects` is intentionally omitted for now

Main goals of this scaffold:

- keep the DDD layering explicit from day one
- keep domain code isolated from framework and IO concerns
- reserve clear integration boundaries for Massive, database, cache, and future workers
- centralize structured JSON logging with request-scoped context and daily file rotation
