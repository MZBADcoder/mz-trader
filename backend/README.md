# Backend

This directory contains the backend scaffold for `trader-refactor`.

Current state:

- structure only
- minimal logging scaffold
- lightweight API bootstrap
- no business code
- no ORM models
- no service implementations

Source layout:

- `src/api`
- `src/application`
- `src/domain`
- `src/infrastructure`
- `src/bootstrap`
- `src/worker`
- `src/main.py`
- `src/settings.py`

Notes:

- `src/` is intentionally flat
- there is no extra `src/trader_refactor_backend/` wrapper package
- `domain/value_objects` is intentionally omitted for now

Main goals of this scaffold:

- keep the DDD layering explicit from day one
- keep domain code isolated from framework and IO concerns
- reserve clear integration boundaries for Massive, database, cache, and future workers
- centralize structured JSON logging with request-scoped context and daily file rotation
