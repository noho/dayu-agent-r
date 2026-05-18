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
    "dayu.config",
    "dayu.fins",
    "dayu.service",
    "dayu.ui",
)
RUNTIME_FORBIDDEN_PREFIXES: tuple[str, ...] = (
    "dayu.host",
    "dayu.engine",
    "dayu.service",
    "dayu.ui",
    "dayu.fins",
)
HOST_BUSINESS_TOOL_SCAN_FORBIDDEN_PREFIXES: tuple[str, ...] = (
    "importlib",
    "pkgutil",
)
FETCH_MORE_ALLOWED_RELATIVE_FILES: frozenset[str] = frozenset(
    {"host/tool_runtime.py", "host/tooling.py"}
)
FETCH_MORE_OWNERSHIP_TOKEN: str = "fetch_more"
ENGINE_FORBIDDEN_PREFIXES: tuple[str, ...] = ("dayu.host",)
HOST_ENGINE_CONTRACT_ALLOWED_MODULES: tuple[str, ...] = (
    "_execution_config_projection.py",
    "api.py",
    "dispatch.py",
    "engine_ingest.py",
    "local_proxy.py",
    "run_input.py",
)
PROJECTION_MODULES: tuple[str, ...] = (
    "projection.py",
    "durable/projection.py",
    "read_model.py",
    "durable/read_model.py",
)
PROJECTION_FORBIDDEN_PREFIXES: tuple[str, ...] = (
    "dayu.engine",
    "dayu.service",
    "dayu.ui",
    "dayu.fins",
    "dayu.config",
    "dayu.runtime",
    "dayu.host.admission",
    "dayu.host.waiting",
    "dayu.host.engine_ingest",
    "dayu.host.dispatch",
    "dayu.host.recovery",
)
READ_API_EVENT_STREAM_FORBIDDEN_PREFIXES: tuple[str, ...] = (
    "dayu.host.projection",
    "dayu.host.durable.projection",
    "dayu.host.read_model",
    "dayu.host.fanout",
    "dayu.host.notification",
)
READ_API_EVENT_STREAM_FORBIDDEN_TOKENS: tuple[str, ...] = (
    "host_projection_checkpoints",
    "host_projection_failures",
    "host_session_timeline_items",
    "repair_minimal_read_models",
    "fanout",
    "wakeup",
)
HOST_ROOT_FORBIDDEN_TOOL_EXPORTS: frozenset[str] = frozenset(
    {"ToolRuntime", "ToolRuntimeHandle", "ToolBundle", "ToolDefinition"}
)
TOOL_RUNTIME_SCHEMA_PROJECTION_FORBIDDEN_PREFIXES: tuple[str, ...] = (
    "dayu.engine",
    "dayu.service",
    "dayu.ui",
    "dayu.fins",
    "dayu.host.dispatch",
    "dayu.host.engine_ingest",
    "dayu.host.projection",
    "dayu.host.waiting",
)
MEMORY_MODULES: tuple[str, ...] = (
    "memory.py",
    "memory_repair.py",
    "durable/memory.py",
)
MEMORY_FORBIDDEN_PREFIXES: tuple[str, ...] = (
    "dayu.engine",
    "dayu.service",
    "dayu.ui",
    "dayu.fins",
)


def _host_root() -> Path:
    """返回 ``dayu/host/`` 源码根目录。

    :returns: ``dayu/host/`` 的绝对路径。
    :raises AssertionError: Host 包缺少 ``__file__`` 时抛出。
    """

    package_file = host.__file__
    assert package_file is not None
    return Path(package_file).resolve().parent


def _package_root(package_file: str | None) -> Path:
    """返回包源码根目录。

    :param package_file: 包 ``__file__`` 值。
    :returns: 包源码根目录。
    :raises AssertionError: 包缺少 ``__file__`` 时抛出。
    """

    assert package_file is not None
    return Path(package_file).resolve().parent


def _iter_python_files(root: Path) -> list[Path]:
    """递归收集指定源码根目录下所有 ``.py`` 文件。

    :param root: 源码根目录。
    :returns: 排序后的源码文件路径列表。
    """

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
    """``dayu.host`` 不得导入 Config / Fins / Service / UI。"""

    violations: list[tuple[str, str]] = []
    for file_path in _iter_python_files(_host_root()):
        for module in _imported_module_names(
            file_path.read_text(encoding="utf-8")
        ):
            if _matches_prefix(module, HOST_FORBIDDEN_PREFIXES):
                violations.append((str(file_path), module))
    assert not violations, f"host forbidden imports: {violations}"


def test_host_does_not_import_business_tool_scanners() -> None:
    """Host 不得通过 importlib / pkgutil 扫描业务工具模块。

    :returns: ``None``。
    :raises AssertionError: Host 模块导入动态模块扫描能力时抛出。
    """

    violations: list[tuple[str, str]] = []
    for file_path in _iter_python_files(_host_root()):
        for module in _imported_module_names(file_path.read_text(encoding="utf-8")):
            if _matches_prefix(module, HOST_BUSINESS_TOOL_SCAN_FORBIDDEN_PREFIXES):
                violations.append((str(file_path), module))
    assert not violations, f"host business tool scanner imports: {violations}"


def test_fetch_more_token_stays_inside_toolruntime_owner_modules() -> None:
    """``fetch_more`` 只能出现在 ToolRuntime factory / tooling policy owner。

    :returns: ``None``。
    :raises AssertionError: Host 其它模块或 Engine / contracts / runtime 引用
        ``fetch_more`` 时抛出。
    """

    dayu_root = _host_root().parent
    violations: list[str] = []
    for file_path in _iter_python_files(dayu_root):
        relative_path = file_path.relative_to(dayu_root).as_posix()
        if relative_path in FETCH_MORE_ALLOWED_RELATIVE_FILES:
            continue
        if FETCH_MORE_OWNERSHIP_TOKEN in file_path.read_text(encoding="utf-8"):
            violations.append(str(file_path))
    assert not violations, f"fetch_more references outside ToolRuntime owner: {violations}"


def test_host_engine_imports_stay_on_allowed_boundary_modules() -> None:
    """Host 只有本地执行边界模块可依赖 Engine contracts / entry。"""

    violations: list[tuple[str, str]] = []
    for file_path in _iter_python_files(_host_root()):
        for module in _imported_module_names(
            file_path.read_text(encoding="utf-8")
        ):
            if _matches_prefix(module, ("dayu.engine",)) and (
                file_path.name not in HOST_ENGINE_CONTRACT_ALLOWED_MODULES
            ):
                violations.append((str(file_path), module))
    assert not violations, f"unexpected host engine imports: {violations}"


def test_runtime_does_not_import_host_or_engine_layers() -> None:
    """``dayu.runtime`` 不得反向导入 Host / Engine 等业务层。"""

    import dayu.runtime as runtime

    runtime_root = _package_root(runtime.__file__)
    violations: list[tuple[str, str]] = []
    for file_path in _iter_python_files(runtime_root):
        for module in _imported_module_names(
            file_path.read_text(encoding="utf-8")
        ):
            if _matches_prefix(module, RUNTIME_FORBIDDEN_PREFIXES):
                violations.append((str(file_path), module))
    assert not violations, f"runtime forbidden imports: {violations}"


def test_projection_modules_do_not_import_forbidden_layers_or_mutators() -> None:
    """projection modules 不得导入上层、runtime 或 Host mutator owner。"""

    host_root = _host_root()
    violations: list[tuple[str, str]] = []
    for relative_path in PROJECTION_MODULES:
        file_path = host_root / relative_path
        for module in _imported_module_names(
            file_path.read_text(encoding="utf-8")
        ):
            if _matches_prefix(module, PROJECTION_FORBIDDEN_PREFIXES):
                violations.append((str(file_path), module))
    assert not violations, f"projection forbidden imports: {violations}"


def test_read_api_stream_does_not_reference_projection_or_fanout_truth() -> None:
    """read_api 不得引用 projection / fanout / repair 作为 stream truth。"""

    file_path = _host_root() / "read_api.py"
    source = file_path.read_text(encoding="utf-8")
    imported_violations: list[str] = []
    for module in _imported_module_names(source):
        if _matches_prefix(module, READ_API_EVENT_STREAM_FORBIDDEN_PREFIXES):
            imported_violations.append(module)
    token_violations = tuple(
        token for token in READ_API_EVENT_STREAM_FORBIDDEN_TOKENS if token in source
    )

    assert not imported_violations, (
        f"read_api forbidden stream imports: {imported_violations}"
    )
    assert not token_violations, (
        f"read_api forbidden stream truth tokens: {token_violations}"
    )


def test_host_root_does_not_export_toolruntime_or_tool_declaration_owners() -> None:
    """``dayu.host`` 包根不得导出 ToolRuntime 或工具声明 owner。"""

    root_exports = frozenset(host.__all__)
    root_namespace = vars(host)
    assert HOST_ROOT_FORBIDDEN_TOOL_EXPORTS.isdisjoint(root_exports)
    for symbol in HOST_ROOT_FORBIDDEN_TOOL_EXPORTS:
        assert symbol not in root_namespace


def test_toolruntime_schema_projection_stays_private_host_owner() -> None:
    """ToolRuntime schema 投影 helper 不得依赖 Engine 或 Host mutator owner。"""

    file_path = _host_root() / "tool_runtime_schema_projection.py"
    violations: list[str] = []
    for module in _imported_module_names(file_path.read_text(encoding="utf-8")):
        if _matches_prefix(
            module, TOOL_RUNTIME_SCHEMA_PROJECTION_FORBIDDEN_PREFIXES
        ):
            violations.append(module)
    assert not violations, (
        f"tool runtime schema projection forbidden imports: {violations}"
    )


def test_memory_modules_do_not_import_upper_business_or_engine_layers() -> None:
    """memory 模块不得依赖 Engine、Service、UI 或 Fins 实现层。

    :returns: ``None``。
    :raises AssertionError: memory 模块出现禁止 import 时抛出。
    """

    host_root = _host_root()
    violations: list[tuple[str, str]] = []
    for relative_path in MEMORY_MODULES:
        file_path = host_root / relative_path
        for module in _imported_module_names(
            file_path.read_text(encoding="utf-8")
        ):
            if _matches_prefix(module, MEMORY_FORBIDDEN_PREFIXES):
                violations.append((str(file_path), module))
    assert not violations, f"memory forbidden imports: {violations}"


def test_engine_does_not_import_host_layer() -> None:
    """``dayu.engine`` 不得反向依赖 Host。"""

    import dayu.engine as engine

    engine_root = _package_root(engine.__file__)
    violations: list[tuple[str, str]] = []
    for file_path in _iter_python_files(engine_root):
        for module in _imported_module_names(
            file_path.read_text(encoding="utf-8")
        ):
            if _matches_prefix(module, ENGINE_FORBIDDEN_PREFIXES):
                violations.append((str(file_path), module))
    assert not violations, f"engine forbidden imports: {violations}"


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
