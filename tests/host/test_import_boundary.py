"""``dayu.host`` 包 import 边界测试。"""

from __future__ import annotations

import ast
from dataclasses import fields
from pathlib import Path

import dayu.host as host
from dayu.host.api import (
    CancelRunRequest,
    CancelSessionRunsRequest,
    CloseSessionRequest,
    CreateSessionRequest,
    EnsureSessionRequest,
    PurgeSessionRequest,
    ReplayRunRequest,
    ResolveWaitRequest,
    RetryRunRequest,
    StartRunRequest,
    SubmitFollowupRequest,
)

HOST_FORBIDDEN_PREFIXES: tuple[str, ...] = (
    "dayu.engine",
    "dayu.fins",
    "dayu.service",
    "dayu.ui",
)


def _host_root() -> Path:
    """返回 ``dayu/host/`` 源码根目录。

    :returns: ``dayu/host/`` 的绝对路径。
    :raises AssertionError: Host 包缺少 ``__file__`` 时抛出。
    """

    package_file = host.__file__
    assert package_file is not None
    return Path(package_file).resolve().parent


def _iter_python_files() -> list[Path]:
    """递归收集 ``dayu/host/`` 下所有 ``.py`` 文件。

    :returns: 排序后的源码文件路径列表。
    """

    root = _host_root()
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def _imported_module_names(source: str) -> list[str]:
    """从源码 AST 中提取绝对 import 的模块名。

    :param source: Python 源码字符串。
    :returns: 模块名列表。
    :raises SyntaxError: 源码无法解析时由 :func:`ast.parse` 抛出。
    """

    tree = ast.parse(source)
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module is not None and node.level == 0:
                names.append(node.module)
    return names


def _matches_prefix(module: str, prefixes: tuple[str, ...]) -> bool:
    """判断模块名是否命中禁止前缀。

    :param module: 待判定模块名。
    :param prefixes: 禁止前缀集合。
    :returns: 命中返回 ``True``，否则返回 ``False``。
    """

    return any(module == prefix or module.startswith(prefix + ".") for prefix in prefixes)


def test_host_does_not_import_upper_or_business_layers() -> None:
    """``dayu.host`` 不得导入 Engine / Fins / Service / UI。"""

    violations: list[tuple[str, str]] = []
    for file_path in _iter_python_files():
        for module in _imported_module_names(
            file_path.read_text(encoding="utf-8")
        ):
            if _matches_prefix(module, HOST_FORBIDDEN_PREFIXES):
                violations.append((str(file_path), module))
    assert not violations, f"host forbidden imports: {violations}"


def test_host_request_dataclasses_do_not_carry_tool_bundle() -> None:
    """per-run / command request 不得携带 business ``ToolBundle`` 字段。"""

    request_fields = (
        *fields(EnsureSessionRequest),
        *fields(CreateSessionRequest),
        *fields(CloseSessionRequest),
        *fields(PurgeSessionRequest),
        *fields(StartRunRequest),
        *fields(CancelRunRequest),
        *fields(CancelSessionRunsRequest),
        *fields(SubmitFollowupRequest),
        *fields(RetryRunRequest),
        *fields(ReplayRunRequest),
        *fields(ResolveWaitRequest),
    )

    assert "business_tool_bundle" not in {
        request_field.name for request_field in request_fields
    }
