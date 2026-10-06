from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

import app as backend


@pytest.fixture
def loaders(monkeypatch):
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


def test_requests_share_runtime_and_cleanup(loaders, monkeypatch):
    runner = Mock(return_value={})
    monkeypatch.setattr(backend, "run_workflows", runner)
    with TestClient(backend.app) as client:
        runtime = backend.app.state.runtime
        for _ in range(2):
            response = client.post("/analyze-event", json={"text": "  Swedish event  "})
            assert response.status_code == 200
            assert response.json() == {"status": "not_implemented", "results": {}}
        assert runner.call_count == 2
        runner.assert_called_with("Swedish event", runtime)
        loaders[0].assert_called_once_with("test/model")
        loaders[1].assert_called_once_with("test/model")
        assert runtime.tokenizer is loaders[0].return_value
        assert runtime.model is loaders[1].return_value
        runtime.model.to.assert_called_once_with("cpu")
        runtime.model.eval.assert_called_once_with()
    assert not hasattr(backend.app.state, "runtime")


def test_scaffold_response(loaders):
    with TestClient(backend.app) as client:
        response = client.post("/analyze-event", json={"text": "Event"})
    assert response.status_code == 200
    assert response.json() == {"status": "not_implemented", "results": {}}


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
        loaders[1].return_value.to.assert_called_once_with(expected)


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
def test_model_loading_failure(loaders, stage):
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


def test_cleanup_after_request_error(loaders, monkeypatch):
    monkeypatch.setattr(backend, "run_workflows", Mock(side_effect=RuntimeError("workflow")))
    with pytest.raises(RuntimeError, match="workflow"):
        with TestClient(backend.app) as client:
            client.post("/analyze-event", json={"text": "Event"})
    assert not hasattr(backend.app.state, "runtime")
