"""Real local vector storage with mocked inference and temporary databases."""

import logging
from concurrent.futures import Future, ThreadPoolExecutor
from threading import Event
from unittest.mock import Mock
from uuid import uuid4

import lancedb
import pyarrow as pa
import pytest
from fastapi.testclient import TestClient

import app as backend
import vector_storage as vectors
import workflows
from persistence import AnalysisPersistence
from test_app import EMBEDDING, loaders


OWNER = "testuser0000001"
OTHER_OWNER = "testuser0000002"
VECTOR = EMBEDDING["vector"]


@pytest.fixture
def store(tmp_path):
    storage = vectors.VectorStorage(tmp_path / "vectors")
    yield storage
    storage.close()


@pytest.mark.parametrize("value", [None, "", "  ", "./data/vectordb/"])
def test_default_path_is_root_relative(monkeypatch, tmp_path, value):
    monkeypatch.chdir(tmp_path)
    if value is None:
        monkeypatch.delenv("LANCEDB_STORAGE_PATH")
    else:
        monkeypatch.setenv("LANCEDB_STORAGE_PATH", value)
    assert vectors.storage_path() == vectors.REPOSITORY_ROOT / "data" / "vectordb"


def test_relative_and_absolute_paths(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LANCEDB_STORAGE_PATH", "custom/vectors")
    assert vectors.storage_path() == vectors.REPOSITORY_ROOT / "custom" / "vectors"
    monkeypatch.setenv("LANCEDB_STORAGE_PATH", str(tmp_path / "absolute"))
    assert vectors.storage_path() == tmp_path / "absolute"


@pytest.mark.parametrize("value", ["s3://bucket/vectors", "db://host/db", "https://host/db", "file:///tmp/db",
                                      "//server/share", "\\\\server\\share"])
def test_remote_paths_rejected(monkeypatch, value):
    monkeypatch.setenv("LANCEDB_STORAGE_PATH", value)
    with pytest.raises(ValueError, match="LANCEDB_STORAGE_PATH"):
        vectors.storage_path()


def test_schema_upsert_restart_and_owner_protection(tmp_path):
    path = tmp_path / "nested" / "db"
    analysis_id = str(uuid4())
    store = vectors.VectorStorage(path)
    assert store.table.schema.equals(vectors.SCHEMA)
    assert len(store.table.schema) == 3
    assert all(not field.nullable for field in store.table.schema)
    store.upsert(VECTOR, OWNER, analysis_id)
    replacement = [0.0, 1.0] + [0.0] * 766
    store.upsert(replacement, OWNER, analysis_id)
    with pytest.raises(ValueError, match="owner"):
        store.upsert(VECTOR, OTHER_OWNER, analysis_id)
    assert store.table.count_rows() == 1
    store.close()
    store.close()
    with pytest.raises(RuntimeError, match="closed"):
        store.search_owned(VECTOR, OWNER, 1)
    reopened = vectors.VectorStorage(path)
    try:
        row = reopened.table.to_arrow().to_pylist()[0]
        assert row == {"vector": replacement, "created_by": OWNER, "analysis_id": analysis_id}
    finally:
        reopened.close()


def test_incompatible_schema_is_not_overwritten(tmp_path):
    db = lancedb.connect(str(tmp_path))
    table = db.create_table(vectors.TABLE_NAME, data=[{"original": "keep"}],
                            schema=pa.schema([pa.field("original", pa.string())]))
    with pytest.raises(RuntimeError, match="schema"):
        vectors.VectorStorage(tmp_path)
    assert table.to_arrow().to_pylist() == [{"original": "keep"}]


@pytest.mark.parametrize("vector", [[], VECTOR[:-1], VECTOR + [0.0], [float("nan")] + VECTOR[1:],
                                    [float("inf")] + VECTOR[1:], [1e100] + VECTOR[1:],
                                    [True] + VECTOR[1:], [0.0] * 768])
def test_invalid_vectors_are_not_written(store, vector):
    with pytest.raises(ValueError):
        store.upsert(vector, OWNER, str(uuid4()))
    assert store.table.count_rows() == 0


@pytest.mark.parametrize("owner", ["", "x' OR true", "a" * 16, "ä" * 15, None])
def test_invalid_owner_rejected_by_writes_and_search(store, owner):
    with pytest.raises(ValueError):
        store.upsert(VECTOR, owner, str(uuid4()))
    with pytest.raises(ValueError):
        store.search_owned(VECTOR, owner, 1)


def test_search_prefilters_owner_and_returns_only_ids_and_distances(store):
    own_id, other_id = str(uuid4()), str(uuid4())
    store.upsert([0.0, 1.0] + [0.0] * 766, OWNER, own_id)
    store.upsert(VECTOR, OTHER_OWNER, other_id)
    assert store.search_owned(VECTOR, OWNER, 1) == [{"analysis_id": own_id, "distance": pytest.approx(1.0)}]
    assert store.search_owned(VECTOR, OTHER_OWNER, 1) == [{"analysis_id": other_id, "distance": pytest.approx(0.0)}]
    assert store.search_owned(VECTOR, "testuser0000003", 1) == []


@pytest.mark.parametrize("limit", [0, -1, True, 1.5])
def test_invalid_search_limit(store, limit):
    with pytest.raises(ValueError):
        store.search_owned(VECTOR, OWNER, limit)


def test_concurrent_upserts_do_not_duplicate(store):
    analysis_id = str(uuid4())
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(store.upsert, VECTOR, OWNER, analysis_id) for _ in range(8)]
        for future in futures:
            future.result()
    assert store.table.count_rows() == 1


@pytest.mark.parametrize("endpoint", ["/analyze-event", "/analyze-event/stream"])
@pytest.mark.parametrize("failed_workflow", [False, True])
def test_analysis_saves_authenticated_embedding(loaders, monkeypatch, endpoint, failed_workflow):
    outputs = ["Title", workflows.WorkflowError(502, "Mock failure")] if failed_workflow else ["Title"] + ["[]"] * 5
    monkeypatch.setattr(workflows, "generate_text", Mock(side_effect=outputs))
    with TestClient(backend.app) as client:
        # Complete inference immediately so workflow failure cannot cancel it.
        ready = Future()
        ready.set_result(EMBEDDING)
        monkeypatch.setattr(backend, "submit_embedding", Mock(return_value=ready))
        response = client.post(endpoint, json={"text": "Event"})
        assert response.status_code == (502 if failed_workflow and endpoint == "/analyze-event" else 200)
        rows = backend.app.state.vector_storage.search_owned(VECTOR, OWNER, 10)
        assert rows == [{"analysis_id": response.headers["X-Analysis-ID"], "distance": pytest.approx(0.0)}]


@pytest.mark.parametrize("endpoint", ["/analyze-event", "/analyze-event/stream"])
def test_write_failure_does_not_change_results_or_generation_status(loaders, monkeypatch, pocketbase, caplog, endpoint):
    monkeypatch.setattr(workflows, "generate_text", Mock(side_effect=["Title"] + ["[]"] * 5))
    with caplog.at_level(logging.INFO, logger=vectors.logger.name):
        with TestClient(backend.app) as client:
            storage = backend.app.state.vector_storage
            monkeypatch.setattr(storage, "upsert", Mock(side_effect=OSError("private data must not be logged")))
            assert client.post(endpoint, json={"text": "Private input"}).status_code == 200
    writes = [body for method, _, body in pocketbase.requests if method in {"POST", "PATCH"}]
    assert writes[-1]["embedding_status"] == "Complete"
    messages = [record.getMessage() for record in caplog.records if record.name == vectors.logger.name]
    assert any("write failed" in message for message in messages)
    assert not any("Private input" in message or "private data" in message or "user-token" in message for message in messages)


def test_pocketbase_create_failure_skips_vector(loaders, monkeypatch, pocketbase, caplog):
    import httpx
    pocketbase.handler = lambda request: httpx.Response(503)
    monkeypatch.setattr(workflows, "generate_text", Mock(side_effect=["Title"] + ["[]"] * 5))
    with TestClient(backend.app) as client:
        assert client.post("/analyze-event", json={"text": "Event"}).status_code == 200
        storage = backend.app.state.vector_storage
    assert storage.table is None
    reopened = vectors.create_vector_storage()
    try:
        assert reopened.table.count_rows() == 0
    finally:
        reopened.close()
    assert "reason=pocketbase_create_failed" in caplog.text


def test_cancelled_and_invalid_embeddings_do_not_write(store):
    persistence = Mock()
    cancelled, invalid, failed = Future(), Future(), Future()
    for future in (cancelled, invalid, failed):
        backend.track_embedding(future, persistence, store)
    cancelled.cancel()
    invalid.set_result({**EMBEDDING, "vector": [0.0]})
    failed.set_exception(RuntimeError("Mock embedding failure"))
    assert store.table.count_rows() == 0
    assert persistence.embedding_completed.call_count == 3
    persistence.embedding_completed.assert_called_with(False)


@pytest.mark.parametrize("analysis_id", ["invalid", "01234567-89ab-1cde-8fab-0123456789ab", "' OR true"])
def test_invalid_analysis_id_rejected(store, analysis_id):
    with pytest.raises(ValueError):
        store.upsert(VECTOR, OWNER, analysis_id)
    assert store.table.count_rows() == 0


@pytest.mark.parametrize("use_environment", [False, True])
def test_dotenv_path_and_environment_precedence(loaders, monkeypatch, tmp_path, use_environment):
    from dotenv import load_dotenv

    configured = tmp_path / "from-dotenv"
    environment = tmp_path / "from-environment"
    dotenv_file = tmp_path / "config.env"
    dotenv_file.write_text(f'LANCEDB_STORAGE_PATH="{configured.as_posix()}"\n', encoding="utf-8")
    if use_environment:
        monkeypatch.setenv("LANCEDB_STORAGE_PATH", str(environment))
    else:
        monkeypatch.delenv("LANCEDB_STORAGE_PATH")
    monkeypatch.setattr(backend, "load_dotenv", lambda **kwargs: load_dotenv(dotenv_file, override=kwargs["override"]))
    with TestClient(backend.app):
        assert vectors.storage_path() == (environment if use_environment else configured)
        assert (vectors.storage_path() / f"{vectors.TABLE_NAME}.lance").is_dir()


def test_embed_only_does_not_save(loaders):
    with TestClient(backend.app) as client:
        assert client.post("/embed-event", json={"text": "Event"}).status_code == 200
        assert backend.app.state.vector_storage.table.count_rows() == 0


def test_startup_storage_failure_prevents_model_loading(loaders, monkeypatch):
    monkeypatch.setattr(backend, "create_vector_storage", Mock(side_effect=RuntimeError("Storage failed")))
    with pytest.raises(RuntimeError, match="Storage failed"):
        with TestClient(backend.app):
            pass
    loaders[0].assert_not_called()
    assert not hasattr(backend.app.state, "vector_storage")
    assert not hasattr(backend.app.state, "pocketbase")


def test_model_startup_failure_closes_storage(loaders, monkeypatch):
    storage = vectors.create_vector_storage()
    monkeypatch.setattr(backend, "create_vector_storage", Mock(return_value=storage))
    monkeypatch.setattr(backend, "load_runtime", Mock(side_effect=RuntimeError("Model failed")))
    with pytest.raises(RuntimeError, match="Model failed"):
        with TestClient(backend.app):
            pass
    assert storage.table is storage.connection is None
    assert not hasattr(backend.app.state, "vector_storage")


def test_shutdown_waits_for_running_embedding_callback(loaders, monkeypatch):
    started, release, written = Event(), Event(), Event()
    with TestClient(backend.app):
        storage = backend.app.state.vector_storage
        persistence = AnalysisPersistence(backend.app.state.pocketbase, str(uuid4()), "Event", OWNER, "user-token")

        def infer():
            started.set()
            assert release.wait(10)
            return EMBEDDING

        original_upsert = storage.upsert

        def save(*args):
            original_upsert(*args)
            written.set()

        monkeypatch.setattr(storage, "upsert", save)
        future = backend.app.state.embedding_executor.submit(infer)
        backend.track_embedding(future, persistence, storage)
        assert started.wait(10)
        # Marks a disconnected analysis failed while inference remains active.
        persistence.finish(error={"code": 499, "message": "Interrupted", "workflow_id": None})
        assert not future.cancel()
        release.set()
    assert written.is_set()
    assert persistence.data["status"] == "Failed"
    assert persistence.data["embedding_status"] == "Complete"
    assert storage.table is storage.connection is None
