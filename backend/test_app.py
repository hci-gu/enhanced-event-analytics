import logging
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

import app as backend
import workflows


EMBEDDING = {
    "vector": [1.0] + [0.0] * 767, "model_id": "google/embeddinggemma-2", "task": "document",
    "dimensions": 768, "normalized": True, "truncated": False, "input_tokens": 10, "embedded_tokens": 10,
}


@pytest.fixture
def loaders(monkeypatch, pocketbase, no_date_inference):
    # Existing inference tests focus on analysis contracts; auth has its own suite.
    monkeypatch.setitem(backend.app.dependency_overrides, backend.require_user,
                        lambda: backend.UserSession("testuser0000001", "user@example.com", "user-token"))
    monkeypatch.setitem(backend.app.dependency_overrides, backend.require_origin, lambda: None)
    monkeypatch.setattr(backend, "load_embedding_runtime", Mock(return_value=Mock(model_id="google/embeddinggemma-2")))
    monkeypatch.setattr(backend, "embed_document", Mock(return_value=EMBEDDING))
    monkeypatch.setattr(backend, "load_dotenv", Mock())
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    monkeypatch.delenv("RETRY_LIMIT", raising=False)
    for name in (
        "uvicorn", "uvicorn.error", "uvicorn.access",
        "uvicorn.error.app", "uvicorn.error.workflows", "uvicorn.error.embeddings", "uvicorn.error.persistence",
    ):
        target = logging.getLogger(name)
        monkeypatch.setattr(target, "level", target.level)
    config = Mock(model_type="bert")
    monkeypatch.setattr(backend.AutoConfig, "from_pretrained", Mock(return_value=config))
    monkeypatch.setenv("MODEL_ID", "test/model")
    monkeypatch.setenv("MODEL_DEVICE", "auto")
    monkeypatch.setattr(backend.torch.cuda, "is_available", Mock(return_value=False))
    tokenizer = Mock()
    model = Mock()
    tokenizer_loader = Mock(return_value=tokenizer)
    model_loader = Mock(return_value=model)
    monkeypatch.setattr(backend.AutoTokenizer, "from_pretrained", tokenizer_loader)
    monkeypatch.setattr(backend.AutoModel, "from_pretrained", model_loader)
    return tokenizer_loader, model_loader


@pytest.mark.parametrize("value,expected", [(None, logging.INFO), (" debug ", logging.DEBUG)])
def test_log_level_configuration(loaders, monkeypatch, value, expected):
    if value is not None:
        monkeypatch.setenv("LOG_LEVEL", value)
    with TestClient(backend.app):
        assert backend.logger.getEffectiveLevel() == expected
        assert workflows.logger.getEffectiveLevel() == expected
        assert logging.getLogger("uvicorn.error").getEffectiveLevel() == expected
        assert logging.getLogger("uvicorn.access").getEffectiveLevel() == expected


@pytest.mark.parametrize("model_type", ["bert", "gemma4"])
@pytest.mark.parametrize("device", ["cpu", "cuda"])
@pytest.mark.parametrize("level", ["INFO", "DEBUG"])
def test_loading_stage_timings(loaders, monkeypatch, caplog, model_type, device, level):
    monkeypatch.setenv("LOG_LEVEL", level)
    monkeypatch.setenv("MODEL_DEVICE", device)
    monkeypatch.setattr(backend.torch.cuda, "is_available", Mock(return_value=True))
    synchronize = Mock()
    monkeypatch.setattr(backend.torch.cuda, "synchronize", synchronize)
    backend.AutoConfig.from_pretrained.return_value.model_type = model_type
    monkeypatch.setattr(backend.AutoProcessor, "from_pretrained", Mock(return_value=Mock()))
    monkeypatch.setattr(backend.Gemma4ForConditionalGeneration, "from_pretrained", Mock(return_value=Mock()))
    clock = Mock(side_effect=range(100))
    monkeypatch.setattr(backend, "perf_counter", clock)
    with caplog.at_level(level, logger=backend.logger.name):
        with TestClient(backend.app):
            pass
    records = [record.getMessage() for record in caplog.records if record.name == backend.logger.name]
    if level == "DEBUG":
        stages = ["categories", "device_selection", "config", "processor" if model_type == "gemma4" else "tokenizer",
                  "weights"] + (["device_placement"] if device == "cpu" else []) + ["eval"]
        assert [message for message in records if message.startswith("Loading stage=")] == [
            message for stage in stages for message in [
                f"Loading stage={stage} status=started",
                f"Loading stage={stage} status=completed duration_seconds=1.000000",
            ]
        ]
    else:
        assert not any(message.startswith("Loading stage=") for message in records)
        assert clock.call_count == 2
    assert any(message.startswith("Model loading finished in") for message in records)
    assert synchronize.call_count == (1 if device == "cuda" and level == "DEBUG" else 0)
    model_loader = backend.Gemma4ForConditionalGeneration.from_pretrained if model_type == "gemma4" else loaders[1]
    if device == "cuda":
        assert model_loader.call_args.kwargs["device_map"] == {"": "cuda:0"}
        model_loader.return_value.to.assert_not_called()
    else:
        assert "device_map" not in model_loader.call_args.kwargs
        model_loader.return_value.to.assert_called_once_with("cpu")


def test_invalid_log_level_prevents_model_loading(loaders, monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "invalid")
    with pytest.raises(RuntimeError, match="LOG_LEVEL must"):
        with TestClient(backend.app):
            pass
    loaders[0].assert_not_called()
    loaders[1].assert_not_called()


@pytest.mark.parametrize("value,expected", [(None, 1), ("0", 0), (" 2 ", 2)])
def test_retry_limit_configuration(loaders, monkeypatch, value, expected):
    if value is not None:
        monkeypatch.setenv("RETRY_LIMIT", value)
    with TestClient(backend.app):
        assert backend.app.state.runtime.retry_limit == expected


@pytest.mark.parametrize("value", ["-1", "1.5", "", "invalid"])
def test_invalid_retry_limit_prevents_model_loading(loaders, monkeypatch, value):
    monkeypatch.setenv("RETRY_LIMIT", value)
    with pytest.raises(RuntimeError, match="RETRY_LIMIT must"):
        with TestClient(backend.app):
            pass
    loaders[0].assert_not_called()
    loaders[1].assert_not_called()


def test_requests_share_runtime_and_cleanup(loaders, monkeypatch):
    empty_results = {"risks": [], "reach": [], "service": [], "properties": [], "protection": []}
    runner = Mock(return_value={"title": "Testhändelse", "results": empty_results})
    monkeypatch.setattr(backend, "run_workflows", runner)
    with TestClient(backend.app) as client:
        runtime = backend.app.state.runtime
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json() == {
            "status": "ok",
            "model_id": "test/model",
            "device": "cpu",
            "model_loaded": True,
            "serving_engine": "transformers",
            "embedding_model_id": "google/embeddinggemma-2",
            "embedding_model_loaded": True,
            "pocketbase_available": True,
        }
        runner.assert_not_called()
        for _ in range(2):
            response = client.post("/analyze-event", json={"text": "  Swedish event  "})
            assert response.status_code == 200
            assert response.json() == {"status": "ok", "title": "Testhändelse", "results": empty_results,
                                       "embedding": EMBEDDING, "embedding_error": None, "dates": None, "dates_error": None}
        assert runner.call_count == 2
        assert runner.call_args.args == ("Swedish event", runtime, backend.app.state.workflow_categories)
        assert callable(runner.call_args.kwargs["on_event"])
        loaders[0].assert_called_once_with("test/model")
        loaders[1].assert_called_once_with(
            "test/model", config=backend.AutoConfig.from_pretrained.return_value
        )
        assert runtime.tokenizer is loaders[0].return_value
        assert runtime.model is loaders[1].return_value
        runtime.model.to.assert_called_once_with("cpu")
        runtime.model.eval.assert_called_once_with()
    assert not hasattr(backend.app.state, "runtime")
    assert not hasattr(backend.app.state, "workflow_categories")


def test_unsupported_model_response(loaders):
    with TestClient(backend.app) as client:
        response = client.post("/analyze-event", json={"text": "Event"})
    assert response.status_code == 503


@pytest.mark.parametrize("article", ["test-event.txt", "test-event2.txt"])
def test_article_endpoint_contract(loaders, monkeypatch, article):
    from pathlib import Path

    generator = Mock(side_effect=[
        "Testhändelse",
        '[{"ID":"översvämningar"}]', '[{"ID":"2._lokalt"}]', '[{"ID":"vatten_va"}]',
        '[{"ID":"varaktighet"}]', '[{"ID":"samhällets_funktionalitet"}]',
    ] * 2)
    monkeypatch.setattr(workflows, "generate_text", generator)
    text = (Path(__file__).parent.parent / "data" / "events" / article).read_text(encoding="utf-8")
    with TestClient(backend.app) as client:
        runtime = backend.app.state.runtime
        for _ in range(2):
            response = client.post("/analyze-event", json={"text": text})
            assert response.status_code == 200
            assert response.json() == {
                "status": "ok",
                "dates": None, "dates_error": None,
                "title": "Testhändelse",
                "embedding": EMBEDDING,
                "embedding_error": None,
                "results": {
                    "risks": [{"ID": "översvämningar", "name": "Översvämningar"}],
                    "reach": [{"ID": "2._lokalt", "name": "2. Lokalt"}],
                    "service": [{"ID": "vatten_va", "name": "Vatten/VA"}],
                    "properties": [{"ID": "varaktighet", "name": "Varaktighet"}],
                    "protection": [{"ID": "samhällets_funktionalitet", "name": "Samhällets funktionalitet"}],
                },
            }
            assert backend.app.state.runtime is runtime
    # This validates the API plumbing, not the article's actual classification.
    assert generator.call_count == 12
    loaders[1].assert_called_once()


@pytest.mark.parametrize("status", [413, 502, 503])
def test_workflow_error_response(loaders, monkeypatch, status):
    monkeypatch.setattr(
        backend, "run_workflows", Mock(side_effect=workflows.WorkflowError(status, "Workflow error"))
    )
    with TestClient(backend.app) as client:
        response = client.post("/analyze-event", json={"text": "Event"})
    assert response.status_code == status
    assert response.json() == {"detail": "Workflow error"}


def test_bad_categories_prevent_model_loading(loaders, monkeypatch):
    monkeypatch.setattr(
        backend, "load_workflow_categories", Mock(side_effect=RuntimeError("Invalid categories"))
    )
    with pytest.raises(RuntimeError, match="Invalid categories"):
        with TestClient(backend.app):
            pass
    loaders[0].assert_not_called()
    loaders[1].assert_not_called()


def test_gemma_generation_loader(loaders, monkeypatch):
    monkeypatch.setenv("MODEL_ID", "google/gemma-4-26B-A4B-it")
    config = backend.AutoConfig.from_pretrained.return_value
    config.model_type = "gemma4"
    processor = Mock()
    processor_loader = Mock(return_value=processor)
    model_loader = Mock(return_value=Mock())
    monkeypatch.setattr(backend.AutoProcessor, "from_pretrained", processor_loader)
    monkeypatch.setattr(backend.Gemma4ForConditionalGeneration, "from_pretrained", model_loader)
    with TestClient(backend.app):
        runtime = backend.app.state.runtime
        assert runtime.processor is processor
        assert runtime.tokenizer is processor.tokenizer
        assert runtime.model is model_loader.return_value
        processor_loader.assert_called_once_with("google/gemma-4-26B-A4B-it")
        model_loader.assert_called_once_with(
            "google/gemma-4-26B-A4B-it", config=config, dtype="auto"
        )
        runtime.model.to.assert_called_once_with("cpu")
        runtime.model.eval.assert_called_once_with()
    loaders[0].assert_not_called()
    loaders[1].assert_not_called()
    assert not hasattr(backend.app.state, "runtime")


@pytest.mark.parametrize("payload", [
    {}, {"text": None}, {"text": 1}, {"text": True},
    {"text": []}, {"text": {}}, {"text": ""}, {"text": " \n\t "},
])
def test_invalid_text(loaders, payload, monkeypatch):
    runner = Mock()
    monkeypatch.setattr(backend, "run_workflows", runner)
    with TestClient(backend.app) as client:
        assert client.post("/analyze-event", json=payload).status_code == 422
    runner.assert_not_called()


@pytest.mark.parametrize("device,available,expected", [
    ("auto", False, "cpu"), ("auto", True, "cuda"),
    ("cpu", True, "cpu"), ("cuda", True, "cuda"),
])
def test_device_selection(loaders, monkeypatch, device, available, expected):
    monkeypatch.setenv("MODEL_DEVICE", device)
    monkeypatch.setattr(backend.torch.cuda, "is_available", Mock(return_value=available))
    with TestClient(backend.app):
        assert backend.app.state.runtime.device == expected
        if expected == "cuda":
            assert loaders[1].call_args.kwargs["device_map"] == {"": "cuda:0"}
            loaders[1].return_value.to.assert_not_called()
        else:
            assert "device_map" not in loaders[1].call_args.kwargs
            loaders[1].return_value.to.assert_called_once_with("cpu")


@pytest.mark.parametrize("model_id", [None, "", "  "])
def test_missing_model_id(loaders, monkeypatch, model_id):
    if model_id is None:
        monkeypatch.delenv("MODEL_ID")
    else:
        monkeypatch.setenv("MODEL_ID", model_id)
    with pytest.raises(RuntimeError, match="MODEL_ID must"):
        with TestClient(backend.app):
            pass
    loaders[0].assert_not_called()


@pytest.mark.parametrize("device,message", [
    ("invalid", "MODEL_DEVICE must"), ("cuda", "requires an available CUDA device"),
])
def test_invalid_device(loaders, monkeypatch, device, message):
    monkeypatch.setenv("MODEL_DEVICE", device)
    with pytest.raises(RuntimeError, match=message):
        with TestClient(backend.app):
            pass
    loaders[0].assert_not_called()


@pytest.mark.parametrize("stage", ["tokenizer", "model", "to", "eval"])
def test_model_loading_failure(loaders, stage, monkeypatch, caplog):
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    failing_call = {
        "tokenizer": loaders[0], "model": loaders[1],
        "to": loaders[1].return_value.to, "eval": loaders[1].return_value.eval,
    }[stage]
    failure = OSError("loading failed")
    failing_call.side_effect = failure
    with pytest.raises(RuntimeError, match="Failed to load MODEL_ID") as error:
        with TestClient(backend.app):
            pass
    assert error.value.__cause__ is failure
    assert not hasattr(backend.app.state, "runtime")
    loading_stage = {"tokenizer": "tokenizer", "model": "weights", "to": "device_placement", "eval": "eval"}[stage]
    assert f"Loading stage={loading_stage} status=failed duration_seconds=" in caplog.text
    assert f"Loading stage={loading_stage} status=completed" not in caplog.text


def test_cleanup_after_request_error(loaders, monkeypatch):
    monkeypatch.setattr(backend, "run_workflows", Mock(side_effect=RuntimeError("workflow")))
    with pytest.raises(RuntimeError, match="workflow"):
        with TestClient(backend.app) as client:
            client.post("/analyze-event", json={"text": "Event"})
    assert not hasattr(backend.app.state, "runtime")
