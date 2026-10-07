# Homepage

React and TypeScript homepage with Swedish labels. Search accepts text but does
not submit or display results yet. Analysera sends trimmed event text to the API;
the current backend returns a placeholder, not a completed analysis.

## Development

Run from `frontend/` with pnpm:

```powershell
pnpm install
Copy-Item .env.example .env
pnpm dev
```

If `.env` already exists, keep it and edit its `API_URL` setting as needed.
`API_URL` is the backend base URL, defaulting to `http://127.0.0.1:8000`.
It is read by Vite from `.env` or the process environment (which takes precedence),
and is not exposed to browser code. Restart Vite after changing it.
Start the backend separately using the instructions in `../backend/README.md`.

The browser posts `{ "text": "..." }` to `/api/analyze-event`. Both `pnpm dev`
and `pnpm preview` proxy `/api/*` to `API_URL`, stripping the `/api` prefix.

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

## Verification and production

```powershell
pnpm lint
pnpm build
pnpm test
pnpm preview
```

API tests use Node's built-in test runner and TypeScript support (Node 22.18+).
They verify the request payload, blank input, placeholder, failure responses,
and development/preview proxy forwarding against a temporary local mock backend.
Run `pnpm build` before `pnpm test` so preview has a production build to serve.

For manual verification, check desktop/mobile layouts and keyboard focus. Search
should accept text without navigating on Enter. Blank event text must disable
Analysera. Submission should preserve text, prevent duplicate requests, and show
loading, placeholder, HTTP error, network error, or invalid-response feedback.

Deploy `dist/` with a same-origin reverse proxy that forwards `/api/*` to the
backend and strips `/api`. Vite's proxy and `API_URL` do not configure a static
production host; configure the backend target in that host's reverse proxy.
