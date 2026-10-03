"""普通 CLI workspace 路径 owner 的契约与直接调用边界测试。"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from dayu.cli.workspace_root import resolve_workspace_root

_EMPTY_MESSAGE = "--base must not be empty"
_NON_DIRECTORY_MESSAGE = "--base must point to a directory; choose a directory path"
_PACKAGE_ROOT = Path(__file__).resolve().parents[2] / "dayu" / "cli"


@pytest.mark.parametrize("value", ("", " \t\n "))
def test_workspace_root_rejects_empty_text(value: str) -> None:
    """空文本和纯空白均由路径 owner 生成相同用法错误。

    Args:
        value: 待解析的空白参数。

    Returns:
        无。

    Raises:
        AssertionError: 错误消息或异常类型偏离契约时抛出。
    """

    with pytest.raises(ValueError, match=f"^{_EMPTY_MESSAGE}$"):
        resolve_workspace_root(value, error_factory=ValueError)


def test_workspace_root_rejects_existing_file_and_file_symlink(tmp_path: Path) -> None:
    """普通文件及指向文件的 symlink 都按最终目标类型拒绝。

    Args:
        tmp_path: 隔离路径根目录。

    Returns:
        无。

    Raises:
        AssertionError: 错误语义或文件内容发生漂移时抛出。
    """

    target = tmp_path / "base"
    target.write_bytes(b"original")
    link = tmp_path / "link"
    link.symlink_to(target)
    for value in (target, link):
        with pytest.raises(ValueError, match=f"^{_NON_DIRECTORY_MESSAGE}$") as error:
            resolve_workspace_root(str(value), error_factory=ValueError)
        assert str(tmp_path) not in str(error.value)
    assert target.read_bytes() == b"original"


def test_workspace_root_preserves_directory_and_unresolved_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """保留目录 symlink、缺失路径、相对路径和空白裁剪语义。

    Args:
        tmp_path: 隔离路径根目录。
        monkeypatch: 切换 cwd 的测试夹具。

    Returns:
        无。

    Raises:
        AssertionError: 返回的规范化路径不符合契约时抛出。
    """

    target = tmp_path / "有 空格 workspace"
    target.mkdir()
    directory_link = tmp_path / "directory-link"
    directory_link.symlink_to(target, target_is_directory=True)
    missing_target = tmp_path / "missing-target"
    dangling_link = tmp_path / "dangling-link"
    dangling_link.symlink_to(missing_target)
    monkeypatch.chdir(tmp_path)
    assert resolve_workspace_root(str(target), error_factory=ValueError) == target
    assert resolve_workspace_root(str(directory_link), error_factory=ValueError) == target
    assert resolve_workspace_root(f"  {target}  ", error_factory=ValueError) == target
    assert resolve_workspace_root(target.name, error_factory=ValueError) == target
    assert resolve_workspace_root("future", error_factory=ValueError) == tmp_path / "future"
    assert resolve_workspace_root(str(dangling_link), error_factory=ValueError) == missing_target


def test_workspace_root_is_the_only_ordinary_cli_resolver() -> None:
    """AST 固定轻量 owner 与三个直接调用者的 import 边界。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: owner 反向依赖或调用者复建解析规则时抛出。
    """

    owner_tree = ast.parse((_PACKAGE_ROOT / "workspace_root.py").read_text(encoding="utf-8"))
    owner_imports = {
        node.module
        for node in ast.walk(owner_tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    owner_imports.update(
        alias.name
        for node in ast.walk(owner_tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    )
    assert owner_imports <= {"__future__", "stat", "collections.abc", "pathlib", "typing"}

    old_tree = ast.parse((_PACKAGE_ROOT / "agent_entrypoint.py").read_text(encoding="utf-8"))
    assert not any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "resolve_workspace_root"
        for node in ast.walk(old_tree)
    )
    assert not any(
        isinstance(node, ast.ImportFrom) and node.module == "dayu.cli.workspace_root"
        for node in ast.walk(old_tree)
    )

    for relative in ("commands/fins.py", "session_execution.py", "commands/session.py"):
        tree = ast.parse((_PACKAGE_ROOT / relative).read_text(encoding="utf-8"))
        assert any(
            isinstance(node, ast.ImportFrom)
            and node.module == "dayu.cli.workspace_root"
            and any(alias.name == "resolve_workspace_root" for alias in node.names)
            for node in ast.walk(tree)
        )
    fins_tree = ast.parse((_PACKAGE_ROOT / "commands/fins.py").read_text(encoding="utf-8"))
    resolver_calls = [
        node
        for node in ast.walk(fins_tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "resolve_workspace_root"
    ]
    assert len(resolver_calls) == 2
    assert all(
        any(keyword.arg == "error_factory" for keyword in call.keywords)
        for call in resolver_calls
    )
