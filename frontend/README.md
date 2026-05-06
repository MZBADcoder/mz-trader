# Trade Helper Frontend

React + TypeScript + Vite frontend scaffold for PRD-0001.

## Structure

```text
src/
  app/        # application bootstrap, providers, routes, global styles
  pages/      # route-level screens
  widgets/    # page sections and terminal panels
  features/   # user actions and use cases
  entities/   # domain-facing client models and API wrappers
  shared/     # generic API, config, utilities, UI, i18n
```

## Planned Routes

| Route | Slice | Purpose |
| --- | --- | --- |
| `/` | `pages/home` | Trade Helper marketing homepage |
| `/auth` | `pages/auth` | Login and registration entry |
| `/terminal` | `pages/terminal` | Market watch terminal |
| `*` | `pages/not-found` | Route fallback |

## Layer Rules

Allowed dependency direction:

```text
app -> pages -> widgets -> features -> entities -> shared
```

Other slices should be imported through their `index.ts` public API.

