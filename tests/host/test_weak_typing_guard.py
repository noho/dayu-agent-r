"""Host P1 弱类型守卫测试。"""

from __future__ import annotations

import ast
from pathlib import Path

import dayu.host as host

_BARE_BUILTIN_GENERICS: frozenset[str] = frozenset(
    {"dict", "list", "tuple", "set", "frozenset"}
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


def _annotation_violations(node: ast.expr | None, *, location: str) -> list[str]:
    """检查注解弱类型违规。

    :param node: 注解节点。
    :param location: 错误位置描述。
    :returns: 违规列表。
    :raises Exception: 不主动抛出异常。
    """

    if node is None:
        return [f"{location}: missing annotation"]
    violations: list[str] = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name):
            if sub.id in {"Any", "object"}:
                violations.append(f"{location}: annotation uses {sub.id}")
        elif isinstance(sub, ast.Attribute):
            if (
                isinstance(sub.value, ast.Name)
                and sub.value.id == "typing"
                and sub.attr == "Any"
            ):
                violations.append(f"{location}: annotation uses typing.Any")
    violations.extend(_bare_builtin_generic_violations(node, location=location))
    return violations


def _bare_builtin_generic_violations(
    node: ast.expr, *, location: str
) -> list[str]:
    """检查裸 builtin 容器注解。

    :param node: 注解节点。
    :param location: 错误位置描述。
    :returns: 违规列表。
    :raises Exception: 不主动抛出异常。
    """

    violations: list[str] = []

    class _Scanner(ast.NodeVisitor):
        def __init__(self) -> None:
            self._inside_subscript_value: int = 0

        def visit_Subscript(self, node: ast.Subscript) -> None:  # noqa: N802
            self._inside_subscript_value += 1
            self.visit(node.value)
            self._inside_subscript_value -= 1
            self.visit(node.slice)

        def visit_Name(self, node: ast.Name) -> None:  # noqa: N802
            if (
                node.id in _BARE_BUILTIN_GENERICS
                and self._inside_subscript_value == 0
            ):
                violations.append(f"{location}: bare builtin generic {node.id}")

    _Scanner().visit(node)
    return violations


def _check_function_def(
    func: ast.FunctionDef | ast.AsyncFunctionDef, *, file: str
) -> list[str]:
    """检查函数签名注解。

    :param func: 函数 AST。
    :param file: 文件路径。
    :returns: 违规列表。
    :raises Exception: 不主动抛出异常。
    """

    violations: list[str] = []
    location_prefix = f"{file}:{func.name}"
    args = func.args
    pos_args = list(args.posonlyargs) + list(args.args)
    for index, arg in enumerate(pos_args):
        if index == 0 and arg.arg in {"self", "cls"}:
            continue
        violations.extend(
            _annotation_violations(
                arg.annotation, location=f"{location_prefix}({arg.arg})"
            )
        )
    for arg in args.kwonlyargs:
        violations.extend(
            _annotation_violations(
                arg.annotation, location=f"{location_prefix}({arg.arg})"
            )
        )
    if args.vararg is not None:
        violations.extend(
            _annotation_violations(
                args.vararg.annotation,
                location=f"{location_prefix}(*{args.vararg.arg})",
            )
        )
    if args.kwarg is not None:
        violations.extend(
            _annotation_violations(
                args.kwarg.annotation,
                location=f"{location_prefix}(**{args.kwarg.arg})",
            )
        )
    if func.returns is None and func.name not in {"__init__"}:
        violations.append(f"{location_prefix}: missing return annotation")
    elif func.returns is not None:
        violations.extend(
            _annotation_violations(
                func.returns, location=f"{location_prefix}->return"
            )
        )
    return violations


def _check_class_field_annotations(cls: ast.ClassDef, *, file: str) -> list[str]:
    """检查类字段注解。

    :param cls: 类 AST。
    :param file: 文件路径。
    :returns: 违规列表。
    :raises Exception: 不主动抛出异常。
    """

    violations: list[str] = []
    for body_node in cls.body:
        if isinstance(body_node, ast.AnnAssign) and isinstance(
            body_node.target, ast.Name
        ):
            location = f"{file}:{cls.name}.{body_node.target.id}"
            violations.extend(
                _annotation_violations(body_node.annotation, location=location)
            )
    return violations


def test_host_disallows_weak_typing() -> None:
    """Host 源码不得出现弱类型签名。"""

    violations: list[str] = []
    for file_path in _iter_host_files():
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        rel = str(file_path)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                violations.extend(_check_function_def(node, file=rel))
            elif isinstance(node, ast.ClassDef):
                violations.extend(_check_class_field_annotations(node, file=rel))
    assert not violations, "weak typing violations:\n" + "\n".join(violations)
