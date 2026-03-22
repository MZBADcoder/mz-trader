# AGENTS.md

## Scope

- This file applies to everything under `backend/`.
- Follow the repo-root `AGENTS.md` as well, but this file is more specific for backend work.

## Stack And Direction

- Stack: FastAPI + SQLAlchemy 2.x + PostgreSQL + Pydantic Settings.
- Use `poetry` for dependency and virtual environment management.
- Persistence must be fully async. Use SQLAlchemy async engine/session and an async PostgreSQL driver.
- Keep the layering strict:

```text
API / Worker -> Application -> Infrastructure -> Domain
```

## Non-Negotiable Architecture Rules

- Domain must stay pure. Do not import `fastapi`, `pydantic`, `sqlalchemy`, `redis`, `celery`, or external HTTP/DB clients in `domain/`.
- Application orchestrates use cases and may depend on concrete infrastructure classes through dependency injection.
- Do not introduce `Protocol`, `ABC`, or interface-only abstractions just to look clean. This backend uses no-interfaces style.
- API and worker are thin entrypoints only. They validate input, call application services, and translate errors.
- API must not import `infrastructure.*` directly.
- Repositories must return domain entities, never ORM models.
- ORM models, sessions, transactions, database mappings, and external clients stay in infrastructure.

## Current Backend Layout

- `src/api/`: routers, schemas, deps, HTTP entrypoints.
- `src/application/`: services and dependency composition.
- `src/domain/`: entities, domain exceptions, pure business rules.
- `src/infrastructure/`: database models, repositories, mappers, external integrations.
- `src/worker/`: async worker entrypoints and task wiring.
- `src/main.py`: FastAPI app bootstrap.
- `src/settings.py`: settings and environment configuration.

## Async Rules

- Use async request handlers, async application services where IO is involved, and async repository methods.
- Use `AsyncSession`; do not use sync `Session` in request or worker flows.
- Use `async with` for Unit of Work and session lifecycles.
- Do not perform blocking IO in the request path. If a library is sync-only, isolate it behind infrastructure and call it off the main async path.
- Database URLs must use an async PostgreSQL dialect. Prefer explicit async driver configuration over fallback defaults.

## Layer Rules

### API

- Keep routers thin.
- Request and response DTOs live in API schemas, not in domain.
- Use `response_model` for serialization. Pydantic response models should enable `from_attributes=True`.
- API may depend on `application.container` or API-local deps, but not directly on repositories, sessions, ORM models, or Redis clients.

### Application

- Application services coordinate a single use case.
- Inject concrete dependencies through `__init__`.
- Do not instantiate repositories, UoWs, or clients inline inside service methods.
- Keep framework objects out of application services unless they are application-level configuration inputs.

### Infrastructure

- Put SQLAlchemy models, async session setup, UoW, mappers, and repository implementations under infrastructure.
- Repositories map ORM models to domain entities before returning.
- Keep SQLAlchemy-specific query details out of API and domain.
- External integrations should expose backend-friendly methods and hide raw client details.

### Domain

- Use `@dataclass(slots=True)` for entities and value objects where appropriate.
- Domain holds invariants, business rules, state transitions, and domain exceptions.
- Domain must not know how persistence, HTTP, queues, or caching work.

## Persistence Rules

- PostgreSQL is the target relational store. Model for PostgreSQL semantics explicitly instead of aiming for lowest-common-denominator SQL.
- SQLAlchemy 2.x style only. Use typed declarative models and modern query APIs.
- One use case should typically run inside one async UoW boundary.
- Keep transaction control centralized in UoW or service orchestration, not scattered across routers.
- Alembic migrations should reflect infrastructure models and schema evolution, not leak into domain logic.

## Testing Rules

- Domain tests are pure unit tests with no database or framework setup.
- Application tests inject mock or fake concrete classes, including fake UoW implementations.
- Integration tests may use real database wiring, but keep them separate from pure domain and application tests.
- Prefer targeted tests for new business rules, mapping logic, and transaction behavior.

## Logging Rules

- Use the Python standard `logging` ecosystem as the base integration layer so FastAPI, Uvicorn, SQLAlchemy, and third-party libraries can share one logging pipeline.
- Prefer structured logs over ad hoc plain-text strings. JSON lines are the default direction for backend application logs.
- MVP logging should be file-based with daily rotation. A per-day rotating application log file is sufficient; do not design around ELK or other centralized log stacks yet.
- Every request-scoped log must include a `request_id`. If the client provides one via header and it passes validation, propagate it; otherwise generate one in middleware.
- Add stable contextual fields where relevant: `user_id`, `method`, `path`, `status_code`, `latency_ms`, `error_code`, `ticker`, and upstream service name.
- Do not log secrets or credential material. Never log raw passwords, JWTs, API keys, auth headers, database URLs, or full upstream credentials.
- Auth failures should be logged, but only with safe metadata such as `email`, `request_id`, client IP, and reason code. Do not log password input.
- External integration failures should log the upstream name, request target, latency, retry count if applicable, and a normalized error summary. Do not leak raw provider payloads unless they are explicitly sanitized.
- Unhandled exceptions must be logged with stack traces and `request_id`.
- Business errors that map to stable API error codes should log the `error_code` and enough context for debugging, but avoid noisy stack traces when the failure is expected.
- Keep logging setup centralized under infrastructure/bootstrap code rather than configuring handlers independently in routers or services.

## Guardrails And Commands

- Boundary checks matter in this repository. Keep `scripts/check_boundaries.py` passing.
- Run backend commands through `poetry run` when working inside this package.
- Typical verification commands:
  - `poetry run python scripts/check_boundaries.py`
  - `poetry run pytest`
- If you add a new layer crossing, stop and justify it before implementing.

## Code Style Expectations

- Favor small services with explicit names tied to a use case.
- Prefer mapper functions over leaking ORM objects upward.
- Keep settings loading centralized.
- Avoid convenience imports that obscure layer boundaries.
