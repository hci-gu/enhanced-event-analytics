import json
from unittest.mock import Mock
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

import app as backend
import workflows
from test_app import EMBEDDING, loaders


@pytest.fixture(autouse=True)
def title_generator(monkeypatch):
    generator = Mock(return_value="Testhändelse")
    monkeypatch.setattr(workflows, "generate_title", generator)
    return generator


def parse_events(response):
    return [
        (lines[0].removeprefix("event: "), json.loads(lines[1].removeprefix("data: ")))
        for frame in response.text.strip().split("\n\n")
        if (lines := frame.splitlines())
    ]


def test_iterator_delivers_progress_before_running_next_workflow(monkeypatch, no_date_inference):
    first = Mock(return_value=[])
    second = Mock(return_value=[{"ID": "a", "name": "Match"}])
    dates = Mock(return_value={"dates": None, "dates_error": None})
    monkeypatch.setattr(workflows, "extract_dates", dates)
    monkeypatch.setattr(workflows, "WORKFLOWS", {
        "first": workflows.Workflow(first, label="Första"),
        "second": workflows.Workflow(second, label="Andra"),
    })
    iterator = workflows.iter_workflow_events("Text", object(), {"first": (), "second": ()})
    assert next(iterator) == ("analysis_started", {"workflows": [
        {"id": "first", "label": "Första"}, {"id": "second", "label": "Andra"},
        {"id": "dates", "label": "Datum"},
    ]})
    first.assert_not_called()
    assert next(iterator) == ("title_completed", {"title": "Testhändelse"})
    first.assert_not_called()
    assert next(iterator) == ("workflow_started", {"id": "first"})
    first.assert_not_called()
    assert next(iterator) == ("workflow_completed", {"id": "first", "results": []})
    first.assert_called_once()
    second.assert_not_called()
    assert next(iterator) == ("workflow_started", {"id": "second"})
    second.assert_not_called()
    assert next(iterator)[0] == "workflow_completed"
    assert next(iterator) == ("workflow_started", {"id": "dates"})
    dates.assert_not_called()
    assert next(iterator) == ("workflow_completed", {"id": "dates", "results": [], "dates": None, "dates_error": None})
    dates.assert_called_once()
    assert next(iterator) == ("analysis_completed", {"dates": None, "dates_error": None})
    with pytest.raises(StopIteration):
        next(iterator)


def test_stream_endpoint_contract_and_existing_json_endpoint(loaders, monkeypatch):
    monkeypatch.setattr(workflows, "generate_text", Mock(return_value="[]"))
    with TestClient(backend.app) as client:
        response = client.post("/analyze-event/stream", json={"text": "  Text  "})
        ordinary = client.post("/analyze-event", json={"text": "Text"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["x-accel-buffering"] == "no"
    events = parse_events(response)
    analysis_id = response.headers["x-analysis-id"]
    assert UUID(analysis_id).version == 4
    assert events[0] == ("analysis_started", {"analysis_id": analysis_id, "workflows": [
        {"id": "risks", "label": "Riskområden"},
        {"id": "reach", "label": "Räckvidd"},
        {"id": "service", "label": "Verksamheter"},
        {"id": "properties", "label": "Egenskaper"},
        {"id": "protection", "label": "Skyddsvärden"},
        {"id": "dates", "label": "Datum"},
    ]})
    assert events[1] == ("title_completed", {"title": "Testhändelse"})
    assert [name for name, _ in events] == ["analysis_started", "title_completed"] + [
        "workflow_started", "workflow_completed",
    ] * 6 + ["analysis_completed"]
    assert events[-1] == ("analysis_completed", {"embedding": EMBEDDING, "embedding_error": None,
                                               "dates": None, "dates_error": None})
    assert ordinary.json() == {"status": "ok", "title": "Testhändelse", "embedding": EMBEDDING,
                              "dates": None, "dates_error": None,
                              "embedding_error": None, "results": {
        "risks": [], "reach": [], "service": [], "properties": [], "protection": [],
    }}
    assert UUID(ordinary.headers["x-analysis-id"]).version == 4
    assert ordinary.headers["x-analysis-id"] != analysis_id


@pytest.mark.parametrize("path", ["/analyze-event", "/analyze-event/stream"])
@pytest.mark.parametrize("recovered", [True, False])
def test_category_retry_endpoint_contract(loaders, monkeypatch, path, recovered):
    outputs = ["invalid", "[]", "[]", "[]", "[]", "[]"] if recovered else ["invalid", "invalid"]
    generator = Mock(side_effect=outputs)
    monkeypatch.setattr(workflows, "generate_text", generator)
    with TestClient(backend.app) as client:
        response = client.post(path, json={"text": "Text"})
    assert generator.call_count == (6 if recovered else 2)
    if path.endswith("/stream"):
        events = parse_events(response)
        assert events[-1][0] == ("analysis_completed" if recovered else "workflow_failed")
        if not recovered:
            assert events[-1][1]["code"] == 502
            assert events[-1][1]["id"] == "risks"
    else:
        assert response.status_code == (200 if recovered else 502)


def test_each_analysis_gets_a_unique_reference(loaders, monkeypatch):
    monkeypatch.setattr(workflows, "generate_text", Mock(return_value="[]"))
    with TestClient(backend.app) as client:
        responses = [client.post(path, json={"text": "Same event"}) for path in [
            "/analyze-event/stream", "/analyze-event/stream", "/analyze-event", "/analyze-event",
        ]]
    ids = [response.headers["x-analysis-id"] for response in responses]
    assert len(set(ids)) == 4
    assert all(UUID(value).version == 4 for value in ids)
    for response in responses[:2]:
        assert parse_events(response)[0][1]["analysis_id"] == response.headers["x-analysis-id"]


@pytest.mark.parametrize("error,code", [
    (workflows.WorkflowError(413, "too long"), 413),
    (workflows.WorkflowError(502, "invalid output"), 502),
    (workflows.WorkflowError(503, "unsupported"), 503),
    (RuntimeError("private internal detail"), 500),
])
def test_failure_preserves_results_and_stops_execution(loaders, monkeypatch, error, code):
    first = Mock(return_value=[{"ID": "flood", "name": "Översvämningar"}])
    failed = Mock(side_effect=error)
    queued = Mock()
    monkeypatch.setattr(workflows, "WORKFLOWS", {
        "first": workflows.Workflow(first), "failed": workflows.Workflow(failed),
        "queued": workflows.Workflow(queued),
    })
    with TestClient(backend.app) as client:
        response = client.post("/analyze-event/stream", json={"text": "Text"})
    events = parse_events(response)
    assert events[0][1]["analysis_id"] == response.headers["x-analysis-id"]
    assert events[1] == ("title_completed", {"title": "Testhändelse"})
    assert events[3] == ("workflow_completed", {
        "id": "first", "results": [{"ID": "flood", "name": "Översvämningar"}],
    })
    assert events[-1][0] == "workflow_failed"
    assert events[-1][1]["id"] == "failed"
    assert events[-1][1]["code"] == code
    assert "private internal detail" not in response.text
    assert "analysis_completed" not in response.text
    queued.assert_not_called()


@pytest.mark.parametrize("payload", [{}, {"text": None}, {"text": 1}, {"text": " \n "}])
def test_stream_validation_before_inference(loaders, monkeypatch, payload):
    runner = Mock()
    monkeypatch.setattr(backend, "iter_workflow_events", runner)
    with TestClient(backend.app) as client:
        response = client.post("/analyze-event/stream", json=payload)
    assert response.status_code == 422
    runner.assert_not_called()


def test_stream_evidence_and_json_compatibility(loaders, monkeypatch):
    monkeypatch.setattr(workflows, "generate_text", Mock(side_effect=[
        '[{"ID":"översvämningar","evidence":["Vatten", "påhittat"]}]', '[]', '[]',
        '[{"ID":"riktning","evidence":["stiger", "påhittat"]}]',
        '[{"ID":"människors_liv_och_hälsa","evidence":["Vatten", "påhittat"]}]',
    ] * 2))
    with TestClient(backend.app) as client:
        streamed = client.post("/analyze-event/stream", json={"text": "Vatten stiger"})
        ordinary = client.post("/analyze-event", json={"text": "Vatten stiger"})
    match = {"ID": "översvämningar", "name": "Översvämningar"}
    assert parse_events(streamed)[3][1]["results"] == [{**match, "evidence": ["Vatten"]}]
    assert ordinary.json()["results"]["risks"] == [match]
    for name, index, match, quote in [
        ("properties", 9, {"ID": "riktning", "name": "Riktning"}, "stiger"),
        ("protection", 11, {"ID": "människors_liv_och_hälsa", "name": "Människors liv och hälsa"}, "Vatten"),
    ]:
        assert parse_events(streamed)[index] == ("workflow_completed", {
            "id": name, "results": [{**match, "evidence": [quote]}],
        })
        assert ordinary.json()["results"][name] == [match]
