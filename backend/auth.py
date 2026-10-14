"""Cookie authentication backed by PocketBase's users collection."""

import os
from dataclasses import dataclass, field

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, EmailStr, Field


router = APIRouter(prefix="/auth", tags=["Authentication"])
COOKIE_NAME = "event_analytics_session"
SESSION_SECONDS = 7 * 24 * 60 * 60
DEFAULT_ORIGINS = ",".join(
    f"http://{host}:{port}" for host in ("localhost", "127.0.0.1") for port in (5173, 4173, 8000)
)


def require_origin(request: Request) -> None:
    allowed = {value.strip().rstrip("/") for value in os.environ.get("AUTH_ALLOWED_ORIGINS", DEFAULT_ORIGINS).split(",") if value.strip()}
    if request.headers.get("origin") not in allowed:
        raise HTTPException(403, "Begäran kommer från en otillåten webbplats.")


@dataclass(frozen=True)
class UserSession:
    id: str
    email: str
    token: str = field(repr=False)

    def public(self) -> dict[str, str]:
        return {"id": self.id, "email": self.email}


def authenticate(request: Request, action: str, *, token: str = "", payload=None) -> UserSession:
    try:
        response = request.app.state.pocketbase.http.post(
            f"/api/collections/users/{action}", json=payload,
            headers={"Authorization": token},
        )
        if response.status_code in {400, 401, 403}:
            raise HTTPException(401, "E-postadressen eller lösenordet är felaktigt." if action == "auth-with-password" else "Din session har gått ut. Logga in igen.")
        response.raise_for_status()
        data = response.json()
        record = data["record"]
        user_id, email, user_token = record["id"], record["email"], data["token"]
        if (record["collectionName"] != "users" or not isinstance(user_id, str)
                or not user_id.isascii() or not user_id.isalnum() or len(user_id) != 15
                or not isinstance(email, str) or not email
                or not isinstance(user_token, str) or not user_token or any(c.isspace() for c in user_token)):
            raise ValueError("Invalid authentication response")
        return UserSession(user_id, email, user_token)
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        raise HTTPException(503, "Inloggningstjänsten är inte tillgänglig. Försök igen.") from None


def require_user(request: Request) -> UserSession:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(401, "Logga in för att fortsätta.")
    return authenticate(request, "auth-refresh", token=token)


def cookie_secure() -> bool:
    return os.environ.get("AUTH_COOKIE_SECURE", "false").strip().lower() == "true"


def set_session(response: Response, session: UserSession) -> None:
    response.set_cookie(COOKIE_NAME, session.token, max_age=SESSION_SECONDS, httponly=True,
                        secure=cookie_secure(), samesite="lax", path="/")
    response.headers["Cache-Control"] = "no-store"


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    password: str = Field(strict=True, min_length=1, max_length=1024)


class RegisterRequest(LoginRequest):
    password: str = Field(strict=True, min_length=8, max_length=1024)
    password_confirm: str = Field(strict=True, min_length=8, max_length=1024)


@router.post("/login", dependencies=[Depends(require_origin)])
def login(payload: LoginRequest, request: Request, response: Response):
    session = authenticate(request, "auth-with-password", payload={"identity": str(payload.email), "password": payload.password})
    set_session(response, session)
    return session.public()


@router.post("/register", dependencies=[Depends(require_origin)], status_code=201)
def register(payload: RegisterRequest, request: Request, response: Response):
    if payload.password != payload.password_confirm:
        raise HTTPException(422, "Lösenorden stämmer inte överens.")
    client = request.app.state.pocketbase
    if not client.has_token:
        raise HTTPException(503, "Registrering är inte tillgänglig just nu.")
    try:
        result = client.http.post("/api/collections/users/records", json={
            "email": str(payload.email), "password": payload.password, "passwordConfirm": payload.password_confirm,
        }, params={"fields": "id"})
        if result.status_code == 400:
            details = result.json().get("data", {})
            if details.get("email", {}).get("code") == "validation_not_unique":
                raise HTTPException(409, "E-postadressen används redan. Logga in istället.")
            raise HTTPException(422, "Kontot kunde inte skapas. Kontrollera e-postadress och lösenord.")
        result.raise_for_status()
    except (httpx.HTTPError, ValueError, AttributeError, TypeError):
        raise HTTPException(503, "Registrering är inte tillgänglig just nu. Försök igen.") from None
    try:
        session = authenticate(request, "auth-with-password", payload={"identity": str(payload.email), "password": payload.password})
    except HTTPException:
        raise HTTPException(503, {"message": "Kontot har skapats. Logga in för att fortsätta.", "account_created": True}) from None
    set_session(response, session)
    return session.public()


@router.get("/session")
def session(response: Response, user: UserSession = Depends(require_user)):
    set_session(response, user)
    return user.public()


@router.post("/logout", dependencies=[Depends(require_origin)], status_code=204)
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME, path="/", httponly=True, secure=cookie_secure(), samesite="lax")
    response.headers["Cache-Control"] = "no-store"
