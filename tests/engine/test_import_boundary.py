"""Engine 包 import 边界测试。

通过 AST 扫描 ``dayu/engine/`` 下所有 ``.py`` 文件的 import 语句，确保：

- Phase 1 起 ``aiohttp`` 仅允许出现在 ``dayu/engine/runners/openai/``
  子树（OpenAI Runner 实现）；其它子树禁止。
- Engine core 永久禁止：``requests`` / ``httpx`` / ``dayu.host`` /
  ``dayu.service`` / ``dayu.ui`` / ``dayu.fins`` / ``dayu.engine.tools``
  / ``dayu.engine.processors`` / 任何 ``*tool_trace*`` 模块。
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
    "dayu.engine.tools",
    "dayu.engine.processors",
)

ENGINE_CORE_FORBIDDEN_SUBSTRINGS: tuple[str, ...] = ("tool_trace",)


def _engine_root() -> Path:
    """返回 ``dayu/engine/`` 的源码根目录路径。"""

    package_file = engine.__file__
    assert package_file is not None
    return Path(package_file).resolve().parent


def _iter_engine_python_files() -> list[Path]:
    """递归收集 ``dayu/engine/`` 下所有 ``.py`` 文件。"""

    root = _engine_root()
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


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
