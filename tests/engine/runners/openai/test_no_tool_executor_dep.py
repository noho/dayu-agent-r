"""Runner 不依赖 ToolExecutor / Trace / Host / Service / UI / fins 的 AST 扫描测试。"""

from __future__ import annotations

import ast
from pathlib import Path

import dayu.engine.runners as runners_pkg

FORBIDDEN_PREFIXES: tuple[str, ...] = (
    "dayu.host",
    "dayu.service",
    "dayu.ui",
    "dayu.fins",
    "dayu.engine.tools",
    "dayu.engine.processors",
)

FORBIDDEN_SUBSTRINGS: tuple[str, ...] = ("tool_trace",)

FORBIDDEN_NAMES: tuple[str, ...] = (
    "ToolExecutor",
    "ToolRegistry",
    "ToolRuntime",
    "ToolTraceRecorder",
    "JsonlToolTraceStore",
)


def _runners_root() -> Path:
    """返回 ``dayu/engine/runners/`` 的源码根。"""

    pkg_file = runners_pkg.__file__
    assert pkg_file is not None
    return Path(pkg_file).resolve().parent


def _iter_python_files() -> list[Path]:
    """递归收集 runners 子树下所有 ``.py`` 文件。"""

    root = _runners_root()
    return sorted(
        p for p in root.rglob("*.py") if "__pycache__" not in p.parts
    )


def _violations_in_file(path: Path) -> list[str]:
    """收集单文件 import 违规。"""

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for prefix in FORBIDDEN_PREFIXES:
                if module == prefix or module.startswith(prefix + "."):
                    violations.append(
                        f"{path}:{node.lineno} import from {module!r}"
                    )
            for substr in FORBIDDEN_SUBSTRINGS:
                if substr in module:
                    violations.append(
                        f"{path}:{node.lineno} import from {module!r}"
                    )
            for alias in node.names:
                if alias.name in FORBIDDEN_NAMES:
                    violations.append(
                        f"{path}:{node.lineno} import name {alias.name!r}"
                    )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                module = alias.name
                for prefix in FORBIDDEN_PREFIXES:
                    if module == prefix or module.startswith(prefix + "."):
                        violations.append(
                            f"{path}:{node.lineno} import {module!r}"
                        )
                for substr in FORBIDDEN_SUBSTRINGS:
                    if substr in module:
                        violations.append(
                            f"{path}:{node.lineno} import {module!r}"
                        )
    return violations


def test_no_forbidden_imports_under_runners() -> None:
    """``dayu/engine/runners/`` 下不得 import Tool* / Host / Service / UI / fins / trace 等模块。"""

    all_violations: list[str] = []
    for path in _iter_python_files():
        all_violations.extend(_violations_in_file(path))
    assert not all_violations, "forbidden imports found:\n" + "\n".join(
        all_violations
    )
