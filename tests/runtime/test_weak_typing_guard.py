"""``dayu.runtime`` 弱类型守卫测试。"""

from __future__ import annotations

import ast
from pathlib import Path

import dayu.runtime as runtime

_BARE_BUILTIN_GENERICS: frozenset[str] = frozenset(
    {"dict", "list", "tuple", "set", "frozenset"}
)
_PHASE12_RUNTIME_HELPERS: frozenset[str] = frozenset(
    {
        "assembly.py",
        "config_loader.py",
        "diagnostic_text.py",
        "location.py",
        "scene_prepare.py",
        "tool_truncation.py",
        "tools_discovery.py",
    }
)


def _runtime_root() -> Path:
    """返回 ``dayu/runtime/`` 源码根目录。

    :returns: runtime 包源码目录。
    """

    package_file = runtime.__file__
    assert package_file is not None
    return Path(package_file).resolve().parent


def _iter_runtime_files() -> list[Path]:
    """收集 runtime 包所有 Python 源码文件。

    :returns: 排序后的源码文件路径列表。
    """

    root = _runtime_root()
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def _annotation_violations(node: ast.expr | None, *, location: str) -> list[str]:
    """检查单个注解节点是否存在弱类型违规。

    :param node: 注解 AST 节点；为 ``None`` 表示缺失注解。
    :param location: 错误消息位置。
    :returns: 违规说明列表。
    """

    if node is None:
        return [f"{location}: missing annotation"]
    violations: list[str] = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name) and sub.id in {"Any", "object"}:
            violations.append(f"{location}: annotation uses {sub.id}")
        elif (
            isinstance(sub, ast.Attribute)
            and isinstance(sub.value, ast.Name)
            and sub.value.id == "typing"
            and sub.attr == "Any"
        ):
            violations.append(f"{location}: annotation uses typing.Any")
    violations.extend(_bare_builtin_generic_violations(node, location=location))
    return violations


def _bare_builtin_generic_violations(
    node: ast.expr, *, location: str
) -> list[str]:
    """检查注解中是否包含未参数化的 builtin 容器。

    :param node: 注解 AST 节点。
    :param location: 错误消息位置。
    :returns: 违规说明列表。
    """

    violations: list[str] = []

    class _Scanner(ast.NodeVisitor):
        """裸容器注解扫描器。"""

        def __init__(self) -> None:
            """初始化扫描状态。

            :returns: ``None``。
            """

            self._inside_subscript_value: int = 0

        def visit_Subscript(self, node: ast.Subscript) -> None:  # noqa: N802
            """扫描参数化注解节点。

            :param node: subscript AST 节点。
            :returns: ``None``。
            """

            self._inside_subscript_value += 1
            self.visit(node.value)
            self._inside_subscript_value -= 1
            self.visit(node.slice)

        def visit_Name(self, node: ast.Name) -> None:  # noqa: N802
            """扫描名称节点。

            :param node: name AST 节点。
            :returns: ``None``。
            """

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
        if func.name != "__init__":
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
    :param file: 文件路径，用于错误消息。
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


def test_runtime_disallows_weak_typing() -> None:
    """``dayu.runtime`` 不得出现弱类型签名。"""

    violations: list[str] = []
    for file_path in _iter_runtime_files():
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        rel = str(file_path)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                violations.extend(_check_function_def(node, file=rel))
            elif isinstance(node, ast.ClassDef):
                violations.extend(_check_class_field_annotations(node, file=rel))
    assert not violations, "weak typing violations:\n" + "\n".join(violations)


def test_runtime_weak_typing_scan_covers_phase12_helpers() -> None:
    """弱类型守卫必须覆盖 Phase 12 runtime public/helper 模块。"""

    scanned_names = {file_path.name for file_path in _iter_runtime_files()}
    missing = sorted(_PHASE12_RUNTIME_HELPERS - scanned_names)
    assert not missing, f"runtime weak typing scan missed files: {missing}"
