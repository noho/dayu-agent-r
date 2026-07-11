"""Engine 包 import 边界测试。

通过 AST 扫描 ``dayu/engine/`` 下所有 ``.py`` 文件的 import 语句，确保：

- Phase 1 起 ``aiohttp`` 仅允许出现在 ``dayu/engine/runners/openai/``
  子树（OpenAI Runner 实现）；其它子树禁止。
- Engine core 永久禁止：``requests`` / ``httpx`` / ``dayu.host`` /
  ``dayu.service`` / ``dayu.ui`` / ``dayu.fins`` / ``dayu.documents`` /
  ``dayu.engine.tools`` / ``dayu.engine.processors`` / 任何 ``*tool_trace*`` 模块。
"""

from __future__ import annotations

import ast
from pathlib import Path

import dayu.engine as engine

# Phase 1：``aiohttp`` 在 OpenAI Runner 实现子树放开；其它仍禁。
GLOBAL_FORBIDDEN_PREFIXES: tuple[str, ...] = ("requests", "httpx")
AIOHTTP_PREFIX: str = "aiohttp"
AIOHTTP_ALLOWED_SUBPATH: tuple[str, ...] = ("runners", "openai")

ENGINE_CORE_FORBIDDEN_PREFIXES: tuple[str, ...] = (
    "dayu.host",
    "dayu.service",
    "dayu.ui",
    "dayu.fins",
    "dayu.documents",
    "dayu.engine.tools",
    "dayu.engine.processors",
)

ENGINE_CORE_FORBIDDEN_SUBSTRINGS: tuple[str, ...] = ("tool_trace",)
ENGINE_TOOL_DECLARATION_MODULE: str = "dayu.contracts.tool_declaration"
ENGINE_TOOL_DECLARATION_FORBIDDEN_MODULES: tuple[str, ...] = (
    ENGINE_TOOL_DECLARATION_MODULE,
)
ENGINE_TOOL_OWNERSHIP_FORBIDDEN_SYMBOLS: frozenset[str] = frozenset(
    {"ToolRuntime", "ToolBundle", "ToolCallable", "ToolDefinition"}
)
ENGINE_TOOL_DECLARATION_STAR_IMPORT_FORBIDDEN_SYMBOLS: frozenset[str] = frozenset(
    {"ToolBundle", "ToolCallable", "ToolDefinition"}
)
STAR_IMPORT_SYMBOL: str = "*"


def _engine_root() -> Path:
    """返回 ``dayu/engine/`` 的源码根目录路径。"""

    package_file = engine.__file__
    assert package_file is not None
    return Path(package_file).resolve().parent


def _tests_engine_root() -> Path:
    """返回 ``tests/engine/`` 的测试根目录路径。

    :returns: tests/engine 目录路径。
    :raises AssertionError: 目录不存在时抛出。
    """

    root = Path(__file__).resolve().parent
    assert root.name == "engine"
    return root


def _iter_engine_python_files() -> list[Path]:
    """递归收集 ``dayu/engine/`` 下所有 ``.py`` 文件。"""

    root = _engine_root()
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def _iter_engine_agent_test_files() -> list[Path]:
    """收集非 OpenAI runner 专项的 Engine 测试文件。

    :returns: tests/engine 下排除 runners/openai 子树后的 Python 文件。
    :raises Exception: 不主动抛出异常。
    """

    root = _tests_engine_root()
    return sorted(
        p
        for p in root.rglob("*.py")
        if "__pycache__" not in p.parts
        and p.relative_to(root).parts[:2] != ("runners", "openai")
    )


def _imported_module_names(source: str) -> list[str]:
    """从源码 AST 中提取所有 ``import`` 与 ``from ... import`` 的模块名。"""

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


def _imported_symbol_refs(source: str) -> list[tuple[str, str]]:
    """从源码 AST 中提取 ``from ... import ...`` 的模块与符号名。

    :param source: Python 源码。
    :returns: ``(module, symbol)`` 列表。
    """

    tree = ast.parse(source)
    refs: list[tuple[str, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module is not None and node.level == 0:
                for alias in node.names:
                    refs.append((node.module, alias.name))
    return refs


def _engine_tool_ownership_import_violations(
    file_path: Path, source: str
) -> list[tuple[str, str, str]]:
    """提取 Engine 工具 owner 导入违规。

    :param file_path: 被扫描的源码文件路径。
    :param source: Python 源码。
    :returns: ``(file_path, module, symbol)`` 违规列表。
    :raises SyntaxError: 源码无法解析时由 :func:`ast.parse` 抛出。
    """

    violations: list[tuple[str, str, str]] = []
    for module in _imported_module_names(source):
        if _matches_prefix(module, ENGINE_TOOL_DECLARATION_FORBIDDEN_MODULES):
            violations.append((str(file_path), module, "module"))
    for module, symbol in _imported_symbol_refs(source):
        if symbol in ENGINE_TOOL_OWNERSHIP_FORBIDDEN_SYMBOLS:
            violations.append((str(file_path), module, symbol))
            continue
        if module == ENGINE_TOOL_DECLARATION_MODULE and symbol == STAR_IMPORT_SYMBOL:
            for forbidden_symbol in sorted(
                ENGINE_TOOL_DECLARATION_STAR_IMPORT_FORBIDDEN_SYMBOLS
            ):
                violations.append((str(file_path), module, forbidden_symbol))
    return violations


def _matches_prefix(module: str, prefixes: tuple[str, ...]) -> bool:
    """判断模块名是否命中任一禁止前缀。"""

    return any(module == p or module.startswith(p + ".") for p in prefixes)


def _matches_substring(module: str, substrings: tuple[str, ...]) -> bool:
    """判断模块名是否命中任一禁止子串。"""

    return any(s in module for s in substrings)


def _path_inside_allowed_aiohttp_subtree(file_path: Path) -> bool:
    """文件是否位于 ``dayu/engine/runners/openai/`` 子树。"""

    try:
        rel = file_path.relative_to(_engine_root())
    except ValueError:
        return False
    parts = rel.parts
    return (
        len(parts) >= len(AIOHTTP_ALLOWED_SUBPATH)
        and parts[: len(AIOHTTP_ALLOWED_SUBPATH)] == AIOHTTP_ALLOWED_SUBPATH
    )


def test_engine_does_not_import_phase0_forbidden_modules() -> None:
    """``requests`` / ``httpx`` 全局禁止；``aiohttp`` 仅 openai runner 子树允许。"""

    violations: list[tuple[str, str]] = []
    for file_path in _iter_engine_python_files():
        for module in _imported_module_names(file_path.read_text(encoding="utf-8")):
            if _matches_prefix(module, GLOBAL_FORBIDDEN_PREFIXES):
                violations.append((str(file_path), module))
                continue
            if _matches_prefix(module, (AIOHTTP_PREFIX,)):
                if not _path_inside_allowed_aiohttp_subtree(file_path):
                    violations.append((str(file_path), module))
    assert not violations, f"forbidden HTTP client imports: {violations}"


def test_engine_does_not_import_engine_core_forbidden_modules() -> None:
    """Engine core 永久禁止导入的模块不得被 Engine 导入。"""

    violations: list[tuple[str, str]] = []
    for file_path in _iter_engine_python_files():
        for module in _imported_module_names(file_path.read_text(encoding="utf-8")):
            if _matches_prefix(module, ENGINE_CORE_FORBIDDEN_PREFIXES):
                violations.append((str(file_path), module))
            elif _matches_substring(module, ENGINE_CORE_FORBIDDEN_SUBSTRINGS):
                violations.append((str(file_path), module))
    assert not violations, f"Engine core forbidden imports: {violations}"


def test_engine_does_not_import_toolruntime_or_tool_declaration_owners() -> None:
    """Engine 不得导入 Host / ToolRuntime 拥有的工具声明对象。"""

    violations: list[tuple[str, str, str]] = []
    for file_path in _iter_engine_python_files():
        violations.extend(
            _engine_tool_ownership_import_violations(
                file_path, file_path.read_text(encoding="utf-8")
            )
        )
    assert not violations, f"Engine forbidden tool owner imports: {violations}"


def test_engine_agent_tests_do_not_import_openai_runner_internals() -> None:
    """Agent / contract 测试不得依赖 OpenAI runner 实现模块。

    :returns: ``None``。
    :raises AssertionError: 非 runner-specific 测试导入 OpenAI runner 时抛出。
    """

    forbidden_prefix = "dayu.engine.runners.openai"
    violations: list[tuple[str, str]] = []
    for file_path in _iter_engine_agent_test_files():
        for module in _imported_module_names(file_path.read_text(encoding="utf-8")):
            if module == forbidden_prefix or module.startswith(forbidden_prefix + "."):
                violations.append((str(file_path), module))
    assert not violations, f"Engine Agent tests import OpenAI runner internals: {violations}"


def test_engine_tool_ownership_boundary_detects_tool_declaration_star_import() -> None:
    """Engine ownership 边界测试必须覆盖工具声明模块的 star import。

    :returns: 无返回值。
    :raises AssertionError: star import 未被识别为工具 owner 导入违规时抛出。
    """

    file_path = _engine_root() / "synthetic_star_import.py"
    source = "from dayu.contracts.tool_declaration import *\n"

    assert _engine_tool_ownership_import_violations(file_path, source) == [
        (str(file_path), ENGINE_TOOL_DECLARATION_MODULE, "module"),
        (str(file_path), ENGINE_TOOL_DECLARATION_MODULE, "ToolBundle"),
        (str(file_path), ENGINE_TOOL_DECLARATION_MODULE, "ToolCallable"),
        (str(file_path), ENGINE_TOOL_DECLARATION_MODULE, "ToolDefinition"),
    ]
