# Homepage

React and TypeScript homepage with Swedish labels. Search accepts text but does
not submit or display results yet. Analysera sends trimmed event text to the API
and immediately opens a live workflow status screen.

On each homepage load, a single `GET /api/health` request checks the backend's
`/health` endpoint. Only an HTTP success with JSON `status: "ok"` passes.
Other statuses, invalid responses, network errors, and a 10-second timeout show
a dismissible error dialog. Close it with Stäng or Escape; reloading checks again.

## Development

Run from `frontend/` with pnpm:

```powershell
pnpm install
Copy-Item .env.example .env
pnpm dev
```

If `.env` already exists, rename its `API_URL` setting to `VITE_API_URL` and keep
the existing URL value. `VITE_API_URL` is the backend base URL, defaulting to
`http://127.0.0.1:8000`.
It is read by Vite from `.env` or the process environment (which takes precedence),
and configures the proxy. Vite also exposes `VITE_` settings to browser code;
use a public backend URL without credentials. Restart Vite after changing it.
Start the backend separately using the instructions in `../backend/README.md`.

The browser posts `{ "text": "..." }` to `/api/analyze-event/stream`. Both `pnpm dev`
and `pnpm preview` proxy `/api/*` to `VITE_API_URL`, stripping the `/api` prefix.

## Colors and layout

Edit `src/colors.css` to customize all homepage colors. It contains primary,
page background, text, border, focus and feedback colors, plus separate
textbox, search, and button colors (including hover and disabled states).
Some widget colors reference the shared variables; replace those references with
color values if you want to customize widgets independently.
Layout styles live in `src/App.css`; global styles live in `src/index.css`.
The event textbox starts with one line and grows with newlines or wrapped text.
Its widget is capped at 290px (or the available viewport space on small screens);
longer text scrolls inside the textarea. Deleting text shrinks it again.

## Workflow status screen

The backend sends the ordered workflow catalog, starts, results, and a terminal
success/failure event using the stream contract in `../backend/README.md`.
Queued workflows are muted; the active workflow is bold with a spinner; completed
workflows are bold with a check. Completed result rows appear in completion order
and expand to show category names, or “Inga kategorier matchade.” The results panel
scrolls internally without jumping when a new result arrives.

The progress ring below the left-hand list counts completed workflows. It disappears
only after terminal success. Failures retain partial results and a static progress
ring; the active workflow fails and remaining workflows are marked “Ej körd.”
Stream interruption or invalid messages display an error without rerunning inference.
The screen stays open after success or failure, with no back button. State is in
memory only: refreshing returns to the homepage. On mobile, status is above results.
New status/result colors are customizable in `src/colors.css`.

### Future frontend milestones

1. Add a sidebar to switch between different event analyses, with a defined storage
   and restoration strategy for their state/results.
2. Add a report/summary page that renders workflow findings within the event text.

These milestones, saved analysis history, and search results are not implemented.

## Verification and production

```powershell
pnpm lint
pnpm build
pnpm test
pnpm preview
```

API tests use Node's built-in test runner and TypeScript support (Node 22.18+).
They verify request payloads, health checks, fragmented streams, workflow state,
terminal progress, failure handling, and unbuffered development/preview proxy
forwarding against a temporary local mock backend.
Screen markup tests compile TSX in memory with the existing TypeScript dependency
and use React server rendering to verify spinner states, collapsed result rows,
and the removal of the progress ring. They do not replace visual browser checks.
Run `pnpm build` before `pnpm test` so preview has a production build to serve.

For manual verification, check desktop/mobile layouts and keyboard focus. Search
should accept text without navigating on Enter. Blank event text must disable
Analysera. Verify immediate status-screen transition, sequential progress, matched
names, empty results, retained partial results after failure, hidden progress after
success, expandable rows and internal scrolling. Keyboard focus moves to the status
screen heading; details can be expanded by keyboard. Reduced motion stops spinner
animation while retaining the active workflow's text status.

Deploy `dist/` with a same-origin reverse proxy that forwards `/api/*` to the
backend and strips `/api`. Vite's proxy and `VITE_API_URL` do not configure a static
production host; configure the backend target in that host's reverse proxy.
Disable response buffering/caching for `/api/analyze-event/stream` and allow long
read timeouts for inference. The frontend does not apply the health check's 10-second
timeout to analysis. Do not automatically retry this POST request.
