import asyncio
import logging
from concurrent.futures import Future, ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import torch
from fastapi import Request
from fastapi.testclient import TestClient
from tokenizers import Tokenizer
from tokenizers.models import WordLevel
from tokenizers.pre_tokenizers import WhitespaceSplit
from tokenizers.processors import TemplateProcessing
from transformers import BatchEncoding, PreTrainedTokenizerFast

import app as backend
import embeddings
import workflows
from test_app import EMBEDDING, loaders
from test_stream import parse_events


@pytest.fixture
def tokenizer():
    # An in-memory tokenizer, with no checkpoint or model downloads.
    raw = Tokenizer(WordLevel({"[UNK]": 0, "[BOS]": 1, "[EOS]": 2, "first": 3, "last": 4}, unk_token="[UNK]"))
    raw.pre_tokenizer = WhitespaceSplit()
    raw.post_processor = TemplateProcessing(single="[BOS] $A [EOS]", special_tokens=[("[BOS]", 1), ("[EOS]", 2)])
    return PreTrainedTokenizerFast(tokenizer_object=raw, unk_token="[UNK]", bos_token="[BOS]", eos_token="[EOS]")


def output_for(inputs):
    hidden = torch.zeros(1, inputs["input_ids"].shape[-1], 768)
    hidden[:, :, 0] = 3
    hidden[:, :, 1] = 4
    return SimpleNamespace(last_hidden_state=hidden)


@pytest.mark.parametrize("words", [8185, 8186, 8187])
def test_prefix_truncation_and_special_tokens(tokenizer, words):
    model = Mock(side_effect=lambda **inputs: output_for(inputs))
    runtime = embeddings.EmbeddingRuntime(tokenizer, model, "cpu")
    text = "first " + "middle " * (words - 2) + "last"
    result = embeddings.embed_document(text, runtime)
    full = tokenizer(embeddings.DOCUMENT_PREFIX + text)["input_ids"]
    used = model.call_args.kwargs["input_ids"][0].tolist()
    assert result["input_tokens"] == len(full)
    assert result["embedded_tokens"] == min(len(full), 8192)
    assert result["truncated"] == (len(full) > 8192)
    assert used[0] == tokenizer.bos_token_id
    assert used[-1] == tokenizer.eos_token_id
    expected = full[:8191] + [tokenizer.eos_token_id] if len(full) > 8192 else full
    assert used == expected
    assert len(result["vector"]) == 768
    assert result["vector"][:2] == pytest.approx([0.6, 0.8])


def test_masked_pooling_and_inference_mode():
    inputs = BatchEncoding({"input_ids": torch.tensor([[1, 2, 0]]), "attention_mask": torch.tensor([[1, 1, 0]])})
    tokenizer = Mock(return_value=inputs)
    hidden = torch.zeros(1, 3, 768)
    hidden[0, 0, 0] = 6
    hidden[0, 1, 1] = 8
    hidden[0, 2, 2] = 1000

    def infer(**kwargs):
        assert torch.is_inference_mode_enabled()
        return SimpleNamespace(last_hidden_state=hidden)

    result = embeddings.embed_document("Text", embeddings.EmbeddingRuntime(tokenizer, Mock(side_effect=infer), "cpu"))
    assert result["vector"][:3] == pytest.approx([0.6, 0.8, 0])
    assert tokenizer.call_args.args == ("title: none | text: Text",)


@pytest.mark.parametrize("kind", ["nan", "inf", "zero", "wrong_dimension", "inference"])
def test_invalid_vectors_and_inference_errors(tokenizer, kind, caplog):
    def infer(**inputs):
        if kind == "inference":
            raise RuntimeError("Mock inference failure")
        hidden = output_for(inputs).last_hidden_state
        if kind == "wrong_dimension":
            hidden = hidden[:, :, :512]
        elif kind == "zero":
            hidden.zero_()
        else:
            hidden[0, 0, 0] = float(kind)
        return SimpleNamespace(last_hidden_state=hidden)

    with caplog.at_level(logging.DEBUG, logger=embeddings.logger.name):
        with pytest.raises(embeddings.EmbeddingError):
            embeddings.embed_document("Text", embeddings.EmbeddingRuntime(tokenizer, Mock(side_effect=infer), "cpu"))
    assert any("embedding_seconds=" in r.message and "status=failed" in r.message for r in caplog.records)


@pytest.mark.parametrize("device,bf16,dtype", [("cpu", True, torch.float32), ("cuda", True, torch.bfloat16), ("cuda", False, torch.float32)])
def test_loading_device_dtype_and_logs(monkeypatch, caplog, device, bf16, dtype):
    config_loader = Mock(return_value=Mock())
    tokenizer_loader = Mock(return_value=Mock())
    model_loader = Mock(return_value=Mock())
    monkeypatch.setattr(embeddings.AutoConfig, "from_pretrained", config_loader)
    monkeypatch.setattr(embeddings.AutoTokenizer, "from_pretrained", tokenizer_loader)
    monkeypatch.setattr(embeddings.AutoModel, "from_pretrained", model_loader)
    monkeypatch.setattr(embeddings.torch.cuda, "is_bf16_supported", Mock(return_value=bf16))
    with caplog.at_level(logging.INFO, logger=embeddings.logger.name):
        runtime = embeddings.load_embedding_runtime(device)
    config_loader.assert_called_once_with(embeddings.MODEL_ID, audio_config=None, vision_config=None)
    model_loader.assert_called_once_with(embeddings.MODEL_ID, config=config_loader.return_value, dtype=dtype)
    runtime.model.to.assert_called_once_with(device)
    runtime.model.eval.assert_called_once()
    assert runtime.tokenizer.truncation_side == "right"
    messages = [r.message for r in caplog.records]
    assert any("loading started" in m and f"device={device}" in m and f"dtype={dtype}" in m for m in messages)
    assert any("loading finished in" in m for m in messages)


def test_loading_failure_is_logged(monkeypatch, caplog):
    monkeypatch.setattr(embeddings.AutoConfig, "from_pretrained", Mock(side_effect=ValueError("Mock config failure")))
    with caplog.at_level(logging.INFO, logger=embeddings.logger.name):
        with pytest.raises(RuntimeError, match="Failed to load embedding model"):
            embeddings.load_embedding_runtime("cpu")
    assert any("loading failed after" in r.message and r.exc_info for r in caplog.records)


@pytest.mark.parametrize("level", [logging.INFO, logging.DEBUG])
def test_token_timing_logs_and_cuda_sync(monkeypatch, caplog, level):
    inputs = BatchEncoding({"input_ids": torch.tensor([[1, 2]]), "attention_mask": torch.tensor([[1, 1]])})
    # Exercise CUDA timing without transferring tensors to an actual GPU.
    monkeypatch.setattr(inputs, "to", Mock(return_value=inputs))
    synchronize = Mock()
    monkeypatch.setattr(embeddings.torch.cuda, "synchronize", synchronize)
    clock = Mock(side_effect=[10.0, 10.5])
    monkeypatch.setattr(embeddings, "perf_counter", clock)
    runtime = embeddings.EmbeddingRuntime(Mock(return_value=inputs), Mock(side_effect=lambda **kw: output_for(kw)), "cuda")
    with caplog.at_level(level, logger=embeddings.logger.name):
        embeddings.embed_document("PRIVATE TEXT", runtime)
    messages = [r.message for r in caplog.records]
    assert not any("PRIVATE TEXT" in m for m in messages)
    if level == logging.DEBUG:
        assert any("input_tokens=2 embedded_tokens=2 truncated=False" in m for m in messages)
        assert any("embedding_seconds=0.500000 status=completed" in m for m in messages)
        assert synchronize.call_count == 2
        assert clock.call_count == 2
    else:
        assert not messages
        synchronize.assert_not_called()
        clock.assert_not_called()


def test_startup_failure_cleans_up_llm(loaders, monkeypatch):
    monkeypatch.setattr(backend, "load_embedding_runtime", Mock(side_effect=RuntimeError("Mock loading failure")))
    with pytest.raises(RuntimeError, match="Mock loading failure"):
        with TestClient(backend.app):
            pass
    assert not hasattr(backend.app.state, "runtime")
    assert not hasattr(backend.app.state, "embedding_executor")


def test_endpoint_runtime_reuse_and_shutdown(loaders):
    with TestClient(backend.app) as client:
        runtime = backend.app.state.embedding_runtime
        executor = backend.app.state.embedding_executor
        for _ in range(2):
            result = client.post("/embed-event", json={"text": "  Text  "})
            assert result.status_code == 200
            assert result.json() == {"status": "ok", "embedding": EMBEDDING}
        backend.load_embedding_runtime.assert_called_once_with("cpu")
        backend.embed_document.assert_called_with("Text", runtime)
    assert not hasattr(backend.app.state, "embedding_runtime")
    assert not hasattr(backend.app.state, "embedding_executor")
    with pytest.raises(RuntimeError, match="shutdown"):
        executor.submit(lambda: None)


@pytest.mark.parametrize("payload", [{}, {"text": ""}, {"text": "  "}, {"text": None}, {"text": 1}, {"text": []}])
def test_endpoint_validation(loaders, payload):
    with TestClient(backend.app) as client:
        assert client.post("/embed-event", json=payload).status_code == 422
        backend.embed_document.assert_not_called()


@pytest.mark.parametrize("path", ["/embed-event", "/analyze-event", "/analyze-event/stream"])
def test_embedding_failure_isolated_from_analysis(loaders, monkeypatch, path):
    monkeypatch.setattr(backend, "embed_document", Mock(side_effect=embeddings.EmbeddingError("Mock embedding failure")))
    monkeypatch.setattr(workflows, "generate_text", Mock(return_value="[]"))
    with TestClient(backend.app) as client:
        response = client.post(path, json={"text": "Text"})
    if path == "/embed-event":
        assert response.status_code == 502
    else:
        assert response.status_code == 200
        data = parse_events(response)[-1][1] if path.endswith("/stream") else response.json()
        assert data["embedding"] is None
        assert data["embedding_error"] == {"code": 502, "message": "Embedding inference failed"}
        if path.endswith("/stream"):
            assert parse_events(response)[-1][0] == "analysis_completed"


@pytest.mark.parametrize("path", ["/analyze-event", "/analyze-event/stream"])
def test_embedding_overlaps_with_analysis(loaders, monkeypatch, path):
    embedding_started = Event()
    analysis_started = Event()

    def embed(*args):
        embedding_started.set()
        assert analysis_started.wait(5), "Analysis blocked behind embedding"
        return EMBEDDING

    def title(*args):
        assert embedding_started.wait(5), "Embedding was not started"
        analysis_started.set()
        return "Testhändelse"

    monkeypatch.setattr(backend, "embed_document", embed)
    monkeypatch.setattr(workflows, "generate_title", title)
    monkeypatch.setattr(workflows, "generate_text", Mock(return_value="[]"))
    with TestClient(backend.app) as client:
        response = client.post(path, json={"text": "Text"})
    assert response.status_code == 200
    data = parse_events(response)[-1][1] if path.endswith("/stream") else response.json()
    assert data["embedding"] == EMBEDDING


def test_embedding_calls_serialize(tokenizer):
    first_entered = Event()
    second_tokenized = Event()
    release = Event()
    calls = []

    def tokenize(text, **kwargs):
        if text.endswith("second"):
            second_tokenized.set()
        return tokenizer(text, **kwargs)

    def infer(**inputs):
        calls.append(1)
        if len(calls) == 1:
            first_entered.set()
            assert release.wait(5)
        return output_for(inputs)

    runtime = embeddings.EmbeddingRuntime(tokenize, Mock(side_effect=infer), "cpu")
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(embeddings.embed_document, "first", runtime)
        try:
            assert first_entered.wait(5)
            second = pool.submit(embeddings.embed_document, "second", runtime)
            assert second_tokenized.wait(5)
            assert len(calls) == 1
        finally:
            release.set()
        first.result(timeout=5)
        second.result(timeout=5)
    assert len(calls) == 2


def test_stream_progress_does_not_wait_for_embedding(loaders, monkeypatch):
    release = Event()

    def embed(*args):
        assert release.wait(5), "Stream progress waited for embedding"
        return EMBEDDING

    monkeypatch.setattr(backend, "embed_document", embed)
    monkeypatch.setattr(workflows, "generate_title", Mock(return_value="Testhändelse"))
    monkeypatch.setattr(workflows, "generate_text", Mock(return_value="[]"))

    async def consume():
        request = Request({"type": "http", "app": backend.app})
        response = backend.analyze_event_stream(backend.AnalyzeEventRequest(text="Text"), request,
                                               backend.UserSession("testuser0000001", "user@example.com", "token"))
        frames = []
        try:
            async for frame in response.body_iterator:
                frames.append(frame)
                if frame.startswith("event: workflow_completed"):
                    release.set()
        finally:
            release.set()
        assert frames[0].startswith("event: analysis_started")
        assert frames[-1].startswith("event: analysis_completed")
        assert '"embedding_error": null' in frames[-1]

    with TestClient(backend.app):
        asyncio.run(consume())


@pytest.mark.parametrize("path", ["json", "stream"])
def test_analysis_failure_cancels_queued_embedding(loaders, monkeypatch, path):
    pending = Future()
    monkeypatch.setattr(backend, "submit_embedding", Mock(return_value=pending))
    monkeypatch.setattr(workflows, "generate_title", Mock(side_effect=workflows.WorkflowError(503, "Unsupported")))
    with TestClient(backend.app) as client:
        response = client.post("/analyze-event" + ("/stream" if path == "stream" else ""), json={"text": "Text"})
    assert pending.cancelled()
    if path == "json":
        assert response.status_code == 503
    else:
        assert parse_events(response)[-1][0] == "workflow_failed"


def test_stream_disconnect_before_iteration_cancels_embedding(loaders, monkeypatch):
    pending = Future()
    monkeypatch.setattr(backend, "submit_embedding", Mock(return_value=pending))
    request = Request({"type": "http", "app": backend.app})

    async def disconnected(*args):
        raise OSError("Client disconnected")

    monkeypatch.setattr(backend.StreamingResponse, "__call__", disconnected)
    with TestClient(backend.app):
        response = backend.analyze_event_stream(backend.AnalyzeEventRequest(text="Text"), request,
                                               backend.UserSession("testuser0000001", "user@example.com", "token"))
        with pytest.raises(OSError):
            asyncio.run(response({}, None, None))
    assert pending.cancelled()
