"""Event-analysis API with a model shared by requests in each server process."""

import json
import logging
import os
from asyncio import to_thread
from _thread import LockType
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from time import perf_counter
from typing import Annotated, Any, Literal
from uuid import uuid4

import torch
from anyio import CancelScope
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.responses import JSONResponse, StreamingResponse
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

from workflows import WorkflowError, iter_workflow_events, load_retry_limit, load_workflow_categories, run_workflows
from embeddings import embed_document, load_embedding_runtime
from persistence import AnalysisPersistence, create_pocketbase_client
from auth import UserSession, require_origin, require_user, router as auth_router


logger = logging.getLogger("uvicorn.error.app")


def configure_logging() -> None:
    level = os.environ.get("LOG_LEVEL", "INFO").strip().upper()
    if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise RuntimeError("LOG_LEVEL must be DEBUG, INFO, WARNING, ERROR, or CRITICAL")
    for name in (
        "uvicorn", "uvicorn.error", "uvicorn.access",
        "uvicorn.error.app", "uvicorn.error.workflows", "uvicorn.error.embeddings", "uvicorn.error.persistence",
    ):
        logging.getLogger(name).setLevel(level)


@dataclass
class ModelRuntime:
    tokenizer: PreTrainedTokenizerBase
    model: PreTrainedModel
    device: str
    model_id: str
    processor: ProcessorMixin | None = None
    inference_lock: LockType = field(default_factory=Lock, repr=False)
    retry_limit: int = 1


@contextmanager
def loading_stage(stage: str, *, device: str | None = None):
    if not logger.isEnabledFor(logging.DEBUG):
        yield
        return
    started = perf_counter()
    logger.debug("Loading stage=%s status=started", stage)
    try:
        yield
        if device == "cuda":
            torch.cuda.synchronize()
    except Exception:
        logger.debug(
            "Loading stage=%s status=failed duration_seconds=%.6f",
            stage, perf_counter() - started,
        )
        raise
    else:
        logger.debug(
            "Loading stage=%s status=completed duration_seconds=%.6f",
            stage, perf_counter() - started,
        )


def load_runtime() -> ModelRuntime:
    retry_limit = load_retry_limit()
    model_id = os.environ.get("MODEL_ID", "").strip()
    if not model_id:
        raise RuntimeError("MODEL_ID must identify a Hugging Face model or local directory")

    with loading_stage("device_selection"):
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
        with loading_stage("config"):
            config = AutoConfig.from_pretrained(model_id)
        placement = {"device_map": {"": "cuda:0"}} if device == "cuda" else {}
        processor = None
        if config.model_type == "gemma4":
            with loading_stage("processor"):
                processor = AutoProcessor.from_pretrained(model_id)
                tokenizer = processor.tokenizer
            with loading_stage("weights", device=device):
                model = Gemma4ForConditionalGeneration.from_pretrained(
                    model_id, config=config, dtype="auto", **placement
                )
        else:
            with loading_stage("tokenizer"):
                tokenizer = AutoTokenizer.from_pretrained(model_id)
            with loading_stage("weights", device=device):
                model = AutoModel.from_pretrained(model_id, config=config, **placement)
        if device == "cpu":
            with loading_stage("device_placement"):
                model.to(device)
        with loading_stage("eval"):
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
        tokenizer=tokenizer, model=model, device=device, model_id=model_id, processor=processor,
        retry_limit=retry_limit,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_dotenv(dotenv_path=Path(__file__).with_name(".env"), override=False)
    configure_logging()
    with create_pocketbase_client() as pocketbase:
        app.state.pocketbase = pocketbase
        try:
            database_health = await to_thread(pocketbase.check_health)
            logger.info("PocketBase connection checked (available=%s)", database_health["pocketbase_available"])
            if not database_health["pocketbase_available"]:
                logger.warning("PocketBase unavailable; backend startup continues. User sessions require PocketBase verification.")
            async with model_lifespan(app):
                yield
        finally:
            del app.state.pocketbase


@asynccontextmanager
async def model_lifespan(app: FastAPI):
    with loading_stage("categories"):
        categories = load_workflow_categories()
    app.state.runtime = load_runtime()
    try:
        app.state.embedding_runtime = load_embedding_runtime(app.state.runtime.device)
        app.state.workflow_categories = categories
        app.state.embedding_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="embedding")
        try:
            yield
        finally:
            app.state.embedding_executor.shutdown(wait=True, cancel_futures=True)
            del app.state.embedding_executor
            del app.state.workflow_categories
            del app.state.embedding_runtime
    finally:
        del app.state.runtime


app = FastAPI(title="Enhanced Event Analytics", lifespan=lifespan)
app.include_router(auth_router)


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    response = await http_exception_handler(request, exc)
    if request.url.path.startswith("/auth/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    if request.url.path.startswith("/auth/"):
        # Pydantic's default errors echo input, which can include passwords.
        return JSONResponse(status_code=422, content={"detail": [
            {key: error[key] for key in ("type", "loc", "msg")} for error in exc.errors()
        ]}, headers={"Cache-Control": "no-store"})
    return await request_validation_exception_handler(request, exc)


@app.get("/health", summary="Check service health")
async def health(request: Request) -> dict[str, str | bool]:
    runtime = request.app.state.runtime
    return {
        "status": "ok",
        "model_id": runtime.model_id,
        "device": runtime.device,
        "model_loaded": True,
        "embedding_model_id": request.app.state.embedding_runtime.model_id,
        "embedding_model_loaded": True,
        **await to_thread(request.app.state.pocketbase.check_health),
    }


class AnalyzeEventRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    text: str = Field(strict=True, min_length=1, description="Event text to analyze")


class DocumentEmbedding(BaseModel):
    vector: list[Annotated[float, Field(allow_inf_nan=False)]] = Field(min_length=768, max_length=768)
    model_id: str
    task: Literal["document"] = "document"
    dimensions: Literal[768] = 768
    normalized: Literal[True] = True
    truncated: bool
    input_tokens: int
    embedded_tokens: int


class EmbeddingFailure(BaseModel):
    code: Literal[502] = 502
    message: str


class EmbedEventResponse(BaseModel):
    status: Literal["ok"] = "ok"
    embedding: DocumentEmbedding


def submit_embedding(text: str, request: Request) -> Future:
    return request.app.state.embedding_executor.submit(
        embed_document, text, request.app.state.embedding_runtime,
    )


def embedding_result(future: Future) -> dict[str, Any]:
    try:
        return {"embedding": DocumentEmbedding(**future.result()).model_dump(), "embedding_error": None}
    except Exception:
        logger.exception("Automatic document embedding failed")
        return {"embedding": None, "embedding_error": {"code": 502, "message": "Embedding inference failed"}}


def track_embedding(future: Future, persistence: AnalysisPersistence) -> None:
    def completed(done: Future):
        try:
            DocumentEmbedding(**done.result())
            success = True
        except Exception:
            success = False
        persistence.embedding_completed(success)
    future.add_done_callback(completed)


@app.post(
    "/embed-event", response_model=EmbedEventResponse,
    summary="Embed event text as a document",
    description="Return a normalized 768-dimensional document vector. Long inputs are right-truncated to 8192 tokens.",
    responses={502: {"description": "Embedding inference failed or returned an invalid vector"}},
)
def embed_event(payload: AnalyzeEventRequest, request: Request,
                user: UserSession = Depends(require_user), origin: None = Depends(require_origin)) -> EmbedEventResponse:
    future = submit_embedding(payload.text, request)
    try:
        return EmbedEventResponse(embedding=DocumentEmbedding(**future.result()))
    except Exception as exc:
        logger.exception("POST /embed-event failed")
        raise HTTPException(status_code=502, detail="Embedding inference failed") from exc
    finally:
        future.cancel()


class AnalyzeEventResponse(BaseModel):
    status: Literal["ok"] = "ok"
    embedding: DocumentEmbedding | None = None
    embedding_error: EmbeddingFailure | None = None
    title: str = Field(description="Generated Swedish event title containing 1–10 words")
    results: dict[str, Any] = Field(
        description="Results keyed by risks, reach, service, properties and protection; each contains matched IDs and display names",
        examples=[{
            "risks": [{"ID": "översvämningar", "name": "Översvämningar"}],
            "reach": [{"ID": "2._lokalt", "name": "2. Lokalt"}],
            "service": [{"ID": "vatten_va", "name": "Vatten/VA"}],
            "properties": [{"ID": "varaktighet", "name": "Varaktighet"}],
            "protection": [{"ID": "samhällets_funktionalitet", "name": "Samhällets funktionalitet"}],
        }],
    )


@app.post(
    "/analyze-event",
    response_model=AnalyzeEventResponse,
    description=(
        "Generate a Swedish title, then categorize event text by risks, reach, services, properties and protection values using the shared model. "
        "Each workflow returns zero, one, or multiple matches with IDs and display names. "
        "A document embedding runs in parallel and is returned at completion; embedding errors preserve analysis results."
    ),
    responses={
        413: {"description": "Event and workflow instructions exceed the input token limit"},
        502: {"description": "Model inference failed or returned invalid output"},
        503: {"description": "Loaded model does not support the generation workflow"},
    },
)
def analyze_event(payload: AnalyzeEventRequest, request: Request, response: Response,
                  user: UserSession = Depends(require_user), origin: None = Depends(require_origin)) -> AnalyzeEventResponse:
    analysis_id = str(uuid4())
    response.headers["X-Analysis-ID"] = analysis_id
    logger.info("POST /analyze-event triggered (analysis_id=%s, text_length=%d)", analysis_id, len(payload.text))
    persistence = AnalysisPersistence(request.app.state.pocketbase, analysis_id, payload.text, user.id, user.token)
    future = None
    try:
        future = submit_embedding(payload.text, request)
        track_embedding(future, persistence)
        results = run_workflows(
            payload.text, request.app.state.runtime, request.app.state.workflow_categories,
            on_event=persistence.on_event,
        )
        persistence.finish(results=results)
        return AnalyzeEventResponse(**results, **embedding_result(future))
    except WorkflowError as exc:
        persistence.finish(error={"workflow_id": persistence.current_workflow, "code": exc.status_code, "message": str(exc)})
        raise HTTPException(
            status_code=exc.status_code, detail=str(exc), headers={"X-Analysis-ID": analysis_id}
        ) from exc
    except Exception:
        persistence.finish(error={"workflow_id": persistence.current_workflow, "code": 500, "message": "Unexpected analysis failure"})
        raise
    finally:
        if future is not None:
            future.cancel()
        else:
            persistence.embedding_completed(False)


def encode_event(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


class EmbeddingStreamingResponse(StreamingResponse):
    """Cancel queued embedding work even if the stream disconnects before iteration."""

    def __init__(self, *args, embedding_future: Future, persistence: AnalysisPersistence, **kwargs):
        super().__init__(*args, **kwargs)
        self.embedding_future = embedding_future
        self.persistence = persistence

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            def close_stream():
                self.embedding_future.cancel()
                self.persistence.finish(error={
                    "workflow_id": self.persistence.current_workflow, "code": 499, "message": "Analysis stream interrupted",
                })
            # A disconnect cancels Starlette's task group. Shield the final write
            # and keep synchronous HTTP work off the event loop.
            with CancelScope(shield=True):
                await to_thread(close_stream)


@app.post(
    "/analyze-event/stream",
    response_class=StreamingResponse,
    summary="Stream sequential workflow progress and results",
    responses={200: {"content": {"text/event-stream": {"schema": {"type": "string"}}}}},
)
def analyze_event_stream(payload: AnalyzeEventRequest, request: Request,
                         user: UserSession = Depends(require_user), origin: None = Depends(require_origin)) -> StreamingResponse:
    analysis_id = str(uuid4())
    logger.info("POST /analyze-event/stream triggered (analysis_id=%s, text_length=%d)", analysis_id, len(payload.text))
    runtime = request.app.state.runtime
    categories = request.app.state.workflow_categories
    persistence = AnalysisPersistence(request.app.state.pocketbase, analysis_id, payload.text, user.id, user.token)
    try:
        future = submit_embedding(payload.text, request)
    except Exception:
        persistence.embedding_completed(False)
        persistence.finish(error={"workflow_id": None, "code": 500, "message": "Embedding submission failed"})
        raise
    track_embedding(future, persistence)

    def stream():
        current_id = None
        try:
            for event, data in iter_workflow_events(payload.text, runtime, categories):
                persistence.on_event(event, data)
                if event == "analysis_started":
                    data = {**data, "analysis_id": analysis_id}
                if event == "workflow_started":
                    current_id = data["id"]
                if event == "analysis_completed":
                    persistence.finish()
                    data = {**data, **embedding_result(future)}
                yield encode_event(event, data)
        except Exception as exc:
            future.cancel()
            code = exc.status_code if isinstance(exc, WorkflowError) else 500
            message = {
                413: "Händelsetexten och instruktionerna överskrider modellens textgräns.",
                502: "Modellanalysen misslyckades eller gav ett ogiltigt resultat.",
                503: "Den laddade modellen stöder inte analysen.",
            }.get(code, "Ett oväntat serverfel avbröt analysen.")
            logger.exception("Streaming analysis failed (analysis_id=%s, workflow=%s)", analysis_id, current_id)
            persistence.finish(error={"workflow_id": current_id, "message": message, "code": code})
            yield encode_event("workflow_failed", {
                "id": current_id, "message": message, "code": code,
            })
        finally:
            future.cancel()

    # Starlette advances synchronous iterators in its worker pool, not the event loop.
    return EmbeddingStreamingResponse(stream(), embedding_future=future, persistence=persistence, media_type="text/event-stream", headers={
        "Cache-Control": "no-cache, no-transform",
        "X-Accel-Buffering": "no",
        "X-Analysis-ID": analysis_id,
    })
