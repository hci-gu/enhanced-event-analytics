import json
from unittest.mock import Mock

import httpx
import pytest
from fastapi.testclient import TestClient

import app as backend
import auth
import workflows
from test_app import loaders


ORIGIN = {"Origin": "http://localhost:5173"}
CREDENTIALS = {"email": "user@example.com", "password": "password123"}


@pytest.fixture
def authentication(loaders, pocketbase, monkeypatch):
    monkeypatch.delitem(backend.app.dependency_overrides, backend.require_user)
    monkeypatch.delitem(backend.app.dependency_overrides, backend.require_origin)
    monkeypatch.delenv("AUTH_ALLOWED_ORIGINS", raising=False)
    monkeypatch.delenv("AUTH_COOKIE_SECURE", raising=False)
    default = pocketbase.handler

    def handler(request):
        if request.url.path.endswith("/auth-with-password") or request.url.path.endswith("/auth-refresh"):
            assert request.headers["Authorization"] != "test-token"
            if request.url.path.endswith("/auth-refresh"):
                if request.headers["Authorization"] not in {"user-token", "second-token"}:
                    return httpx.Response(401, json={})
            user_id = "seconduser00001" if request.headers["Authorization"] == "second-token" else "testuser0000001"
            return httpx.Response(200, json={"token": "user-token", "record": {
                "id": user_id, "email": "user@example.com", "collectionName": "users",
            }})
        if request.url.path.endswith("/users/records"):
            assert request.headers["Authorization"] == "test-token"
            return httpx.Response(200, json={"id": "testuser0000001"})
        return default(request)

    pocketbase.handler = handler
    return pocketbase


def test_login_session_logout_and_cookie_attributes(authentication):
    with TestClient(backend.app) as client:
        assert client.get("/auth/session").status_code == 401
        response = client.post("/auth/login", json=CREDENTIALS, headers=ORIGIN)
        assert response.status_code == 200
        assert response.json() == {"id": "testuser0000001", "email": "user@example.com"}
        cookie = response.headers["set-cookie"]
        assert "HttpOnly" in cookie and "SameSite=lax" in cookie and "Max-Age=604800" in cookie
        assert "Secure" not in cookie
        assert response.headers["Cache-Control"] == "no-store"
        assert client.get("/auth/session").status_code == 200
        assert client.post("/auth/logout", headers=ORIGIN).status_code == 204
        assert client.get("/auth/session").status_code == 401


def test_secure_cookie_option(authentication, monkeypatch):
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "true")
    with TestClient(backend.app) as client:
        assert "Secure" in client.post("/auth/login", json=CREDENTIALS, headers=ORIGIN).headers["set-cookie"]


def test_wrong_credentials_are_unauthorized_and_auth_errors_are_not_cached(authentication):
    default = authentication.handler

    def wrong_password(request):
        if request.url.path.endswith("/auth-with-password"):
            return httpx.Response(400, json={"message": "Private internal details"})
        return default(request)

    authentication.handler = wrong_password
    with TestClient(backend.app) as client:
        response = client.post("/auth/login", json=CREDENTIALS, headers=ORIGIN)
        assert response.status_code == 401
        assert response.headers["Cache-Control"] == "no-store"
        assert "set-cookie" not in response.headers
        assert "Private internal details" not in response.text


def test_custom_origin_and_missing_registration_service_token(authentication, monkeypatch):
    monkeypatch.setenv("AUTH_ALLOWED_ORIGINS", "https://analytics.example")
    authentication.token = ""
    with TestClient(backend.app) as client:
        assert client.post("/auth/login", json=CREDENTIALS, headers=ORIGIN).status_code == 403
        headers = {"Origin": "https://analytics.example"}
        assert client.post("/auth/login", json=CREDENTIALS, headers=headers).status_code == 200
        response = client.post("/auth/register", json={**CREDENTIALS, "password_confirm": "password123"}, headers=headers)
        assert response.status_code == 503
    assert not any(path.endswith("/users/records") for _, path, _ in authentication.requests)


def test_registration_logs_in_and_forwards_only_allowed_fields(authentication):
    with TestClient(backend.app) as client:
        response = client.post("/auth/register", json={**CREDENTIALS, "password_confirm": "password123"}, headers=ORIGIN)
        assert response.status_code == 201
        assert "token" not in response.json()
        assert client.get("/auth/session").status_code == 200
    payload = next(body for method, path, body in authentication.requests if path.endswith("/users/records"))
    assert payload == {**CREDENTIALS, "passwordConfirm": "password123"}


@pytest.mark.parametrize("payload", [
    {**CREDENTIALS, "password": "short"},
    {**CREDENTIALS, "password_confirm": "different"},
    {**CREDENTIALS, "password_confirm": "password123", "verified": True},
    {**CREDENTIALS, "email": "not-email", "password_confirm": "password123"},
])
def test_registration_validation_never_echoes_passwords(authentication, payload):
    with TestClient(backend.app) as client:
        response = client.post("/auth/register", json=payload, headers=ORIGIN)
        assert response.status_code == 422
        assert "password123" not in response.text and '"input"' not in response.text
    assert not any(path.endswith("/users/records") for _, path, _ in authentication.requests)


def test_duplicate_email_and_account_created_login_failure(authentication):
    default = authentication.handler

    def duplicate(request):
        if request.url.path.endswith("/users/records"):
            return httpx.Response(400, json={"data": {"email": {"code": "validation_not_unique"}}})
        return default(request)

    with TestClient(backend.app) as client:
        authentication.handler = duplicate
        data = {**CREDENTIALS, "password_confirm": "password123"}
        assert client.post("/auth/register", json=data, headers=ORIGIN).status_code == 409

        def login_failure(request):
            if request.url.path.endswith("/auth-with-password"):
                return httpx.Response(500, json={})
            return default(request)

        authentication.handler = login_failure
        response = client.post("/auth/register", json=data, headers=ORIGIN)
        assert response.status_code == 503
        assert response.json()["detail"]["account_created"] is True
        assert "set-cookie" not in response.headers


@pytest.mark.parametrize("endpoint", ["/auth/login", "/auth/register", "/auth/logout", "/analyze-event", "/analyze-event/stream", "/embed-event"])
@pytest.mark.parametrize("origin", [None, "http://untrusted.example"])
def test_origin_protection(authentication, endpoint, origin):
    with TestClient(backend.app) as client:
        client.cookies.set(auth.COOKIE_NAME, "user-token")
        headers = {} if origin is None else {"Origin": origin}
        body = {**CREDENTIALS, "password_confirm": "password123"} if endpoint == "/auth/register" else CREDENTIALS if endpoint == "/auth/login" else {"text": "Event"}
        assert client.post(endpoint, json=body, headers=headers).status_code == 403
        backend.embed_document.assert_not_called()


@pytest.mark.parametrize("endpoint", ["/analyze-event", "/analyze-event/stream", "/embed-event"])
@pytest.mark.parametrize("token", [None, "expired"])
def test_invalid_sessions_rejected_before_inference(authentication, endpoint, token):
    with TestClient(backend.app) as client:
        if token:
            client.cookies.set(auth.COOKIE_NAME, token)
        assert client.post(endpoint, json={"text": "Event"}, headers=ORIGIN).status_code == 401
        backend.embed_document.assert_not_called()
    assert not any(path.endswith("/Analysis/records") for _, path, _ in authentication.requests)


def test_pocketbase_unavailable_blocks_auth_but_not_startup_health_or_logout(authentication):
    def offline(request):
        raise httpx.ConnectError("offline", request=request)

    authentication.handler = offline
    with TestClient(backend.app) as client:
        assert client.get("/health").status_code == 200
        client.cookies.set(auth.COOKIE_NAME, "user-token")
        assert client.get("/auth/session").status_code == 503
        assert client.post("/analyze-event", json={"text": "Event"}, headers=ORIGIN).status_code == 503
        assert client.post("/auth/login", json=CREDENTIALS, headers=ORIGIN).status_code == 503
        assert client.post("/auth/logout", headers=ORIGIN).status_code == 204
        backend.embed_document.assert_not_called()


@pytest.mark.parametrize("endpoint", ["/analyze-event", "/analyze-event/stream"])
def test_creator_comes_from_verified_user_and_remains_on_updates(authentication, monkeypatch, endpoint):
    monkeypatch.setattr(workflows, "generate_text", Mock(side_effect=(["Title"] + ["[]"] * 5) * 2))
    with TestClient(backend.app) as client:
        for token in ("user-token", "second-token"):
            client.cookies.set(auth.COOKIE_NAME, token)
            assert client.post(endpoint, json={"text": "Event", "created_by": "forgeduser00001"}, headers=ORIGIN).status_code == 200
    saved = [body for method, path, body in authentication.requests if "/Analysis/records" in path]
    ids = {body["analysis_id"] for body in saved}
    assert len(ids) == 2
    assert {body["created_by"] for body in saved} == {"testuser0000001", "seconduser00001"}
    for analysis_id in ids:
        assert len({body["created_by"] for body in saved if body["analysis_id"] == analysis_id}) == 1


def test_user_session_cannot_be_superuser(authentication):
    default = authentication.handler

    def wrong_collection(request):
        if request.url.path.endswith("/auth-refresh"):
            return httpx.Response(200, json={"token": "super-token", "record": {
                "id": "testuser0000001", "email": "admin@example.com", "collectionName": "_superusers",
            }})
        return default(request)

    authentication.handler = wrong_collection
    with TestClient(backend.app) as client:
        client.cookies.set(auth.COOKIE_NAME, "user-token")
        assert client.get("/auth/session").status_code == 503
