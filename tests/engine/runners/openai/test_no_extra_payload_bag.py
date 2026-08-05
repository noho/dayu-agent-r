"""Runner / payload 不接受 ``**kwargs`` / ``Any`` / ``set_tools`` 等 OLD 反例测试。"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import dayu.engine.runners.openai.payload as payload_module
from dayu.engine.contracts.runner import AsyncRunner
from dayu.engine.runners.openai.payload import build_request_payload
from dayu.engine.runners.openai.runner import AsyncOpenAIRunner


def test_call_signature_matches_protocol() -> None:
    """``AsyncOpenAIRunner.call`` 与 ``AsyncRunner.call`` 参数名一致、不含 kwargs。"""

    runner_sig = inspect.signature(AsyncOpenAIRunner.call)
    proto_sig = inspect.signature(AsyncRunner.call)
    runner_names = list(runner_sig.parameters.keys())
    proto_names = list(proto_sig.parameters.keys())
    assert runner_names == proto_names, (
        f"runner.call params {runner_names} != protocol {proto_names}"
    )
    for sig in (runner_sig, proto_sig):
        for p in sig.parameters.values():
            assert p.kind is not inspect.Parameter.VAR_KEYWORD
            assert p.kind is not inspect.Parameter.VAR_POSITIONAL


def test_no_set_tools() -> None:
    """OLD 的 ``set_tools`` 入口必须不存在。"""

    assert not hasattr(AsyncOpenAIRunner, "set_tools")


def test_build_request_payload_signature_no_kwargs() -> None:
    """Payload builder 只接受封闭的显式 keyword 参数。

    :returns: ``None``。
    :raises AssertionError: 参数集合、参数种类或 structured-output default
        不符合 owner contract 时抛出。
    """

    sig = inspect.signature(build_request_payload)
    expected = {
        "messages",
        "options",
        "tools",
        "spec",
        "structured_output",
    }
    assert set(sig.parameters.keys()) == expected
    for p in sig.parameters.values():
        assert p.kind is inspect.Parameter.KEYWORD_ONLY
    assert (
        sig.parameters["structured_output"].default
        is inspect.Parameter.empty
    )


def _payload_source_tree() -> ast.Module:
    """加载 ``payload.py`` 源码 AST。"""

    path = Path(payload_module.__file__).resolve()
    return ast.parse(path.read_text(encoding="utf-8"))


def test_payload_source_no_any() -> None:
    """``payload.py`` 不应 import ``typing.Any`` / 使用 ``Any`` 名字。"""

    tree = _payload_source_tree()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module == "typing":
                for alias in node.names:
                    assert alias.name != "Any", (
                        "payload.py must not import typing.Any"
                    )
        if isinstance(node, ast.Name) and node.id == "Any":
            raise AssertionError(
                "payload.py must not reference Any; use JsonValue / TypedDict"
            )


def test_payload_source_no_kwargs_in_signatures() -> None:
    """``payload.py`` 中函数签名一律不接受 ``**kwargs``。"""

    tree = _payload_source_tree()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert node.args.kwarg is None, (
                f"function {node.name!r} accepts **kwargs"
            )
