# Repository Guidelines

## Project Structure & Module Organization

- `frontend/`: React/TypeScript with Vite. Entry points: `src/main.tsx`, `src/App.tsx`; styles: `src/*.css`; imported assets: `src/assets/`; static files: `public/`.
- `backend/`: FastAPI/Pydantic dependencies in `pyproject.toml`; `app.py` is empty, with no API implemented yet.
- `pocketbase/`: Go service in `main.go`, serving `pb_public/` when present. Runtime databases belong in ignored `pb_data/`.
- `data/`: Swedish news inputs in `test-event.txt` and `test-event2.txt`, with source links in root `README.md`. These are not automated tests.
- `system-design.md` describes the architecture; root `assets/` contains its diagrams. Keep these aligned with implementation changes.

## Architecture & Implementation Status

The design proposes `/analyze-event` to combine multiple event-analysis workflows. PocketBase stores proposed `Events` fields (`event_id`, nullable `group_id`, `text`); the `Analysis` schema is unfinished. These endpoints, workflows, and collections are not implemented in checked-in code. Document API and schema decisions as they are added.

## Build, Test, and Development Commands

Run commands from the indicated directory using PowerShell.

- In `frontend/`, `pnpm install` installs dependencies using `pnpm-lock.yaml`.
- `pnpm dev` starts Vite with hot reload.
- `pnpm build` runs TypeScript project checks and produces `dist/`.
- `pnpm lint` checks TypeScript and React rules through ESLint.
- `pnpm preview` previews the production build locally.
- In `backend/`, `python -m py_compile app.py` checks syntax. Requires Python 3.10+; no backend launch command exists yet.
- In `pocketbase/`, `go run . serve` starts the service; `go build .` compiles it. Go version: see `go.mod`.

## Coding Style & Naming Conventions

Match nearby code: TypeScript uses two spaces, single quotes, and no semicolons; Python uses four spaces; format Go with `gofmt`. Use PascalCase for React components, camelCase for TypeScript functions/variables, and snake_case for Python functions. ESLint is configured; no dedicated frontend/Python formatter is configured.

## Testing Guidelines

No automated tests or coverage threshold are configured. Run frontend lint/build and relevant language checks. When adding tests, document their runner; use `*.test.tsx`, `test_*.py`, or `*_test.go`. Use `data/` samples for future analysis smoke checks. Describe manual UI verification.

## Commit & Pull Request Guidelines

History uses descriptive subjects such as `pocketbase setup`; no formal prefix convention exists. Keep commits focused. PRs should explain changes, affected services, verification, and related issues. Include UI screenshots and disclose unrun checks.

## Agent & Configuration Practices

Use PowerShell, `rg`, and `apply_patch`; inspect existing code before editing and preserve unrelated changes. Never commit credentials or local database contents. Request escalation when necessary commands fail because of sandbox restrictions.
