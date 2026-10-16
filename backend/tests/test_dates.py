"""Date workflow tests use mocked inference and never load model weights."""

import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

import app as backend
import workflows
from test_app import loaders
from test_persistence import writes
from test_stream import parse_events


EXTRACT_DATES = workflows.extract_dates


def empty_dates(**changes):
    return {
        "published_at": None, "event_start": None, "event_end": None,
        "end_status": "unknown", "duration_hint": None,
        "evidence": {"published_at": [], "event_start": [], "event_end": []}, **changes,
    }


@pytest.mark.parametrize("value", ["2026-10-16", "2026-10-16T09:35", "2026-10-16T09:35+02:00"])
def test_preserves_precision_and_filters_evidence(monkeypatch, value):
    output = empty_dates(published_at=value)
    output["evidence"]["published_at"] = ["Publicerad", "Publicerad", "invented"]
    generator = Mock(return_value=json.dumps(output))
    monkeypatch.setattr(workflows, "generate_text", generator)
    result = EXTRACT_DATES("Publicerad", object())
    assert result["dates"]["published_at"] == value
    assert result["dates"]["evidence"]["published_at"] == ["Publicerad"]
    assert result["dates_error"] is None
    assert generator.call_args.kwargs["workflow_name"] == "dates"


@pytest.mark.parametrize("value", ["2026-02-30", "2026-13-01", "tomorrow", "2026-10-16T25:00", "2026-10-16T10:30:40", "2026-10-16T09:35+00:99"])
def test_invalid_individual_dates_are_null(monkeypatch, value):
    output = empty_dates(published_at=value, duration_hint="~1D")
    output["evidence"]["published_at"] = ["Source"]
    generator = Mock(return_value=json.dumps(output))
    monkeypatch.setattr(workflows, "generate_text", generator)
    result = EXTRACT_DATES("Source", object())
    assert result["dates"]["published_at"] is None
    assert result["dates"]["duration_hint"] == "~1D"
    assert result["dates_error"] is None
    generator.assert_called_once()


@pytest.mark.parametrize("hint", ["~1H", "~2D", "~1W", "~1M", "~1Y", "~0D", "2D", "~1h"])
def test_duration_hint_never_creates_dates(monkeypatch, hint):
    monkeypatch.setattr(workflows, "generate_text", Mock(return_value=json.dumps(empty_dates(duration_hint=hint))))
    dates = EXTRACT_DATES("Text", object())["dates"]
    assert dates["duration_hint"] == (hint if hint in {"~1H", "~2D", "~1W", "~1M", "~1Y"} else None)
    assert dates["event_start"] is dates["event_end"] is None


@pytest.mark.parametrize("status,quotes,expected", [
    ("until_further_notice", ["Pågår"], "until_further_notice"),
    ("until_further_notice", ["invented"], "unknown"),
    ("dated", [], "unknown"),
])
def test_open_ended_status_requires_verified_evidence(monkeypatch, status, quotes, expected):
    output = empty_dates(end_status=status)
    output["evidence"]["event_end"] = quotes
    monkeypatch.setattr(workflows, "generate_text", Mock(return_value=json.dumps(output)))
    dates = EXTRACT_DATES("Pågår", object())["dates"]
    assert dates["end_status"] == expected
    assert dates["event_start"] is dates["event_end"] is None


@pytest.mark.parametrize("start,end,reversed_interval", [
    ("2026-10-17", "2026-10-16", True),
    ("2026-10-16T15:00", "2026-10-16T14:00", True),
    ("2026-10-16T15:00+02:00", "2026-10-16T14:00Z", False),
    ("2026-10-16", "2026-10-16T10:00", False),
    ("2026-10-16T10:00", "2026-10-16T10:00Z", False),
])
def test_interval_consistency(monkeypatch, start, end, reversed_interval):
    output = empty_dates(event_start=start, event_end=end)
    output["evidence"] = {"published_at": [], "event_start": ["Source"], "event_end": ["Source"]}
    monkeypatch.setattr(workflows, "generate_text", Mock(return_value=json.dumps(output)))
    dates = EXTRACT_DATES("Source", object())["dates"]
    assert dates["event_start"] == start
    assert dates["event_end"] == (None if reversed_interval else end)
    assert dates["end_status"] == ("unknown" if reversed_interval else "dated")


@pytest.mark.parametrize("month,hour", [(1, 13), (7, 14)])
def test_clock_timezone_dst_and_retry_stability(monkeypatch, month, hour):
    clock = Mock()
    clock.now.return_value = datetime(2026, month, 16, 12, 34, 56, tzinfo=timezone.utc).astimezone(ZoneInfo("Europe/Stockholm"))
    monkeypatch.setattr(workflows, "datetime", clock)
    generator = Mock(side_effect=["{}", json.dumps(empty_dates())])
    monkeypatch.setattr(workflows, "generate_text", generator)
    result = EXTRACT_DATES("Text", SimpleNamespace(retry_limit=1, analysis_timezone=ZoneInfo("Europe/Stockholm")))
    assert result["dates"] == empty_dates()
    clock.now.assert_called_once_with(ZoneInfo("Europe/Stockholm"))
    for call in generator.call_args_list:
        assert f"Datumet är 2026:{month:02}:16 {hour}:34" in call.args[0][0]["content"]
        assert "56" not in call.args[0][0]["content"]


@pytest.mark.parametrize("name", ["Europe/Stockholm", "UTC", "America/New_York"])
def test_timezone_configuration(monkeypatch, name):
    monkeypatch.setenv("ANALYSIS_TIMEZONE", name)
    assert workflows.load_analysis_timezone().key == name


def test_invalid_timezone_prevents_model_loading(loaders, monkeypatch):
    monkeypatch.setenv("ANALYSIS_TIMEZONE", "Invalid/Timezone")
    with pytest.raises(RuntimeError, match="ANALYSIS_TIMEZONE"):
        with TestClient(backend.app):
            pass
    loaders[0].assert_not_called()
    loaders[1].assert_not_called()


@pytest.mark.parametrize("output,calls,code", [
    ("not JSON", 2, 502), ("[]", 2, 502),
    (workflows.WorkflowError(502, "private error"), 1, 502),
    (RuntimeError("private error"), 1, 500),
])
def test_failures_are_nonfatal_and_do_not_leak_errors(monkeypatch, output, calls, code):
    generator = Mock(side_effect=output) if isinstance(output, Exception) else Mock(return_value=output)
    monkeypatch.setattr(workflows, "generate_text", generator)
    result = EXTRACT_DATES("Text", object())
    assert result["dates"] is None
    assert result["dates_error"]["code"] == code
    assert "private" not in result["dates_error"]["message"]
    assert generator.call_count == calls


@pytest.mark.parametrize("endpoint", ["/analyze-event", "/analyze-event/stream"])
@pytest.mark.parametrize("failed", [False, True])
def test_final_workflow_api_and_persistence(loaders, pocketbase, monkeypatch, endpoint, failed):
    monkeypatch.setattr(workflows, "extract_dates", EXTRACT_DATES)
    text = "Publicerad 2026-10-15. Uppdaterad 2026-10-16. Avbrottet börjar imorgon. Enligt talespersonen klart 2026-10-18."
    output = empty_dates(published_at="2026-10-15", event_start="2026-10-16", event_end="2026-10-18", end_status="dated")
    output["evidence"] = {
        "published_at": ["Publicerad 2026-10-15"],
        "event_start": ["Publicerad 2026-10-15", "Avbrottet börjar imorgon"],
        "event_end": ["Enligt talespersonen klart 2026-10-18"],
    }
    generator = Mock(side_effect=["Rubrik"] + ["[]"] * 5 + (["invalid"] * 2 if failed else [json.dumps(output)]))
    monkeypatch.setattr(workflows, "generate_text", generator)
    with TestClient(backend.app) as client:
        response = client.post(endpoint, json={"text": text})
    assert response.status_code == 200
    data = parse_events(response)[-1][1] if endpoint.endswith("/stream") else response.json()
    final = writes(pocketbase)[-1][1]
    assert data["dates"] == final["dates"] == (None if failed else output)
    assert data["dates_error"] == final["dates_error"]
    assert bool(data["dates_error"]) == failed
    assert final["status"] == "Complete"
    assert final["error"] is None
    assert set(final["predictions"]) == set(workflows.WORKFLOWS)
    assert generator.call_args_list[-1].kwargs["workflow_name"] == "dates"
    assert "dates" not in final["predictions"]
    # These verify the prompt contract and plumbing, not real-model extraction quality.
    prompt = generator.call_args.args[0][0]["content"]
    for instruction in ("ignorera uppdateringar", "ALDRIG analystiden", "intervjuades prognoser", "Saknas publiceringsankare"):
        assert instruction in prompt


def test_unsupported_dates_are_removed(monkeypatch):
    output = empty_dates(published_at="2026-10-15", event_start="2026-10-16", event_end="2026-10-17", end_status="dated")
    monkeypatch.setattr(workflows, "generate_text", Mock(return_value=json.dumps(output)))
    assert EXTRACT_DATES("No dates", object())["dates"] == empty_dates()
