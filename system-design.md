
# Overview
![image](assets/system-overview.png)

## Frontend
TypeScript React homepage with an event textbox, analysis submission, and a
search input (search results are not implemented). The browser calls
`POST /api/analyze-event/stream`; the development/preview proxy forwards this to the
backend's `/analyze-event/stream` using `VITE_API_URL`. Production requires the same proxy
rewrite. Homepage colors are configurable in `frontend/src/colors.css`.
The top-right menu switches between Hem, Status and Sammanfattning. Status is
available after submission; Sammanfattning requires a successful analysis.
Navigation preserves the current analysis and any active request. Returning Home
allows a replacement submission after processing finishes; only one analysis is
kept in memory. Completion opens the summary automatically only when Status is
selected, and completed Status remains accessible through the menu.

Submission immediately opens a status screen with registry-ordered expandable
workflow rows in one scrolling panel. Queued rows are greyed out, the current row
shows a spinner and completed rows show a checkmark with predicted tags. Only
completed rows expand, showing matched categories and verified supporting quotes.
A progress ring below the workflow list disappears on successful completion;
failures retain partial results and mark unrun workflows. Successful terminal
confirmation opens a summary showing unchanged original input on the left and
shared expandable workflow widgets on the right, separated by a divider.
Exact supporting quotes highlight all
occurrences; overlapping passages retain all associations. Hover/focus connects
passages and workflows in both directions; click/tap pins selection, Escape clears
it. Text/results scroll independently and stack on mobile. State is in memory only.
The title text is initially absent, with its heading area reserved to keep other
widgets in place. A background title step replaces the former UUID
heading once finished; both analysis and summary screens use the generated title.
It has no status row or contribution to category progress.

## Backend
FastAPI exposes `POST /analyze-event`, accepting JSON with a non-empty `text`
string. It trims the text and currently returns
`{"status":"ok","title":"Händelserubrik","results":{"risks":[],"reach":[],"service":[]}}`.
Each workflow's list may contain zero, one, or multiple matches, each with `ID`
and display `name`. Invalid text returns HTTP 422.

The lifespan loads a configurable Transformers tokenizer and base model once
per server process into `app.state.runtime`. `MODEL_ID` selects a Hugging Face
model or local directory; `MODEL_DEVICE=auto|cpu|cuda` selects its device.
Each server worker loads its own model. CPU and CUDA 12.8 dependency profiles
are managed with uv extras; see [backend setup](backend/README.md).

`workflows.py` defines independent workflow functions and the `WORKFLOWS` registry.
A fixed `generate_title` step outside the registry runs before categorization,
using a separate Swedish prompt and the shared model. It generates a factual
title, strips surrounding quotes/whitespace and validates 1–10 words using Pydantic,
without truncation. Overlong titles use the fallback. Generation allows
64 output tokens. Inference failure or unusable output logs a warning and falls
back to `Händelseanalys` without retrying; 413/503 errors still stop analysis.
The risk, reach, and service workflows each use their own Swedish system prompt
and the matching category file in `backend/schemas/`. Each evaluates all of its
IDs and descriptions in one Gemma generation call, reusing the same processor and
model instance. The registry runs the workflows in order and combines their results. Definitions
are validated once at startup; returned IDs are validated and mapped to display
names. Each categorization call also returns supporting quotes; only nonblank exact
substrings are retained and deduplicated. Invalid evidence is logged and omitted,
while valid categories remain available. Quote presence does not establish factual
or classification accuracy. A shared runtime lock serializes model access across requests and workflows.
Inputs exceeding 8192 tokens return HTTP 413; invalid model output or inference
failures return HTTP 502; unsupported model runtimes return HTTP 503.

`POST /analyze-event/stream` uses the same validation and execution but streams
`analysis_started`, `title_completed`, `workflow_started`, `workflow_completed`, and terminal
`analysis_completed` or `workflow_failed` events. Streaming inference runs in a
worker thread; errors after headers are sent are stream events. The frontend consumes
these updates through fetch. Production proxies must avoid buffering and allow
long inference timeouts. Stream matches include `evidence: string[]`; the original
JSON endpoint excludes evidence and adds a top-level title. Categorization allows 4096
output tokens to accommodate quotes, keeping the existing 8192 input-token limit.

Each validated request keeps a fresh UUID v4 in logs and the `X-Analysis-ID`
header, also included as `analysis_id` in stream metadata. Titles are display
metadata and do not replace this identifier. UUIDs are retained for future storage;
neither titles nor identifiers are persisted yet.

The evidence-linked summary and LLM title generation milestones are implemented.
A sidebar to switch event analyses remains future work. PocketBase persistence remains unimplemented;
the diagram below describes the intended architecture.

![backend](assets/system-backend.png)

## Pocketbase
Data layer using Pocketbase, serving using Go. 

Collections
- Events (event_id, group_id: nullable, text)
- Analysis ()
