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
`AutoModel` and `AutoTokenizer`, then launch:

```powershell
$env:MODEL_ID = 'bert-base-multilingual-cased'
$env:MODEL_DEVICE = 'auto'
uv run --extra CPU uvicorn app:app
# Or use the CUDA profile:
uv run --extra CUDA uvicorn app:app
```

`MODEL_ID` is required. `MODEL_DEVICE` accepts `auto` (default), `cpu`, or `cuda`.
Auto selects CUDA when available and otherwise CPU; explicit CUDA fails startup
if unavailable. Configuration comes from the process environment, not `.env`.
The first startup downloads model/tokenizer files into the Hugging Face cache
unless a local directory or cached model is used. Loading errors prevent startup.

FastAPI's lifespan loads the tokenizer and model once per server process, moves
the model to the selected device, and enables evaluation mode. They stay in
`app.state.runtime` until shutdown. Each Uvicorn worker loads its own copy, so
start with one worker to avoid multiplying RAM/VRAM usage.

## API

Interactive documentation: `http://127.0.0.1:8000/docs`.

```powershell
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/analyze-event' -ContentType 'application/json' -Body '{"text":"Event text to analyze"}'
```

HTTP 200 response:

```json
{"status":"not_implemented","results":{}}
```

Text is trimmed; missing, non-string, empty, and whitespace-only values return
HTTP 422. Analysis and persistence are not implemented yet. `run_workflows(text,
runtime)` is the synchronous extension point for future workflows using the
shared model; the route runs in FastAPI's thread pool. Future inference should
use `torch.inference_mode()` and account for concurrent access to the shared model.

## Verification

```powershell
uv run --extra CPU python -m py_compile app.py test_app.py
uv run --extra CPU python -m pytest
uv lock --check
```

Tests mock model loading and do not download model weights or require a GPU.
