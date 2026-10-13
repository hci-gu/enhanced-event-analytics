
# Overview
![image](assets/system-overview.png)

## Frontend
TypeScript React homepage with an event textbox, analysis submission, and a
search input (search results are not implemented). The browser calls
`POST /api/analyze-event/stream`; the development/preview proxy forwards this to the
backend's `/analyze-event/stream` using `VITE_API_URL`. Production requires the same proxy
rewrite. Shared colors are configurable in `frontend/src/colors.css`.
All three screens use the approved Editorial design: ivory surfaces, terracotta
accents, serif headings, thin borders and a persistent header with search and Sidor
navigation. Crimson Pro and Switzer load from font services with local fallbacks.
The top-right menu switches between Hem, Status and Sammanfattning. Status is
available after submission; Sammanfattning requires a successful analysis.
Navigation preserves the current analysis and any active request. Returning Home
allows a replacement submission after processing finishes; only one analysis is
kept in memory. Completion opens the summary automatically only when Status is
selected, and completed Status remains accessible through the menu.

Submission immediately opens a status screen with registry-ordered expandable
workflow rows in one scrolling panel. Queued rows are greyed out, the current row
shows a subtle activity pulse and visible status text; completed rows show a checkmark with predicted tags. Only
completed rows expand, showing matched categories and verified supporting quotes.
A thin progress bar and completed/total count below the workflow list disappear on successful completion;
failures retain partial results and mark unrun workflows. Successful terminal
confirmation opens a summary showing unchanged original input on the left and
shared expandable workflow widgets on the right in a second content column.
Collapsed groups show their category names. Ny analys clears the composer and
focuses it while retaining completed results in the menu until a new submission.
Exact supporting quotes highlight all
occurrences; overlapping passages retain all associations.
Each workflow header has an unlabeled highlight switch, enabled by default and
available while collapsed. Disabled workflows leave other overlapping colors intact.
Activating a result quote scrolls its first occurrence to roughly 25% down the text
viewport, within scroll limits, even when its workflow highlights are off.
Hover/focus connects passages and workflows in both directions; click/tap pins selection, Escape clears
it. Text/results scroll independently and stack on mobile. State is in memory only.
The title text is initially absent, with its heading area reserved to keep other
widgets in place. A background title step replaces the former UUID
heading once finished; both analysis and summary screens use the generated title.
It has no status row or contribution to category progress.

## Backend
FastAPI exposes `POST /analyze-event`, accepting JSON with a non-empty `text`
string. It trims the text and currently returns
`{"status":"ok","title":"Händelserubrik","results":{"risks":[],"reach":[],"service":[],"properties":[],"protection":[]}}`.
Each workflow's list may contain zero, one, or multiple matches, each with `ID`
and display `name`. Invalid text returns HTTP 422.
Successful responses also include `embedding` and `embedding_error` fields.

The lifespan loads a configurable Transformers tokenizer and base model once
per server process into `app.state.runtime`. `MODEL_ID` selects a Hugging Face
model or local directory; `MODEL_DEVICE=auto|cpu|cuda` selects its device.
Each server worker loads its own model. CPU and CUDA 12.8 dependency profiles
are managed with uv extras; see [backend setup](backend/README.md).

Startup additionally loads text-only `google/embeddinggemma-2` using Transformers
5.19+, with audio and vision towers disabled, onto the same resolved device as
the LLM. Both models are required for startup. Embeddings use bfloat16 on
compatible CUDA hardware, otherwise float32. INFO logs record embedding model
load start and completion with duration, model ID, device, and dtype. DEBUG logs
record full/embedded token counts, truncation, embedding duration, and status;
CUDA timing synchronization is enabled only at DEBUG. Input text and vectors
are not logged.

`POST /embed-event` accepts the same text payload and returns a normalized
768-dimensional document embedding with model/task/dimension metadata, token
counts, and a truncation flag. The document prefix is `title: none | text: `;
no generated title is needed. Inputs are right-truncated to 8192 tokens including
prefix and special tokens. Attention-mask-aware mean pooling of projected token
representations and L2 normalization run in float32. Invalid vectors or inference
failures return 502. Query and other embedding tasks remain future work.

Both analysis endpoints submit embedding work before title generation to a
lifespan-managed single-worker executor. Its separate model lock allows overlap
with LLM inference while serializing embeddings. JSON responses and the existing
`analysis_completed` stream payload return the vector only at completion, with
`embedding_error: null`. Embedding failures preserve successful classification
with `embedding: null` and a structured 502 embedding error. Analysis failures
retain existing terminal behavior. Queued embedding work is cancelled on failure
or stream closure; running inference may finish with its result discarded.
Shutdown waits for active embedding work before releasing the runtimes.
The frontend accepts but does not retain these additional fields. No text/vector
persistence, related-event search, clustering, or graph storage is implemented.

`workflows.py` defines independent workflow functions and the `WORKFLOWS` registry.
A fixed `generate_title` step outside the registry runs before categorization,
using a separate Swedish prompt and the shared model. It generates a factual
title, strips surrounding quotes/whitespace and validates 1–10 words using Pydantic,
without truncation. Overlong titles use the fallback. Generation allows
64 output tokens. Inference failure or unusable output logs a warning and falls
back to `Händelseanalys` without retrying; 413/503 errors still stop analysis.
The risk, reach, service, properties, and protection workflows each use their own Swedish system prompt
and the matching category file in `backend/schemas/`. Each evaluates all of its
IDs and descriptions in one Gemma generation call, reusing the same processor and
model instance. Properties selects supported characteristics of the event's
development; assessment examples guide category selection without adding output
fields. Protection selects affected or explicitly threatened protection values.
Both use the existing category and evidence result format. The registry runs
risks, reach, service, properties, then protection and combines their results. Definitions
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
