"""``dayu.contracts`` 包 import 边界测试。

通过 AST 扫描 ``dayu/contracts/`` 下所有 ``.py`` 文件的 import 语句，
确保：

- 永久禁止：``dayu.engine`` / ``dayu.host`` / ``dayu.runtime`` /
  ``dayu.service`` / ``dayu.ui`` / ``dayu.fins``（任意子模块）。
- Phase 0 当前禁止：``aiohttp`` / ``requests`` / ``httpx``。

公共契约层不允许反向依赖任何上层包。
"""

from __future__ import annotations

import ast
from pathlib import Path

import dayu.contracts as contracts

PHASE0_FORBIDDEN_PREFIXES: tuple[str, ...] = ("aiohttp", "requests", "httpx")

CONTRACTS_PERMANENT_FORBIDDEN_PREFIXES: tuple[str, ...] = (
    "dayu.engine",
    "dayu.host",
    "dayu.runtime",
    "dayu.service",
    "dayu.ui",
    "dayu.fins",
)


def _contracts_root() -> Path:
    """返回 ``dayu/contracts/`` 的源码根目录路径。

    :returns: ``dayu/contracts/`` 的绝对路径。
    """

    package_file = contracts.__file__
    assert package_file is not None
    return Path(package_file).resolve().parent


def _iter_python_files() -> list[Path]:
    """递归收集 ``dayu/contracts/`` 下所有 ``.py`` 文件。

    :returns: 排序后的文件路径列表，已排除 ``__pycache__``。
    """

    root = _contracts_root()
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def _imported_module_names(source: str) -> list[str]:
    """从源码 AST 中提取所有 ``import`` 与 ``from ... import`` 的模块名。

    :param source: Python 源码字符串。
    :returns: 模块名列表（按 AST 出现顺序）。
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
    """判断模块名是否命中任一禁止前缀（包括等于本身或为子模块）。

    :param module: 待判定的模块名。
    :param prefixes: 禁止前缀元组。
    :returns: 命中返回 ``True``，否则 ``False``。
    """

    return any(module == p or module.startswith(p + ".") for p in prefixes)


def test_contracts_does_not_import_phase0_forbidden_modules() -> None:
    """Phase 0 暂时禁止的运行期模块不得被 ``dayu.contracts`` 导入。"""

    violations: list[tuple[str, str]] = []
    for file_path in _iter_python_files():
        for module in _imported_module_names(
            file_path.read_text(encoding="utf-8")
        ):
            if _matches_prefix(module, PHASE0_FORBIDDEN_PREFIXES):
                violations.append((str(file_path), module))
    assert not violations, f"Phase 0 forbidden imports: {violations}"


def test_contracts_does_not_import_upper_layers() -> None:
    """``dayu.contracts`` 永久禁止反向依赖任何上层包。"""

    violations: list[tuple[str, str]] = []
    for file_path in _iter_python_files():
        for module in _imported_module_names(
            file_path.read_text(encoding="utf-8")
        ):
            if _matches_prefix(module, CONTRACTS_PERMANENT_FORBIDDEN_PREFIXES):
                violations.append((str(file_path), module))
    assert not violations, f"reverse-dependency imports: {violations}"
