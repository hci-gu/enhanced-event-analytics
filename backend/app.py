"""Event-analysis API with a model shared by requests in each server process."""

import json
import logging
import os
from _thread import LockType
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from time import perf_counter
from typing import Any, Literal
from uuid import uuid4

import torch
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from transformers import (
    AutoConfig,
    AutoModel,
    AutoProcessor,
    AutoTokenizer,
    Gemma4ForConditionalGeneration,
    PreTrainedModel,
    PreTrainedTokenizerBase,
    ProcessorMixin,
)

from workflows import WorkflowError, iter_workflow_events, load_workflow_categories, run_workflows


logger = logging.getLogger("uvicorn.error.app")


@dataclass
class ModelRuntime:
    tokenizer: PreTrainedTokenizerBase
    model: PreTrainedModel
    device: str
    model_id: str
    processor: ProcessorMixin | None = None
    inference_lock: LockType = field(default_factory=Lock, repr=False)


def load_runtime() -> ModelRuntime:
    model_id = os.environ.get("MODEL_ID", "").strip()
    if not model_id:
        raise RuntimeError("MODEL_ID must identify a Hugging Face model or local directory")

    device = os.environ.get("MODEL_DEVICE", "auto")
    if device not in {"auto", "cpu", "cuda"}:
        raise RuntimeError("MODEL_DEVICE must be auto, cpu, or cuda")
    if device in {"auto", "cuda"}:
        cuda_available = torch.cuda.is_available()
        if device == "cuda" and not cuda_available:
            raise RuntimeError("MODEL_DEVICE=cuda requires an available CUDA device")
        device = "cuda" if cuda_available else "cpu"

    started = perf_counter()
    logger.info("Model loading started (model_id=%s, device=%s)", model_id, device)
    try:
        config = AutoConfig.from_pretrained(model_id)
        processor = None
        if config.model_type == "gemma4":
            processor = AutoProcessor.from_pretrained(model_id)
            tokenizer = processor.tokenizer
            model = Gemma4ForConditionalGeneration.from_pretrained(
                model_id, config=config, dtype="auto"
            )
        else:
            tokenizer = AutoTokenizer.from_pretrained(model_id)
            model = AutoModel.from_pretrained(model_id, config=config)
        model.to(device)
        model.eval()
    except Exception as exc:
        logger.exception(
            "Model loading failed after %.2fs (model_id=%s, device=%s)",
            perf_counter() - started, model_id, device,
        )
        raise RuntimeError(f"Failed to load MODEL_ID={model_id!r} on {device}: {exc}") from exc
    logger.info(
        "Model loading finished in %.2fs (model_id=%s, device=%s)",
        perf_counter() - started, model_id, device,
    )
    return ModelRuntime(
        tokenizer=tokenizer, model=model, device=device, model_id=model_id, processor=processor
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_dotenv(dotenv_path=Path(__file__).with_name(".env"), override=False)
    categories = load_workflow_categories()
    app.state.runtime = load_runtime()
    app.state.workflow_categories = categories
    try:
        yield
    finally:
        del app.state.runtime
        del app.state.workflow_categories


app = FastAPI(title="Enhanced Event Analytics", lifespan=lifespan)


@app.get("/health", summary="Check service health")
async def health(request: Request) -> dict[str, str | bool]:
    runtime = request.app.state.runtime
    return {
        "status": "ok",
        "model_id": runtime.model_id,
        "device": runtime.device,
        "model_loaded": True,
    }


class AnalyzeEventRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    text: str = Field(strict=True, min_length=1, description="Event text to analyze")


class AnalyzeEventResponse(BaseModel):
    status: Literal["ok"] = "ok"
    title: str = Field(description="Generated Swedish event title of at most eight words")
    results: dict[str, Any] = Field(
        description="Results keyed by risks, reach and service; each contains matched IDs and display names",
        examples=[{
            "risks": [{"ID": "översvämningar", "name": "Översvämningar"}],
            "reach": [{"ID": "2._lokalt", "name": "2. Lokalt"}],
            "service": [{"ID": "vatten_va", "name": "Vatten/VA"}],
        }],
    )


@app.post(
    "/analyze-event",
    response_model=AnalyzeEventResponse,
    description=(
        "Generate a Swedish title, then categorize event text by risks, reach and services using the shared model. "
        "Each workflow returns zero, one, or multiple matches with IDs and display names."
    ),
    responses={
        413: {"description": "Event and workflow instructions exceed the input token limit"},
        502: {"description": "Model inference failed or returned invalid output"},
        503: {"description": "Loaded model does not support the generation workflow"},
    },
)
def analyze_event(payload: AnalyzeEventRequest, request: Request, response: Response) -> AnalyzeEventResponse:
    analysis_id = str(uuid4())
    response.headers["X-Analysis-ID"] = analysis_id
    logger.info("POST /analyze-event triggered (analysis_id=%s, text_length=%d)", analysis_id, len(payload.text))
    try:
        results = run_workflows(
            payload.text, request.app.state.runtime, request.app.state.workflow_categories
        )
    except WorkflowError as exc:
        raise HTTPException(
            status_code=exc.status_code, detail=str(exc), headers={"X-Analysis-ID": analysis_id}
        ) from exc
    return AnalyzeEventResponse(**results)


def encode_event(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.post(
    "/analyze-event/stream",
    response_class=StreamingResponse,
    summary="Stream sequential workflow progress and results",
    responses={200: {"content": {"text/event-stream": {"schema": {"type": "string"}}}}},
)
def analyze_event_stream(payload: AnalyzeEventRequest, request: Request) -> StreamingResponse:
    analysis_id = str(uuid4())
    logger.info("POST /analyze-event/stream triggered (analysis_id=%s, text_length=%d)", analysis_id, len(payload.text))
    runtime = request.app.state.runtime
    categories = request.app.state.workflow_categories

    def stream():
        current_id = None
        try:
            for event, data in iter_workflow_events(payload.text, runtime, categories):
                if event == "analysis_started":
                    data = {**data, "analysis_id": analysis_id}
                if event == "workflow_started":
                    current_id = data["id"]
                yield encode_event(event, data)
        except Exception as exc:
            code = exc.status_code if isinstance(exc, WorkflowError) else 500
            message = {
                413: "Händelsetexten och instruktionerna överskrider modellens textgräns.",
                502: "Modellanalysen misslyckades eller gav ett ogiltigt resultat.",
                503: "Den laddade modellen stöder inte analysen.",
            }.get(code, "Ett oväntat serverfel avbröt analysen.")
            logger.exception("Streaming analysis failed (analysis_id=%s, workflow=%s)", analysis_id, current_id)
            yield encode_event("workflow_failed", {
                "id": current_id, "message": message, "code": code,
            })

    # Starlette advances synchronous iterators in its worker pool, not the event loop.
    return StreamingResponse(stream(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache, no-transform",
        "X-Accel-Buffering": "no",
        "X-Analysis-ID": analysis_id,
    })
