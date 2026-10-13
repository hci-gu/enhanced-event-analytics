"""Text-only document embeddings, independent of the analysis model lock."""

import logging
from _thread import LockType
from dataclasses import dataclass, field
from threading import Lock
from time import perf_counter
from typing import Any

import torch
from transformers import AutoConfig, AutoModel, AutoTokenizer, PreTrainedModel, PreTrainedTokenizerBase


MODEL_ID = "google/embeddinggemma-2"
MAX_INPUT_TOKENS = 8192
DIMENSIONS = 768
DOCUMENT_PREFIX = "title: none | text: "
logger = logging.getLogger("uvicorn.error.embeddings")


class EmbeddingError(Exception):
    """An embedding could not be generated or validated."""


@dataclass
class EmbeddingRuntime:
    tokenizer: PreTrainedTokenizerBase
    model: PreTrainedModel
    device: str
    model_id: str = MODEL_ID
    inference_lock: LockType = field(default_factory=Lock, repr=False)


def load_embedding_runtime(device: str) -> EmbeddingRuntime:
    dtype = torch.bfloat16 if device == "cuda" and torch.cuda.is_bf16_supported() else torch.float32
    started = perf_counter()
    logger.info("Embedding model loading started (model_id=%s, device=%s, dtype=%s)", MODEL_ID, device, dtype)
    try:
        config = AutoConfig.from_pretrained(MODEL_ID, audio_config=None, vision_config=None)
        tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
        # Truncation must retain the beginning of the document.
        tokenizer.truncation_side = "right"
        model = AutoModel.from_pretrained(MODEL_ID, config=config, dtype=dtype)
        model.to(device)
        model.eval()
    except Exception as exc:
        logger.exception(
            "Embedding model loading failed after %.2fs (model_id=%s, device=%s, dtype=%s)",
            perf_counter() - started, MODEL_ID, device, dtype,
        )
        raise RuntimeError(f"Failed to load embedding model {MODEL_ID!r} on {device}") from exc
    logger.info(
        "Embedding model loading finished in %.2fs (model_id=%s, device=%s, dtype=%s)",
        perf_counter() - started, MODEL_ID, device, dtype,
    )
    return EmbeddingRuntime(tokenizer=tokenizer, model=model, device=device)


def embed_document(text: str, runtime: EmbeddingRuntime) -> dict[str, Any]:
    try:
        inputs = runtime.tokenizer(
            DOCUMENT_PREFIX + text, add_special_tokens=True, truncation=False,
            return_attention_mask=True, return_token_type_ids=False, return_tensors="pt", verbose=False,
        )
        input_tokens = inputs["input_ids"].shape[-1]
        if input_tokens > MAX_INPUT_TOKENS:
            # Use the tokenizer's normal encoding path so fast-tokenizer postprocessors
            # retain BOS/EOS and any other model-specific special tokens.
            inputs = runtime.tokenizer(
                DOCUMENT_PREFIX + text, add_special_tokens=True, truncation=True,
                max_length=MAX_INPUT_TOKENS, return_attention_mask=True,
                return_token_type_ids=False, return_tensors="pt", verbose=False,
            )
        embedded_tokens = inputs["input_ids"].shape[-1]
        truncated = input_tokens > embedded_tokens
        logger.debug(
            "Embedding input_tokens=%d embedded_tokens=%d truncated=%s",
            input_tokens, embedded_tokens, truncated,
        )
        with runtime.inference_lock, torch.inference_mode():
            debug_metrics = logger.isEnabledFor(logging.DEBUG)
            if debug_metrics and runtime.device == "cuda":
                torch.cuda.synchronize()
            started = perf_counter() if debug_metrics else None
            status = "failed"
            try:
                inputs = inputs.to(runtime.device)
                hidden = runtime.model(**inputs).last_hidden_state.float()
                mask = inputs["attention_mask"].unsqueeze(-1).to(hidden.dtype)
                pooled = (hidden * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1)
                norm = torch.linalg.vector_norm(pooled, dim=-1, keepdim=True)
                if (
                    pooled.shape != (1, DIMENSIONS)
                    or not torch.isfinite(pooled).all()
                    or not torch.isfinite(norm).all()
                    or (norm <= 0).any()
                ):
                    raise EmbeddingError("Embedding model returned an invalid vector")
                vector = pooled / norm
                status = "completed"
            finally:
                if debug_metrics:
                    if runtime.device == "cuda":
                        torch.cuda.synchronize()
                    logger.debug("Embedding embedding_seconds=%.6f status=%s", perf_counter() - started, status)
            values = vector[0].cpu().tolist()
        return {
            "vector": values, "model_id": runtime.model_id, "task": "document",
            "dimensions": DIMENSIONS, "normalized": True, "truncated": truncated,
            "input_tokens": input_tokens, "embedded_tokens": embedded_tokens,
        }
    except EmbeddingError:
        raise
    except Exception as exc:
        logger.debug("Embedding status=failed", exc_info=True)
        raise EmbeddingError("Embedding inference failed") from exc
