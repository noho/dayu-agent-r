"""``dayu.runtime`` 包 import 边界测试。

确保 ``dayu.runtime.*`` 不反向依赖任何业务层（engine/host/service/ui/fins），
也不引入 Phase 0 禁止的运行期 HTTP 库。
"""

from __future__ import annotations

import ast
from pathlib import Path

import dayu.runtime as runtime

PHASE0_FORBIDDEN_PREFIXES: tuple[str, ...] = ("aiohttp", "requests", "httpx")

RUNTIME_PERMANENT_FORBIDDEN_PREFIXES: tuple[str, ...] = (
    "dayu.engine",
    "dayu.host",
    "dayu.service",
    "dayu.ui",
    "dayu.fins",
)


def _runtime_root() -> Path:
    """返回 ``dayu/runtime/`` 的源码根目录路径。

    :returns: ``dayu/runtime/`` 的绝对路径。
    """

    package_file = runtime.__file__
    assert package_file is not None
    return Path(package_file).resolve().parent


def _iter_python_files() -> list[Path]:
    """递归收集 ``dayu/runtime/`` 下所有 ``.py`` 文件。

    :returns: 排序后的文件路径列表，已排除 ``__pycache__``。
    """

    root = _runtime_root()
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


def test_runtime_does_not_import_business_layers() -> None:
    """``dayu.runtime.*`` 永久禁止反向依赖任何业务层。"""

    violations: list[tuple[str, str]] = []
    for file_path in _iter_python_files():
        for module in _imported_module_names(
            file_path.read_text(encoding="utf-8")
        ):
            if _matches_prefix(module, RUNTIME_PERMANENT_FORBIDDEN_PREFIXES):
                violations.append((str(file_path), module))
    assert not violations, f"reverse-dependency imports: {violations}"


def test_runtime_import_boundary_scan_covers_lane_module() -> None:
    """runtime import 边界扫描必须覆盖新增 ``lane.py``。"""

    scanned_names = {file_path.name for file_path in _iter_python_files()}
    assert "lane.py" in scanned_names


def test_runtime_import_boundary_scan_covers_filelock_module() -> None:
    """runtime import 边界扫描必须覆盖新增 ``filelock.py``。"""

    scanned_names = {file_path.name for file_path in _iter_python_files()}
    assert "filelock.py" in scanned_names


def test_runtime_import_boundary_scan_covers_config_loader_module() -> None:
    """runtime import 边界扫描必须覆盖 ``config_loader.py``。"""

    scanned_names = {file_path.name for file_path in _iter_python_files()}
    assert "config_loader.py" in scanned_names


def test_runtime_import_boundary_scan_covers_numeric_module() -> None:
    """runtime import 边界扫描必须覆盖有限数值真源 ``numeric.py``。

    :returns: ``None``。
    :raises AssertionError: 新增 runtime module 未进入扫描时抛出。
    """

    scanned_names = {file_path.name for file_path in _iter_python_files()}
    assert "numeric.py" in scanned_names


def test_runtime_import_boundary_scan_covers_location_module() -> None:
    """runtime import 边界扫描必须覆盖 ``location.py``。"""

    scanned_names = {file_path.name for file_path in _iter_python_files()}
    assert "location.py" in scanned_names


def test_runtime_import_boundary_scan_covers_workspace_paths_module() -> None:
    """runtime import 边界扫描必须覆盖 ``workspace_paths.py``。"""

    scanned_names = {file_path.name for file_path in _iter_python_files()}
    assert "workspace_paths.py" in scanned_names


def test_runtime_import_boundary_scan_covers_scene_prepare_module() -> None:
    """runtime import 边界扫描必须覆盖 ``scene_prepare.py``。"""

    scanned_names = {file_path.name for file_path in _iter_python_files()}
    assert "scene_prepare.py" in scanned_names


def test_runtime_import_boundary_scan_covers_tools_discovery_module() -> None:
    """runtime import 边界扫描必须覆盖 ``tools_discovery.py``。"""

    scanned_names = {file_path.name for file_path in _iter_python_files()}
    assert "tools_discovery.py" in scanned_names


def test_runtime_import_boundary_scan_covers_assembly_module() -> None:
    """runtime import 边界扫描必须覆盖 ``assembly.py``。"""

    scanned_names = {file_path.name for file_path in _iter_python_files()}
    assert "assembly.py" in scanned_names


def test_runtime_import_boundary_scan_covers_tool_truncation_module() -> None:
    """runtime import 边界扫描必须覆盖 ``tool_truncation.py``。"""

    scanned_names = {file_path.name for file_path in _iter_python_files()}
    assert "tool_truncation.py" in scanned_names


def test_runtime_does_not_import_phase0_forbidden_modules() -> None:
    """Phase 0 暂时禁止的运行期模块不得被 ``dayu.runtime`` 导入。"""

    violations: list[tuple[str, str]] = []
    for file_path in _iter_python_files():
        for module in _imported_module_names(
            file_path.read_text(encoding="utf-8")
        ):
            if _matches_prefix(module, PHASE0_FORBIDDEN_PREFIXES):
                violations.append((str(file_path), module))
    assert not violations, f"Phase 0 forbidden imports: {violations}"


def test_third_party_filelock_import_is_confined_to_runtime_filelock() -> None:
    """第三方 ``filelock`` 只能由 ``dayu.runtime.filelock`` 直接导入。"""

    dayu_root = _runtime_root().parent
    allowed_file = _runtime_root() / "filelock.py"
    violations: list[tuple[str, str]] = []
    for file_path in sorted(dayu_root.rglob("*.py")):
        if "__pycache__" in file_path.parts or file_path == allowed_file:
            continue
        for module in _imported_module_names(file_path.read_text(encoding="utf-8")):
            if _matches_prefix(module, ("filelock",)):
                violations.append((str(file_path), module))

    assert not violations, f"third-party filelock imports outside wrapper: {violations}"
