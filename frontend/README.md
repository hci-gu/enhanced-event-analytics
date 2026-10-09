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
The UUID from `analysis_started.analysis_id` is displayed as the analysis title.
The results panel is initially empty; visible status captions and result headings
are omitted while screen-reader announcements remain available.
Queued workflows are muted; the active workflow is bold with a spinner; completed
workflows are bold with a check. Completed result rows appear in completion order
and expand to show category names, or “Inga kategorier matchade.” The results panel
scrolls internally without jumping when a new result arrives.

The progress ring near the bottom center of the left column counts completed workflows. It disappears
only after terminal success. Failures retain partial results and a static progress
ring; the active workflow fails and remaining workflows are marked “Ej körd.”
Stream interruption or invalid messages display an error without rerunning inference.
Successful terminal confirmation opens the evidence-linked summary; failures stay
on the status screen. Neither screen has a back button. State is in
memory only: refreshing returns to the homepage. On mobile, status is above results.
New status/result colors are customizable in `src/colors.css`.

## Evidence-linked summary

The summary keeps the UUID title, displays the original input unchanged on the
left, and shows expandable workflows in backend registry order on the right.
Each pane scrolls internally; mobile stacks text above results.
Verified supporting quotes are highlighted at every exact occurrence. Overlapping
passages retain all category/workflow links and display workflow colors in bands.
Edit `--evidence-risks-color`, `--evidence-reach-color`, `--evidence-service-color`,
and `--evidence-fallback-color` in `src/colors.css` to customize them.

Hover or focus a passage to emphasize its workflows; hover or focus a workflow
to emphasize its passages. Click/tap either to pin selection; select it again or
press Escape to clear. Enter/Space selects keyboard-focused passages. Temporary
hover/focus takes precedence and leaving restores the pinned selection. Workflow
rows still expand normally. Categories with no verified quotes display
“Verifierat textstöd saknas.” Quotes are model-selected support: exact presence is
validated, but their reasoning and classification quality still need review.

### Future frontend milestones

1. Make the LLM's first workflow generate a short event title. Display that title
   instead of the UUID, keeping the backend UUID as the stable analysis reference.
2. Add a sidebar to switch between different event analyses, with a defined storage
   and restoration strategy for their state/results.
The evidence-linked summary milestone is implemented. Title generation, sidebar
navigation, saved analysis history, and search results remain future work.

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
Evidence tests cover exact text preservation, Unicode, repeated and overlapping
quotes, stream validation, and selection state. Summary markup tests cover
accessible highlights, registry order, missing evidence, and safe text rendering.
Run `pnpm build` before `pnpm test` so preview has a production build to serve.

For manual verification, check desktop/mobile layouts and keyboard focus. Search
should accept text without navigating on Enter. Blank event text must disable
Analysera. Verify immediate status-screen transition, sequential progress, matched
names, empty results, retained partial results after failure, hidden progress after
success, expandable rows and internal scrolling. Keyboard focus moves to the status
screen heading; details can be expanded by keyboard. Reduced motion stops spinner
animation while retaining the active workflow's text status.
After terminal success, verify summary highlights in both directions, pinned
selection, Escape, keyboard Enter/Space, original whitespace, and independent
scrolling. Failures and premature disconnections must not open the summary.

Deploy `dist/` with a same-origin reverse proxy that forwards `/api/*` to the
backend and strips `/api`. Vite's proxy and `VITE_API_URL` do not configure a static
production host; configure the backend target in that host's reverse proxy.
Disable response buffering/caching for `/api/analyze-event/stream` and allow long
read timeouts for inference. The frontend does not apply the health check's 10-second
timeout to analysis. Do not automatically retry this POST request.
