"""Event-analysis API with a model shared by requests in each server process."""

import logging
import os
from _thread import LockType
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Any, Literal

import torch
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
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

from workflows import WorkflowError, load_workflow_categories, run_workflows


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
        raise RuntimeError(f"Failed to load MODEL_ID={model_id!r} on {device}: {exc}") from exc
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
        "Categorize event text by risks, reach and services using separate prompts and the shared model. "
        "Each workflow returns zero, one, or multiple matches with IDs and display names."
    ),
    responses={
        413: {"description": "Event and workflow instructions exceed the input token limit"},
        502: {"description": "Model inference failed or returned invalid output"},
        503: {"description": "Loaded model does not support the generation workflow"},
    },
)
def analyze_event(payload: AnalyzeEventRequest, request: Request) -> AnalyzeEventResponse:
    logger.info("POST /analyze-event triggered (text_length=%d)", len(payload.text))
    try:
        results = run_workflows(
            payload.text, request.app.state.runtime, request.app.state.workflow_categories
        )
    except WorkflowError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return AnalyzeEventResponse(results=results)
