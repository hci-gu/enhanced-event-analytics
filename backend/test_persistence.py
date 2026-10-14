import logging
import asyncio
from concurrent.futures import Future
from unittest.mock import Mock

import httpx
import pytest
from fastapi.testclient import TestClient

import app as backend
import workflows
from persistence import AnalysisPersistence, PocketBaseClient, create_pocketbase_client
from test_app import EMBEDDING, loaders


def writes(service):
    return [(method, body) for method, _, body in service.requests if method in {"POST", "PATCH"}]


@pytest.mark.parametrize("endpoint", ["/analyze-event", "/analyze-event/stream"])
def test_incremental_persistence_and_info_logs(loaders, pocketbase, monkeypatch, caplog, endpoint):
    monkeypatch.setattr(workflows, "generate_text", Mock(side_effect=[
        "Testhändelse", '[{"ID":"översvämningar","evidence":["Event"]}]', "[]", "[]", "[]", "[]",
    ]))
    with caplog.at_level(logging.INFO, logger="uvicorn.error.persistence"):
        with TestClient(backend.app) as client:
            response = client.post(endpoint, json={"text": "  Event\ntext  "})
            assert response.status_code == 200
    saved = writes(pocketbase)
    assert saved[0][0] == "POST"
    assert saved[0][1]["analysis_id"] == response.headers["X-Analysis-ID"]
    assert saved[0][1]["original_text"] == "Event\ntext"
    assert saved[0][1]["status"] == saved[0][1]["embedding_status"] == "Processing"
    assert saved[0][1]["finished_at"] == ""
    assert all(method == "PATCH" for method, _ in saved[1:])
    final = saved[-1][1]
    assert final["status"] == final["embedding_status"] == "Complete"
    assert final["finished_at"]
    assert final["title"] == "Testhändelse"
    assert set(final["predictions"]) == set(workflows.WORKFLOWS)
    assert final["predictions"]["risks"][0]["evidence"] == ["Event"]
    assert any(set(body["predictions"]) == {"risks"} for _, body in saved)
    assert "vector" not in str(final)
    logs = [record for record in caplog.records if record.name == "uvicorn.error.persistence"]
    assert len(logs) == len(saved)
    assert all(record.levelno == logging.INFO for record in logs)
    assert all("Event" not in record.getMessage() and "test-token" not in record.getMessage() for record in logs)
    assert pocketbase.clients[0].http.is_closed
    assert not hasattr(backend.app.state, "pocketbase")


@pytest.mark.parametrize("endpoint", ["/analyze-event", "/analyze-event/stream"])
def test_failed_workflow_keeps_partial_predictions(loaders, pocketbase, monkeypatch, endpoint):
    monkeypatch.setattr(workflows, "generate_text", Mock(side_effect=[
        "Testhändelse", "[]", workflows.WorkflowError(502, "Inference failed"),
    ]))
    with TestClient(backend.app) as client:
        response = client.post(endpoint, json={"text": "Event"})
        assert response.status_code == (502 if endpoint == "/analyze-event" else 200)
    final = writes(pocketbase)[-1][1]
    assert final["status"] == "Failed"
    assert final["finished_at"]
    assert final["predictions"] == {"risks": []}
    assert final["error"]["workflow_id"] == "reach"
    assert final["error"]["code"] == 502


@pytest.mark.parametrize("endpoint", ["/analyze-event", "/analyze-event/stream"])
def test_embedding_failure_does_not_fail_analysis(loaders, pocketbase, monkeypatch, endpoint):
    monkeypatch.setattr(workflows, "generate_text", Mock(side_effect=["Testhändelse"] + ["[]"] * 5))
    monkeypatch.setattr(backend, "embed_document", Mock(side_effect=RuntimeError("Failed embedding")))
    with TestClient(backend.app) as client:
        assert client.post(endpoint, json={"text": "Event"}).status_code == 200
    final = writes(pocketbase)[-1][1]
    assert final["status"] == "Complete"
    assert final["embedding_status"] == "Failed"
    assert final["error"] is None


def test_database_outage_and_recovery_do_not_require_restart(loaders, pocketbase, monkeypatch):
    healthy_handler = pocketbase.handler

    def unavailable(request):
        raise httpx.ConnectError("Connection refused", request=request)

    pocketbase.handler = unavailable
    monkeypatch.setattr(workflows, "generate_text", Mock(side_effect=["Testhändelse"] + ["[]"] * 5))
    with TestClient(backend.app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"
        assert health.json()["pocketbase_available"] is False
        assert health.json()["pocketbase_persistence_ready"] is False
        pocketbase.handler = healthy_handler
        assert client.get("/health").json()["pocketbase_persistence_ready"] is True
        assert client.post("/analyze-event", json={"text": "Event"}).status_code == 200
    assert writes(pocketbase)[-1][1]["status"] == "Complete"


@pytest.mark.parametrize("failure", ["offline", "timeout", "unauthorized", "malformed"])
def test_create_failure_does_not_abort_or_retry_analysis(loaders, pocketbase, monkeypatch, failure):
    healthy_handler = pocketbase.handler

    def handler(request):
        if request.method == "POST":
            if failure == "offline":
                raise httpx.ConnectError("refused", request=request)
            if failure == "timeout":
                raise httpx.ReadTimeout("timeout", request=request)
            return httpx.Response(403, json={}) if failure == "unauthorized" else httpx.Response(200, json={})
        return healthy_handler(request)

    pocketbase.handler = handler
    monkeypatch.setattr(workflows, "generate_text", Mock(side_effect=["Testhändelse"] + ["[]"] * 5))
    with TestClient(backend.app) as client:
        assert client.post("/analyze-event", json={"text": "Event"}).status_code == 200
    assert len(writes(pocketbase)) == 1


def test_failed_update_is_recovered_by_next_snapshot(loaders, pocketbase, monkeypatch):
    healthy_handler = pocketbase.handler
    failed = False

    def handler(request):
        nonlocal failed
        if request.method == "PATCH" and not failed:
            failed = True
            return httpx.Response(500, json={})
        return healthy_handler(request)

    pocketbase.handler = handler
    monkeypatch.setattr(workflows, "generate_text", Mock(side_effect=["Testhändelse"] + ["[]"] * 5))
    with TestClient(backend.app) as client:
        assert client.post("/analyze-event", json={"text": "Event"}).status_code == 200
    assert failed
    assert writes(pocketbase)[-1][1]["status"] == "Complete"
    assert len(writes(pocketbase)[-1][1]["predictions"]) == 5


def test_missing_token_disables_writes_but_not_health_or_inference(loaders, pocketbase, monkeypatch):
    pocketbase.token = ""
    monkeypatch.setattr(workflows, "generate_text", Mock(side_effect=["Testhändelse"] + ["[]"] * 5))
    with TestClient(backend.app) as client:
        health = client.get("/health").json()
        assert health["pocketbase_available"] is True
        assert health["pocketbase_persistence_ready"] is False
        assert client.post("/analyze-event", json={"text": "Event"}).status_code == 200
    assert not writes(pocketbase)


def test_default_connection_configuration(monkeypatch):
    monkeypatch.delenv("POCKETBASE_URL", raising=False)
    monkeypatch.delenv("POCKETBASE_TOKEN", raising=False)
    with create_pocketbase_client() as client:
        assert str(client.http.base_url) == "http://127.0.0.1:8090"
        assert client.http.timeout.read == 2.0
        assert not client.has_token


def test_authenticated_requests_and_health_response_validation():
    def handler(request):
        assert request.headers["Authorization"] == "test-token"
        return httpx.Response(200, json=[])

    with PocketBaseClient("http://127.0.0.1:8090", "test-token", transport=httpx.MockTransport(handler)) as client:
        assert client.check_health() == {"pocketbase_available": False, "pocketbase_persistence_ready": False}


def test_late_embedding_update_preserves_category_finish_time(pocketbase):
    with backend.create_pocketbase_client() as client:
        persistence = AnalysisPersistence(client, "01234567-89ab-4cde-8fab-0123456789ab", "Event", "testuser0000001")
        future = Future()
        backend.track_embedding(future, persistence)
        persistence.finish(results={"title": "Title", "results": {"risks": []}})
        terminal = writes(pocketbase)[-1][1]
        assert terminal["status"] == "Complete"
        assert terminal["embedding_status"] == "Processing"
        future.set_result(EMBEDDING)
        persistence.finish(error={"code": 499, "message": "Interrupted", "workflow_id": None})
        final = writes(pocketbase)[-1][1]
        assert final["status"] == final["embedding_status"] == "Complete"
        assert final["finished_at"] == terminal["finished_at"]
        assert final["error"] is None


def test_stream_disconnect_before_first_event_marks_failure(pocketbase, monkeypatch):
    async def disconnect(*args):
        raise asyncio.CancelledError()

    monkeypatch.setattr(backend.StreamingResponse, "__call__", disconnect)
    with backend.create_pocketbase_client() as client:
        persistence = AnalysisPersistence(client, "01234567-89ab-4cde-8fab-0123456789ab", "Event", "testuser0000001")
        future = Future()
        backend.track_embedding(future, persistence)
        response = backend.EmbeddingStreamingResponse(iter(()), embedding_future=future, persistence=persistence)
        with pytest.raises(asyncio.CancelledError):
            asyncio.run(response({}, None, None))
        assert future.cancelled()
    final = writes(pocketbase)[-1][1]
    assert final["status"] == final["embedding_status"] == "Failed"
    assert final["error"]["code"] == 499
    assert final["finished_at"]


def test_model_startup_failure_closes_database_client(loaders, pocketbase, monkeypatch):
    monkeypatch.setattr(backend, "load_runtime", Mock(side_effect=RuntimeError("Model unavailable")))
    with pytest.raises(RuntimeError, match="Model unavailable"):
        with TestClient(backend.app):
            pass
    assert pocketbase.clients[0].http.is_closed
    assert not hasattr(backend.app.state, "pocketbase")
