# Repository Guidelines

## Project Structure & Module Organization

- `frontend/`: React 19/TypeScript with Vite and React Compiler. `src/App.tsx` owns the composer, health dialog, navigation, and in-memory analysis. `api.ts` handles HTTP, `analysis.ts` handles stream parsing/state, and `evidence.ts` links exact quotes. `AnalysisScreen`, `SummaryScreen`, `WorkflowRow`, and `PageMenu` provide the analysis UI. Shared colors live in `src/colors.css`; global and component layouts use `src/*.css`. Tests live in `tests/`.
- `backend/`: FastAPI/Pydantic API in `app.py`; shared inference, title generation, and registered categorization workflows in `workflows.py`. Category definitions live in `schemas/*.json`. Dependencies and CPU/CUDA profiles are managed by `pyproject.toml` and `uv.lock`; mocked pytest suites are `test_*.py`. `smoke_articles.py` calls a running backend for real inference.
- `pocketbase/`: Go service in `main.go`, serving `pb_public/` when present. Runtime databases belong in ignored `pb_data/`.
- `data/`: Swedish news samples in `test-event*.txt`, with source links for the original two articles in root `README.md`. These are inputs, not test suites.
- `frontend/README.md` and `backend/README.md` document setup, behavior, and verification. `system-design.md` describes implemented and planned architecture; root `assets/` contains its diagrams. Keep these aligned with implementation changes. `frontend/DESIGN.md` and `src/Design.css` are historical design references; the latter is not imported by the application.

## Architecture & Implementation Status

- FastAPI implements `GET /health`, `POST /analyze-event`, and `POST /analyze-event/stream`. Analysis accepts a trimmed, nonempty string in `{ "text": "..." }`; invalid input returns 422. The JSON response contains `status`, `title`, and `results` keyed by `risks`, `reach`, and `service`, with category `ID` and display `name`. Streaming matches also include verified `evidence` quotes; the JSON endpoint excludes evidence.
- Startup validates categories and loads one runtime per process into `app.state.runtime`. `SERVING_ENGINE=transformers|vllm` defaults to Transformers; `/health` reports `serving_engine`. Transformers Gemma 4 uses `AutoProcessor` and `Gemma4ForConditionalGeneration`; other `AutoModel` runtimes can serve health but currently do not support analysis generation. Embedded async vLLM requires Linux/CUDA, uses one GPU/TP=1 and internal workers without an HTTP server, and bridges synchronous workflows to the application event loop. A shared lock serializes either engine. vLLM loads embeddings first, disables multimodal inputs, and uses eager execution without CUDA graphs. `VLLM_GPU_MEMORY_UTILIZATION` defaults to 0.50 (finite in (0, 1]); optional positive-integer `VLLM_KV_CACHE_MEMORY_BYTES` overrides automatic cache sizing and the utilization budget. Neither enforces a hard total-memory limit. Use one Uvicorn worker.
- A Swedish title step runs before the ordered `WORKFLOWS` registry and is excluded from category progress. Titles are validated as 1–10 words; unusable output or inference failure falls back to `Händelseanalys`. Category workflows have separate Swedish prompts and validated IDs from `schemas/`. Evidence must be a nonblank exact substring of the trimmed input; invalid quotes are discarded without dropping valid categories.
- Input is capped at 8192 tokens; category generation allows 4096 output tokens and titles allow 64. `RETRY_LIMIT` (default 1) retries invalid category JSON/IDs, not inference failures or invalid evidence. Input-limit, inference/output, and unsupported-runtime errors use 413, 502, and 503 respectively.
- Streaming emits `analysis_started`, `title_completed`, `workflow_started`, `workflow_completed`, then `analysis_completed` or terminal `workflow_failed`. Failures retain completed results; errors after headers are sent remain events inside HTTP 200. EOF without a terminal event is an interruption. Each request gets a UUID in `X-Analysis-ID` and stream metadata; IDs are not persisted or queryable.
- The Swedish Editorial frontend has Hem, Status, and Sammanfattning screens, expandable workflows, and bidirectional evidence highlights with keyboard/pinned selection. It checks health once on load with a 10-second timeout. Only one analysis is kept in memory; navigation preserves active work, successful completion opens the summary only from Status, and refresh clears state. Search results and saved analysis history remain unimplemented. Target PC browsers while keeping narrow desktop windows usable and honoring reduced motion.
- Vite development/preview proxies `/api/*` to `VITE_API_URL` (default `http://127.0.0.1:8000`), stripping `/api`. Production requires its own same-origin reverse proxy with streaming buffering/caching disabled and long inference timeouts. Do not automatically retry analysis POSTs.
- PocketBase currently only serves static files. Event/analysis persistence and collections are unimplemented; proposed `Events` fields are `event_id`, nullable `group_id`, and `text`, and the `Analysis` schema remains unfinished. Document API and schema decisions as they are added.

## Build, Test, and Development Commands

Run commands from the indicated directory using PowerShell.

- In `frontend/`, `pnpm install` installs dependencies using `pnpm-lock.yaml`.
- `pnpm dev` starts Vite with hot reload.
- `pnpm build` runs TypeScript project checks and produces `dist/`.
- `pnpm lint` checks TypeScript and React rules through ESLint.
- `pnpm test` runs `tests/*.test.mjs` with Node's built-in test runner; use Node 22.18+ and run `pnpm build` first because proxy tests also exercise preview.
- `pnpm preview` previews the production build locally.
- In `frontend/`, `node tests/browser-smoke.mjs '<path-to-playwright-package>'` checks the built UI with mocked APIs after `pnpm build`; requires a locally available Playwright package and Chromium or Edge.
- In `backend/`, use Python 3.10+ and uv. `uv sync --extra CPU` installs the Windows/Linux CPU profile; `uv sync --extra CUDA` installs the Linux-only CUDA 13.0 profile including vLLM 0.29.0. Choose exactly one; plain `uv sync` does not install PyTorch. CUDA binaries must match Spark's ARM64 architecture when deployed there. FastAPI is constrained to vLLM's supported 0.133–0.136 range.
- `uv run --extra CPU uvicorn app:app` starts the API; use `--extra CUDA` for the CUDA profile. Startup requires `MODEL_ID`; `MODEL_DEVICE` accepts `auto`, `cpu`, or `cuda`. Startup reads `backend/.env` without overriding process variables. `LOG_LEVEL` defaults to `INFO`; `DEBUG` adds generation metrics and validation/retry logs. See `backend/README.md` for setup details.
- `uv run --extra CPU python -m py_compile app.py workflows.py` checks backend syntax without loading a model.
- `uv run --extra CPU python -m pytest` runs the mocked backend suite; `uv lock --check` verifies the lockfile. Use the selected CUDA extra instead where appropriate.
- In `pocketbase/`, `go run . serve` starts the service; `go build .` compiles it. Go version: see `go.mod`.

## Coding Style & Naming Conventions

Match nearby code: TypeScript uses two spaces, single quotes, and no semicolons; Python uses four spaces; format Go with `gofmt`. Use PascalCase for React components, camelCase for TypeScript functions/variables, and snake_case for Python functions. ESLint is configured; no dedicated frontend/Python formatter is configured.

## Testing Guidelines

Run the smallest relevant checks for the change. Frontend verification uses lint/build and Node tests in `tests/*.test.mjs`, covering health/API contracts, stream state, proxying, navigation, rendered markup, and evidence linking. The optional browser smoke script serves `dist/` with mocked APIs and checks desktop/narrow layouts, keyboard navigation, transitions, scrolling, and evidence selection without contacting the backend. Backend pytest suites mock model loading and generation; they cover startup, API/stream contracts, category validation/retries, title fallback, and evidence filtering without downloading weights or requiring a GPU. No coverage threshold is configured. Follow existing test naming and document any new runner. Describe manual UI verification and disclose unrun checks.

When implementing features, do not run any tests that require loading a model, including tests whose fixtures or setup load models. Use mocks or model-independent checks instead, and report any model-loading tests that were skipped.

Do not start the real backend or run `smoke_articles.py` as routine feature verification: startup loads a model, and the smoke script performs real inference against a resident model. Reserve these checks for an explicit request for real-model verification; mocked tests do not establish classification quality.

## Commit & Pull Request Guidelines

History uses descriptive subjects such as `pocketbase setup`; no formal prefix convention exists. Keep commits focused. PRs should explain changes, affected services, verification, and related issues. Include UI screenshots and disclose unrun checks.

## Agent & Configuration Practices

Use PowerShell, `rg`, and `apply_patch`; inspect existing code before editing and preserve unrelated changes. Never commit credentials or local database contents. Request escalation when necessary commands fail because of sandbox restrictions.
