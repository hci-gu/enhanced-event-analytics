"""Embedded-engine tests use mocked weights, CUDA, vLLM, and HTTP services."""

import asyncio
import builtins
import json
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
import torch
from fastapi.testclient import TestClient

import app as backend
import serving
import workflows


@pytest.fixture
def settings_environment(monkeypatch):
    monkeypatch.setattr(serving.sys, "platform", "linux")
    monkeypatch.setattr(torch.cuda, "is_available", Mock(return_value=True))
    monkeypatch.setenv("MODEL_ID", "nvidia/Gemma-4-26B-A4B-NVFP4")
    monkeypatch.setenv("MODEL_DEVICE", "auto")
    monkeypatch.delenv("RETRY_LIMIT", raising=False)


@pytest.mark.parametrize("value,expected", [(None, "transformers"), (" transformers ", "transformers"), ("vllm", "vllm")])
def test_engine_selection(monkeypatch, value, expected):
    if value is not None:
        monkeypatch.setenv("SERVING_ENGINE", value)
    assert serving.load_serving_engine() == expected


@pytest.mark.parametrize("value", ["", "VLLM", "other"])
def test_invalid_engine_prevents_loading(monkeypatch, value, pocketbase):
    monkeypatch.setenv("SERVING_ENGINE", value)
    monkeypatch.setattr(backend, "load_dotenv", Mock())
    loader = Mock()
    monkeypatch.setattr(backend, "load_runtime", loader)
    with pytest.raises(RuntimeError, match="SERVING_ENGINE must"):
        with TestClient(backend.app):
            pass
    loader.assert_not_called()


@pytest.mark.parametrize("memory,expected", [(None, 0.7), (" 0.5 ", 0.5), ("1", 1)])
def test_vllm_memory(settings_environment, monkeypatch, memory, expected):
    if memory is not None:
        monkeypatch.setenv("VLLM_GPU_MEMORY_UTILIZATION", memory)
    settings = serving.VllmSettings.from_environment()
    assert settings.gpu_memory_utilization == expected
    assert settings.retry_limit == 1


@pytest.mark.parametrize("value", ["0", "-1", "1.01", "nan", "inf", "bad", ""])
def test_invalid_memory(settings_environment, monkeypatch, value):
    monkeypatch.setenv("VLLM_GPU_MEMORY_UTILIZATION", value)
    with pytest.raises(RuntimeError, match="VLLM_GPU_MEMORY_UTILIZATION"):
        serving.VllmSettings.from_environment()


@pytest.mark.parametrize("platform,device,available,message", [
    ("win32", "auto", True, "requires Linux"),
    ("linux", "cpu", True, "requires an available CUDA"),
    ("linux", "auto", False, "requires an available CUDA"),
    ("linux", "bad", True, "MODEL_DEVICE must"),
])
def test_vllm_platform_device(settings_environment, monkeypatch, platform, device, available, message):
    monkeypatch.setattr(serving.sys, "platform", platform)
    monkeypatch.setenv("MODEL_DEVICE", device)
    monkeypatch.setattr(torch.cuda, "is_available", Mock(return_value=available))
    with pytest.raises(RuntimeError, match=message):
        serving.VllmSettings.from_environment()


def test_missing_model_id(settings_environment, monkeypatch):
    monkeypatch.delenv("MODEL_ID")
    with pytest.raises(RuntimeError, match="MODEL_ID must"):
        serving.VllmSettings.from_environment()


def test_missing_vllm_dependency(monkeypatch):
    monkeypatch.setitem(sys.modules, "vllm", None)
    with pytest.raises(RuntimeError, match="install the Linux CUDA extra"):
        serving.create_vllm_engine(serving.VllmSettings("test/model", 1, 0.7))


@pytest.fixture
def fake_vllm(monkeypatch):
    calls = []
    engine = SimpleNamespace(abort=AsyncMock(), shutdown=Mock(), failure=None, outputs=[])

    async def generate(prompt, params, *, request_id):
        calls.append((prompt, params, request_id))
        if engine.failure is not None:
            raise engine.failure
        yield SimpleNamespace(finished=False, outputs=[])
        engine.outputs.append(len(calls))
        yield SimpleNamespace(
            finished=True, prompt_token_ids=prompt["prompt_token_ids"],
            outputs=[SimpleNamespace(token_ids=[12, 13])],
        )

    engine.generate = generate
    args = Mock(side_effect=lambda **kwargs: SimpleNamespace(**kwargs))
    sampling = Mock(side_effect=lambda **kwargs: SimpleNamespace(**kwargs))
    loader = Mock(return_value=engine)
    monkeypatch.setitem(sys.modules, "vllm", SimpleNamespace(SamplingParams=sampling))
    monkeypatch.setitem(sys.modules, "vllm.engine.arg_utils", SimpleNamespace(AsyncEngineArgs=args))
    monkeypatch.setitem(sys.modules, "vllm.v1.engine.async_llm", SimpleNamespace(AsyncLLM=SimpleNamespace(from_engine_args=loader)))
    monkeypatch.delenv("VLLM_WORKER_MULTIPROC_METHOD", raising=False)
    return SimpleNamespace(engine=engine, args=args, sampling=sampling, loader=loader, calls=calls)


def test_engine_arguments_and_cleanup(fake_vllm):
    async def check():
        adapter = serving.create_vllm_engine(serving.VllmSettings("test/model", 1, 0.65))
        args = fake_vllm.args.call_args.kwargs
        assert args == {
            "model": "test/model", "dtype": "auto", "trust_remote_code": False,
            "tensor_parallel_size": 1, "max_num_seqs": 1, "max_model_len": 12288,
            "gpu_memory_utilization": 0.65, "enable_log_requests": False,
        }
        await adapter.close()
        await adapter.close()
        fake_vllm.engine.shutdown.assert_called_once()
    asyncio.run(check())


def test_adapter_initialization_failure_closes_engine(fake_vllm):
    # Creating the adapter without an owning event loop fails after the fake
    # engine has been initialized; its workers must still be shut down.
    with pytest.raises(RuntimeError, match="no running event loop"):
        serving.create_vllm_engine(serving.VllmSettings("test/model", 1, 0.7))
    fake_vllm.engine.shutdown.assert_called_once()


def test_generation_and_metrics(fake_vllm, caplog, monkeypatch):
    async def check():
        adapter = serving.create_vllm_engine(serving.VllmSettings("test/model", 1, 0.7))
        tokenizer = Mock()
        tokenizer.apply_chat_template.return_value = {"input_ids": torch.tensor([[10, 11]])}
        tokenizer.decode.return_value = "[]"
        runtime = backend.ModelRuntime(tokenizer, fake_vllm.engine, "cuda", "test/model", engine=adapter)
        monkeypatch.setattr(serving, "perf_counter", Mock(side_effect=[10.0, 12.0]))
        try:
            with caplog.at_level("DEBUG", logger=workflows.logger.name):
                output = await asyncio.to_thread(workflows.generate_text, [], runtime, workflow_name="Risk", retries=1)
            assert output == "[]"
            tokenizer.apply_chat_template.assert_called_once_with(
                [], tokenize=True, return_dict=True, return_tensors="pt",
                add_generation_prompt=True, enable_thinking=False,
            )
            assert fake_vllm.calls[0][0] == {"prompt_token_ids": [10, 11]}
            assert fake_vllm.sampling.call_args.kwargs == {
                "temperature": 0, "n": 1, "max_tokens": 4096, "skip_special_tokens": True,
            }
            tokenizer.decode.assert_called_once_with([12, 13], skip_special_tokens=True)
            assert "input_tokens=2 output_tokens=2" in caplog.text
            assert "generation_seconds=2.000000 tokens_per_second=1.00 retries=1" in caplog.text
            assert not adapter.requests
            assert not runtime.inference_lock.locked()
        finally:
            await adapter.close()
    asyncio.run(check())


@pytest.mark.parametrize("length,status", [(8192, None), (8193, 413)])
def test_vllm_token_limits(fake_vllm, length, status):
    async def check():
        adapter = serving.create_vllm_engine(serving.VllmSettings("test/model", 1, 0.7))
        tokenizer = Mock()
        tokenizer.apply_chat_template.return_value = {"input_ids": torch.tensor([[10] * length])}
        tokenizer.decode.return_value = "Title"
        runtime = backend.ModelRuntime(tokenizer, fake_vllm.engine, "cuda", "test/model", engine=adapter)
        try:
            if status:
                with pytest.raises(workflows.WorkflowError) as error:
                    await asyncio.to_thread(workflows.generate_text, [], runtime)
                assert error.value.status_code == status
                assert not fake_vllm.calls
            else:
                assert await asyncio.to_thread(workflows.generate_text, [], runtime, max_new_tokens=64) == "Title"
                assert fake_vllm.sampling.call_args.kwargs["max_tokens"] == 64
        finally:
            await adapter.close()
    asyncio.run(check())


def test_generation_failure_aborts_and_releases_lock(fake_vllm):
    async def check():
        adapter = serving.create_vllm_engine(serving.VllmSettings("test/model", 1, 0.7))
        tokenizer = Mock()
        tokenizer.apply_chat_template.return_value = {"input_ids": torch.tensor([[10]])}
        runtime = backend.ModelRuntime(tokenizer, fake_vllm.engine, "cuda", "test/model", engine=adapter)
        fake_vllm.engine.failure = RuntimeError("failed inference")
        try:
            with pytest.raises(workflows.WorkflowError) as error:
                await asyncio.to_thread(workflows.generate_text, [], runtime)
            assert error.value.status_code == 502
            fake_vllm.engine.abort.assert_awaited_once()
            assert not runtime.inference_lock.locked()
            assert not adapter.requests
        finally:
            await adapter.close()
    asyncio.run(check())


@pytest.mark.parametrize("output", [None, SimpleNamespace(finished=False, outputs=[])])
def test_incomplete_generation_is_failure(fake_vllm, output):
    async def check():
        async def incomplete(*args, **kwargs):
            if output is not None:
                yield output
        fake_vllm.engine.generate = incomplete
        adapter = serving.create_vllm_engine(serving.VllmSettings("test/model", 1, 0.7))
        try:
            with pytest.raises(RuntimeError, match="no completed output"):
                await adapter._generate([10], SimpleNamespace())
            fake_vllm.engine.abort.assert_awaited_once()
            assert not adapter.requests
        finally:
            await adapter.close()
    asyncio.run(check())


def test_closed_engine_returns_unavailable(fake_vllm):
    async def check():
        adapter = serving.create_vllm_engine(serving.VllmSettings("test/model", 1, 0.7))
        runtime = backend.ModelRuntime(Mock(), fake_vllm.engine, "cuda", "test/model", engine=adapter)
        await adapter.close()
        with pytest.raises(workflows.WorkflowError) as error:
            await asyncio.to_thread(workflows.generate_text, [], runtime)
        assert error.value.status_code == 503
        assert not fake_vllm.calls
    asyncio.run(check())


def test_shutdown_aborts_active_request(fake_vllm):
    async def check():
        started = asyncio.Event()
        async def pending(*args, **kwargs):
            started.set()
            await asyncio.Event().wait()
            yield
        fake_vllm.engine.generate = pending
        adapter = serving.create_vllm_engine(serving.VllmSettings("test/model", 1, 0.7))
        task = asyncio.create_task(adapter._generate([10], SimpleNamespace()))
        await asyncio.wait_for(started.wait(), 2)
        await adapter.close()
        assert task.cancelled()
        assert not adapter.requests
        fake_vllm.engine.abort.assert_awaited_once()
        fake_vllm.engine.shutdown.assert_called_once()
    asyncio.run(check())


def test_generation_is_serialized(fake_vllm):
    async def check():
        active = 0
        maximum_active = 0
        async def generate(prompt, params, *, request_id):
            nonlocal active, maximum_active
            active += 1
            maximum_active = max(active, maximum_active)
            await asyncio.sleep(0.01)
            active -= 1
            yield SimpleNamespace(finished=True, prompt_token_ids=[10], outputs=[SimpleNamespace(token_ids=[12])])
        fake_vllm.engine.generate = generate
        adapter = serving.create_vllm_engine(serving.VllmSettings("test/model", 1, 0.7))
        tokenizer = Mock()
        tokenizer.apply_chat_template.return_value = {"input_ids": torch.tensor([[10]])}
        tokenizer.decode.return_value = "[]"
        runtime = backend.ModelRuntime(tokenizer, fake_vllm.engine, "cuda", "test/model", engine=adapter)
        try:
            assert await asyncio.gather(*[
                asyncio.to_thread(workflows.generate_text, [], runtime) for _ in range(2)
            ]) == ["[]", "[]"]
            assert maximum_active == 1
            with pytest.raises(RuntimeError, match="worker thread"):
                workflows.generate_text([], runtime)
        finally:
            await adapter.close()
    asyncio.run(check())


@pytest.fixture
def api_runtime(monkeypatch, pocketbase, settings_environment, fake_vllm, request):
    mode = request.param
    monkeypatch.setenv("SERVING_ENGINE", mode)
    monkeypatch.setattr(backend, "load_dotenv", Mock())
    config_loader = Mock(return_value=SimpleNamespace(model_type="gemma4"))
    monkeypatch.setattr(backend.AutoConfig, "from_pretrained", config_loader)
    processor = Mock()
    processor.apply_chat_template.return_value = {"input_ids": torch.tensor([[10, 11]])}
    if mode == "transformers":
        class Inputs(dict):
            def to(self, device):
                return self
        processor.apply_chat_template.return_value = Inputs(input_ids=torch.tensor([[10, 11]]))
    monkeypatch.setattr(backend.AutoProcessor, "from_pretrained", Mock(return_value=processor))
    model = Mock()
    model.generate.return_value = torch.tensor([[10, 11, 12, 13]])
    monkeypatch.setattr(backend.Gemma4ForConditionalGeneration, "from_pretrained", Mock(return_value=model))
    embedding_loader = Mock(return_value=SimpleNamespace(model_id="google/embeddinggemma-2"))
    monkeypatch.setattr(backend, "load_embedding_runtime", embedding_loader)
    embedding = {
        "vector": [1.0] + [0.0] * 767, "model_id": "google/embeddinggemma-2", "task": "document",
        "dimensions": 768, "normalized": True, "truncated": False, "input_tokens": 10, "embedded_tokens": 10,
    }
    monkeypatch.setattr(backend, "embed_document", Mock(return_value=embedding))
    monkeypatch.setitem(backend.app.dependency_overrides, backend.require_user,
                        lambda: backend.UserSession("testuser0000001", "user@example.com", "user-token"))
    monkeypatch.setitem(backend.app.dependency_overrides, backend.require_origin, lambda: None)
    return SimpleNamespace(
        mode=mode, processor=processor, model=model, embedding_loader=embedding_loader,
        decode=processor.tokenizer.decode if mode == "vllm" else processor.decode,
        config_loader=config_loader, embedding=embedding,
    )


@pytest.mark.parametrize("api_runtime", ["transformers", "vllm"], indirect=True)
@pytest.mark.parametrize("stream", [False, True])
def test_analysis_contract_for_both_engines(api_runtime, stream, fake_vllm, pocketbase):
    api_runtime.decode.side_effect = ["Testhändelse", "bad JSON", '[{"ID":"översvämningar","evidence":["Water","wrong"]}]'] + ["[]"] * 4
    with TestClient(backend.app) as client:
        assert client.get("/health").json()["serving_engine"] == api_runtime.mode
        response = client.post("/analyze-event/stream" if stream else "/analyze-event", json={"text": "Water rises"})
        assert response.status_code == 200
        if stream:
            events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
            assert events[3]["results"][0]["evidence"] == ["Water"]
            assert "event: analysis_completed" in response.text
            result = {
                "title": events[1]["title"],
                "results": {event["id"]: event["results"] for event in events if "results" in event},
                **events[-1],
            }
        else:
            result = response.json()
            assert "evidence" not in result["results"]["risks"][0]
        assert result["title"] == "Testhändelse"
        assert result["embedding"] == api_runtime.embedding
        assert result["results"]["risks"][0]["ID"] == "översvämningar"
        assert api_runtime.decode.call_count == 7
        assert pocketbase.requests
    assert not hasattr(backend.app.state, "runtime")
    if api_runtime.mode == "vllm":
        fake_vllm.engine.shutdown.assert_called_once()


@pytest.mark.parametrize("api_runtime", ["transformers"], indirect=True)
def test_transformers_does_not_import_vllm(api_runtime, monkeypatch):
    original = builtins.__import__
    def guarded(name, *args, **kwargs):
        assert not name.startswith("vllm")
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", guarded)
    monkeypatch.setenv("VLLM_GPU_MEMORY_UTILIZATION", "invalid but unused")
    with TestClient(backend.app):
        pass


@pytest.mark.parametrize("api_runtime", ["transformers", "vllm"], indirect=True)
@pytest.mark.parametrize("stream", [False, True])
def test_title_fallback_and_terminal_failure(api_runtime, stream, pocketbase):
    api_runtime.decode.side_effect = ["not a valid title " * 5, "[]", "invalid", "invalid"]
    with TestClient(backend.app) as client:
        response = client.post("/analyze-event/stream" if stream else "/analyze-event", json={"text": "Water rises"})
    assert api_runtime.decode.call_count == 4
    if stream:
        events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
        assert events[1]["title"] == workflows.FALLBACK_TITLE
        assert events[3] == {"id": "risks", "results": []}
        assert events[-1]["code"] == 502
        assert events[-1]["id"] == "reach"
        assert "event: analysis_completed" not in response.text
    else:
        assert response.status_code == 502
    assert pocketbase.requests[-1][2]["status"] == "Failed"


@pytest.mark.parametrize("api_runtime", ["vllm"], indirect=True)
def test_vllm_inference_failure_uses_title_fallback_and_does_not_retry(api_runtime, fake_vllm):
    fake_vllm.engine.failure = RuntimeError("inference failed")
    with TestClient(backend.app) as client:
        response = client.post("/analyze-event/stream", json={"text": "Water rises"})
    events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
    assert events[1]["title"] == workflows.FALLBACK_TITLE
    assert events[-1]["code"] == 502
    assert events[-1]["id"] == "risks"
    assert len(fake_vllm.calls) == 2  # title fallback, then one failing category call
    assert fake_vllm.engine.abort.await_count == 2


@pytest.mark.parametrize("api_runtime", ["vllm"], indirect=True)
@pytest.mark.parametrize("failure", ["embedding", "engine", "executor"])
def test_partial_startup_cleanup(api_runtime, fake_vllm, monkeypatch, failure):
    def fail(*args, **kwargs):
        raise RuntimeError("startup failed")
    if failure == "embedding":
        api_runtime.embedding_loader.side_effect = fail
    elif failure == "engine":
        fake_vllm.loader.side_effect = fail
    else:
        monkeypatch.setattr(backend, "ThreadPoolExecutor", fail)
    with pytest.raises(RuntimeError, match="startup failed"):
        with TestClient(backend.app):
            pass
    for name in ("runtime", "embedding_runtime", "workflow_categories", "embedding_executor"):
        assert not hasattr(backend.app.state, name)
    if failure == "executor":
        fake_vllm.engine.shutdown.assert_called_once()
    if failure == "embedding":
        fake_vllm.loader.assert_not_called()


@pytest.mark.parametrize("api_runtime", ["vllm"], indirect=True)
def test_embedding_loaded_before_vllm(api_runtime, fake_vllm):
    order = Mock()
    order.attach_mock(api_runtime.embedding_loader, "embedding")
    order.attach_mock(fake_vllm.loader, "engine")
    with TestClient(backend.app):
        pass
    assert [call[0] for call in order.mock_calls] == ["embedding", "engine"]
