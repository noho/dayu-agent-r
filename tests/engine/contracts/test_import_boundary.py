"""``dayu.engine.contracts`` 包 import 边界测试。

通过 AST 扫描 ``dayu/engine/contracts/`` 下所有 ``.py`` 文件的 import
语句，确保：

- Engine 契约**不得**反向依赖 Host / Service / UI / fins。
- Engine 契约**不得**依赖任何具体 Runner 实现（``dayu.engine.runners``
  及其子树）；契约只描述协作协议，禁止落到实现细节。
- Engine 契约**不得**引入运行期 HTTP 客户端（``aiohttp`` / ``requests``
  / ``httpx``）；这些只属于 Runner 实现侧。
- Engine 契约**不得**引入 ``dayu.engine.tools`` / ``dayu.engine.processors``
  这两个上层包（它们目前不存在，但作为长期边界守卫继续断言）。

设计依据：``docs/code_review.md`` §4 / §5 / §5.1：``dayu.engine.contracts``
是 Engine 语义真源契约层，必须保持稳定边界。
"""

from __future__ import annotations

import ast
from pathlib import Path

import dayu.engine.contracts as engine_contracts

ENGINE_CONTRACTS_FORBIDDEN_PREFIXES: tuple[str, ...] = (
    "dayu.host",
    "dayu.service",
    "dayu.ui",
    "dayu.fins",
    "dayu.engine.runners",
    "dayu.engine.tools",
    "dayu.engine.processors",
    "aiohttp",
    "requests",
    "httpx",
)

ENGINE_CONTRACTS_FORBIDDEN_SUBSTRINGS: tuple[str, ...] = ("tool_trace",)


def _engine_contracts_root() -> Path:
    """返回 ``dayu/engine/contracts/`` 的源码根目录路径。

    :returns: ``dayu/engine/contracts/`` 的绝对路径。
    """

    package_file = engine_contracts.__file__
    assert package_file is not None
    return Path(package_file).resolve().parent


def _iter_python_files() -> list[Path]:
    """递归收集 ``dayu/engine/contracts/`` 下所有 ``.py`` 文件。

    :returns: 排序后的文件路径列表，已排除 ``__pycache__``。
    """

    root = _engine_contracts_root()
    return sorted(
        p for p in root.rglob("*.py") if "__pycache__" not in p.parts
    )


def _imported_module_names(source: str) -> list[str]:
    """从源码 AST 中提取所有 ``import`` 与 ``from ... import`` 的模块名。

    :param source: Python 源码。
    :returns: 模块名列表。
    :raises SyntaxError: 当源码不合法时由 :func:`ast.parse` 抛出。
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
    """判断模块名是否命中任一禁止前缀。

    :param module: 模块名。
    :param prefixes: 禁止前缀元组。
    :returns: 命中返回 ``True``，否则 ``False``。
    """

    return any(module == p or module.startswith(p + ".") for p in prefixes)


def _matches_substring(module: str, substrings: tuple[str, ...]) -> bool:
    """判断模块名是否命中任一禁止子串。

    :param module: 模块名。
    :param substrings: 禁止子串元组。
    :returns: 命中返回 ``True``，否则 ``False``。
    """

    return any(s in module for s in substrings)


def test_engine_contracts_does_not_import_forbidden_modules() -> None:
    """Engine 契约层不得反向依赖上层 / 实现层 / 运行期 HTTP 客户端。"""

    violations: list[tuple[str, str]] = []
    for file_path in _iter_python_files():
        for module in _imported_module_names(
            file_path.read_text(encoding="utf-8")
        ):
            if _matches_prefix(module, ENGINE_CONTRACTS_FORBIDDEN_PREFIXES):
                violations.append((str(file_path), module))
            elif _matches_substring(
                module, ENGINE_CONTRACTS_FORBIDDEN_SUBSTRINGS
            ):
                violations.append((str(file_path), module))
    assert not violations, (
        f"forbidden imports in dayu.engine.contracts: {violations}"
    )
