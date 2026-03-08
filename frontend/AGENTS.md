# AGENTS.md

## Scope

- This file applies to everything under `frontend/`.
- Follow the repo-root `AGENTS.md` as well, but this file defines frontend-specific structure.

## Current State

- `frontend/` is currently empty.
- Treat this as a greenfield frontend and establish structure before adding feature code.
- Tech Stack: React + TypeScript + Vite.

## Recommended Default Structure

Use the `react-structure` default: a lightweight Feature-Sliced layout that keeps bootstrapping in `app/`, route screens in `pages/`, user capabilities in `features/`, domain-facing client logic in `entities/`, and reusable primitives in `shared/`.

```text
src/
  app/
    providers/
    routes/
    styles/
  pages/
  widgets/
  features/
  entities/
  shared/
    api/
    config/
    lib/
    ui/
  main.tsx
  vite-env.d.ts
```

Within a slice such as `features/auth/login/`, use this internal structure when needed:

```text
<slice>/
  api/
  model/
  ui/
  lib/
  index.ts
```

- `api/`: request functions and DTOs.
- `model/`: state, actions, selectors, validators, and use-case logic with no UI.
- `ui/`: slice-local components.
- `lib/`: helpers local to the slice.
- `index.ts`: the only public entry for imports from other slices or layers.

## Hard Structure Rules

- Allowed dependency direction uses the same meaning as the backend layering rule: `A -> B` means `A` may depend on `B`.

```text
app -> pages -> widgets -> features -> entities -> shared
```

- Do not import upward across layers. For example, `shared` must not depend on `entities`, and `features` must not depend on `pages` or `app`.
- Import other slices through their public API (`index.ts`) unless you are inside the same slice.
- Keep `pages/` thin. Pages compose widgets, features, and entities; they should not hide business workflows.
- Keep `shared/` generic. Do not move business-specific logic into `shared`.
- Prefer colocated tests inside the owning slice unless the project adopts a different explicit testing convention later.

## Placement Rules

- Route screens go to `src/pages/<page>/ui/...`.
- Reusable page sections go to `src/widgets/<widget>/ui/...`.
- User actions and use cases go to `src/features/<feature>/...`.
- Domain-facing client logic goes to `src/entities/<entity>/...`.
- Generic utilities, API client primitives, config, and UI kit pieces go to `src/shared/...`.
- When adding new code, classify it into one of these buckets before creating files.

## API Integration Rules

- Do not call backend APIs directly from page components.
- Centralize low-level HTTP access in `shared/api`, then wrap feature-specific or entity-specific calls inside the owning slice.
- Keep request and response typing explicit. Do not rely on loosely typed `any` payloads.
- When backend contracts change, update the consuming frontend code in the same change.
- Normalize backend errors at the client boundary before they spread into UI code.

## Collaboration With Backend

- Backend remains the source of truth for business rules and persisted data semantics.
- Frontend may derive view models, formatting, and interaction state, but should not silently re-implement server rules.
- If a screen depends on filtering, pagination, sorting, auth, or realtime updates, make those assumptions explicit close to the API module or feature model.

## Scaffolding Expectations

- After initializing the app, add the `@/* -> src/*` path alias in both Vite and TypeScript config.
- Create the layer folders before adding feature code.
- Add ESLint import-boundary rules early so cross-layer violations are caught by tooling.
- Keep routing and global providers inside `src/app/`, not scattered across pages or features.

## Quality Bar

- Prefer intentional structure over a flat component dump.
- Keep reusable primitives in `shared/ui`, not inside random feature folders.
- Keep server state and UI state separated conceptually, even if the data library is chosen later.
- Add tests near the slice when the frontend stack is established.
- Keep environment-specific config centralized and avoid scattering raw URLs or feature flags through components.
