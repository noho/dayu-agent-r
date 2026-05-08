"""Engine 不得 ``import dayu.runtime.log``。

按 ``docs/engine/phase1_5-plan.md``：``dayu.engine`` 各模块**只能**通过
stdlib ``logging.getLogger(__name__)`` 获得 logger，logger 装配由上层
（Host / CLI）通过 :mod:`dayu.runtime.log` 完成。Engine **允许**
``import dayu.runtime.cancellation`` 与无装配副作用的
``dayu.runtime.log_levels``。

本测试通过 AST 扫描 ``dayu/engine/`` 下所有 ``.py`` 文件的 ``import``
语句，确保没有任何 Engine 模块直接依赖 :mod:`dayu.runtime.log`。
"""

from __future__ import annotations

import ast
from pathlib import Path

import dayu.engine as engine

_FORBIDDEN_LOG_MODULE: str = "dayu.runtime.log"


def _engine_root() -> Path:
    """返回 ``dayu/engine/`` 的源码根目录路径。

    :returns: ``dayu/engine/`` 的绝对路径。
    """

    package_file = engine.__file__
    assert package_file is not None
    return Path(package_file).resolve().parent


def _iter_python_files() -> list[Path]:
    """递归收集 ``dayu/engine/`` 下所有 ``.py`` 文件。

    :returns: 排序后的文件路径列表，已排除 ``__pycache__``。
    """

    root = _engine_root()
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def _imported_module_names(source: str) -> list[str]:
    """从源码 AST 中提取所有 ``import`` 与 ``from ... import`` 的模块名。

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


def test_engine_does_not_import_runtime_log() -> None:
    """``dayu.engine.*`` 不得 ``import dayu.runtime.log``。"""

    violations: list[tuple[str, str]] = []
    for file_path in _iter_python_files():
        for module in _imported_module_names(
            file_path.read_text(encoding="utf-8")
        ):
            if (
                module == _FORBIDDEN_LOG_MODULE
                or module.startswith(_FORBIDDEN_LOG_MODULE + ".")
            ):
                violations.append((str(file_path), module))
    assert not violations, (
        f"engine modules must not import {_FORBIDDEN_LOG_MODULE}: {violations}"
    )
