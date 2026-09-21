"""Executable preservation contract against the complete, pinned upstream snapshot."""

import ast
import hashlib
import importlib.util
import inspect
import json
import tarfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import translation_agent
from translation_agent import runtime, utils

ROOT = Path(__file__).resolve().parents[1]
PROVENANCE = ROOT / "docs/upstream/translation-agent"


@pytest.fixture(scope="module")
def pristine(tmp_path_factory):
    destination = tmp_path_factory.mktemp("upstream")
    with tarfile.open(PROVENANCE / "source.tar.gz") as archive:
        archive.extractall(destination, filter="data")
    return destination


@pytest.fixture
def original(monkeypatch, pristine):
    import openai

    spec = importlib.util.spec_from_file_location(
        "pristine_translation_agent", pristine / "src/translation_agent/utils.py"
    )
    module = importlib.util.module_from_spec(spec)
    # Import the original exactly, without a live credential or network request.
    with monkeypatch.context() as scoped:
        scoped.setattr(openai, "OpenAI", lambda **kwargs: SimpleNamespace())
        spec.loader.exec_module(module)
    return module


def test_complete_upstream_tree_is_retained_byte_for_byte(pristine):
    manifest = json.loads((PROVENANCE / "UPSTREAM.json").read_text())
    assert manifest["commit"] == "e0fc605acbb5d78cb7a58a98bc8bd8f0056df49c"
    for relative, digest in manifest["sha256"].items():
        assert hashlib.sha256((pristine / relative).read_bytes()).hexdigest() == digest, relative
    assert {
        "app/app.py",
        "app/process.py",
        "app/patch.py",
        "examples/example_script.py",
        "tests/test_agent.py",
        "pyproject.toml",
    } <= manifest["sha256"].keys()


def test_relocated_business_functions_are_original_bodies_with_only_runtime_hooks(pristine):
    original_tree = ast.parse((pristine / "src/translation_agent/utils.py").read_text())
    relocated_tree = ast.parse(Path(utils.__file__).read_text())

    class RemoveBinding(ast.NodeTransformer):
        def visit_Call(self, node):
            self.generic_visit(node)
            if (
                isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "_runtime"
                and node.func.attr == "complete"
            ):
                return ast.Call(func=node.args[2], args=node.args[3:], keywords=node.keywords)
            return node

    originals = {n.name: n for n in original_tree.body if isinstance(n, ast.FunctionDef)}
    relocated = {
        n.name: RemoveBinding().visit(n)
        for n in relocated_tree.body
        if isinstance(n, ast.FunctionDef)
    }
    assert originals.keys() == relocated.keys()
    for name in originals.keys() - {"get_completion"}:
        assert ast.dump(originals[name]) == ast.dump(relocated[name]), name


@pytest.mark.parametrize("country", ["", "Mexico"])
@pytest.mark.parametrize(
    "function,args",
    [
        ("one_chunk_initial_translation", ["English", "Spanish", "Hello world"]),
        ("one_chunk_reflect_on_translation", ["English", "Spanish", "Hello world", "Hola mundo"]),
        (
            "one_chunk_improve_translation",
            ["English", "Spanish", "Hello world", "Hola mundo", "Keep the tone"],
        ),
        ("multichunk_initial_translation", ["English", "Spanish", ["Hello ", "world"]]),
        (
            "multichunk_reflect_on_translation",
            ["English", "Spanish", ["Hello ", "world"], ["Hola ", "mundo"]],
        ),
        (
            "multichunk_improve_translation",
            ["English", "Spanish", ["Hello ", "world"], ["Hola ", "mundo"], ["Note 1", "Note 2"]],
        ),
    ],
)
def test_stage_defaults_and_return_contract_match_original(
    original, monkeypatch, country, function, args
):
    original_calls, relocated_calls = [], []

    def completion(log):
        def run(*args, **kwargs):
            log.append((args, kwargs))
            return f"result-{len(log)}"

        return run

    monkeypatch.setattr(original, "get_completion", completion(original_calls))
    monkeypatch.setattr(utils, "get_completion", completion(relocated_calls))
    kwargs = {"country": country} if "reflect" in function else {}
    assert getattr(original, function)(*args, **kwargs) == getattr(utils, function)(*args, **kwargs)
    assert original_calls == relocated_calls
    assert inspect.signature(getattr(original, function)) == inspect.signature(
        getattr(utils, function)
    )


@pytest.mark.parametrize("json_mode", [False, True])
def test_standalone_sdk_contract_preserved(original, monkeypatch, json_mode):
    first, second = Mock(), Mock()
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content='{"result":"ok"}'))]
    )
    first.chat.completions.create.return_value = response
    second.chat.completions.create.return_value = response
    monkeypatch.setattr(original, "client", first)
    monkeypatch.setattr(utils, "client", second)
    assert original.get_completion(
        "prompt", "system", "model", 0.4, json_mode
    ) == utils.get_completion("prompt", "system", "model", 0.4, json_mode)
    assert first.chat.completions.create.call_args == second.chat.completions.create.call_args


def test_host_binding_never_constructs_another_sdk_client(monkeypatch):
    import openai

    monkeypatch.setattr(utils, "client", None)
    monkeypatch.setattr(openai, "OpenAI", Mock(side_effect=AssertionError("second client")))
    with runtime.bind(lambda *args, **kwargs: "complete translation"):
        assert (
            translation_agent.translate("English", "Chinese", "Hello", "") == "complete translation"
        )
    assert utils.client is None


def test_original_chunk_size_behavior_is_not_silently_fixed(original):
    for count, limit in [(10, 1000), (1000, 1000), (1800, 1000), (6000, 1000)]:
        assert utils.calculate_chunk_size(count, limit) == original.calculate_chunk_size(
            count, limit
        )


@pytest.mark.parametrize("country", ["", "中国大陆"])
@pytest.mark.parametrize("long", [False, True])
def test_chinese_host_templates_preserve_original_workflow(original, monkeypatch, country, long):
    import copy

    from translation_fixture import EchoModel, source_from_prompt

    from youtube_strataread.workbench.translation import DEFAULTS, TranslationPipeline

    source = "A detailed statement about the project. " * (220 if long else 1)
    expected = []

    def complete(prompt, system_message="You are a helpful assistant.", **kwargs):
        expected.append(
            [{"role": "system", "content": system_message}, {"role": "user", "content": prompt}]
        )
        return source_from_prompt(prompt)

    monkeypatch.setattr(original, "get_completion", complete)
    translation = original.translate("English", "Simplified Chinese", source, country)
    model = EchoModel()
    config = copy.deepcopy(DEFAULTS)
    config["country"] = country
    result = TranslationPipeline(model, "shared-model", config).run(source, source_lang="English")
    assert result.translation == translation
    actual = [call[1] for call in model.calls if "完整译文：\n" not in call[1][-1]["content"]]
    assert len(actual) == len(expected)
    assert [source_from_prompt(messages[-1]["content"]) for messages in actual] == [
        source_from_prompt(messages[-1]["content"]) for messages in expected
    ]
    for messages in actual:
        assert "专业语言学家" in messages[0]["content"]
        assert "简体中文" in messages[0]["content"]
        assert "请" in messages[-1]["content"]
        assert "Your task" not in messages[-1]["content"]
    if country:
        assert any(country in messages[-1]["content"] for messages in actual)
    assert all(call[0] == "shared-model" for call in model.calls)


@pytest.mark.parametrize("filename", ["app.py", "process.py", "patch.py"])
def test_optional_ui_bodies_preserved_with_only_relative_imports(pristine, filename):
    expected = (pristine / "app" / filename).read_bytes()
    expected = expected.replace(b"from process import (", b"from .process import (").replace(
        b"from patch import (", b"from .patch import ("
    )
    assert (ROOT / "src/translation_agent/webui" / filename).read_bytes() == expected


def test_binding_is_context_local_and_restores_after_failure():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    barrier = Barrier(2)

    def run(value):
        with runtime.bind(lambda *args, **kwargs: value):
            barrier.wait(timeout=5)
            return translation_agent.translate("English", "Chinese", "source", "")

    with ThreadPoolExecutor(2) as pool:
        assert list(pool.map(run, ["first", "second"])) == ["first", "second"]
    with pytest.raises(RuntimeError), runtime.bind(lambda *args, **kwargs: "leaked"):
        raise RuntimeError("test")
    assert runtime.complete("function", {}, lambda: "standalone") == "standalone"
