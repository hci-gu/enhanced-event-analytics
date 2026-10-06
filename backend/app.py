"""Event-analysis API with a model shared by requests in each server process."""

import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Literal

import torch
from fastapi import FastAPI, Request
from pydantic import BaseModel, ConfigDict, Field
from transformers import AutoModel, AutoTokenizer, PreTrainedModel, PreTrainedTokenizerBase


@dataclass
class ModelRuntime:
    tokenizer: PreTrainedTokenizerBase
    model: PreTrainedModel
    device: str


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
        tokenizer = AutoTokenizer.from_pretrained(model_id)
        model = AutoModel.from_pretrained(model_id)
        model.to(device)
        model.eval()
    except Exception as exc:
        raise RuntimeError(f"Failed to load MODEL_ID={model_id!r} on {device}") from exc
    return ModelRuntime(tokenizer=tokenizer, model=model, device=device)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.runtime = load_runtime()
    try:
        yield
    finally:
        del app.state.runtime


app = FastAPI(title="Enhanced Event Analytics", lifespan=lifespan)


class AnalyzeEventRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    text: str = Field(strict=True, min_length=1, description="Event text to analyze")


class AnalyzeEventResponse(BaseModel):
    status: Literal["not_implemented"] = "not_implemented"
    results: dict[str, Any] = Field(default_factory=dict)


def run_workflows(text: str, runtime: ModelRuntime) -> dict[str, Any]:
    """Future workflows receive validated text and the already-loaded model.

    No analysis is performed yet. Add inference here using torch.inference_mode()
    and the shared tokenizer/model, with inputs placed on runtime.device.
    """
    return {}


@app.post(
    "/analyze-event",
    response_model=AnalyzeEventResponse,
    description=(
        "Validate event text and pass it to the shared-model workflow runner. "
        "Workflows are not implemented yet; returns not_implemented and empty results."
    ),
)
def analyze_event(payload: AnalyzeEventRequest, request: Request) -> AnalyzeEventResponse:
    return AnalyzeEventResponse(results=run_workflows(payload.text, request.app.state.runtime))
