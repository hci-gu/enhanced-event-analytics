import json
from types import SimpleNamespace

import httpx
import pytest

import app as backend
from persistence import PocketBaseClient


@pytest.fixture(autouse=True)
def serving_environment(monkeypatch):
    monkeypatch.delenv("SERVING_ENGINE", raising=False)
    monkeypatch.delenv("VLLM_GPU_MEMORY_UTILIZATION", raising=False)


@pytest.fixture
def pocketbase(monkeypatch):
    """A mock HTTP service: tests never contact a real database."""
    service = SimpleNamespace(requests=[], authorizations=[], clients=[])

    def default_handler(request):
        if request.url.path == "/api/health":
            return httpx.Response(200, json={"code": 200})
        return httpx.Response(200, json={"id": "testrecord00001"})

    service.handler = default_handler

    def dispatch(request):
        service.requests.append((request.method, request.url.path, json.loads(request.content) if request.content else None))
        service.authorizations.append(request.headers.get("Authorization"))
        return service.handler(request)

    def create():
        client = PocketBaseClient("http://127.0.0.1:8090", transport=httpx.MockTransport(dispatch))
        service.clients.append(client)
        return client

    monkeypatch.setattr(backend, "create_pocketbase_client", create)
    return service
