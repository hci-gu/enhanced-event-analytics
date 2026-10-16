import base64
import json
from uuid import UUID

import httpx
import pytest
from fastapi.testclient import TestClient

import app as backend
from persistence import PocketBaseClient


def item(index=0, **extra):
    return {
        "id": f"record{index:09d}", "analysis_id": str(UUID(f"{index:08x}-1234-4234-8234-123456789abc")),
        "title": f"Händelse {index}", "status": "Complete", "created": "2026-10-16 09:00:00.000Z",
        "finished_at": "2026-10-16 09:01:00.000Z", **extra,
    }


@pytest.fixture
def history_client(monkeypatch):
    requests = []
    state = {"items": []}

    def handler(request):
        requests.append(request)
        return httpx.Response(state.get("status", 200), json={"items": state["items"]})

    storage = PocketBaseClient("http://127.0.0.1:8090", transport=httpx.MockTransport(handler))
    monkeypatch.setattr(backend.app.state, "pocketbase", storage, raising=False)
    monkeypatch.setitem(backend.app.dependency_overrides, backend.require_user,
                        lambda: backend.UserSession("testuser0000001", "user@example.com", "user-token"))
    # No lifespan: history reads must not initialize models or contact a real service.
    client = TestClient(backend.app)
    yield client, state, requests
    client.close()
    storage.http.close()


def test_history_first_five_and_cursor_uses_owner_token_and_stable_order(history_client):
    client, state, requests = history_client
    state["items"] = [item(index) for index in range(6)]
    response = client.get("/analyses")
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    data = response.json()
    assert len(data["items"]) == 5
    cursor = data["next_cursor"]
    assert json.loads(base64.urlsafe_b64decode(cursor)) == [item(4)["created"], item(4)["id"]]
    request = requests[-1]
    assert request.headers["Authorization"] == "user-token"
    assert request.url.params["sort"] == "-created,-id"
    assert request.url.params["perPage"] == "6"
    assert request.url.params["filter"] == 'created_by = "testuser0000001" && status = "Complete"'
    assert "original_text" not in request.url.params["fields"]
    state["items"] = [item(index) for index in range(20)]
    response = client.get("/analyses", params={"limit": 20, "cursor": cursor})
    assert response.status_code == 200
    assert len(response.json()["items"]) == 20
    assert response.json()["next_cursor"] is None
    assert 'created < "2026-10-16 09:00:00.000Z"' in requests[-1].url.params["filter"]
    assert 'id < "record000000004"' in requests[-1].url.params["filter"]


@pytest.mark.parametrize("params", [
    {"limit": 0}, {"limit": 21}, {"cursor": "invalid"},
    {"cursor": base64.urlsafe_b64encode(json.dumps(['" || true', "record000000001"]).encode()).decode()},
    {"cursor": base64.urlsafe_b64encode(json.dumps(["2026-99-16 09:00:00.000Z", "record000000001"]).encode()).decode()},
    {"cursor": base64.urlsafe_b64encode(b'{}').decode()},
])
def test_invalid_pagination_never_queries_storage(history_client, params):
    client, _, requests = history_client
    response = client.get("/analyses", params=params)
    assert response.status_code == 422
    assert response.headers["Cache-Control"] == "no-store"
    assert not requests


def test_detail_restores_source_evidence_dates_and_unknown_workflows(history_client):
    client, state, requests = history_client
    record = item(original_text="Vatten stiger.", predictions={
        "risks": [{"ID": "flood", "name": "Översvämningar", "evidence": ["Vatten stiger"]}], "old": [],
    }, dates={"published_at": "2026-10-15"}, dates_error=None)
    state["items"] = [record]
    response = client.get(f'/analyses/{record["analysis_id"]}')
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    data = response.json()
    assert data["original_text"] == record["original_text"]
    assert data["predictions"] == record["predictions"]
    assert data["dates"] == record["dates"]
    assert data["workflows"] == [{"id": "risks", "label": "Riskområden"}, {"id": "old", "label": "old"}, {"id": "dates", "label": "Datum"}]
    assert 'created_by = "testuser0000001"' in requests[-1].url.params["filter"]


def test_missing_foreign_or_incomplete_analysis_is_not_found(history_client):
    client, _, _ = history_client
    response = client.get(f'/analyses/{item()["analysis_id"]}')
    assert response.status_code == 404
    assert response.headers["Cache-Control"] == "no-store"


def test_storage_errors_are_recoverable_and_do_not_expose_details(history_client):
    client, state, _ = history_client
    state["status"] = 500
    response = client.get("/analyses")
    assert response.status_code == 503
    assert response.headers["Cache-Control"] == "no-store"
    assert "user-token" not in response.text


def test_anonymous_reads_require_login(history_client, monkeypatch):
    client, _, requests = history_client
    monkeypatch.delitem(backend.app.dependency_overrides, backend.require_user)
    assert client.get("/analyses").status_code == 401
    assert client.get(f'/analyses/{item()["analysis_id"]}').status_code == 401
    assert not requests
