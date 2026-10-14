"""Generation adapters; vLLM is imported only for a selected CUDA runtime."""

import asyncio
import logging
import math
import os
import sys
from dataclasses import dataclass
from time import perf_counter
from typing import TYPE_CHECKING, Any, Protocol
from uuid import uuid4

if TYPE_CHECKING:
    from app import ModelRuntime


def load_serving_engine() -> str:
    value = os.environ.get("SERVING_ENGINE", "transformers").strip()
    if value not in {"transformers", "vllm"}:
        raise RuntimeError("SERVING_ENGINE must be transformers or vllm")
    return value


@dataclass(frozen=True)
class VllmSettings:
    model_id: str
    retry_limit: int
    gpu_memory_utilization: float
    kv_cache_memory_bytes: int | None = None

    @classmethod
    def from_environment(cls):
        import torch
        from workflows import load_retry_limit

        model_id = os.environ.get("MODEL_ID", "").strip()
        if not model_id:
            raise RuntimeError("MODEL_ID must identify a Hugging Face model or local directory")
        retry_limit = load_retry_limit()
        device = os.environ.get("MODEL_DEVICE", "auto")
        if device not in {"auto", "cpu", "cuda"}:
            raise RuntimeError("MODEL_DEVICE must be auto, cpu, or cuda")
        if sys.platform != "linux":
            raise RuntimeError("SERVING_ENGINE=vllm requires Linux and the CUDA extra")
        if device == "cpu" or not torch.cuda.is_available():
            raise RuntimeError("SERVING_ENGINE=vllm requires an available CUDA device and MODEL_DEVICE=auto or cuda")
        try:
            memory = float(os.environ.get("VLLM_GPU_MEMORY_UTILIZATION", "0.50"))
            if not math.isfinite(memory) or not 0 < memory <= 1:
                raise ValueError
        except ValueError as exc:
            raise RuntimeError("VLLM_GPU_MEMORY_UTILIZATION must be finite and greater than 0 and at most 1") from exc
        cache_value = os.environ.get("VLLM_KV_CACHE_MEMORY_BYTES", "").strip()
        cache_bytes = None
        if cache_value:
            try:
                cache_bytes = int(cache_value)
                if cache_bytes <= 0:
                    raise ValueError
            except ValueError as exc:
                raise RuntimeError("VLLM_KV_CACHE_MEMORY_BYTES must be a positive integer in bytes or blank") from exc
        return cls(model_id, retry_limit, memory, cache_bytes)


class GenerationEngine(Protocol):
    def generate(self, messages: list[dict[str, str]], runtime: "ModelRuntime", *,
                 max_new_tokens: int, workflow_name: str, retries: int) -> str: ...

    async def close(self) -> None: ...


class TransformersEngine:
    def generate(self, messages, runtime, **kwargs) -> str:
        from workflows import _generate_transformers

        return _generate_transformers(messages, runtime, **kwargs)

    async def close(self) -> None:
        # Dropping the runtime releases the Transformers model and processor.
        pass


class VllmEngine:
    def __init__(self, engine: Any, sampling_params: Any):
        self.engine = engine
        self.sampling_params = sampling_params
        self.loop = asyncio.get_running_loop()
        self.requests: dict[str, asyncio.Task] = {}
        self.closed = False

    def generate(self, messages, runtime: "ModelRuntime", *, max_new_tokens: int,
                 workflow_name: str, retries: int) -> str:
        from workflows import MAX_INPUT_TOKENS, WorkflowError, logger

        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None
        if running_loop is self.loop:
            raise RuntimeError("Synchronous vLLM generation must run in a worker thread")
        with runtime.inference_lock:
            if self.closed or not self.loop.is_running():
                raise WorkflowError(503, "The model engine is shutting down")
            try:
                template = runtime.processor if runtime.processor is not None else runtime.tokenizer
                inputs = template.apply_chat_template(
                    messages, tokenize=True, return_dict=True, return_tensors="pt",
                    add_generation_prompt=True, enable_thinking=False,
                )
                # Processors return a batch, even for one conversation. Keep the
                # same preparation as Transformers, but send only flat CPU IDs.
                tokens = inputs["input_ids"][0].tolist()
                if len(tokens) > MAX_INPUT_TOKENS:
                    raise WorkflowError(413, "Event and workflow instructions exceed 8192 tokens")
                params = self.sampling_params(
                    temperature=0, n=1, max_tokens=max_new_tokens, skip_special_tokens=True,
                )
                started = perf_counter()
                future = asyncio.run_coroutine_threadsafe(self._generate(tokens, params), self.loop)
                result = future.result()
                seconds = perf_counter() - started
                completion = result.outputs[0]
                if logger.isEnabledFor(logging.DEBUG):
                    output_tokens = len(completion.token_ids)
                    logger.debug(
                        "LLM call workflow=%s input_tokens=%d output_tokens=%d "
                        "generation_seconds=%.6f tokens_per_second=%.2f retries=%d status=generated",
                        workflow_name, len(result.prompt_token_ids), output_tokens, seconds,
                        output_tokens / seconds if seconds > 0 else 0.0, retries,
                    )
                return runtime.tokenizer.decode(completion.token_ids, skip_special_tokens=True)
            except WorkflowError:
                raise
            except Exception as exc:
                logger.debug("LLM call workflow=%s status=failed retries=%d", workflow_name, retries, exc_info=True)
                raise WorkflowError(502, "Model inference failed") from exc

    async def _generate(self, tokens: list[int], params: Any):
        from workflows import WorkflowError

        if self.closed:
            raise WorkflowError(503, "The model engine is shutting down")
        request_id = str(uuid4())
        self.requests[request_id] = asyncio.current_task()
        finished = False
        try:
            result = None
            async for output in self.engine.generate(
                {"prompt_token_ids": tokens}, params, request_id=request_id,
            ):
                result = output
            if result is None or not result.finished or len(result.outputs) != 1:
                raise RuntimeError("vLLM returned no completed output")
            finished = True
            return result
        finally:
            try:
                if not finished:
                    await self.engine.abort(request_id)
            finally:
                self.requests.pop(request_id, None)

    async def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        tasks = list(self.requests.values())
        try:
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
        finally:
            self.engine.shutdown()


def create_vllm_engine(settings: VllmSettings) -> VllmEngine:
    from workflows import MAX_INPUT_TOKENS, MAX_OUTPUT_TOKENS

    try:
        from vllm import SamplingParams
        from vllm.engine.arg_utils import AsyncEngineArgs
        from vllm.v1.engine.async_llm import AsyncLLM
    except ImportError as exc:
        raise RuntimeError("SERVING_ENGINE=vllm requires vLLM; install the Linux CUDA extra") from exc

    args = AsyncEngineArgs(
        model=settings.model_id, dtype="auto", trust_remote_code=False,
        tensor_parallel_size=1, max_num_seqs=1,
        max_model_len=MAX_INPUT_TOKENS + MAX_OUTPUT_TOKENS,
        gpu_memory_utilization=settings.gpu_memory_utilization,
        kv_cache_memory_bytes=settings.kv_cache_memory_bytes,
        language_model_only=True, enforce_eager=True,
        enable_log_requests=False,
    )
    # Embeddings have already initialized CUDA in the parent process.
    # Spawn workers rather than forking that initialized CUDA context.
    os.environ.setdefault("VLLM_WORKER_MULTIPROC_METHOD", "spawn")
    engine = AsyncLLM.from_engine_args(args)
    try:
        return VllmEngine(engine, SamplingParams)
    except BaseException:
        engine.shutdown()
        raise
