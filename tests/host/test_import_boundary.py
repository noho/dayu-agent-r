"""Host P1 import 边界测试。"""

from __future__ import annotations

import ast
from pathlib import Path

import dayu.host as host

HOST_FORBIDDEN_PREFIXES: tuple[str, ...] = (
    "dayu.fins",
    "dayu.service",
    "dayu.ui",
)


def _host_root() -> Path:
    """返回 ``dayu/host/`` 源码根目录。

    :returns: Host 包根目录。
    :raises AssertionError: 包文件缺失时抛出。
    """

    package_file = host.__file__
    assert package_file is not None
    return Path(package_file).resolve().parent


def _iter_host_files() -> list[Path]:
    """收集 Host 包源码文件。

    :returns: 排序后的 Python 文件列表。
    :raises Exception: 不主动抛出异常。
    """

    root = _host_root()
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def _imported_module_names(source: str) -> list[str]:
    """从源码中提取 import 模块名。

    :param source: Python 源码。
    :returns: 模块名列表。
    :raises SyntaxError: 源码无法解析时抛出。
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
    """判断模块是否命中禁止前缀。

    :param module: 模块名。
    :param prefixes: 禁止前缀。
    :returns: 命中返回 ``True``。
    :raises Exception: 不主动抛出异常。
    """

    return any(module == p or module.startswith(p + ".") for p in prefixes)


def test_host_does_not_import_upper_or_domain_layers() -> None:
    """Host 不得导入 fins / service / ui。"""

    violations: list[tuple[str, str]] = []
    for file_path in _iter_host_files():
        for module in _imported_module_names(
            file_path.read_text(encoding="utf-8")
        ):
            if _matches_prefix(module, HOST_FORBIDDEN_PREFIXES):
                violations.append((str(file_path), module))
    assert not violations, f"Host forbidden imports: {violations}"
