# AGENTS.md

## Project Positioning
- This repository is a new implementation under `/Users/mz/pmf/trader-refactor`.
- `/Users/mz/pmf/trader-helper` is a reference repository for product intent, domain behavior, API expectations, data semantics, and migration context.
- Do not treat `/Users/mz/pmf/trader-helper` as the structure, design, or implementation baseline that must be preserved.
- Prefer clearer boundaries, simpler abstractions, stronger tests, and better long-term maintainability over compatibility with legacy internal structure.

## Source Repository Rules
- Treat `/Users/mz/pmf/trader-helper` as read-only reference input.
- Never modify, delete, rename, format, or generate files under `/Users/mz/pmf/trader-helper`.
- Read from `/Users/mz/pmf/trader-helper` only when needed to understand user-facing behavior, business rules, data contracts, operational constraints, or existing edge cases.
- If a task appears to require changing `/Users/mz/pmf/trader-helper`, stop and ask the user first.

## Working Boundary
- All new code, docs, scripts, configs, migrations, tests, and generated artifacts must live under `/Users/mz/pmf/trader-refactor`.
- Use the current repository as the only writable workspace.
- When reusing ideas from the source repository, re-express them to fit the new architecture instead of copying legacy layering or accidental complexity.

## Engineering Direction
- Build the new system around explicit boundaries, cohesive modules, and testable application flows.
- Keep domain logic independent from framework and storage details where practical.
- Favor composition over deep inheritance, and concrete implementations over speculative abstractions.
- Preserve externally important behavior only where it is intentionally required; otherwise choose the cleaner design.
- When behavior differs from the source repository, make the change explicit in code comments, tests, or future docs as the project evolves.

## Decision Heuristics
- Use the source repository to answer: what problem the old system solved, what inputs and outputs existed, what edge cases were already known.
- Do not use the source repository to answer: how folders must be organized, what abstractions must exist, or what technical debt should be carried forward.
- If the old and new approaches conflict, prefer the approach that improves correctness, clarity, operability, and maintainability in this repository.
