# Event analysis backend

Run these PowerShell commands from `backend/`. Python 3.10+ and uv are required.
Choose exactly one PyTorch profile (extra names are case insensitive):

```powershell
uv sync --extra CPU
# Or, on a Linux NVIDIA CUDA machine (includes both serving engines):
uv sync --extra CUDA
```

The CPU profile supports Windows and Linux and uses the official CPU-only PyTorch
index. The CUDA profile targets Linux only and includes vLLM 0.29.0, Accelerate,
PyTorch 2.13.0 and torchvision 0.28.0 from the official CUDA 13.0 index. It needs
a CUDA 13.0-compatible NVIDIA driver. Both profiles cannot be enabled together.
The CUDA extra has Linux markers and does not supply a Windows GPU installation.
FastAPI is constrained to 0.133–0.136 to match vLLM's declared dependencies.
Plain `uv sync` does not install PyTorch; select a profile when running the API.

Use [`google/gemma-4-26B-A4B-it`](https://huggingface.co/google/gemma-4-26B-A4B-it)
for event analysis, then launch:

```powershell
$env:MODEL_ID = 'google/gemma-4-26B-A4B-it'
$env:MODEL_DEVICE = 'auto'
$env:SERVING_ENGINE = 'transformers'
uv run --extra CPU uvicorn app:app
# Or use the CUDA profile:
uv run --extra CUDA uvicorn app:app
```

`MODEL_ID` is required. `MODEL_DEVICE` accepts `auto` (default), `cpu`, or `cuda`.
Auto selects CUDA when available and otherwise CPU; explicit CUDA fails startup
if unavailable. Startup loads `backend/.env` using `python-dotenv`. You can put
`MODEL_ID` and `MODEL_DEVICE` there instead of setting them in PowerShell.
Existing process environment variables take precedence over `.env` values.
For an existing installation, update `MODEL_ID` in your local `.env` or process
environment and restart the backend. The 26B A4B checkpoint is a mixture-of-experts
model; its active parameter count does not mean only 4B parameters need to fit
in memory. The current loader places the full checkpoint on CPU or GPU 0.

## Serving engine selection

`SERVING_ENGINE` defaults to `transformers`; its only accepted values are
`transformers` and `vllm` (lowercase, surrounding whitespace trimmed). Invalid
values fail startup. `MODEL_ID` remains required for either engine, with no
automatic model selection or fallback between engines.

For a DGX Spark running Linux, install the CUDA extra and configure:

```dotenv
SERVING_ENGINE=vllm
MODEL_ID=nvidia/Gemma-4-26B-A4B-NVFP4
MODEL_DEVICE=cuda
VLLM_GPU_MEMORY_UTILIZATION=0.50
VLLM_KV_CACHE_MEMORY_BYTES=
```

Launch with `uv run --extra CUDA uvicorn app:app --workers 1`. The embedded
async vLLM Python engine lives for the FastAPI application's lifetime; it starts
internal worker processes but exposes no separate HTTP server. CUDA worker
creation defaults to `spawn` because embeddings have already initialized CUDA.
vLLM requires Linux, available CUDA, and `MODEL_DEVICE=auto` or `cuda`; explicit
CPU selection fails startup. Transformers remains the CPU/default option and
does not import vLLM. Use the Google BF16 checkpoint above for Transformers and
the [NVIDIA pre-quantized NVFP4 checkpoint](https://huggingface.co/nvidia/Gemma-4-26B-A4B-NVFP4)
for vLLM. The latter loads saved quantized weights, without re-quantizing each boot.
Remote model code is not enabled implicitly.

`VLLM_GPU_MEMORY_UTILIZATION` is the fraction of total GPU memory budgeted for
vLLM, including its model and KV cache. It defaults to `0.50`, must be finite and
greater than zero and at most one, and is validated only in vLLM mode. Startup
loads EmbeddingGemma on CUDA first so its resident allocation is visible to vLLM.
Allow additional headroom for embedding activations and the OS. Spark shares
physical RAM between CPU and GPU; this budget is not a hard total-memory limit
or a guarantee that a selected checkpoint fits. Existing `.env` values override
the new default, so change an existing `0.70` setting explicitly.

`VLLM_KV_CACHE_MEMORY_BYTES` optionally specifies a positive integer allocation
for the KV cache, in bytes (for example, `4294967296` for 4 GiB). Blank or absent
uses automatic sizing. When set, vLLM ignores `gpu_memory_utilization` for cache
sizing. This limits only the KV cache, not model weights, temporary allocations,
embeddings, or total system memory. Check startup's reported cache capacity: it
must accommodate the 12,288-token context, or startup fails. The example size
is not a hardware-verified recommendation.

vLLM uses `language_model_only=True` to disable multimodal inputs and
`enforce_eager=True` to avoid CUDA graph memory overhead. Eager execution can
reduce throughput. These settings apply only to the embedded vLLM engine.

The engine uses one GPU, tensor parallel size one, one simultaneous generation
sequence, and a 12,288-token context budget (8,192 input plus 4,096 output).
Generation remains serialized across workflows/requests, uses greedy decoding,
and disables thinking through the chat template. Prepared prompt token IDs go
directly to vLLM; completed output tokens are decoded without special tokens.
Synchronous workflow threads submit work to FastAPI's event loop, keeping that
loop responsive. Shutdown cancels/aborts outstanding engine requests and releases
vLLM workers. Stream disconnect behavior is otherwise unchanged.

Spark is Linux ARM64 (GB10). Use compatible ARM64 CUDA/PyTorch/vLLM binaries and
the pinned dependency stack. Package resolution alone does not verify Spark's
NVFP4 kernels. Consult [vLLM installation guidance](https://docs.vllm.ai/en/v0.29.0/getting_started/installation/gpu/)
for binaries, drivers, and any required kernel toolchain. Mocked tests do not
establish real-model classification quality or hardware compatibility.

## Logging and runtime

`LOG_LEVEL` defaults to `INFO` and controls backend and Uvicorn logging from
application startup onward. Set it in `.env` to `DEBUG`, `INFO`, `WARNING`,
`ERROR`, or `CRITICAL` (case insensitive), then restart the service. Invalid
values prevent startup. DEBUG logs report each LLM call's workflow, input/output
token counts, generation duration, and output tokens per second. Timing covers
`model.generate()` for Transformers and the awaited engine request for vLLM,
including prompt prefill, excluding lock waiting, prompt preparation, transfers,
and final decoding; Transformers CUDA is synchronized for DEBUG timing.
Output counts include generated special tokens, before decoding removes them.
Workflow logs report output validation, available/selected category counts and
selected IDs, or title fallback. `retries=0` with `output_valid=true` means the
first attempt passed validation. Each additional category generation increments
the retry count, and invalid output logs whether the retry limit is exhausted.
DEBUG does not enable logging for third-party libraries.
DEBUG also logs loading-stage start, completion/failure, and `duration_seconds`
for category definitions, device selection, model configuration, processor (Gemma) or tokenizer
(other models), weights, CPU device placement, and evaluation mode. CUDA models
load directly onto `cuda:0` with `device_map={"": "cuda:0"}`; there is no separate
CUDA `device_placement` stage or subsequent `.to()` call. The CUDA weights stage
is synchronized before its timer finishes. The weights stage includes
everything inside `from_pretrained()`, including checkpoint reading and model
construction and CUDA placement. Compare total startup time when benchmarking
against the previous separate placement stage. INFO retains the overall model-loading duration without stage logs
or the additional CUDA synchronization. Transformers 5.19 (the locked version)
already loads weights asynchronously by default; the older
`HF_ENABLE_PARALLEL_LOADING` flag is not used by that version.

`RETRY_LIMIT` defaults to `1` and must be a non-negative integer. Each category
workflow may retry malformed JSON or invalid category IDs this many times,
using the original event/category definitions plus corrective instructions.
With `1`, two invalid responses return HTTP 502; `0` disables retries. Configure
it in `.env` and restart. Invalid values prevent model loading. Inference failures,
input-limit errors, and unsupported models are not retried. Invalid evidence is
still discarded rather than retried, and the title retains its existing fallback.
The backend requires Transformers 5.19+ (below 6). In Transformers mode, Gemma 4 uses `AutoProcessor` and
`Gemma4ForConditionalGeneration`; the processor is available as
`app.state.runtime.processor` for chat-template preparation. Its tokenizer is
also available through `app.state.runtime.tokenizer`. Checkpoints are loaded
in their saved precision (`dtype="auto"`) to avoid an unnecessary float32 copy.
After updating dependencies, run `uv sync --extra CPU` or `uv sync --extra CUDA`
before restarting the service.
The first startup downloads model/tokenizer files into the Hugging Face cache
unless a local directory or cached model is used. Loading errors prevent startup.

In Transformers mode, FastAPI's lifespan loads the tokenizer and model once per server process and
enables evaluation mode. CUDA selection loads the full model directly onto GPU 0
using Accelerate (included in the CUDA extra). Explicit CPU selection stays on
CPU even when CUDA is available. They stay in
`app.state.runtime` until shutdown. Each Uvicorn worker loads its own copy, so
start with one worker to avoid multiplying RAM/VRAM usage.

Startup also loads `google/embeddinggemma-2` into `app.state.embedding_runtime`
on the LLM's resolved device. Both audio and vision towers are disabled; only
text embeddings are supported. It uses bfloat16 on CUDA with native support,
otherwise float32 (never float16). Both models must load successfully before the
service starts. The first startup may download both checkpoints. Each worker
holds both model copies, so account for their combined RAM/VRAM requirements.
Embedding model load start, completion with elapsed time, and model ID/device/dtype
are logged at INFO; loading failures include exception details.
DEBUG embedding logs include `input_tokens`, `embedded_tokens`, `truncated`,
`embedding_seconds`, and completion/failure status. Token counts include the
document prefix and special tokens. Timing starts after acquiring the embedding
lock and covers device transfer, inference, pooling, and float32 normalization;
it excludes queue time, tokenization, and conversion to a JSON vector. CUDA is
synchronized around that work only at DEBUG. Text and vectors are never logged.

## PocketBase persistence

Startup creates a reusable HTTP client for local PocketBase at
`http://127.0.0.1:8090`, checks `/api/health`, and closes the client on shutdown
after embedding workers finish. `POCKETBASE_URL` overrides the loopback HTTP address
(127.0.0.1, localhost or ::1); non-loopback URLs, credentials and URL paths are rejected. Requests
use a two-second timeout per HTTP operation and ignore proxy environment variables.
PocketBase being offline does not prevent startup; model loading
requirements still apply. Startup logs availability.

No backend superuser credential is required. `POCKETBASE_TOKEN` is no longer read;
remove an old entry from local configuration. Apply the collection migrations and
restart PocketBase before starting the backend. Python verifies/refreshes the
user's session, then sends that refreshed user token in the Authorization header
for every create/update in that analysis, including asynchronous embedding writes.
Tokens are kept per analysis and never placed in the shared client's headers,
returned by `/health`, or included in persistence logs. See the
[PocketBase authentication guide](https://pocketbase.io/docs/authentication/).

Both analysis endpoints create one Analysis record after verifying the session and before submitting inference,
using the request UUID, verified user ID in `created_by`, trimmed original text, and both statuses set to
`Processing`. They update the same record after title generation and every
completed workflow, retaining evidence in storage even though the JSON response
omits category evidence. Date results and nonfatal date errors are stored separately
in the optional `dates` and `dates_error` JSON fields, outside `predictions`.
Apply the date-field migration before deploying this backend; existing records
need no backfill. Category failure saves `Failed`, structured error details, and completed
predictions. Success saves `Complete`. Both terminal states set `finished_at` in
UTC. Embedding completion independently updates `embedding_status` without
changing the category status or finish time. Cancellation before an embedding
result sets its status to `Failed`; already-running embedding work may still
finish successfully. Vectors are returned by the API and separately persisted in
LanceDB as described below. `/embed-event` alone does not create an Analysis record.

Every successful create/update logs at INFO with operation, UUID, record ID and
both statuses. Failed writes log a warning with HTTP status/error type; request
text, predictions, token and response bodies are excluded. Persistence failures after authentication never
abort inference or change the existing analysis API/stream responses. This is
best-effort persistence: an unsuccessful or timed-out create is not retried, and
that run proceeds without further writes. Later updates send the accumulated
snapshot, so a subsequent successful update recovers missed intermediate writes.
Failed final writes have no background retry or durable queue. A stream disconnect
marks unfinished category analysis `Failed` (error code 499), but process crashes
can still leave `Processing` records requiring future recovery.
If a user token expires or is revoked during inference, subsequent writes can
fail; there is no privileged fallback or background reauthentication. Analysis
still returns its computed results and failed writes are logged.

## LanceDB vector storage

LanceDB runs embedded in Python on the same machine as the backend and PocketBase;
there is no additional database service. Both dependency profiles include LanceDB
and PyArrow. Use one backend worker. Startup opens and validates the vector table
before loading models; initialization failure prevents startup without overwriting
an incompatible table. Shutdown releases storage after embedding workers and their
completion callbacks finish, including cleanup when model startup fails.

Configure the optional path in `backend/.env`:

```dotenv
LANCEDB_STORAGE_PATH=./data/vectordb/
```

Absent or blank uses `./data/vectordb/`. Both the default and relative overrides
resolve against the repository root, regardless of the launch directory. Absolute
local paths are supported; remote URIs and network shares are rejected. Process
environment variables take precedence over `.env`. The directory is created
automatically. `/data/vectordb/` is ignored by Git; keep custom directories outside
version control too. Changing the path selects another database; it does not move
existing vectors.

The `analysis_embeddings` table has exactly three non-null fields: `vector`
(768 float32 values), `created_by` (verified PocketBase user ID), and `analysis_id`
(backend UUID v4). It stores only normalized `google/embeddinggemma-2` document
embeddings. A future model change needs an explicit migration or separate table,
even if dimensions remain 768. Source text, titles and predictions stay in PocketBase.

Both analysis endpoints save validated embeddings when generation completes,
including successful embeddings from failed/disconnected category analyses.
Queued cancellation or generation failure creates no vector row. If the initial
PocketBase create failed, vector storage is skipped to avoid a knowingly missing
text reference. `/embed-event` remains generation-only. Writes are serialized and
idempotent by `analysis_id`; an existing row's owner cannot be changed.

Runtime write failures log warnings and preserve API/stream responses.
`embedding_status` continues to describe generation, not storage success. INFO logs
record initialization and successful writes; skipped writes and failures record
the analysis ID and reason/error type without vectors, source text, or tokens.
There is no automatic retry queue or historical backfill. Writes to PocketBase and
LanceDB are not atomic, so failures require later reconciliation or reanalysis.

The internal `search_owned(vector, created_by, limit)` interface validates the user
ID and prefilters that owner before exact cosine-distance search. It returns only
analysis IDs and distances. No approximate index is created. Public search and
retrieval endpoints and frontend integration are deferred; future text retrieval
must independently verify PocketBase record ownership. Do not expose database
files directly to users.

Back up the entire vector database directory and PocketBase's `pb_data/` together
while the backend and PocketBase are stopped, or use coordinated filesystem
snapshots. A vector database backup alone cannot restore source text. Restart with
the same configured path to reopen existing vectors.

## Private PocketBase boundary

Browsers communicate only with Python through `/api`; do not expose PocketBase
or forward any public route to its port. The Go service rejects non-loopback
listener addresses and direct HTTPS mode, including explicit command-line flags.
Run `go run . serve --http=127.0.0.1:8090`; HTTPS belongs to the reverse proxy in
front of Python/frontend. PocketBase's dashboard remains available locally.

The Analysis create rule requires a users identity and matching `created_by`.
Updates require the same creator and cannot change `created_by`, `analysis_id`,
or `original_text`. Listing, viewing and deletion remain locked; no frontend
database query/search routes exist yet. Public users registration is allowed by
its create rule, while the other user record operations remain locked. Python
exposes only email/password registration and model-generated analysis operations.
PocketBase also rejects registration of verified/visibility/custom-ID values and
strips hidden token-key input before rule evaluation.

This design relies on local process/network isolation: a process able to call
PocketBase directly with a user's token has that user's result-write permissions.
The Origin allowlist protects Python's browser endpoints; it does not make an
exposed PocketBase safe. Do not add a generic database proxy to Python.

## Login and registration

The browser uses FastAPI through the existing same-origin `/api` proxy. PocketBase
remains on localhost; no superuser token is used by the backend.
Apply migrations and restart PocketBase so the existing/default `users` auth
collection has required unique email, email/password login, an eight-character
password minimum, and seven-day tokens. Existing accounts and token secrets are
preserved. The users create rule permits anonymous registration; FastAPI mediates
it without any Authorization header. Other user record APIs remain locked.
New accounts sign in immediately without email verification.
Authentication alert emails are disabled for this initial flow; no SMTP is needed.

| Endpoint | Input | Success |
| --- | --- | --- |
| `POST /auth/login` | `{ "email": "...", "password": "..." }` | `{ "id": "...", "email": "..." }` and session cookie |
| `POST /auth/register` | Email/password plus `password_confirm` | HTTP 201, user and session cookie |
| `GET /auth/session` | Session cookie | Verified user and refreshed cookie |
| `POST /auth/logout` | No credentials required | HTTP 204 and cleared cookie; works offline |

The HttpOnly `event_analytics_session` cookie has Path `/`, SameSite=Lax and a
seven-day Max-Age. The session endpoint verifies/refreshes it with PocketBase's
`users/auth-refresh`; every inference request independently verifies the user
before creating records or submitting model work. The shared HTTP client uses
per-request user authorization without any default Authorization header.
Responses contain only user ID/email; auth responses, including failures, use
`Cache-Control: no-store`. Passwords/tokens are not logged or echoed in validation errors.

Set `AUTH_COOKIE_SECURE=true` in production HTTPS. The default `false` supports
local HTTP. Set `AUTH_ALLOWED_ORIGINS` to a comma-separated list of exact frontend
origins (scheme, host and port; no paths or wildcards). Defaults allow localhost
and 127.0.0.1 on ports 5173, 4173 and 8000. Every state-changing auth/inference POST
must have an allowed `Origin` header, including CLI clients. Keep Cookie,
Set-Cookie and Origin headers intact through the production reverse proxy.
No PocketBase credentials belong in Vite environment variables.

Missing/invalid sessions return 401. PocketBase failure during verification returns
503 without running inference; backend startup and `/health` still work. After
verification, record writes remain best effort. Duplicate email returns 409;
invalid registration returns 422. If the account was created but automatic login
failed, the response has `detail.account_created: true` and the frontend switches
to login without retrying registration. Logout clears only this browser's cookie;
it does not revoke tokens on other devices. There is no password reset, OAuth,
email verification, retrieval endpoint or per-user search feature yet.

## API

Interactive documentation: `http://127.0.0.1:8000/docs`.

`GET /health` returns HTTP 200 once startup completes, reporting the loaded
model ID and selected device without running inference. Each call probes PocketBase
again, so outage/recovery is visible without restarting the backend.
`pocketbase_available` means the health endpoint responded successfully.
The former `pocketbase_persistence_ready` field is removed: a public health check
cannot establish a particular user's write permission or validate private schemas.
Each authenticated record write checks its own access; missing/misconfigured
collections or failed writes are logged separately.
PocketBase failure leaves top-level `status: "ok"` because model health is separate;
authenticated requests still need PocketBase to verify their session. Example:

```json
{"status":"ok","model_id":"google/gemma-4-26B-A4B-it","device":"cpu","model_loaded":true,"serving_engine":"transformers","embedding_model_id":"google/embeddinggemma-2","embedding_model_loaded":true,"pocketbase_available":true}
```

```powershell
# Supply an existing user account; do not use the PocketBase superuser token.
$loginBody = @{ email = 'user@example.com'; password = '<user-password>' } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/auth/login' -Headers @{ Origin = 'http://localhost:8000' } -ContentType 'application/json' -Body $loginBody -SessionVariable analyticsSession
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/analyze-event' -Headers @{ Origin = 'http://localhost:8000' } -WebSession $analyticsSession -ContentType 'application/json' -Body '{"text":"Event text to analyze"}'
```

HTTP 200 response:

```json
{
  "status": "ok",
  "title": "Översvämningar påverkar vattenförsörjningen",
  "results": {
    "risks": [{"ID": "översvämningar", "name": "Översvämningar"}],
    "reach": [{"ID": "2._lokalt", "name": "2. Lokalt"}],
    "service": [{"ID": "vatten_va", "name": "Vatten/VA"}],
    "properties": [{"ID": "varaktighet", "name": "Varaktighet"}],
    "protection": [{"ID": "samhällets_funktionalitet", "name": "Samhällets funktionalitet"}]
  }
}
```

Text is trimmed; missing, non-string, empty, and whitespace-only values return
HTTP 422. Each workflow can return zero, one, or multiple matches; no matches
returns an empty list under that workflow's key. IDs and display names are resolved
from `schemas/risks.json`, `schemas/reach.json`, `schemas/service.json`,
`schemas/properties.json`, and `schemas/protection.json`, respectively.
Persistence is not implemented. Successful analysis responses additionally
contain `embedding` and `embedding_error`, described below; the category-only
example above omits those fields for readability.

## Document embeddings

`POST /embed-event` accepts the same trimmed, nonempty `{ "text": "..." }`
payload (invalid input returns 422) and returns `{ "status": "ok", "embedding": {...} }`.
The embedding object contains:

| Field | Value |
| --- | --- |
| `vector` | 768 finite floating-point numbers, L2-normalized |
| `model_id` | `google/embeddinggemma-2` |
| `task` | `document` |
| `dimensions` | `768` |
| `normalized` | `true` |
| `truncated` | Whether the input was shortened |
| `input_tokens` | Full token count including prefix and special tokens |
| `embedded_tokens` | Token count actually embedded, at most 8192 |

The text is prefixed with `title: none | text: ` independently of the generated
analysis title. Overlong documents are right-truncated, preserving special tokens;
only the beginning is represented. The model's projected token representations
are mean-pooled using the attention mask and normalized in float32. Nonfinite,
zero-norm, or incorrectly sized output and inference failures return HTTP 502.
The endpoint has no query, similarity, or clustering task selection yet.

Both analysis endpoints start the same embedding helper before title generation.
A single-worker embedding executor and separate lock serialize embedding calls,
while allowing embedding and LLM inference to overlap on the same device. This
can increase device load; overlapping requests do not guarantee faster GPU work.
Category progress proceeds normally, but successful completion waits for the
embedding. JSON analysis responses and streaming `analysis_completed` payloads
contain `embedding` plus `embedding_error: null` on success. If embedding fails,
analysis results remain successful with `embedding: null` and
`embedding_error: { "code": 502, "message": "Embedding inference failed" }`.
Analysis failures retain their existing error behavior. Queued embedding work is
cancelled when analysis fails or a stream closes; running inference can finish,
with its result discarded. Shutdown cancels queued work and waits for running
embedding inference before releasing runtimes.

The frontend accepts these completion fields but does not store or display them.
Vector persistence, search-query embeddings, and related-event retrieval are
future work. Document similarity quality requires separate evaluation.

## Workflows

The fixed `generate_title(text, runtime)` step runs first, outside the category
registry. Its separate Swedish prompt asks for a factual title containing 1–10
words. It uses the same model and inference lock, deterministic generation and
input limit, with at most 64 output tokens. Surrounding whitespace and quotes
are removed. Pydantic validates 1–10 whitespace-separated words without truncating
the title. Overlong, blank, multiline or structured output and inference failures use `Händelseanalys` and
log a warning without retrying. Input-limit and unsupported-runtime errors still
stop analysis with 413/503. Title generation start and duration are logged at INFO.

`workflows.py` contains independent workflow functions and a `WORKFLOWS` registry.
The functions are `categorize_risks`, `categorize_reach`, `categorize_service`,
`categorize_properties`, and `categorize_protection`,
each accepting `(text, runtime, categories)` and using its own Swedish system prompt.
Risks evaluates supported risk areas; reach evaluates geographical/organizational
scope without assuming the user's organization or automatically selecting broader/narrower
levels. Service evaluates affected functions and those explicitly involved in handling
the event, avoiding matches based only on a mentioned location. Properties selects
event characteristics that the text provides enough information to assess;
assessment examples in the schema guide selection and are not separate output
values. Protection selects affected or explicitly threatened protection values.
Both return category IDs and display names, with verified evidence in streaming
responses, using the same format as the existing workflows. The shared helper
handles generation and validated ID-to-name mapping. To add a
workflow, define a function with that signature and register `Workflow(function,
"category-file.json", "Display label")` under its result key. A function that does not need categories
can use `Workflow(function)` and receives an empty tuple. Remove an entry to disable
a workflow. `run_workflows` generates the title first, then runs registered functions
in order, then extracts dates and returns `{title, results, dates, dates_error}` with category results under their registry
keys (`risks`, `reach`, `service`, `properties`, `protection`) in that order.
The stream labels for the new workflows are `Egenskaper` and `Skyddsvärden`.
All seven steps reuse the same model instance;
there is one model call per step, not a separate model per task.

### Date extraction

`extract_dates(text, runtime)` runs after all categories and before completion,
outside the category registry. The status catalog appends `dates` (label `Datum`),
with `workflow_started` before extraction and `workflow_completed` afterward.
The completion event carries an empty `results` list plus `dates` and `dates_error`;
these remain outside category predictions. Date errors complete this step with
an error payload instead of sending the terminal `workflow_failed` event.
It uses the shared inference engine and
lock, an independent Swedish system prompt, and up to 1024 output tokens.
`ANALYSIS_TIMEZONE="Europe/Stockholm"` configures the IANA timezone; invalid values
prevent startup before model loading. The `tzdata` dependency supplies timezone
data on Windows. Python `datetime` captures the workflow start once and injects
`Datumet är YYYY:MM:DD HH:MM`, reused for validation retries.

Both the JSON response and streaming `analysis_completed` payload include:

```json
{
  "dates": {
    "published_at": null,
    "event_start": null,
    "event_end": null,
    "end_status": "unknown",
    "duration_hint": null,
    "evidence": {"published_at": [], "event_start": [], "event_end": []}
  },
  "dates_error": null
}
```

The prompt selects original creation/publication, ignoring updates, and one primary
event interval. Relative event expressions use original publication, never the
analysis clock; missing anchors and ambiguous endpoints remain null. Forecasts
attributed to people in the source are allowed. Values use `YYYY-MM-DD` or
`YYYY-MM-DDTHH:MM`, with a timezone suffix only if supplied by the source. Missing
times are never filled with midnight. `end_status` is `dated` when an end exists,
`until_further_notice` for a supported ongoing event with no known end, otherwise
`unknown`; the start can remain null independently.

The optional `duration_hint` is a separate rough model estimate matching
`~[positive integer][H|D|W|M|Y]` (hours/days/weeks/months/years). It never creates an
end date. Exact source evidence is grouped by date field; `event_end` quotes also
support ongoing status. The backend deduplicates and filters quotes against the
original text, clears dates without verified quotes, validates calendar formats,
clears reversed interval ends, and normalizes end status. Exact substring checks
do not prove that a quote semantically supports a date: publication selection,
relative-date interpretation and prognosis quality still require model evaluation.

Malformed output retries using `RETRY_LIMIT`; invalid individual dates/hints become
null without dropping other valid values. Inference failure or exhausted retries
returns `dates: null` and `dates_error: {"code": ..., "message": ...}` while analysis
and category results remain successful. No information is a successful extraction
with the empty object shown above. The frontend consumes valid dates from stream
completion and renders a selectable timeline below the summary's category cards.
It hides the widget for empty/invalid/failed extraction; the analysis reference is
the browser-recorded completion reception time, separate from source dates.

Category definitions are validated and loaded once during startup before model
loading. Missing files, invalid JSON, blank/non-string fields, or duplicate IDs
prevent startup. Restart after editing categories. The model sees only category IDs
and descriptions, not a separate display-name field, and is instructed in Swedish
to use supported facts rather than speculative consequences or instructions embedded
in the event. These instructions guide the model; classification quality still needs review.

The route runs in FastAPI's thread pool. A shared runtime lock serializes prompt
preparation, generation and decoding for all requests/workflows using `generate_text`.
Generation uses inference mode, disables thinking and sampling, and allows 4096
new tokens. The complete input is capped at 8192 tokens; exceeding it returns HTTP
413 without truncation. Malformed category output or unknown IDs return HTTP 502
after exhausting `RETRY_LIMIT`; inference failures return HTTP 502 immediately.
Unsupported runtimes return HTTP 503. In Transformers mode, only Gemma's loaded
generation runtime currently supports the workflow; base models can still start
and serve health. vLLM mode uses the selected model's text generation engine.

The frontend uses the streaming endpoint below. The existing JSON endpoint remains
available for scripts and other clients, with the additional top-level `title` field.

## Live analysis stream

Both analysis endpoints generate a fresh UUID v4 reference for each validated
request, available in the `X-Analysis-ID` response header. The JSON endpoint's
response body includes the title separately from category results. References are
logged and stored in PocketBase when persistence is configured; the backend has
no analysis retrieval endpoint yet. Stream metadata includes the same UUID as `analysis_id`.

`POST /analyze-event/stream` accepts the same `{ "text": "..." }` payload and
returns `text/event-stream`. Input validation occurs before streaming (HTTP 422).
Each frame is `event: <name>` followed by `data: <JSON>` and a blank line:

| Event | JSON data |
| --- | --- |
| `analysis_started` | `{ "analysis_id": "<uuid>", "workflows": [{ "id": "risks", "label": "Riskområden" }, ...] }` |
| `title_completed` | `{ "title": "Översvämningar påverkar vattenförsörjningen" }` |
| `workflow_started` | `{ "id": "risks" }` |
| `workflow_completed` | `{ "id": "risks", "results": [{ "ID": "...", "name": "...", "evidence": ["exact supporting quote"] }] }` |
| `workflow_failed` | `{ "id": "risks", "message": "...", "code": 502 }` |
| `analysis_completed` | `{ "embedding": { ... }, "embedding_error": null, "dates": { ... }, "dates_error": null }` (each optional result can independently be null with a structured error) |

The catalog follows category registry order and appends `dates` (`Datum`) last;
category labels default to the registry key when absent.
After `analysis_started`, title generation runs before any category workflow and
emits `title_completed`. It is excluded from the catalog and category progress.
The frontend reserves an empty heading area initially and renders the title
once received, retaining it if a later workflow fails. UUIDs remain internal
metadata and are no longer displayed as headings on either screen.
Completed results may contain an empty list. Streaming workflows must return lists
of matched IDs and display names. Both endpoints share `iter_workflow_events`;
LLM inference remains serialized by the existing runtime lock; document embedding
uses its own runtime and lock. Each categorization
prompt requests objects with category `ID` and an `evidence` array in the same
model call. The backend validates IDs, resolves names, and deduplicates quotes.
Only nonblank exact substrings of the trimmed input are retained: no fuzzy
matching or normalization. Missing, malformed, or unmatched evidence is omitted
and rejected evidence is logged without discarding the valid category. Empty
evidence arrays indicate unavailable verified text support. The original JSON
endpoint excludes evidence to preserve its response contract. These checks verify
quote presence, not the model's reasoning or classification accuracy.
Synchronous stream
iteration runs in Starlette's worker pool, leaving the event loop free.

The stream stops at the first workflow failure; completed results remain usable.
After response headers are sent, errors are terminal `workflow_failed` events
inside HTTP 200, not changed HTTP statuses. The ID can be null for an error before
a workflow starts. Unexpected exceptions send a safe message; details are logged
server-side. Clients must treat EOF without a terminal event as interruption.
There are no stored jobs or automatic job resume/retry; an in-flight model call cannot
be interrupted immediately when a client disconnects.

Reverse proxies must disable response buffering and caching for this endpoint
and allow long read timeouts (CPU inference can take several minutes). The stream
sets `X-Accel-Buffering: no` and `Cache-Control: no-cache, no-transform`; configure
the hosting proxy as well. The frontend's `/api` prefix must be stripped.

## Verification

```powershell
uv run --extra CPU python -m py_compile app.py serving.py auth.py workflows.py embeddings.py persistence.py vector_storage.py
uv run --extra CPU python -m pytest
uv lock --check
```

All backend test scripts and shared fixtures live in `tests/`. Pytest discovers
the mocked suite there; the real-inference smoke script is excluded by its filename.
Tests mock both model loading and inference and do not download model weights or require a GPU.
Serving tests cover both engine paths with mocked vLLM, configuration rejection,
serialized generation, token limits, lifecycle cleanup, and JSON/SSE contracts.
Auth and persistence tests use a mocked HTTP transport and never contact a real PocketBase
database. They cover startup/health/outage recovery, authentication, incremental
writes, partial failure, independent embedding status, cancellation, creator attribution,
cookie handling, origin checks, registration validation and client cleanup.
Embedding tests cover text-only loading, device/dtype selection, truncation,
pooling/normalization, logging, concurrent analysis, failures, and cleanup.
They include both `data/events/` articles to verify endpoint plumbing with mocked outputs;
those checks do not establish article classification accuracy.

For real inference, restart the backend with Gemma and run this from `backend/`:

```powershell
uv run --extra CPU python tests/smoke_articles.py --email user@example.com
```

This sends both articles to the running backend, reusing its resident model rather
than loading a second copy. It prompts for the user's password (or reads
`ANALYTICS_PASSWORD` from the process environment), logs in, and retains the session
cookie. `ANALYTICS_EMAIL` can replace `--email`; `--origin` must match the backend
allowlist when using a deployed service. It creates attributed Analysis records.
It prints matched IDs/names and checks the response
contract for all five workflows and model health metadata. Review the flooding article for
`Översvämningar` and `Vattenbrist och torka`; check that the suspicious-object article
accounts for the later finding that the object was not dangerous, without inventing
an explosion or terrorism. Also review the reach levels and whether service matches
are supported by actual effects or response activities. Review whether property
matches have enough information for assessment and protection matches describe
affected or explicitly threatened values. Exact matches are not asserted because quality needs
manual review. A request can take up to five minutes on CPU.
