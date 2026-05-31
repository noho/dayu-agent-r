"""``dayu.host`` 弱类型守卫测试。

通过 AST 扫描 ``dayu/host/`` 下所有源码文件，禁止：

- ``Any`` / ``object`` 出现在注解中。
- 函数 / 方法参数无注解（除 ``self`` / ``cls``）。
- 函数 / 方法返回值无注解（``__init__`` 例外）。
- 注解中出现裸 ``dict`` / ``list`` / ``tuple`` / ``set`` / ``frozenset``。
"""

from __future__ import annotations

import ast
from pathlib import Path

import dayu.host as host


def _host_root() -> Path:
    """返回 ``dayu/host/`` 源码根目录。

    :returns: ``dayu/host/`` 的绝对路径。
    :raises AssertionError: Host 包缺少 ``__file__`` 时抛出。
    """

    package_file = host.__file__
    assert package_file is not None
    return Path(package_file).resolve().parent


def _iter_files() -> list[Path]:
    """收集 Host 包所有 ``.py`` 源码文件。

    :returns: 排序后的文件路径列表。
    """

    root = _host_root()
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


_BARE_BUILTIN_GENERICS: frozenset[str] = frozenset(
    {"dict", "list", "tuple", "set", "frozenset"}
)
EXPLICIT_WEAK_TYPING_SCAN_FILES: frozenset[str] = frozenset({"durable/purge.py"})


def _annotation_violations(node: ast.expr | None, *, location: str) -> list[str]:
    """检查单个注解节点是否违规。

    :param node: 注解 AST 节点；为 ``None`` 表示缺注解。
    :param location: 用于错误消息的位置描述。
    :returns: 违规说明列表。
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
    """检查注解中是否包含未参数化的裸 builtin 容器。

    :param node: 注解 AST 节点。
    :param location: 错误消息位置描述。
    :returns: 违规说明列表。
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
    """检查函数 / 方法签名注解完整性与弱类型违规。

    :param func: 函数或方法 AST 节点。
    :param file: 文件路径，用于错误消息。
    :returns: 违规说明列表。
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
    if func.returns is None:
        if func.name not in {"__init__"}:
            violations.append(f"{location_prefix}: missing return annotation")
    else:
        violations.extend(
            _annotation_violations(
                func.returns, location=f"{location_prefix}->return"
            )
        )
    return violations


def _check_class_field_annotations(cls: ast.ClassDef, *, file: str) -> list[str]:
    """检查 dataclass 字段 / 类变量注解完整性与弱类型违规。

    :param cls: 类定义 AST 节点。
    :param file: 文件路径。
    :returns: 违规说明列表。
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
    """``dayu.host`` 不得出现 ``Any`` / ``object`` / 未注解 / 裸容器。"""

    violations: list[str] = []
    for file_path in _iter_files():
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        rel = str(file_path)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                violations.extend(_check_function_def(node, file=rel))
            elif isinstance(node, ast.ClassDef):
                violations.extend(_check_class_field_annotations(node, file=rel))
    assert not violations, "weak typing violations:\n" + "\n".join(violations)


def test_explicit_host_modules_are_covered_by_weak_typing_scan() -> None:
    """新增高风险 Host 模块必须被弱类型全包扫描覆盖。"""

    root = _host_root()
    scanned_files = frozenset(
        file_path.relative_to(root).as_posix() for file_path in _iter_files()
    )
    assert EXPLICIT_WEAK_TYPING_SCAN_FILES <= scanned_files
