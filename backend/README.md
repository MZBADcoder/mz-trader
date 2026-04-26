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

Notes:

- `src/` is intentionally flat
- there is no extra `src/trader_refactor_backend/` wrapper package
- `domain/value_objects` is intentionally omitted for now

Main goals of this scaffold:

- keep the DDD layering explicit from day one
- keep domain code isolated from framework and IO concerns
- reserve clear integration boundaries for Massive, database, cache, and future workers
- centralize structured JSON logging with request-scoped context and daily file rotation
