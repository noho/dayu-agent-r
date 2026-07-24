"""CLI import boundary 自动化测试。"""

from __future__ import annotations

import ast
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SESSION_COMMAND_PATH = _REPO_ROOT / "dayu" / "cli" / "commands" / "session.py"
_TOOL_TRACE_COMMAND_PATH = (
    _REPO_ROOT / "dayu" / "cli" / "commands" / "tool_trace.py"
)
_COMMAND_MODULES_WITH_PRIVATE_OWNERS = frozenset(
    {
        "dayu.cli.commands.prompt",
        "dayu.cli.commands.interactive",
    }
)


def test_session_command_does_not_import_prompt_interactive_private_symbols() -> None:
    """session command 不得从 prompt / interactive command 导入下划线私有符号。

    :returns: ``None``。
    :raises AssertionError: import boundary 被破坏时抛出。
    """

    module = ast.parse(_SESSION_COMMAND_PATH.read_text(encoding="utf-8"))
    private_imports: list[str] = []
    for node in ast.walk(module):
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.module not in _COMMAND_MODULES_WITH_PRIVATE_OWNERS:
            continue
        for alias in node.names:
            if alias.name.startswith("_"):
                private_imports.append(f"{node.module}.{alias.name}")

    assert private_imports == []


def test_tool_trace_command_only_depends_on_service_public_boundary() -> None:
    """tool_trace command 不得导入 Host、Engine、Fins 或 durable internals。

    :returns: ``None``。
    :raises AssertionError: CLI 越过 Service/public contract 时抛出。
    """

    module = ast.parse(_TOOL_TRACE_COMMAND_PATH.read_text(encoding="utf-8"))
    forbidden_imports: list[str] = []
    for node in ast.walk(module):
        if isinstance(node, ast.Import):
            imported_modules = tuple(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported_modules = (() if node.module is None else (node.module,))
        else:
            continue
        for module_name in imported_modules:
            if module_name.startswith(
                (
                    "dayu.host",
                    "dayu.engine",
                    "dayu.fins",
                    "dayu.runtime",
                )
            ):
                forbidden_imports.append(module_name)

    assert forbidden_imports == []
