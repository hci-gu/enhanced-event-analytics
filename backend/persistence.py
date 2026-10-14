"""Best-effort PocketBase persistence; database failures never stop inference."""

import logging
import os
from ipaddress import ip_address
from datetime import datetime, timezone
from threading import Lock
from typing import Any

import httpx


logger = logging.getLogger("uvicorn.error.persistence")
RECORDS_PATH = "/api/collections/Analysis/records"


class PocketBaseClient:
    def __init__(self, url: str, *, transport=None):
        address = httpx.URL(url)
        try:
            loopback = ip_address(address.host).is_loopback
        except ValueError:
            loopback = address.host == "localhost"
        if address.scheme != "http" or not loopback or address.userinfo or address.query or address.fragment or address.path not in {"", "/"}:
            raise ValueError("POCKETBASE_URL must be a loopback HTTP address without credentials or a path")
        self.http = httpx.Client(
            base_url=url, timeout=2.0, trust_env=False, transport=transport,
        )

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.http.close()

    def check_health(self) -> dict[str, bool]:
        available = False
        try:
            response = self.http.get("/api/health")
            response.raise_for_status()
            available = response.json().get("code") == 200
        except (httpx.HTTPError, ValueError, AttributeError):
            pass
        return {"pocketbase_available": available}

    def save(self, analysis_id: str, data: dict[str, Any], token: str, record_id: str | None = None) -> str | None:
        operation = "update" if record_id else "create"
        try:
            if record_id:
                response = self.http.patch(f"{RECORDS_PATH}/{record_id}", json=data, params={"fields": "id"},
                                           headers={"Authorization": token})
            else:
                response = self.http.post(RECORDS_PATH, json=data, params={"fields": "id"},
                                          headers={"Authorization": token})
            response.raise_for_status()
            saved_id = response.json()["id"]
            if not isinstance(saved_id, str) or not saved_id.isalnum() or len(saved_id) != 15:
                raise ValueError("Invalid PocketBase record ID")
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            # Do not log response bodies, exception text, tokens, or record content.
            code = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
            logger.warning(
                "PocketBase record write failed (operation=%s, analysis_id=%s, http_status=%s, error_type=%s)",
                operation, analysis_id, code, type(exc).__name__,
            )
            return None
        logger.info(
            "PocketBase record saved (operation=%s, analysis_id=%s, record_id=%s, created_by=%s, status=%s, embedding_status=%s)",
            operation, analysis_id, saved_id, data["created_by"], data["status"], data["embedding_status"],
        )
        return saved_id


def create_pocketbase_client() -> PocketBaseClient:
    return PocketBaseClient(
        os.environ.get("POCKETBASE_URL", "http://127.0.0.1:8090").strip(),
    )


class AnalysisPersistence:
    def __init__(self, client: PocketBaseClient, analysis_id: str, text: str, created_by: str, token: str):
        self.client = client
        self.analysis_id = analysis_id
        self._token = token
        self.lock = Lock()
        self.current_workflow = None
        self.terminal = False
        self.data = {
            "analysis_id": analysis_id, "original_text": text, "created_by": created_by,
            "status": "Processing", "embedding_status": "Processing",
            "title": "", "predictions": {}, "error": None, "finished_at": "",
        }
        # Do not retry an uncertain POST: it may have committed before a timeout.
        self.record_id = client.save(analysis_id, self.data, self._token)

    def _save(self):
        if self.record_id:
            self.client.save(self.analysis_id, self.data, self._token, self.record_id)

    def on_event(self, event: str, data: dict[str, Any]):
        with self.lock:
            if event == "workflow_started":
                self.current_workflow = data["id"]
            elif event == "title_completed":
                self.data["title"] = data["title"]
                self._save()
            elif event == "workflow_completed":
                self.data["predictions"][data["id"]] = data["results"]
                self._save()

    def embedding_completed(self, success: bool):
        with self.lock:
            self.data["embedding_status"] = "Complete" if success else "Failed"
            self._save()

    def finish(self, *, error: dict[str, Any] | None = None, results: dict[str, Any] | None = None):
        with self.lock:
            if self.terminal:
                return
            self.terminal = True
            if results:
                self.data["title"] = results["title"]
                for workflow_id, predictions in results["results"].items():
                    self.data["predictions"].setdefault(workflow_id, predictions)
            self.data["status"] = "Failed" if error else "Complete"
            self.data["error"] = error
            self.data["finished_at"] = datetime.now(timezone.utc).isoformat()
            self._save()
