# Event analysis backend

Run these PowerShell commands from `backend/`. Python 3.10+ and uv are required.
Choose exactly one PyTorch profile (extra names are case insensitive):

```powershell
uv sync --extra CPU
# Or, on an NVIDIA CUDA machine:
uv sync --extra CUDA
```

The CPU profile uses the official CPU-only PyTorch index. The CUDA profile uses
the official CUDA 12.8 index and targets Windows/Linux NVIDIA machines. It needs
a CUDA 12.8-compatible NVIDIA driver; the wheels supply the CUDA runtime, so a
separate CUDA toolkit is not needed. Both profiles cannot be enabled together.
Plain `uv sync` does not install PyTorch; select a profile when running the API.

Configure a Hugging Face model ID or local model directory compatible with
`AutoModel` and `AutoTokenizer`, or a Gemma 4 checkpoint, then launch:

```powershell
$env:MODEL_ID = 'google/gemma-4-E2B-it'
$env:MODEL_DEVICE = 'auto'
uv run --extra CPU uvicorn app:app
# Or use the CUDA profile:
uv run --extra CUDA uvicorn app:app
```

`MODEL_ID` is required. `MODEL_DEVICE` accepts `auto` (default), `cpu`, or `cuda`.
Auto selects CUDA when available and otherwise CPU; explicit CUDA fails startup
if unavailable. Startup loads `backend/.env` using `python-dotenv`. You can put
`MODEL_ID` and `MODEL_DEVICE` there instead of setting them in PowerShell.
Existing process environment variables take precedence over `.env` values.
Gemma 4 uses Transformers 5.7+ with `AutoProcessor` and
`Gemma4ForConditionalGeneration`; the processor is available as
`app.state.runtime.processor` for chat-template preparation. Its tokenizer is
also available through `app.state.runtime.tokenizer`. Checkpoints are loaded
in their saved precision (`dtype="auto"`) to avoid an unnecessary float32 copy.
After updating dependencies, run `uv sync --extra CPU` or `uv sync --extra CUDA`
before restarting the service.
The first startup downloads model/tokenizer files into the Hugging Face cache
unless a local directory or cached model is used. Loading errors prevent startup.

FastAPI's lifespan loads the tokenizer and model once per server process, moves
the model to the selected device, and enables evaluation mode. They stay in
`app.state.runtime` until shutdown. Each Uvicorn worker loads its own copy, so
start with one worker to avoid multiplying RAM/VRAM usage.

## API

Interactive documentation: `http://127.0.0.1:8000/docs`.

`GET /health` returns HTTP 200 once startup completes, reporting the loaded
model ID and selected device without running inference. Example:

```json
{"status":"ok","model_id":"google/gemma-4-E2B-it","device":"cpu","model_loaded":true}
```

```powershell
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/analyze-event' -ContentType 'application/json' -Body '{"text":"Event text to analyze"}'
```

HTTP 200 response:

```json
{
  "status": "ok",
  "results": {
    "risks": [{"ID": "översvämningar", "name": "Översvämningar"}],
    "reach": [{"ID": "2._lokalt", "name": "2. Lokalt"}],
    "service": [{"ID": "vatten_va", "name": "Vatten/VA"}]
  }
}
```

Text is trimmed; missing, non-string, empty, and whitespace-only values return
HTTP 422. Each workflow can return zero, one, or multiple matches; no matches
returns an empty list under that workflow's key. IDs and display names are resolved
from `schemas/risks.json`, `schemas/reach.json`, and `schemas/service.json`, respectively.
Persistence is not implemented.

## Workflows

`workflows.py` contains independent workflow functions and a `WORKFLOWS` registry.
The functions are `categorize_risks`, `categorize_reach`, and `categorize_service`,
each accepting `(text, runtime, categories)` and using its own Swedish system prompt.
Risks evaluates supported risk areas; reach evaluates geographical/organizational
scope without assuming the user's organization or automatically selecting broader/narrower
levels. Service evaluates affected functions and those explicitly involved in handling
the event, avoiding matches based only on a mentioned location. The shared helper
handles generation and validated ID-to-name mapping. To add a
workflow, define a function with that signature and register `Workflow(function,
"category-file.json")` under its result key. A function that does not need categories
can use `Workflow(function)` and receives an empty tuple. Remove an entry to disable
a workflow. `run_workflows` runs the registered functions in order and collects each
result under its registry key (`risks`, `reach`, `service`). All three reuse the same
model instance; there is one model call per workflow, not a separate model per task.

Category definitions are validated and loaded once during startup before model
loading. Missing files, invalid JSON, blank/non-string fields, or duplicate IDs
prevent startup. Restart after editing categories. The model sees only category IDs
and descriptions, not a separate display-name field, and is instructed in Swedish
to use supported facts rather than speculative consequences or instructions embedded
in the event. These instructions guide the model; classification quality still needs review.

The route runs in FastAPI's thread pool. A shared runtime lock serializes prompt
preparation, generation and decoding for all requests/workflows using `generate_text`.
Generation uses inference mode, disables thinking and sampling, and allows 1024
new tokens. The complete input is capped at 8192 tokens; exceeding it returns HTTP
413 without truncation. Malformed output, unknown IDs, or inference failures return
HTTP 502; unsupported runtimes return HTTP 503. Only Gemma's loaded generation
runtime currently supports the workflow; base models can still start and serve health.

The frontend currently expects `not_implemented` and will reject this new response.
Frontend result handling is deferred; test the backend through `/docs` or HTTP requests.

## Verification

```powershell
uv run --extra CPU python -m py_compile app.py workflows.py test_app.py test_workflows.py smoke_articles.py
uv run --extra CPU python -m pytest
uv lock --check
```

Tests mock model loading and do not download model weights or require a GPU.
They include both `data/` articles to verify endpoint plumbing with mocked outputs;
those checks do not establish article classification accuracy.

For real inference, restart the backend with Gemma and run this from `backend/`:

```powershell
uv run --extra CPU python smoke_articles.py
```

This sends both articles to the running backend, reusing its resident model rather
than loading a second copy. It prints matched IDs/names and checks the response
contract for all three workflows and unchanged health metadata. Review the flooding article for
`Översvämningar` and `Vattenbrist och torka`; check that the suspicious-object article
accounts for the later finding that the object was not dangerous, without inventing
an explosion or terrorism. Also review the reach levels and whether service matches
are supported by actual effects or response activities. Exact matches are not asserted because quality needs
manual review. A request can take up to five minutes on CPU.
