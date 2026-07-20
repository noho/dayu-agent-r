"""``dayu.host`` 包 import 边界测试。"""

from __future__ import annotations

import ast
from dataclasses import fields
from pathlib import Path

import pytest

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
    {"host/tool_runtime.py", "host/tooling.py", "runtime/tools_discovery.py"}
)
FETCH_MORE_OWNERSHIP_TOKEN: str = "fetch_more"
OLD_FETCH_MORE_PROJECTION_TOKENS: tuple[str, ...] = (
    "fetch_more_args",
    "project_for_llm",
    "continuation_hint",
)
ENGINE_FORBIDDEN_PREFIXES: tuple[str, ...] = ("dayu.host",)
HOST_ENGINE_CONTRACT_ALLOWED_MODULES: tuple[str, ...] = (
    "_execution_config_projection.py",
    "_runner_call_manifest.py",
    "api.py",
    "compact_pipeline.py",
    "compaction_operation.py",
    "dispatch.py",
    "engine_ingest.py",
    "llm_compaction.py",
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
PURGE_DURABLE_MODULES: tuple[str, ...] = ("durable/purge.py",)
PURGE_DURABLE_FORBIDDEN_PREFIXES: tuple[str, ...] = (
    "dayu.config",
    "dayu.engine",
    "dayu.fins",
    "dayu.runtime",
    "dayu.service",
    "dayu.ui",
    "dayu.host.admission",
    "dayu.host.audit",
    "dayu.host.command",
    "dayu.host.dispatch",
    "dayu.host.open_host",
    "dayu.host.recovery",
)
WAIT_CALLBACK_FORBIDDEN_PREFIXES: tuple[str, ...] = (
    "dayu.service",
    "dayu.ui",
    "fastapi",
    "flask",
    "starlette",
    "django",
    "aiohttp",
)
MEMORY_SNAPSHOT_BUSINESS_TEST_FILES: tuple[str, ...] = (
    "tests/host/test_compact_material.py",
    "tests/host/test_run_input_builder.py",
    "tests/host/test_memory_projection.py",
)
MEMORY_SNAPSHOT_CONSTRUCTOR_SCAN_FILES: tuple[str, ...] = (
    "tests/host/test_compact_material.py",
    "tests/host/test_run_input_builder.py",
)
SNAPSHOT_DIGEST_KEYWORD = "snapshot_digest"
PENDING_SNAPSHOT_DIGEST_VALUE = "pending"
MEMORY_SNAPSHOT_CONSTRUCTOR_NAME = "ConversationMemorySnapshotVNext"


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


def _repo_root() -> Path:
    """返回当前仓库根目录。

    :returns: 仓库根目录。
    :raises AssertionError: 测试文件不在预期仓库布局内时抛出。
    """

    root = Path(__file__).resolve().parents[2]
    assert (root / "tests" / "host" / "test_import_boundary.py").is_file()
    return root


def _package_name_from_root(package_root: Path) -> tuple[str, ...]:
    """从 package root 路径解析绝对 Python package 前缀。

    :param package_root: 包源码根目录。
    :returns: package name parts。
    :raises AssertionError: 路径无法确定为 Python package 时抛出。
    """

    resolved_root = package_root.resolve()
    if not (resolved_root / "__init__.py").is_file():
        raise AssertionError(f"package root is not a package: {resolved_root}")

    names: list[str] = [resolved_root.name]
    current = resolved_root.parent
    while (current / "__init__.py").is_file():
        names.append(current.name)
        current = current.parent
    names.reverse()
    if not names:
        raise AssertionError(f"package prefix cannot be determined: {resolved_root}")
    return tuple(names)


def _relative_import_module_name(
    *,
    scanned_file: Path,
    package_root: Path,
    level: int,
    module: str | None,
) -> str:
    """把相对 ``from`` import 解析为绝对模块名。

    :param scanned_file: 被扫描源码文件路径。
    :param package_root: 本次扫描的 package root。
    :param level: AST ``ImportFrom.level``。
    :param module: AST ``ImportFrom.module``。
    :returns: 解析后的绝对模块名。
    :raises AssertionError: 文件不在 package root 下或相对回溯越界时抛出。
    """

    if level <= 0:
        raise AssertionError("relative import level must be positive")

    resolved_file = scanned_file.resolve()
    resolved_root = package_root.resolve()
    try:
        relative_file = resolved_file.relative_to(resolved_root)
    except ValueError as exc:
        raise AssertionError(
            f"scanned file is outside package root: file={resolved_file}, root={resolved_root}"
        ) from exc

    if relative_file.suffix != ".py":
        raise AssertionError(f"scanned file is not a Python source file: {resolved_file}")

    relative_package_parts = relative_file.parent.parts
    climb_count = level - 1
    if climb_count > len(relative_package_parts):
        raise AssertionError(
            "relative import exceeds package root: " f"file={resolved_file}, root={resolved_root}, level={level}"
        )

    package_parts = (
        *_package_name_from_root(resolved_root),
        *relative_package_parts[: len(relative_package_parts) - climb_count],
    )
    if module is not None:
        package_parts = (*package_parts, *module.split("."))
    if not package_parts:
        raise AssertionError(f"package prefix cannot be determined for relative import: {resolved_file}")
    return ".".join(package_parts)


def _imported_module_names(source: str, *, scanned_file: Path, package_root: Path) -> list[str]:
    """从源码 AST 中提取 import 的绝对模块名。

    :param source: Python 源码字符串。
    :param scanned_file: 被扫描源码文件路径。
    :param package_root: 本次扫描的 package root。
    :returns: 模块名列表。
    :raises AssertionError: 相对 import 无法确定解析边界时抛出。
    :raises SyntaxError: 源码无法解析时由 :func:`ast.parse` 抛出。
    """

    tree = ast.parse(source)
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                if node.module is None:
                    raise AssertionError("absolute ImportFrom must carry module")
                names.append(node.module)
            else:
                names.append(
                    _relative_import_module_name(
                        scanned_file=scanned_file,
                        package_root=package_root,
                        level=node.level,
                        module=node.module,
                    )
                )
    return names


def _matches_prefix(module: str, prefixes: tuple[str, ...]) -> bool:
    """判断模块名是否命中禁止前缀。

    :param module: 待判定模块名。
    :param prefixes: 禁止前缀集合。
    :returns: 命中返回 ``True``，否则返回 ``False``。
    """

    return any(module == prefix or module.startswith(prefix + ".") for prefix in prefixes)


def _write_test_package_file(path: Path, source: str) -> Path:
    """写入 import scanner 单元测试使用的临时 Python 文件。

    :param path: 目标文件路径。
    :param source: Python 源码。
    :returns: 目标文件路径。
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path


def _string_keyword_value_lines(source: str, *, keyword: str, value: str) -> list[int]:
    """返回指定字符串 keyword 参数值出现的源码行号。

    :param source: Python 源码字符串。
    :param keyword: 要扫描的 call keyword 名。
    :param value: 要匹配的字符串常量值。
    :returns: 命中的源码行号列表。
    :raises SyntaxError: 源码无法解析时由 :func:`ast.parse` 抛出。
    """

    tree = ast.parse(source)
    line_numbers: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for call_keyword in node.keywords:
            if call_keyword.arg != keyword:
                continue
            keyword_value = call_keyword.value
            if (
                isinstance(keyword_value, ast.Constant)
                and isinstance(keyword_value.value, str)
                and keyword_value.value == value
            ):
                line_numbers.append(keyword_value.lineno)
    return line_numbers


def _call_name_lines(source: str, *, call_name: str) -> list[int]:
    """返回指定函数或类调用名及简单别名出现的源码行号。

    :param source: Python 源码字符串。
    :param call_name: 要扫描的调用名。
    :returns: 命中的源码行号列表。
    :raises SyntaxError: 源码无法解析时由 :func:`ast.parse` 抛出。
    """

    tree = ast.parse(source)
    callable_names: set[str] = {call_name}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == call_name:
                    callable_names.add(alias.asname or alias.name)
        elif isinstance(node, ast.Assign) and _is_named_reference(node.value, call_name=call_name):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    callable_names.add(target.id)

    line_numbers: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        function = node.func
        if isinstance(function, ast.Name) and function.id in callable_names:
            line_numbers.append(function.lineno)
        elif isinstance(function, ast.Attribute) and function.attr == call_name:
            line_numbers.append(function.lineno)
    return line_numbers


def _is_named_reference(node: ast.expr, *, call_name: str) -> bool:
    """判断表达式是否直接引用指定名字。

    :param node: AST 表达式节点。
    :param call_name: 要匹配的名字。
    :returns: 直接引用该名字返回 ``True``，否则返回 ``False``。
    """

    return (
        isinstance(node, ast.Name)
        and node.id == call_name
        or isinstance(node, ast.Attribute)
        and node.attr == call_name
    )


def test_import_scanner_collects_absolute_imports(tmp_path: Path) -> None:
    """import scanner 收集 absolute import 模块名。"""

    package_root = tmp_path / "samplepkg"
    _write_test_package_file(package_root / "__init__.py", "")
    scanned_file = _write_test_package_file(
        package_root / "module.py",
        "import os\nfrom dayu.host import api\n",
    )

    assert _imported_module_names(
        scanned_file.read_text(encoding="utf-8"),
        scanned_file=scanned_file,
        package_root=package_root,
    ) == ["os", "dayu.host"]


def test_import_scanner_resolves_same_package_relative_import(
    tmp_path: Path,
) -> None:
    """import scanner 把同包相对 import 解析成绝对模块名。"""

    package_root = tmp_path / "samplepkg"
    _write_test_package_file(package_root / "__init__.py", "")
    _write_test_package_file(package_root / "subpkg" / "__init__.py", "")
    scanned_file = _write_test_package_file(
        package_root / "subpkg" / "module.py",
        "from .service import build\n",
    )

    assert _imported_module_names(
        scanned_file.read_text(encoding="utf-8"),
        scanned_file=scanned_file,
        package_root=package_root,
    ) == ["samplepkg.subpkg.service"]


def test_import_scanner_resolves_parent_package_relative_import(
    tmp_path: Path,
) -> None:
    """import scanner 把父包相对 import 解析成绝对模块名。"""

    package_root = tmp_path / "samplepkg"
    _write_test_package_file(package_root / "__init__.py", "")
    _write_test_package_file(package_root / "subpkg" / "__init__.py", "")
    scanned_file = _write_test_package_file(
        package_root / "subpkg" / "module.py",
        "from ..shared import value\n",
    )

    assert _imported_module_names(
        scanned_file.read_text(encoding="utf-8"),
        scanned_file=scanned_file,
        package_root=package_root,
    ) == ["samplepkg.shared"]


def test_import_scanner_resolves_no_module_relative_import(
    tmp_path: Path,
) -> None:
    """import scanner 对 ``from . import x`` 返回当前 package 前缀。"""

    package_root = tmp_path / "samplepkg"
    _write_test_package_file(package_root / "__init__.py", "")
    _write_test_package_file(package_root / "subpkg" / "__init__.py", "")
    scanned_file = _write_test_package_file(
        package_root / "subpkg" / "module.py",
        "from . import sibling\n",
    )

    assert _imported_module_names(
        scanned_file.read_text(encoding="utf-8"),
        scanned_file=scanned_file,
        package_root=package_root,
    ) == ["samplepkg.subpkg"]


def test_import_scanner_fails_loudly_for_unresolvable_relative_import(
    tmp_path: Path,
) -> None:
    """import scanner 对超出 package root 的相对 import fail loudly。"""

    package_root = tmp_path / "samplepkg"
    _write_test_package_file(package_root / "__init__.py", "")
    scanned_file = _write_test_package_file(
        package_root / "module.py",
        "from ..outside import value\n",
    )

    with pytest.raises(AssertionError, match="relative import exceeds package root"):
        _imported_module_names(
            scanned_file.read_text(encoding="utf-8"),
            scanned_file=scanned_file,
            package_root=package_root,
        )


def test_string_keyword_value_scan_uses_ast_not_literal_format() -> None:
    """keyword value scanner 不依赖源码字面格式。"""

    source = """
build_snapshot(
    snapshot_digest = 'pending',
)
build_snapshot(snapshot_digest="sha256:ok")
"""

    assert _string_keyword_value_lines(
        source,
        keyword=SNAPSHOT_DIGEST_KEYWORD,
        value=PENDING_SNAPSHOT_DIGEST_VALUE,
    ) == [3]


def test_call_name_scan_uses_ast_not_literal_format() -> None:
    """call name scanner 不依赖源码字面格式。"""

    source = """
from dayu.host.memory import ConversationMemorySnapshotVNext as MemorySnapshot
snapshot_alias = ConversationMemorySnapshotVNext
snapshot_alias(
    schema_version="conversation_memory_snapshot_v1",
)
factory.ConversationMemorySnapshotVNext(
    schema_version="conversation_memory_snapshot_v1",
)
ConversationMemorySnapshotVNext (
    schema_version="conversation_memory_snapshot_v1",
)
MemorySnapshot(
    schema_version="conversation_memory_snapshot_v1",
)
"""

    assert _call_name_lines(
        source,
        call_name=MEMORY_SNAPSHOT_CONSTRUCTOR_NAME,
    ) == [4, 7, 10, 13]


def test_memory_snapshot_business_tests_do_not_scatter_pending_digest() -> None:
    """业务测试不得散落 memory snapshot digest 中间态 sentinel。"""

    violations: list[str] = []
    repo_root = _repo_root()
    for relative_path in MEMORY_SNAPSHOT_BUSINESS_TEST_FILES:
        file_path = repo_root / relative_path
        for line_number in _string_keyword_value_lines(
            file_path.read_text(encoding="utf-8"),
            keyword=SNAPSHOT_DIGEST_KEYWORD,
            value=PENDING_SNAPSHOT_DIGEST_VALUE,
        ):
            violations.append(f"{relative_path}:{line_number}")

    assert not violations, f"snapshot digest sentinel scattered: {violations}"


def test_memory_snapshot_constructor_stays_in_shared_factory() -> None:
    """compact/run-input 业务测试不得直接构造 memory snapshot。"""

    violations: list[str] = []
    repo_root = _repo_root()
    for relative_path in MEMORY_SNAPSHOT_CONSTRUCTOR_SCAN_FILES:
        file_path = repo_root / relative_path
        for line_number in _call_name_lines(
            file_path.read_text(encoding="utf-8"),
            call_name=MEMORY_SNAPSHOT_CONSTRUCTOR_NAME,
        ):
            violations.append(f"{relative_path}:{line_number}")

    assert not violations, f"memory snapshot constructor outside factory: {violations}"


def test_host_does_not_import_upper_or_business_layers() -> None:
    """``dayu.host`` 不得导入 Config / Fins / Service / UI。"""

    violations: list[tuple[str, str]] = []
    host_root = _host_root()
    for file_path in _iter_python_files(host_root):
        for module in _imported_module_names(
            file_path.read_text(encoding="utf-8"),
            scanned_file=file_path,
            package_root=host_root,
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
    host_root = _host_root()
    for file_path in _iter_python_files(host_root):
        for module in _imported_module_names(
            file_path.read_text(encoding="utf-8"),
            scanned_file=file_path,
            package_root=host_root,
        ):
            if _matches_prefix(module, HOST_BUSINESS_TOOL_SCAN_FORBIDDEN_PREFIXES):
                violations.append((str(file_path), module))
    assert not violations, f"host business tool scanner imports: {violations}"


def test_fetch_more_token_stays_inside_toolruntime_owner_modules() -> None:
    """``fetch_more`` 只能出现在 ToolRuntime owner 模块中。

    :returns: ``None``。
    :raises AssertionError: Host 其它模块或 Engine / contracts / runtime 引用
        ``fetch_more``，或迁移代码引入 OLD fetch-more projection 时抛出。
    """

    dayu_root = _host_root().parent
    violations: list[str] = []
    old_projection_violations: list[str] = []
    for file_path in _iter_python_files(dayu_root):
        relative_path = file_path.relative_to(dayu_root).as_posix()
        source = file_path.read_text(encoding="utf-8")
        for token in OLD_FETCH_MORE_PROJECTION_TOKENS:
            if token in source:
                old_projection_violations.append(f"{relative_path}:{token}")
        if relative_path in FETCH_MORE_ALLOWED_RELATIVE_FILES:
            continue
        if FETCH_MORE_OWNERSHIP_TOKEN in source:
            violations.append(str(file_path))
    assert not violations, f"fetch_more references outside ToolRuntime owner: {violations}"
    assert not old_projection_violations, (
        "OLD fetch-more projection references migrated: " f"{old_projection_violations}"
    )


def test_host_engine_imports_stay_on_allowed_boundary_modules() -> None:
    """Host 只有本地执行边界模块可依赖 Engine contracts / entry。"""

    violations: list[tuple[str, str]] = []
    host_root = _host_root()
    for file_path in _iter_python_files(host_root):
        for module in _imported_module_names(
            file_path.read_text(encoding="utf-8"),
            scanned_file=file_path,
            package_root=host_root,
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
            file_path.read_text(encoding="utf-8"),
            scanned_file=file_path,
            package_root=runtime_root,
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
            file_path.read_text(encoding="utf-8"),
            scanned_file=file_path,
            package_root=host_root,
        ):
            if _matches_prefix(module, PROJECTION_FORBIDDEN_PREFIXES):
                violations.append((str(file_path), module))
    assert not violations, f"projection forbidden imports: {violations}"


def test_read_api_stream_does_not_reference_projection_or_fanout_truth() -> None:
    """read_api 不得引用 projection / fanout / repair 作为 stream truth。"""

    file_path = _host_root() / "read_api.py"
    source = file_path.read_text(encoding="utf-8")
    imported_violations: list[str] = []
    for module in _imported_module_names(
        source,
        scanned_file=file_path,
        package_root=_host_root(),
    ):
        if _matches_prefix(module, READ_API_EVENT_STREAM_FORBIDDEN_PREFIXES):
            imported_violations.append(module)
    token_violations = tuple(token for token in READ_API_EVENT_STREAM_FORBIDDEN_TOKENS if token in source)

    assert not imported_violations, f"read_api forbidden stream imports: {imported_violations}"
    assert not token_violations, f"read_api forbidden stream truth tokens: {token_violations}"


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
    for module in _imported_module_names(
        file_path.read_text(encoding="utf-8"),
        scanned_file=file_path,
        package_root=_host_root(),
    ):
        if _matches_prefix(module, TOOL_RUNTIME_SCHEMA_PROJECTION_FORBIDDEN_PREFIXES):
            violations.append(module)
    assert not violations, f"tool runtime schema projection forbidden imports: {violations}"


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
            file_path.read_text(encoding="utf-8"),
            scanned_file=file_path,
            package_root=host_root,
        ):
            if _matches_prefix(module, MEMORY_FORBIDDEN_PREFIXES):
                violations.append((str(file_path), module))
    assert not violations, f"memory forbidden imports: {violations}"


def test_purge_durable_module_stays_low_level_host_owner() -> None:
    """purge durable primitive 不得反向依赖上层或 public command owner。

    :returns: ``None``。
    :raises AssertionError: purge durable 模块导入上层、runtime 或 command /
        audit / dispatch owner 时抛出。
    """

    host_root = _host_root()
    violations: list[tuple[str, str]] = []
    for relative_path in PURGE_DURABLE_MODULES:
        file_path = host_root / relative_path
        for module in _imported_module_names(
            file_path.read_text(encoding="utf-8"),
            scanned_file=file_path,
            package_root=host_root,
        ):
            if _matches_prefix(module, PURGE_DURABLE_FORBIDDEN_PREFIXES):
                violations.append((str(file_path), module))
    assert not violations, f"purge durable forbidden imports: {violations}"


def test_wait_callback_adapter_has_no_service_ui_or_web_framework_dependency() -> None:
    """wait callback Host adapter 不得依赖 Service/UI 或 Web framework。"""

    file_path = _host_root() / "wait_callback.py"
    violations: list[str] = []
    for module in _imported_module_names(
        file_path.read_text(encoding="utf-8"),
        scanned_file=file_path,
        package_root=_host_root(),
    ):
        if _matches_prefix(module, WAIT_CALLBACK_FORBIDDEN_PREFIXES):
            violations.append(module)
    assert not violations, f"wait callback forbidden imports: {violations}"


def test_engine_does_not_import_host_layer() -> None:
    """``dayu.engine`` 不得反向依赖 Host。"""

    import dayu.engine as engine

    engine_root = _package_root(engine.__file__)
    violations: list[tuple[str, str]] = []
    for file_path in _iter_python_files(engine_root):
        for module in _imported_module_names(
            file_path.read_text(encoding="utf-8"),
            scanned_file=file_path,
            package_root=engine_root,
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

    assert "business_tool_bundle" not in {request_field.name for request_field in request_fields}
