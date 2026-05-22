"""``dayu.service`` 包 import 边界测试。"""

from __future__ import annotations

import ast
from pathlib import Path

import dayu.service as service

SERVICE_FORBIDDEN_PREFIXES: tuple[str, ...] = (
    "dayu.ui",
    "dayu.fins",
)


def _service_root() -> Path:
    """返回 ``dayu/service/`` 源码根目录。

    :returns: service 包源码目录。
    """

    package_file = service.__file__
    assert package_file is not None
    return Path(package_file).resolve().parent


def _iter_python_files() -> list[Path]:
    """收集 service 包 Python 文件。

    :returns: 排序后的源码文件列表。
    """

    return sorted(
        path for path in _service_root().rglob("*.py") if "__pycache__" not in path.parts
    )


def _imported_module_names(source: str) -> list[str]:
    """从源码中提取 import 模块名。

    :param source: Python 源码。
    :returns: import 模块名列表。
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
    """判断模块名是否命中任一前缀。

    :param module: 模块名。
    :param prefixes: 前缀集合。
    :returns: 命中返回 ``True``。
    """

    return any(module == prefix or module.startswith(prefix + ".") for prefix in prefixes)


def test_service_does_not_import_ui_or_fins_layers() -> None:
    """Service 层不得反向依赖 UI，也不得直接绕过 Host 调用 Fins。"""

    violations: list[tuple[str, str]] = []
    for file_path in _iter_python_files():
        source = file_path.read_text(encoding="utf-8")
        for module in _imported_module_names(source):
            if _matches_prefix(module, SERVICE_FORBIDDEN_PREFIXES):
                violations.append((str(file_path), module))

    assert not violations, f"service import boundary violations: {violations}"

