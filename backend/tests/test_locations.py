import json
import logging
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
from fastapi.testclient import TestClient

import app as backend
import locations
import workflows
from test_app import loaders
from test_persistence import writes
from test_stream import parse_events


def mention(name="Stockholm", **changes):
    return {"mention": name, "query": name, "roles": ["event-site"], "evidence": [name],
            "country_code": "se", "country": "Sweden", "city": name, "region": None,
            "continent": None, "granularity": "city", **changes}


def match(display_name="Stockholm", **changes):
    return {"lon": 18.06, "lat": 59.33, "formatted": display_name, "city": display_name,
            "state": "Stockholm County", "country": "Sweden", "country_code": "se",
            "result_type": "city", "place_id": display_name, "rank": {"confidence": 0.5},
            "datasource": {"attribution": "© OpenStreetMap contributors"}, **changes}


@pytest.fixture
def provider(monkeypatch):
    state = SimpleNamespace(requests=[], results=[match()], status=200)

    def handler(request):
        state.requests.append(request)
        if hasattr(state, "handler"):
            return state.handler(request)
        return httpx.Response(state.status, json={"results": state.results})

    original = locations.GeoapifyClient
    monkeypatch.setattr(locations, "GeoapifyClient", lambda key: original(key, transport=httpx.MockTransport(handler)))
    monkeypatch.setattr(locations, "wait_for_request_slot", lambda: None)
    return state


def extract(monkeypatch, places, text=None):
    generator = Mock(return_value=json.dumps({"locations": places}))
    monkeypatch.setattr(workflows, "generate_text", generator)
    runtime = SimpleNamespace(retry_limit=1, workflow_settings=workflows.WorkflowSettings(geoapify_api_key="test-secret"))
    output = workflows.extract_locations(text or " ".join(p["mention"] for p in places), runtime)
    return output, generator


def test_grounded_roles_order_deduplication_and_attribution(monkeypatch, provider):
    provider.handler = lambda r: httpx.Response(200, json={"results": [match(r.url.params["text"])]})
    places = [mention("Uppsala", roles=["contextual"]), mention("Stockholm"),
              mention("Uppsala", roles=["affected-area"]), mention("Stockholm", roles=["affected-area"]),
              mention("Made up", evidence=["not in source"])]
    output, generator = extract(monkeypatch, places, "Uppsala och Stockholm")
    assert [entry["mentions"] for entry in output["location"]] == [["Stockholm"], ["Uppsala"]]
    assert output["location"][0]["roles"] == ["event-site", "affected-area"]
    assert output["location"][1]["roles"] == ["affected-area", "contextual"]
    assert len(provider.requests) == 2
    entry = output["location"][0]
    assert entry["longitude"] == 18.06 and entry["latitude"] == 59.33
    assert entry["confidence"] == 0.5  # No additional acceptance threshold.
    assert entry["attribution"]["datasource"]["attribution"] == "© OpenStreetMap contributors"
    assert output["location_error"] is None
    assert generator.call_args.kwargs["workflow_name"] == "location"
    assert all(r.url.params["bias"] == "countrycode:none" for r in provider.requests)
    assert all(r.url.params["filter"] == "countrycode:se" for r in provider.requests)


def test_source_order_within_roles_and_highest_constrained_match(monkeypatch, provider):
    provider.results = [match(country_code="us", place_id="foreign"), match(place_id="first"), match(place_id="second")]
    output, _ = extract(monkeypatch, [mention("Uppsala"), mention("Stockholm")], "Stockholm och Uppsala")
    assert output["location"][0]["mentions"] == ["Stockholm", "Uppsala"]
    assert output["location"][0]["place_id"] == "first"


@pytest.mark.parametrize("level,result_type", [("facility", "amenity"), ("street", "street"), ("region", "state")])
def test_swedish_precision(monkeypatch, provider, level, result_type):
    provider.results = [match(result_type=result_type)]
    output, _ = extract(monkeypatch, [mention("Platsen", granularity=level)])
    assert output["location"][0]["granularity"] == level


def test_explicit_fallback_and_no_invented_fallback(monkeypatch, provider):
    def handler(request):
        return httpx.Response(200, json={"results": [match()] if request.url.params["text"] == "Stockholm" else []})
    provider.handler = handler
    place = mention("Fabriken", query="Fabriken, Stockholm", granularity="facility", city="Stockholm")
    output, _ = extract(monkeypatch, [place], "Fabriken i Stockholm")
    assert output["location"][0]["granularity"] == "city"
    assert output["location"][0]["mentions"] == ["Fabriken"]
    provider.requests.clear()
    output, _ = extract(monkeypatch, [place], "Fabriken")
    assert output["location"][0]["status"] == "unresolved"
    assert len(provider.requests) == 1


def test_foreign_locations_are_country_points_and_continents_are_supported(monkeypatch, provider):
    def handler(request):
        query = request.url.params["text"]
        result = (match("France", lon=2.0, lat=46.0, country="France", country_code="fr", result_type="country", place_id="fr")
                  if query == "France" else match("Europe", name="Europe", country=None, country_code=None, place_id="eu"))
        return httpx.Response(200, json={"results": [result]})
    provider.handler = handler
    places = [mention("Paris", country="France", country_code="fr", city="Paris"),
              mention("Europa", country=None, country_code=None, continent="Europe", granularity="continent")]
    output, _ = extract(monkeypatch, places)
    assert [entry["granularity"] for entry in output["location"]] == ["country", "continent"]
    assert all(entry["city"] is None and entry["region"] is None for entry in output["location"])
    assert [r.url.params["text"] for r in provider.requests] == ["France", "continent Europe"]


def test_unknown_foreign_city_is_resolved_again_at_country_level(monkeypatch, provider):
    provider.handler = lambda r: httpx.Response(200, json={"results": [match(
        "Paris" if r.url.params["text"] == "Paris" else "France", country_code="fr", country="France",
        result_type="city" if r.url.params["text"] == "Paris" else "country")]})
    output, _ = extract(monkeypatch, [mention("Paris", country_code=None, country=None)])
    assert output["location"][0]["granularity"] == "country"
    assert len(provider.requests) == 2


def test_empty_unresolved_and_invalid_coordinates(monkeypatch, provider):
    output, _ = extract(monkeypatch, [], "No places")
    assert output == {"location": [], "location_error": None}
    assert not provider.requests
    provider.results = [match(lon=181), match(lat=True)]
    output, _ = extract(monkeypatch, [mention()])
    assert output["location"][0]["longitude"] is None
    assert output["location"][0]["latitude"] is None
    assert output["location"][0]["status"] == "unresolved"


@pytest.mark.parametrize("failure", ["timeout", "rate", "malformed"])
def test_partial_lookup_failure_and_secret_redaction(monkeypatch, provider, caplog, failure):
    def handler(request):
        if request.url.params["text"] == "Stockholm":
            return httpx.Response(200, json={"results": [match()]})
        if failure == "timeout":
            raise httpx.ReadTimeout("test-secret", request=request)
        return httpx.Response(429 if failure == "rate" else 200, json={} if failure == "malformed" else {"error": "test-secret"})
    provider.handler = handler
    with caplog.at_level(logging.DEBUG):
        output, _ = extract(monkeypatch, [mention(), mention("Uppsala")])
    assert [entry["status"] for entry in output["location"]] == ["resolved", "unresolved"]
    assert output["location_error"]["code"] == (429 if failure == "rate" else 502)
    assert "test-secret" not in caplog.text + json.dumps(output)
    assert len(provider.requests) == 2


def test_invalid_model_output_retries_but_inference_failure_does_not(monkeypatch, provider):
    runtime = SimpleNamespace(retry_limit=1, workflow_settings=workflows.WorkflowSettings(geoapify_api_key="test-secret"))
    for side_effect, count in [(["{}", "{}"], 2), ([RuntimeError("test-secret")], 1)]:
        generator = Mock(side_effect=side_effect)
        monkeypatch.setattr(workflows, "generate_text", generator)
        output = workflows.extract_locations("Stockholm", runtime)
        assert output["location"] is None and output["location_error"]["code"] == 502
        assert "test-secret" not in json.dumps(output)
        assert generator.call_count == count
    assert not provider.requests


def test_missing_key_skips_inference(monkeypatch, provider):
    generator = Mock()
    monkeypatch.setattr(workflows, "generate_text", generator)
    output = workflows.extract_locations("Stockholm", SimpleNamespace(workflow_settings=workflows.WorkflowSettings()))
    assert output["location_error"]["code"] == 503
    generator.assert_not_called()
    assert not provider.requests


def test_distinct_queries_are_bounded_with_nonfatal_warning(monkeypatch, provider):
    provider.handler = lambda r: httpx.Response(200, json={"results": [match(r.url.params["text"])]})
    output, _ = extract(monkeypatch, [mention(f"Plats {index}") for index in range(25)])
    assert len(provider.requests) == len(output["location"]) == 20
    assert output["location_error"]["code"] == 206


def test_query_budget_prioritizes_sites_over_earlier_context(monkeypatch, provider):
    provider.handler = lambda r: httpx.Response(200, json={"results": [match(r.url.params["text"])]})
    places = [mention(f"Bakgrund {index}", roles=["contextual"]) for index in range(20)] + [mention()]
    output, _ = extract(monkeypatch, places)
    assert output["location"][0]["mentions"] == ["Stockholm"]
    assert len(provider.requests) == 20


def test_fallback_requests_share_lookup_budget(monkeypatch, provider):
    provider.results = []
    places = [mention(f"Fabrik {index}", city="Stockholm", granularity="facility") for index in range(20)]
    output, _ = extract(monkeypatch, places, "Stockholm " + " ".join(p["mention"] for p in places))
    assert len(provider.requests) == 20
    assert output["location_error"]["code"] == 206
    assert len(output["location"]) == 20


def test_failed_queries_are_cached_for_the_analysis(monkeypatch, provider):
    provider.status = 429
    output, _ = extract(monkeypatch, [mention(), mention(roles=["affected-area"])])
    assert len(provider.requests) == 1
    assert output["location"][0]["roles"] == ["event-site", "affected-area"]
    assert output["location_error"]["code"] == 429


def test_rate_limiter_spaces_process_requests(monkeypatch):
    clock = SimpleNamespace(now=10.0)
    waits = []
    def advance(delay):
        waits.append(delay)
        clock.now += delay
    monkeypatch.setattr(locations, "_last_request", float("-inf"))
    monkeypatch.setattr(locations, "monotonic", lambda: clock.now)
    monkeypatch.setattr(locations, "sleep", advance)
    locations.wait_for_request_slot()
    locations.wait_for_request_slot()
    locations.wait_for_request_slot()
    assert waits == pytest.approx([0.2, 0.2])


@pytest.mark.parametrize("disable_date,disable_location", [(False, False), (True, False), (False, True), (True, True)])
def test_flags_skip_calls_and_progress(monkeypatch, disable_date, disable_location):
    monkeypatch.setattr(workflows, "WORKFLOWS", {})
    monkeypatch.setattr(workflows, "generate_title", Mock(return_value="Rubrik"))
    dates = Mock(return_value={"dates": None, "dates_error": None})
    places = Mock(return_value={"location": [], "location_error": None})
    monkeypatch.setattr(workflows, "extract_dates", dates)
    monkeypatch.setattr(workflows, "extract_locations", places)
    runtime = SimpleNamespace(workflow_settings=workflows.WorkflowSettings(disable_date, disable_location))
    events = list(workflows.iter_workflow_events("Text", runtime, {}))
    ids = [w["id"] for w in events[0][1]["workflows"]]
    assert ids == ([] if disable_date else ["dates"]) + ([] if disable_location else ["location"])
    assert dates.call_count == int(not disable_date)
    assert places.call_count == int(not disable_location)
    assert [data["id"] for event, data in events if event == "workflow_started"] == ids


def test_settings_defaults_validation_and_secret_repr(monkeypatch):
    monkeypatch.delenv("DISABLE_LOCATION_WORKFLOW")
    assert workflows.load_workflow_settings() == workflows.WorkflowSettings()
    monkeypatch.setenv("GEOAPIFY_API_KEY", "test-secret")
    assert "test-secret" not in repr(workflows.load_workflow_settings())
    monkeypatch.setenv("DISABLE_DATE_WORKFLOW", "invalid")
    with pytest.raises(RuntimeError, match="DISABLE_DATE_WORKFLOW"):
        workflows.load_workflow_settings()


def test_settings_are_loaded_after_dotenv_and_frozen_for_runtime(loaders, monkeypatch):
    def load_settings(**kwargs):
        assert kwargs["override"] is False
        monkeypatch.setenv("DISABLE_DATE_WORKFLOW", "true")
        monkeypatch.setenv("DISABLE_LOCATION_WORKFLOW", "false")
        monkeypatch.setenv("GEOAPIFY_API_KEY", "test-secret")
    monkeypatch.setattr(backend, "load_dotenv", load_settings)
    with TestClient(backend.app):
        settings = backend.app.state.runtime.workflow_settings
        assert settings == workflows.WorkflowSettings(True, False, "test-secret")
        monkeypatch.setenv("DISABLE_LOCATION_WORKFLOW", "true")
        assert backend.app.state.runtime.workflow_settings == settings


@pytest.mark.parametrize("endpoint", ["/analyze-event", "/analyze-event/stream"])
@pytest.mark.parametrize("failed", [False, True])
def test_api_and_persistence_preserve_location_and_category_results(loaders, pocketbase, monkeypatch, provider, endpoint, failed):
    monkeypatch.setenv("DISABLE_LOCATION_WORKFLOW", "false")
    monkeypatch.setenv("GEOAPIFY_API_KEY", "test-secret")
    provider.status = 429 if failed else 200
    monkeypatch.setattr(workflows, "generate_text", Mock(side_effect=["Rubrik"] + ["[]"] * 5 + [json.dumps({"locations": [mention()]})]))
    with TestClient(backend.app) as client:
        response = client.post(endpoint, json={"text": "Stockholm"})
    assert response.status_code == 200
    data = parse_events(response)[-1][1] if endpoint.endswith("/stream") else response.json()
    final = writes(pocketbase)[-1][1]
    assert data["location"] == final["location"]
    assert data["location_error"] == final["location_error"]
    assert bool(data["location_error"]) == failed
    assert final["status"] == "Complete" and final["error"] is None
    assert set(final["predictions"]) == set(workflows.WORKFLOWS)
    if endpoint.endswith("/stream"):
        events = parse_events(response)
        assert events[-3] == ("workflow_started", {"id": "location"})
        assert events[-2][1]["results"] == []
        assert events[0][1]["workflows"][-1] == {"id": "location", "label": "Lokalisering"}
