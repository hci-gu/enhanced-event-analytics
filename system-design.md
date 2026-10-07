
# Overview
![image](assets/system-overview.png)

## Frontend
TypeScript React homepage with an event textbox, analysis submission, and a
search input (search results are not implemented). The browser calls
`POST /api/analyze-event`; the development/preview proxy forwards this to the
backend's `/analyze-event` using `API_URL`. Production requires the same proxy
rewrite. Homepage colors are configurable in `frontend/src/colors.css`.

## Backend
FastAPI exposes `POST /analyze-event`, accepting JSON with a non-empty `text`
string. It trims the text and currently returns
`{"status":"not_implemented","results":{}}`. Invalid text returns HTTP 422.

The lifespan loads a configurable Transformers tokenizer and base model once
per server process into `app.state.runtime`. `MODEL_ID` selects a Hugging Face
model or local directory; `MODEL_DEVICE=auto|cpu|cuda` selects its device.
Each server worker loads its own model. CPU and CUDA 12.8 dependency profiles
are managed with uv extras; see [backend setup](backend/README.md).

The synchronous `run_workflows` extension point will process the text using
several workflows and combine their results. Those workflows and PocketBase
persistence are not implemented yet; the diagram below describes the intended
architecture.

![backend](assets/system-backend.png)

## Pocketbase
Data layer using Pocketbase, serving using Go. 

Collections
- Events (event_id, group_id: nullable, text)
- Analysis ()
