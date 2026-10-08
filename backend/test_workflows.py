import json
from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import torch

import workflows


@pytest.fixture
def categories():
    return (
        workflows.Category(ID="flood", name="Display flood", description="Water inundates roads."),
        workflows.Category(ID="cold", name="Display cold", description="Extreme cold affects people."),
    )


@pytest.mark.parametrize("output,expected", [
    ("[]", []), ('["flood"]', ["flood"]),
    ('["cold", "flood", "cold"]', ["flood", "cold"]),
    ('```json\n["flood"]\n```', ["flood"]),
    ('```\n["flood"]\n```', ["flood"]),
])
def test_risk_matches(categories, monkeypatch, output, expected):
    generator = Mock(return_value=output)
    monkeypatch.setattr(workflows, "generate_text", generator)
    runtime = object()
    results = workflows.categorize_risks("Event text", runtime, categories)
    assert results == [
        {"ID": category.ID, "name": category.name}
        for category in categories if category.ID in expected
    ]
    generator.assert_called_once()
    messages, actual_runtime = generator.call_args.args
    assert actual_runtime is runtime
    payload = json.loads(messages[1]["content"])
    assert payload["händelsetext"] == "Event text"
    assert payload["riskområden"] == [
        {"ID": category.ID, "description": category.description} for category in categories
    ]
    assert "Display flood" not in json.dumps(messages)
    assert "noll, en eller flera" in messages[0]["content"]


@pytest.mark.parametrize("output", [
    "not JSON", '{"matches": []}', '"flood"', "null", '[1]', '[true]',
    '[{}]', '["unknown"]', 'Here are the matches: ["flood"]', '["flood"',
])
def test_invalid_model_output(categories, monkeypatch, output):
    monkeypatch.setattr(workflows, "generate_text", Mock(return_value=output))
    with pytest.raises(workflows.WorkflowError) as error:
        workflows.categorize_risks("Event", object(), categories)
    assert error.value.status_code == 502


@pytest.mark.parametrize("contents", [
    "invalid JSON", "{}", '[{"ID": "a", "name": "A"}]',
    '[{"ID": " ", "name": "A", "description": "D"}]',
    '[{"ID": "a", "name": " ", "description": "D"}]',
    '[{"ID": "a", "name": "A", "description": " "}]',
    '[{"ID": 1, "name": "A", "description": "D"}]',
    '[{"ID": "a", "name": "A", "description": "D"},'
    '{"ID": "a", "name": "B", "description": "E"}]',
])
def test_invalid_category_file(tmp_path, contents):
    path = tmp_path / "categories.json"
    path.write_text(contents, encoding="utf-8")
    with pytest.raises(RuntimeError, match="Failed to load workflow categories"):
        workflows.load_categories(path)


def test_missing_category_file(tmp_path):
    with pytest.raises(RuntimeError, match="Failed to load workflow categories"):
        workflows.load_categories(tmp_path / "missing.json")


def test_valid_category_file(tmp_path):
    path = tmp_path / "categories.json"
    path.write_text(
        '[{"ID": "översvämningar", "name": "Översvämningar", "description": "Höga vattennivåer."}]',
        encoding="utf-8",
    )
    categories = workflows.load_categories(path)
    assert len(categories) == 1
    assert categories[0].name == "Översvämningar"


class Inputs(dict):
    def to(self, device):
        assert device == "cpu"
        return self


@pytest.fixture
def runtime():
    processor = Mock()
    processor.apply_chat_template.return_value = Inputs(input_ids=torch.tensor([[10, 11]]))
    processor.decode.return_value = "[]"
    model = Mock()
    model.can_generate.return_value = True
    model.generate.return_value = torch.tensor([[10, 11, 12, 13]])
    return SimpleNamespace(processor=processor, model=model, device="cpu", inference_lock=Lock())


def test_generation_uses_only_new_tokens(runtime):
    def generate(**kwargs):
        assert not torch.is_grad_enabled()
        assert runtime.inference_lock.locked()
        assert kwargs["max_new_tokens"] == 1024
        assert kwargs["do_sample"] is False
        return torch.tensor([[10, 11, 12, 13]])

    runtime.model.generate.side_effect = generate
    assert workflows.generate_text([], runtime) == "[]"
    tokens = runtime.processor.decode.call_args.args[0]
    assert tokens.tolist() == [12, 13]
    assert runtime.processor.apply_chat_template.call_args.kwargs["enable_thinking"] is False
    assert not runtime.inference_lock.locked()


@pytest.mark.parametrize("token_count,status", [(8192, None), (8193, 413)])
def test_input_limit(runtime, token_count, status):
    runtime.processor.apply_chat_template.return_value = Inputs(
        input_ids=torch.zeros((1, token_count), dtype=torch.long)
    )
    if status is None:
        assert workflows.generate_text([], runtime) == "[]"
        runtime.model.generate.assert_called_once()
    else:
        with pytest.raises(workflows.WorkflowError) as error:
            workflows.generate_text([], runtime)
        assert error.value.status_code == status
        runtime.model.generate.assert_not_called()
    assert not runtime.inference_lock.locked()


@pytest.mark.parametrize("stage", ["prepare", "generate", "decode"])
def test_inference_failure_releases_lock(runtime, stage):
    call = {
        "prepare": runtime.processor.apply_chat_template,
        "generate": runtime.model.generate,
        "decode": runtime.processor.decode,
    }[stage]
    call.side_effect = RuntimeError("inference failed")
    with pytest.raises(workflows.WorkflowError) as error:
        workflows.generate_text([], runtime)
    assert error.value.status_code == 502
    assert not runtime.inference_lock.locked()


@pytest.mark.parametrize("missing_processor", [True, False])
def test_unsupported_runtime(runtime, missing_processor):
    if missing_processor:
        runtime.processor = None
    else:
        runtime.model.can_generate.return_value = False
    with pytest.raises(workflows.WorkflowError) as error:
        workflows.generate_text([], runtime)
    assert error.value.status_code == 503
    runtime.model.generate.assert_not_called()


def test_concurrent_generation_is_serialized(runtime):
    entered = Event()
    release = Event()
    order = []

    def prepare(*args, **kwargs):
        order.append("prepare")
        return Inputs(input_ids=torch.tensor([[10, 11]]))

    def generate(**kwargs):
        assert runtime.inference_lock.locked()
        order.append("generate")
        entered.set()
        assert release.wait(timeout=5)
        return torch.tensor([[10, 11, 12]])

    def decode(*args, **kwargs):
        order.append("decode")
        return "[]"

    runtime.processor.apply_chat_template.side_effect = prepare
    runtime.model.generate.side_effect = generate
    runtime.processor.decode.side_effect = decode
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(workflows.generate_text, [], runtime)
        try:
            assert entered.wait(timeout=5)
            second = executor.submit(workflows.generate_text, [], runtime)
            acquired = runtime.inference_lock.acquire(blocking=False)
            if acquired:
                runtime.inference_lock.release()
            assert not acquired
        finally:
            release.set()
        assert first.result(timeout=5) == "[]"
        assert second.result(timeout=5) == "[]"
    assert order == ["prepare", "generate", "decode"] * 2


def test_registry_orchestrates_functions(categories, monkeypatch):
    first = Mock(return_value=[])
    second = Mock(return_value={"summary": "Example"})
    monkeypatch.setattr(workflows, "WORKFLOWS", {
        "risks": workflows.Workflow(first, "risks.json"),
        "other": workflows.Workflow(second, "other.json"),
    })
    runtime = object()
    result = workflows.run_workflows("Event", runtime, {"risks": categories, "other": ()})
    assert result == {"risks": [], "other": {"summary": "Example"}}
    first.assert_called_once_with("Event", runtime, categories)
    second.assert_called_once_with("Event", runtime, ())
