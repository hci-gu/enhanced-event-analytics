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
    ("[]", []), ('[{"ID":"flood"}]', ["flood"]),
    ('[{"ID":"cold"},{"ID":"flood"},{"ID":"cold"}]', ["flood", "cold"]),
    ('```json\n[{"ID":"flood"}]\n```', ["flood"]),
    ('```\n[{"ID":"flood"}]\n```', ["flood"]),
])
@pytest.mark.parametrize("function,options_key,prompt", [
    (workflows.categorize_risks, "riskområden", workflows.RISK_SYSTEM_PROMPT),
    (workflows.categorize_reach, "räckviddsnivåer", workflows.REACH_SYSTEM_PROMPT),
    (workflows.categorize_service, "verksamheter", workflows.SERVICE_SYSTEM_PROMPT),
])
def test_category_matches(categories, monkeypatch, output, expected, function, options_key, prompt):
    generator = Mock(return_value=output)
    monkeypatch.setattr(workflows, "generate_text", generator)
    runtime = object()
    results = function("Event text", runtime, categories)
    assert results == [
        {"ID": category.ID, "name": category.name, "evidence": []}
        for category in categories if category.ID in expected
    ]
    generator.assert_called_once()
    messages, actual_runtime = generator.call_args.args
    assert actual_runtime is runtime
    payload = json.loads(messages[1]["content"])
    assert payload["händelsetext"] == "Event text"
    assert payload[options_key] == [
        {"ID": category.ID, "description": category.description} for category in categories
    ]
    assert "Display flood" not in json.dumps(messages)
    assert "noll, en eller flera" in messages[0]["content"]
    assert messages[0] == {"role": "system", "content": prompt}


@pytest.mark.parametrize("output", [
    "not JSON", '{"matches": []}', '"flood"', "null", '[1]', '[true]',
    '[{}]', '[{"ID":"unknown"}]', '["flood"]', 'Here are the matches: []', '["flood"',
])
@pytest.mark.parametrize("function", [
    workflows.categorize_risks, workflows.categorize_reach, workflows.categorize_service,
])
def test_invalid_model_output(categories, monkeypatch, output, function):
    monkeypatch.setattr(workflows, "generate_text", Mock(return_value=output))
    with pytest.raises(workflows.WorkflowError) as error:
        function("Event", object(), categories)
    assert error.value.status_code == 502


def test_registered_workflows_have_separate_prompts_and_categories(monkeypatch):
    generator = Mock(side_effect=["Testhändelse", "[]", "[]", "[]"])
    monkeypatch.setattr(workflows, "generate_text", generator)
    categories = workflows.load_workflow_categories()
    assert set(categories) == {"risks", "reach", "service"}
    runtime = object()
    assert workflows.run_workflows("Event", runtime, categories) == {
        "title": "Testhändelse", "results": {"risks": [], "reach": [], "service": []},
    }
    assert generator.call_count == 4
    assert generator.call_args_list[0].args[0][0]["content"] == workflows.TITLE_SYSTEM_PROMPT
    prompts = set()
    for call, (name, options_key) in zip(generator.call_args_list[1:], [
        ("risks", "riskområden"), ("reach", "räckviddsnivåer"), ("service", "verksamheter"),
    ]):
        messages, actual_runtime = call.args
        assert actual_runtime is runtime
        prompts.add(messages[0]["content"])
        payload = json.loads(messages[1]["content"])
        assert {item["ID"] for item in payload[options_key]} == {
            category.ID for category in categories[name]
        }
        assert all(set(item) == {"ID", "description"} for item in payload[options_key])
    assert len(prompts) == 3


@pytest.mark.parametrize("function,wrong_id", [
    (workflows.categorize_reach, "vatten_va"),
    (workflows.categorize_service, "2._lokalt"),
])
def test_ids_from_other_workflow_are_rejected(monkeypatch, function, wrong_id):
    monkeypatch.setattr(workflows, "generate_text", Mock(return_value=json.dumps([{"ID": wrong_id}])))
    name = "reach" if function is workflows.categorize_reach else "service"
    categories = workflows.load_workflow_categories()[name]
    with pytest.raises(workflows.WorkflowError) as error:
        function("Event", object(), categories)
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
        assert kwargs["max_new_tokens"] == 4096
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
    title = Mock(return_value="Testhändelse")
    monkeypatch.setattr(workflows, "generate_title", title)
    first = Mock(return_value=[])
    second = Mock(return_value={"summary": "Example"})
    monkeypatch.setattr(workflows, "WORKFLOWS", {
        "risks": workflows.Workflow(first, "risks.json"),
        "other": workflows.Workflow(second, "other.json"),
    })
    runtime = object()
    result = workflows.run_workflows("Event", runtime, {"risks": categories, "other": ()})
    assert result == {"title": "Testhändelse", "results": {"risks": [], "other": {"summary": "Example"}}}
    title.assert_called_once_with("Event", runtime)
    first.assert_called_once_with("Event", runtime, categories)
    second.assert_called_once_with("Event", runtime, ())


@pytest.mark.parametrize("evidence,expected", [
    (["Vatten stiger", "Vatten stiger", "😀"], ["Vatten stiger", "😀"]),
    (["vatten stiger", "Vatten  stiger", "", " ", 12, None], []),
    ("Vatten stiger", []),
    (None, []),
])
def test_verified_evidence(categories, monkeypatch, caplog, evidence, expected):
    output = [{"ID": "flood", "evidence": evidence}]
    monkeypatch.setattr(workflows, "generate_text", Mock(return_value=json.dumps(output)))
    result = workflows.categorize_risks("Vatten stiger 😀\nVatten stiger", object(), categories)
    assert result == [{"ID": "flood", "name": "Display flood", "evidence": expected}]
    if not expected:
        assert "rejected" in caplog.text


def test_duplicate_categories_merge_evidence(categories, monkeypatch):
    monkeypatch.setattr(workflows, "generate_text", Mock(return_value=json.dumps([
        {"ID": "flood", "evidence": ["Vatten"]},
        {"ID": "flood", "evidence": ["stiger", "Vatten"]},
    ])))
    assert workflows.categorize_risks("Vatten stiger", object(), categories)[0]["evidence"] == ["Vatten", "stiger"]
