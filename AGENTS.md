# AGENTS.md

## Scope

- This file applies to the whole repository.
- If a task is entirely inside `backend/` or `frontend/`, also follow the nested `AGENTS.md` in that directory.

## Repository Layout

- `backend/`: FastAPI backend, async-first, DDD layering, PostgreSQL persistence.
- `frontend/`: frontend application workspace. It is currently empty and should be treated as a fresh app boundary.
- `docs/`: shared reference material, product design records, staged evolution plans, and backlog notes.

## Documentation-Driven Project Management

- This project is intentionally managed through repository documents instead of external tools such as Jira.
- docs could be written in both English and Simplified Chinese.
- Treat `docs/` as working project memory for both the developer and Codex agents.
- When a task is driven by a product iteration, read the relevant PRD and evolution docs before changing code.
- When a change materially affects scope, workflow, API usage, or phased delivery, update the relevant document in the same task when practical.

## Docs Directory Guide

- `docs/external-api-reference/`: external provider or third-party API notes.
- `docs/prd/`: product requirement documents for major iterations. Each PRD should describe scope, goals, non-goals, scenarios, functional requirements, and acceptance criteria.
- `docs/backend-evolution/`: backend execution plans derived from a PRD. Use these documents to break one PRD into staged backend work. If a PRD is an epic, each file here should represent one large backend task or phase.
- `docs/frontend-evolution/`: frontend execution plans and frontend design notes derived from a PRD. Use these documents to break one PRD into staged frontend work and record layouts, flows, states, interaction details, and implementation constraints.
- `docs/frontend-evolution/prototypes/`: static frontend HTML prototypes used to iterate visual direction and interaction details before implementation.
- `docs/todo/`: backlog notes for incomplete or intentionally deferred work. Record partially finished features, known gaps, and bugs found during testing that are not being fixed immediately.

## Document Usage Rules

- PRD defines the target outcome; evolution docs define phased implementation; todo records known leftovers after a phase ships.
- Do not use `docs/todo/` as a substitute for product scope. If something changes the intended product behavior, update the PRD or evolution doc instead of only adding a todo note.
- External API usage should be backed by `docs/external-api-reference/` when the integration is important enough to affect design or repeated implementation work.
- Frontend design decisions that are currently expressed only in chat should be written into `docs/frontend-evolution/` once they start guiding implementation. Static HTML prototypes should live in `docs/frontend-evolution/prototypes/`.
- Keep documents actionable. Prefer concrete scope, constraints, acceptance criteria, open questions, and next steps over narrative filler.

## Working Agreement

- Keep root-level code minimal. Product code should live in `backend/` or `frontend/`, not at repository root.
- Use the root only for repo-wide documentation, shared tooling, CI, and cross-project coordination files.
- Do not mix backend and frontend dependencies in the same workspace or command.
- Run backend commands from `backend/` and frontend commands from `frontend/`.
- When a change affects both sides, update both implementations in the same task when practical.

## Full-Stack Coordination Rules

- Treat API contracts as an explicit boundary. Backend owns route semantics and server-side business rules; frontend owns presentation, interaction flow, and client state.
- Avoid silent contract drift. If request or response fields change, update the relevant backend schema, frontend client usage, and any shared docs in `docs/` in the same change.
- Keep cross-project assumptions documented. If a workflow depends on auth, pagination, filtering, realtime events, or error codes, record the agreed behavior near the implementation or in `docs/`.
- Prefer one source of truth for integration details. Do not duplicate endpoint rules across random markdown files.
- If a future shared package is introduced for generated types or API clients, keep it deliberately versioned and lightweight. Do not create an ad hoc shared module at the repo root without a clear owner.

## Change Placement

- Backend-only business logic, persistence rules, and integration code belong in `backend/`.
- Frontend-only UI composition, client-side state, and view models belong in `frontend/`.
- Cross-cutting operational docs, onboarding notes, and architectural decisions belong in `docs/` or the nearest relevant package README/ARCHITECTURE file.
- Product planning, phased delivery notes, external API documentation, text prototypes, and backlog records belong in the appropriate `docs/` subdirectory instead of ad hoc notes elsewhere.

## Quality Bar

- Keep changes narrow and localized to the owning workspace.
- Prefer following the repository's existing conventions, module structure, naming, and implementation patterns before introducing a new pattern.
- When an area already has a local practice, extend that practice unless there is a concrete reason to realign it.
- Prefer explicit structure over convenience shortcuts that blur frontend/backend boundaries.
- Preserve nested architecture constraints instead of bypassing them for speed.
- Add or update documentation when introducing a new cross-project convention, external dependency, or integration workflow.
- Keep project-management documents aligned with delivered code so repository context stays useful for future agent runs.

## Git Commit Message Convention

When the user asks to commit and does not provide a custom format, follow this default:

- Commit messages must be written in English by default.
- The title should be a single sentence summarizing the main change.
- The title must include one type: `feat` / `bugfix` / `refactor`.
- The title must include the primary scope: `frontend` or `backend` (for cross-layer changes, use the dominant scope).
- Recommended format: `<type>(<scope>): <one-sentence summary>`.
- If the change is large, add details in the description/body using `summary` / `detail`.

## Git Conflict Resolution (Rebase + Squash Before Main Merge)

For this single-developer project, keep `main` updated first, then rebase your feature branch onto latest `main`, squash branch commits into one, and finally merge with fast-forward only.
This keeps history linear and avoids extra merge commits.

Recommended flow (no merge commit):

1. `git checkout main`
2. `git pull --ff-only origin main`
3. `git checkout <feature-branch>`
4. `git rebase main`
5. If conflicts happen: resolve markers (`<<<<<<<`, `=======`, `>>>>>>>`), run `git add <file>`, then `git rebase --continue` (repeat until done).
6. `git reset --soft main`
7. `git commit -m "<type>(<scope>): <one-sentence summary>"`，if the change is large, add details in the description/body using `summary` / `detail`.
8. `git checkout main`
9. `git merge --ff-only <feature-branch>`

If you need to cancel conflict resolution:

1. `git rebase --abort`

If `git merge --ff-only` fails, it means `main` changed after your rebase.
Pull latest `main` and rebase the feature branch again.

Push rules:

1. Push `main` normally: `git push origin main`.
2. If a rebased feature branch has already been pushed before, update it with `git push --force-with-lease origin <feature-branch>`.

Unless explicitly requested, do not use `git merge --no-ff` in this repo.
