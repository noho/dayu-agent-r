"""``dayu.documents`` 包 import 边界测试。

共享文档基础包不得反向依赖 Host / Engine / Service / UI / Fins，也不得
导入具体工具实现。它只提供文档处理与 Docling runtime 基础能力。
"""

from __future__ import annotations

import ast
from pathlib import Path

import dayu.documents as documents

DOCUMENTS_FORBIDDEN_PREFIXES: tuple[str, ...] = (
    "dayu.engine",
    "dayu.host",
    "dayu.service",
    "dayu.ui",
    "dayu.fins",
    "dayu.tools",
)


def _documents_root() -> Path:
    """返回 ``dayu/documents/`` 的源码根目录路径。

    :returns: ``dayu/documents/`` 的绝对路径。
    """

    package_file = documents.__file__
    assert package_file is not None
    return Path(package_file).resolve().parent


def _iter_python_files() -> list[Path]:
    """递归收集 ``dayu/documents/`` 下所有 ``.py`` 文件。

    :returns: 排序后的文件路径列表，已排除 ``__pycache__``。
    """

    root = _documents_root()
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


def _matches_prefix(module: str, prefixes: tuple[str, ...]) -> bool:
    """判断模块名是否命中任一禁止前缀。

    :param module: 模块名。
    :param prefixes: 禁止前缀元组。
    :returns: 命中返回 ``True``，否则返回 ``False``。
    """

    return any(module == p or module.startswith(p + ".") for p in prefixes)


def test_documents_do_not_import_forbidden_layers() -> None:
    """``dayu.documents`` 不得依赖 Host / Engine / Service / UI / Fins / tools。"""

    violations: list[tuple[str, str]] = []
    for file_path in _iter_python_files():
        for module in _imported_module_names(file_path.read_text(encoding="utf-8")):
            if _matches_prefix(module, DOCUMENTS_FORBIDDEN_PREFIXES):
                violations.append((str(file_path), module))
    assert not violations, f"forbidden imports in dayu.documents: {violations}"


def test_documents_import_boundary_scan_covers_docling_runtime() -> None:
    """documents import 边界扫描必须覆盖 Docling runtime 真源。"""

    scanned_names = {file_path.name for file_path in _iter_python_files()}
    assert "docling_runtime.py" in scanned_names


def test_documents_import_boundary_scan_covers_processors() -> None:
    """验证 documents import 边界扫描覆盖当前 processors 子包文件。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 当前 processor 文件遗漏或已删除文件仍存在时抛出。
    """

    scanned_relpaths = {
        file_path.relative_to(_documents_root()).as_posix()
        for file_path in _iter_python_files()
    }
    assert "processors/markdown_processor.py" in scanned_relpaths
    assert "processors/bs_processor.py" in scanned_relpaths
    assert "processors/docling_processor.py" in scanned_relpaths
    assert "processors/source_snapshot.py" in scanned_relpaths
    removed_snapshot_path = "processors/" + "bounded" + "_source.py"
    assert removed_snapshot_path not in scanned_relpaths
