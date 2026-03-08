# Backend Architecture

This backend follows a strict layering rule:

```text
API / Worker -> Application -> Infrastructure -> Domain
```

## Non-negotiable Rules

- `domain/` stays pure and must not import FastAPI, Pydantic, SQLAlchemy, Redis, Celery, or external clients.
- `application/` orchestrates use cases and may depend on concrete infrastructure classes through dependency injection.
- `api/` and `worker/` are thin entrypoints only.
- `api/` must not import `infrastructure.*` directly.
- repositories must return domain objects, not ORM models.
- no Protocol, ABC, or interface layer should be introduced just for abstraction.

## Current Stage

This scaffold intentionally contains only placeholders.

Missing on purpose:

- business entities
- DTO definitions
- routers
- database models
- repository implementations
- external client adapters

