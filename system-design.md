
# Overview
![image](assets/system-overview.png)

## Frontend
TypeScript React homepage with an event textbox, analysis submission, and a
search input (search results are not implemented). The browser calls
`POST /api/analyze-event/stream`; the development/preview proxy forwards this to the
backend's `/analyze-event/stream` using `VITE_API_URL`. Production requires the same proxy
rewrite. Homepage colors are configurable in `frontend/src/colors.css`.
Submission immediately opens a status screen showing queued, current and completed
workflows. Completed results append to expandable rows in an internally scrolling
panel. A progress ring below the workflow list disappears on successful completion;
failures retain partial results and mark unrun workflows. Successful terminal
confirmation replaces status with a summary showing unchanged original input
and registry-ordered expandable workflows. Exact supporting quotes highlight all
occurrences; overlapping passages retain all associations. Hover/focus connects
passages and workflows in both directions; click/tap pins selection, Escape clears
it. Text/results scroll independently and stack on mobile. State is in memory only.

## Backend
FastAPI exposes `POST /analyze-event`, accepting JSON with a non-empty `text`
string. It trims the text and currently returns
`{"status":"ok","results":{"risks":[],"reach":[],"service":[]}}`.
Each workflow's list may contain zero, one, or multiple matches, each with `ID`
and display `name`. Invalid text returns HTTP 422.

The lifespan loads a configurable Transformers tokenizer and base model once
per server process into `app.state.runtime`. `MODEL_ID` selects a Hugging Face
model or local directory; `MODEL_DEVICE=auto|cpu|cuda` selects its device.
Each server worker loads its own model. CPU and CUDA 12.8 dependency profiles
are managed with uv extras; see [backend setup](backend/README.md).

`workflows.py` defines independent workflow functions and the `WORKFLOWS` registry.
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
`analysis_started`, `workflow_started`, `workflow_completed`, and terminal
`analysis_completed` or `workflow_failed` events. Streaming inference runs in a
worker thread; errors after headers are sent are stream events. The frontend consumes
these updates through fetch. Production proxies must avoid buffering and allow
long inference timeouts. Stream matches include `evidence: string[]`; the original
JSON endpoint excludes this field and remains compatible. Generation allows 4096
output tokens to accommodate quotes, keeping the existing 8192 input-token limit.

The evidence-linked summary milestone is implemented. Future frontend milestones
are LLM title generation and a sidebar to switch event analyses. PocketBase persistence remains unimplemented;
the diagram below describes the intended architecture.

![backend](assets/system-backend.png)

## Pocketbase
Data layer using Pocketbase, serving using Go. 

Collections
- Events (event_id, group_id: nullable, text)
- Analysis ()
