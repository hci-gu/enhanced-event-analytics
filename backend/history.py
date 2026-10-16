"""Read completed analyses using the signed-in user's PocketBase permissions."""

import base64
import binascii
import json
import re
from datetime import datetime
from typing import Annotated, Any, Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field, UUID4, ValidationError

from auth import UserSession, require_user
from persistence import RECORDS_PATH
from workflows import WORKFLOWS


router = APIRouter(prefix="/analyses", tags=["History"])
TIMESTAMP = r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}Z$"


class HistoryItem(BaseModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9]{15}$")
    analysis_id: UUID4
    title: str
    status: Literal["Complete"]
    created: str = Field(pattern=TIMESTAMP)
    finished_at: str = ""


class HistoryPage(BaseModel):
    items: list[HistoryItem]
    next_cursor: str | None


class SavedAnalysis(HistoryItem):
    original_text: str
    predictions: dict[str, Any]
    dates: dict[str, Any] | None = None
    dates_error: dict[str, Any] | None = None
    workflows: list[dict[str, str]] = Field(default_factory=list)


def read_records(request: Request, user: UserSession, params: dict) -> list[dict]:
    try:
        response = request.app.state.pocketbase.http.get(
            RECORDS_PATH, params=params, headers={"Authorization": user.token},
        )
        response.raise_for_status()
        items = response.json()["items"]
        if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
            raise ValueError("Invalid records")
        return items
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        raise HTTPException(503, "Historiken är inte tillgänglig. Försök igen.") from None


def cursor_filter(cursor: str) -> str:
    try:
        created, record_id = json.loads(base64.b64decode(cursor, altchars=b"-_", validate=True))
        if not isinstance(created, str) or not re.fullmatch(TIMESTAMP, created):
            raise ValueError("Invalid timestamp")
        datetime.fromisoformat(created.replace("Z", "+00:00"))
        if not isinstance(record_id, str) or not re.fullmatch(r"[a-zA-Z0-9]{15}", record_id):
            raise ValueError("Invalid ID")
    except (ValueError, TypeError, binascii.Error):
        raise HTTPException(422, "Ogiltig historikmarkör.") from None
    return f' && (created < "{created}" || (created = "{created}" && id < "{record_id}"))'


@router.get("", response_model=HistoryPage)
def list_analyses(request: Request, response: Response, user: UserSession = Depends(require_user),
                  limit: Annotated[int, Query(ge=1, le=20)] = 5,
                  cursor: Annotated[str | None, Query(max_length=256)] = None):
    response.headers["Cache-Control"] = "no-store"
    condition = f'created_by = "{user.id}" && status = "Complete"'
    if cursor is not None:
        condition += cursor_filter(cursor)
    records = read_records(request, user, {
        "filter": condition, "sort": "-created,-id", "perPage": limit + 1, "skipTotal": "true",
        "fields": "id,analysis_id,title,status,created,finished_at",
    })
    try:
        items = [HistoryItem.model_validate(record) for record in records[:limit]]
    except ValidationError:
        raise HTTPException(503, "Historiken innehåller ett ogiltigt resultat.") from None
    next_cursor = None
    if len(records) > limit and items:
        last = items[-1]
        next_cursor = base64.urlsafe_b64encode(json.dumps([last.created, last.id]).encode()).decode()
    return HistoryPage(items=items, next_cursor=next_cursor)


@router.get("/{analysis_id}", response_model=SavedAnalysis)
def get_analysis(analysis_id: UUID4, request: Request, response: Response,
                 user: UserSession = Depends(require_user)):
    response.headers["Cache-Control"] = "no-store"
    records = read_records(request, user, {
        "filter": f'created_by = "{user.id}" && status = "Complete" && analysis_id = "{analysis_id}"',
        "perPage": 1, "skipTotal": "true",
        "fields": "id,analysis_id,title,status,created,finished_at,original_text,predictions,dates,dates_error",
    })
    if not records:
        raise HTTPException(404, "Analysen kunde inte hittas.")
    try:
        result = SavedAnalysis.model_validate(records[0])
    except ValidationError:
        raise HTTPException(503, "Den sparade analysen är ogiltig.") from None
    # Keep old workflow IDs even if the current registry has changed.
    result.workflows = [
        {"id": name, "label": (WORKFLOWS[name].label or name) if name in WORKFLOWS else name}
        for name in result.predictions
    ] + [{"id": "dates", "label": "Datum"}]
    return result
