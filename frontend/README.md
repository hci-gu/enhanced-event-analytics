# Editorial analysis workspace

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

The home, status and summary screens implement the approved Superdesign Editorial
designs: ivory surfaces, terracotta accents, a subtle paper grid, serif headings,
thin rules and offset card borders. The header and Sidor dropdown remain available
on every screen. Prototype example data and badges are not included in the app;
all workflow names, states, categories and evidence come from the analysis stream.
The application targets PC browsers. Narrow-window rules keep controls usable
when desktop windows are resized; phone layouts are not a product requirement.

Crimson Pro and Switzer are loaded through Google Fonts and Fontshare CSS imports
in `src/index.css`. Georgia and system sans fonts are used if those services are
unavailable. The font URLs contain no event or analysis data.

Edit `src/colors.css` to customize all shared colors. It contains primary,
page background, text, border, focus and feedback colors, plus separate
textbox, search, and button colors (including hover and disabled states).
Some widget colors reference the shared variables; replace those references with
color values if you want to customize widgets independently.
Layout styles live in `src/App.css`; global styles live in `src/index.css`.
The event textbox has a generous minimum height and grows with newlines or wrapped
text up to 560px on desktop (400px on mobile). Longer text scrolls internally.
The home screen itself scrolls on short viewports so the submit action stays
reachable. Motion is disabled when the user requests reduced motion.

## Workflow status screen

The backend sends the ordered workflow catalog, starts, results, and a terminal
success/failure event using the stream contract in `../backend/README.md`.
The heading area starts empty and displays the Swedish title from `title_completed`
once available. The UUID stays in internal metadata. Workflow rows stay in registry
order in one scrolling panel. Queued rows are greyed out; the active row has a
subtle pulsing indicator and a visible Pågår label; completed rows have a checkmark
and predicted tags. Only completed rows
expand, showing categories and verified supporting quotes, or “Inga kategorier matchade.”
Tags wrap without truncation, and the allocated title area prevents layout jumps.

The thin progress bar below the scrolling rows counts completed workflows and
shows the completed/total count. It disappears
only after terminal success. Failures retain partial results and a static progress
bar; the active workflow fails and remaining workflows are marked “Ej körd.”
Stream interruption or invalid messages display an error without rerunning inference.
Successful terminal confirmation opens the evidence-linked summary only when
Status is selected; failures stay on Status. State is in memory only: refreshing
returns to the homepage. Mobile rows wrap their tags below the workflow label.
New status/result colors are customizable in `src/colors.css`.

## Evidence-linked summary

The summary keeps the generated title, displays the original input unchanged on the
left, and shows expandable workflows in backend registry order on the right.
Category names remain visible when result groups are collapsed. Ny analys returns
to an empty composer while preserving the completed result in the Sidor menu until
a new submission replaces it.
Each pane scrolls internally; mobile stacks text above results.
Verified supporting quotes are highlighted at every exact occurrence. Overlapping
passages retain all category/workflow links and display workflow colors in bands.
Edit `--evidence-risks-color`, `--evidence-reach-color`, `--evidence-service-color`,
and `--evidence-fallback-color` in `src/colors.css` to customize them.
Each result-group label has a filled dot in its evidence color. Hover, keyboard
focus and linked evidence selection tint the card with a 45% blend of that color
over the card surface. The dot remains at full strength.

The Sidor dropdown fades and slides in and out; closed navigation is inert so its
links cannot receive focus during the closing transition. Completed workflow
disclosures expand/collapse over 180ms, including when activated by keyboard.
Both transitions honor reduced motion.

Hover or focus a passage to emphasize its workflows; hover or focus a workflow
to emphasize its passages. Click/tap either to pin selection; select it again or
press Escape to clear. Enter/Space selects keyboard-focused passages. Temporary
hover/focus takes precedence and leaving restores the pinned selection. Workflow
rows still expand normally. Categories with no verified quotes display
“Verifierat textstöd saknas.” Quotes are model-selected support: exact presence is
validated, but their reasoning and classification quality still need review.

## Navigation

The top-right menu offers Hem, Status and Sammanfattning on every page, beside
the search on every screen. Status is disabled until submission; Sammanfattning
requires successful completion. Returning Home preserves input/results and does
not interrupt an active stream. New submissions are blocked while processing;
afterward, submitting another event replaces the previous analysis. Completed
Status can be revisited without redirecting automatically.
The dropdown closes after selection, outside click or Escape. Tab, arrow keys,
Home and End support keyboard navigation, skipping disabled entries.

### Future frontend milestones

Title generation, page navigation and the evidence-linked summary are implemented.
Saved analysis history, navigation between multiple analyses, and search results
remain future work.

## Verification and production

```powershell
pnpm lint
pnpm build
pnpm test
pnpm preview
```

With a locally available Playwright package and Chromium or Edge, run the browser
smoke check after `pnpm build`:

```powershell
node tests/browser-smoke.mjs '<path-to-playwright-package>'
```

It serves the production build on a temporary local port with a mocked streaming
API. Desktop/mobile checks cover dropdown keyboard/dismissal behavior, retained
results, completion navigation, replacement submissions, stable title placement,
tags, quotes, evidence selection and scrolling. Screenshots are written to a
temporary directory reported by the command. It does not contact the backend or
load a model.

API tests use Node's built-in test runner and TypeScript support (Node 22.18+).
They verify request payloads, health checks, fragmented streams, workflow state,
terminal progress, failure handling, and unbuffered development/preview proxy
forwarding against a temporary local mock backend.
Screen markup tests compile TSX in memory with the existing TypeScript dependency
and use React server rendering to verify spinner states, collapsed result rows,
and the removal of the progress bar. They do not replace visual browser checks.
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
animation while retaining the active workflow's text status. Verify Ny analys
clears the composer and leaves completed results accessible through the menu.
After terminal success, verify summary highlights in both directions, pinned
selection, Escape, keyboard Enter/Space, original whitespace, and independent
scrolling. Failures and premature disconnections must not open the summary.

Deploy `dist/` with a same-origin reverse proxy that forwards `/api/*` to the
backend and strips `/api`. Vite's proxy and `VITE_API_URL` do not configure a static
production host; configure the backend target in that host's reverse proxy.
Disable response buffering/caching for `/api/analyze-event/stream` and allow long
read timeouts for inference. The frontend does not apply the health check's 10-second
timeout to analysis. Do not automatically retry this POST request.
